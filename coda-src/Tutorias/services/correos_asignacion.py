"""Vista previa y envío del lote exacto, con registro temporal por destinatario."""
from collections import OrderedDict
from contextlib import contextmanager
import fcntl
import json
import logging
import re
import smtplib
from threading import Thread
import time

from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.validators import validate_email

from .envios_asignacion import cargar_lote

logger = logging.getLogger(__name__)
MARCADORES = {
    'alumno': {'nombre_alumno', 'nombre_tutor', 'licenciatura', 'referencia_tutor', 'url_tutorias'},
    'tutor': {'nombre_tutor', 'saludo_tutor', 'tratamiento_tutor', 'url_tutorias'},
}


def validar_mensaje(texto, tipo, asunto=False):
    desconocidos = set(re.findall(r'\{([^{}]+)\}', texto)) - MARCADORES[tipo]
    if desconocidos:
        raise ValidationError('Marcadores no admitidos: ' + ', '.join(sorted(desconocidos)) + '.')
    if asunto and ('\r' in texto or '\n' in texto):
        raise ValidationError('El asunto debe ocupar una sola línea.')


def personalizar(texto, tipo, carta):
    validar_mensaje(texto, tipo)
    valores = {'nombre_alumno': carta['nombre'], 'nombre_tutor': carta['nombre_tutor'],
               'licenciatura': carta['licenciatura'],
               'url_tutorias': carta.get('url_tutorias', settings.TUTORIAS_SITE_URL)}
    if any('{' + marcador + '}' in texto for marcador in ('referencia_tutor', 'saludo_tutor', 'tratamiento_tutor')):
        sexo = carta.get('sexo_tutor')
        if sexo not in ('M', 'F'):
            raise ValidationError('Falta el sexo del tutor en el lote. Revisa sus datos y vuelve a preparar las cartas.')
        femenino = sexo == 'F'
        tratamiento = 'Dra.' if femenino else 'Dr.'
        valores.update(saludo_tutor='Estimada' if femenino else 'Estimado',
                       tratamiento_tutor=tratamiento,
                       referencia_tutor=('de la profesora ' if femenino else 'del profesor ') +
                                        tratamiento + ' ' + carta['nombre_tutor'])
    return re.sub(r'\{([^{}]+)\}', lambda marcador: valores[marcador.group(1)], texto)


def correos_del_lote(lote):
    _, cartas = cargar_lote(lote)
    grupos = OrderedDict()
    for indice, carta in enumerate(cartas):
        clave = f"{carta['tipo']}-{carta['destinatario_id']}"
        if clave not in grupos:
            tipo = carta['tipo']
            mensajes = lote['mensajes']
            asunto = personalizar(mensajes['asunto_' + tipo], tipo, carta)
            validar_mensaje(asunto, tipo, asunto=True)
            cuerpo = personalizar(mensajes['cuerpo_' + tipo], tipo, carta)
            try:
                validate_email(carta['correo'])
                valido = True
            except ValidationError:
                valido = False
            grupos[clave] = {'id': clave, 'tipo': tipo, 'nombre': carta['nombre'],
                             'correo': carta['correo'], 'asunto': asunto, 'cuerpo': cuerpo,
                             'valido': valido, 'adjuntos': []}
        grupos[clave]['adjuntos'].append({**carta, 'indice': indice})
    return list(grupos.values())


@contextmanager
def bloqueo(carpeta):
    with (carpeta / 'envio.lock').open('a') as archivo:
        try:
            fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValidationError('Este lote ya se está enviando. Espera a que termine.')
        try:
            yield
        finally:
            fcntl.flock(archivo, fcntl.LOCK_UN)


def guardar_estado(carpeta, estado):
    temporal = carpeta / 'envio.json.tmp'
    temporal.write_text(json.dumps(estado, ensure_ascii=False), encoding='utf-8')
    temporal.replace(carpeta / 'envio.json')


