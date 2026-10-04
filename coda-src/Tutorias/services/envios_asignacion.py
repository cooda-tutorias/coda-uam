"""Lotes PDF temporales, fuera de MEDIA_ROOT y accesibles desde la sesión."""
import json
import fcntl
import logging
from pathlib import Path
import shutil
from tempfile import gettempdir
import time
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError

from .lotes_asignacion import generar_documentos

logger = logging.getLogger(__name__)


def raiz_lotes():
    return Path(getattr(settings, 'CARTAS_ENVIO_ROOT', Path(gettempdir()) / 'coddaa-envios'))


def borrar_lote_inactivo(carpeta):
    """No borrar los adjuntos mientras otro proceso los está enviando."""
    with (carpeta / 'envio.lock').open('a') as archivo:
        try:
            fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        estado = carpeta / 'envio.json'
        if estado.exists():
            datos = json.loads(estado.read_text(encoding='utf-8'))
            if datos.get('fase') == 'en_cola' and time.time() - datos.get('actualizado', 0) < 15:
                return False
        shutil.rmtree(carpeta)
        return True


def limpiar_lotes_caducados():
    raiz = raiz_lotes()
    if not raiz.exists():
        return 0
    eliminados = 0
    for carpeta in raiz.glob('lote-*'):
        try:
            marca = carpeta / 'cartas.json'
            fecha = marca.stat().st_mtime if marca.exists() else carpeta.stat().st_mtime
            if carpeta.is_dir() and not carpeta.is_symlink() and time.time() - fecha > 86400:
                eliminados += borrar_lote_inactivo(carpeta)
        except (OSError, ValueError):
            logger.exception('No se pudo limpiar un lote PDF caducado')
    return eliminados


def preparar_lote(alumnos, datos):
    """Publica el lote solo cuando todas las cartas se generaron correctamente."""
    carpeta = None
    try:
        limpiar_lotes_caducados()
        raiz_lotes().mkdir(parents=True, exist_ok=True, mode=0o700)
        token = uuid4().hex
        carpeta = raiz_lotes() / ('lote-' + token)
        carpeta.mkdir(mode=0o700)
        cartas = []
        for indice, carta in enumerate(generar_documentos(alumnos, {**datos, 'formato': 'pdf'})):
            contenido = carta.pop('contenido')
            carta['archivo'] = f'{indice}.pdf'
            (carpeta / carta['archivo']).write_bytes(contenido)
            cartas.append(carta)
        (carpeta / 'cartas.json').write_text(json.dumps(cartas, ensure_ascii=False), encoding='utf-8')
        return {'token': token, 'caduca': time.time() + 86400, 'total_cartas': len(cartas)}
    except Exception as error:
        if carpeta is not None and carpeta.exists():
            try:
                shutil.rmtree(carpeta)
            except OSError:
                logger.exception('No se pudo limpiar el lote incompleto')
        if isinstance(error, OSError):
            logger.exception('No se pudo guardar el lote de asignación')
            raise ValidationError('No se pudo guardar el lote PDF. Intenta nuevamente.') from error
        raise


def cargar_lote(lote):
    token = lote.get('token', '')
    if len(token) != 32 or any(c not in '0123456789abcdef' for c in token) or lote.get('caduca', 0) <= time.time():
        raise ValidationError('El lote preparado ha caducado. Vuelve a prepararlo.')
    carpeta = raiz_lotes() / ('lote-' + token)
    try:
        cartas = json.loads((carpeta / 'cartas.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValidationError('El lote preparado ya no está disponible. Vuelve a prepararlo.') from error
    return carpeta, cartas


def eliminar_lote(lote):
    try:
        carpeta, _ = cargar_lote(lote)
    except ValidationError:
        return
    try:
        borrar_lote_inactivo(carpeta)
    except (OSError, ValueError):
        logger.exception('No se pudo eliminar el lote anterior; se limpiará al caducar')
