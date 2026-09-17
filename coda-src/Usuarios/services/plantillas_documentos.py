"""Validación de documentos y selección predeterminada por propósito."""
from io import BytesIO
import docx
from django.core.exceptions import ValidationError
from docx.opc.exceptions import PackageNotFoundError
from zipfile import BadZipFile
from lxml.etree import XMLSyntaxError


def validar_archivo(archivo, tipo):
    from Tutorias.services.cartas_asignacion import validar_plantilla
    if not str(archivo.name).lower().endswith('.docx'):
        raise ValidationError('Selecciona un archivo Word .docx.')
    try:
        archivo.open('rb')
        documento = docx.Document(BytesIO(archivo.read()))
        validar_plantilla(documento, tipo)
    except (OSError, ValueError, KeyError, BadZipFile, PackageNotFoundError, XMLSyntaxError) as error:
        raise ValidationError('No se pudo abrir el archivo Word. Comprueba que sea un .docx válido.') from error
    finally:
        if not archivo.closed:
            archivo.seek(0)


def configurar_campo(form, campo, tipo):
    from Usuarios.models import Documento
    campo_form = form.fields[campo]
    campo_form.queryset = Documento.objects.filter(tipo=tipo).order_by('nombre')
    activa = campo_form.queryset.filter(activa=True).first()
    if activa:
        campo_form.initial = getattr(activa, campo_form.to_field_name or 'pk')
    else:
        campo_form.help_text = 'No hay plantilla predeterminada para este tipo. Configúrala en Ajustes o selecciona una para esta generación.'
