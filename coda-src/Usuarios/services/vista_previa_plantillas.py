"""Conversión local aislada por petición; no publica archivos ni modifica el Word."""
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
from tempfile import TemporaryDirectory

from django.core.cache import cache


class ErrorVistaPrevia(Exception):
    pass


def convertir_pdf(contenido):
    ejecutable = shutil.which('libreoffice') or shutil.which('soffice')
    if not ejecutable:
        raise ErrorVistaPrevia('La vista previa no está disponible en este servidor. Puedes descargar el Word.')
    with TemporaryDirectory(prefix='plantilla-pdf-') as carpeta:
        ruta = Path(carpeta)
        entrada = ruta / 'plantilla.docx'
        entrada.write_bytes(contenido)
        comando = [ejecutable, '-env:UserInstallation=' + (ruta / 'perfil').as_uri(),
                   '--headless', '--nologo', '--nodefault', '--norestore',
                   '--convert-to', 'pdf:writer_pdf_Export', '--outdir', str(ruta), str(entrada)]
        try:
            proceso = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                proceso.communicate(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(proceso.pid, signal.SIGKILL)
                proceso.communicate()
                raise ErrorVistaPrevia('La vista previa tardó demasiado. Inténtalo de nuevo o descarga el Word.')
            pdf = ruta / 'plantilla.pdf'
            if proceso.returncode != 0 or not pdf.exists():
                raise ErrorVistaPrevia('No se pudo convertir esta plantilla a PDF. Puedes descargar el Word.')
            resultado = pdf.read_bytes()
            if not resultado.startswith(b'%PDF-'):
                raise ErrorVistaPrevia('No se pudo generar una vista previa válida. Puedes descargar el Word.')
            return resultado
        except OSError as error:
            raise ErrorVistaPrevia('No se pudo preparar la vista previa. Puedes descargar el Word.') from error


def obtener_pdf(documento):
    try:
        archivo = documento.archivo_fuente
        archivo.open('rb')
        try:
            contenido = archivo.read()
        finally:
            archivo.close()
    except OSError as error:
        raise ErrorVistaPrevia('El archivo de la plantilla no está disponible.') from error
    clave = 'plantilla-pdf-v1-' + hashlib.sha256(contenido).hexdigest()
    pdf = cache.get(clave)
    if pdf is None:
        pdf = convertir_pdf(contenido)
        cache.set(clave, pdf, timeout=900)
    return pdf