def leer_estado(carpeta):
    archivo = carpeta / 'envio.json'
    if not archivo.exists():
        return {'fase': 'sin_enviar', 'correos': {}}
    try:
        return json.loads(archivo.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValidationError('No se pudo leer el registro del envío. No vuelvas a enviar este lote hasta comprobar sus resultados.') from error


def estado_envio(lote):
    carpeta, _ = cargar_lote(lote)
    estado = leer_estado(carpeta)
    # Si el proceso murió, no repetir los correos cuyo resultado no conocemos.
    if estado['fase'] in ('en_cola', 'enviando') and time.time() - estado.get('actualizado', 0) > 15:
        try:
            with bloqueo(carpeta):
                estado = leer_estado(carpeta)
                if estado['fase'] in ('en_cola', 'enviando') and time.time() - estado.get('actualizado', 0) > 15:
                    for resultado in estado['correos'].values():
                        if resultado['estado'] == 'enviando':
                            resultado.update(estado='incierto', detalle='Envío interrumpido; comprueba si el correo llegó antes de volver a enviarlo.')
                    estado['fase'] = 'interrumpido'
                    guardar_estado(carpeta, estado)
        except ValidationError:
            pass
    return estado


def iniciar_envio(lote):
    carpeta, _ = cargar_lote(lote)
    correos = correos_del_lote(lote)
    estado_envio(lote)
    with bloqueo(carpeta):
        estado = leer_estado(carpeta)
        if estado['fase'] in ('en_cola', 'enviando'):
            raise ValidationError('Este lote ya se está enviando. Espera a que termine.')
        pendientes = []
        for correo in correos:
            previo = estado['correos'].get(correo['id'], {}).get('estado', 'pendiente')
            if correo['valido'] and previo in ('pendiente', 'fallido'):
                # Comprobar todos los adjuntos antes de iniciar el envío.
                for adjunto in correo['adjuntos']:
                    if not (carpeta / adjunto['archivo']).read_bytes().startswith(b'%PDF-'):
                        raise ValidationError('Una carta PDF no está disponible. Vuelve a preparar el lote.')
                pendientes.append(correo)
                estado['correos'][correo['id']] = {'estado': 'pendiente', 'detalle': ''}
        if not pendientes:
            raise ValidationError('No hay correos pendientes o fallidos que puedan enviarse.')
        estado.update(fase='en_cola', actualizado=time.time())
        guardar_estado(carpeta, estado)
    try:
        Thread(target=procesar_envio, args=(carpeta, pendientes), daemon=True).start()
    except Exception:
        with bloqueo(carpeta):
            estado['fase'] = 'interrumpido'
            guardar_estado(carpeta, estado)
        raise ValidationError('No se pudo iniciar el envío. Intenta nuevamente.')


def procesar_envio(carpeta, correos):
    """Un hilo por lote, igual que el envío de notificaciones existente."""
    try:
        with bloqueo(carpeta):
            estado = leer_estado(carpeta)
            estado['fase'] = 'enviando'
            for correo in correos:
                resultado = estado['correos'][correo['id']]
                # Los errores al leer el PDF ocurren antes de contactar al SMTP.
                try:
                    mensaje = EmailMessage(correo['asunto'], correo['cuerpo'], to=[correo['correo']])
                    for adjunto in correo['adjuntos']:
                        mensaje.attach(adjunto['ruta'].rsplit('/', 1)[-1],
                                       (carpeta / adjunto['archivo']).read_bytes(), 'application/pdf')
                except Exception:
                    logger.exception('No se pudieron preparar los adjuntos del correo de asignación')
                    resultado.update(estado='fallido', detalle='No se pudieron leer los adjuntos.')
                    guardar_estado(carpeta, estado)
                    continue
                resultado.update(estado='enviando', detalle='')
                estado['actualizado'] = time.time()
                guardar_estado(carpeta, estado)
                try:
                    if mensaje.send(fail_silently=False) != 1:
                        resultado.update(estado='fallido', detalle='El servidor de correo no aceptó el envío.')
                    else:
                        resultado.update(estado='enviado', detalle='Aceptado por el servidor de correo.')
                except (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError,
                        smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError):
                    logger.exception('El servidor rechazó el correo de asignación')
                    resultado.update(estado='fallido', detalle='El servidor de correo rechazó el envío. Puedes reintentarlo.')
                except Exception:
                    logger.exception('No se pudo confirmar el envío del correo de asignación')
                    resultado.update(estado='incierto', detalle='No se pudo confirmar el envío. Comprueba si llegó antes de volver a enviarlo.')
                estado['actualizado'] = time.time()
                guardar_estado(carpeta, estado)
            estado.update(fase='terminado', actualizado=time.time())
            guardar_estado(carpeta, estado)
    except Exception:
        logger.exception('Se interrumpió el procesamiento del lote de correos de asignación')
