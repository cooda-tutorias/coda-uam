"""Validación de fotos subidas: se identifica el formato por el contenido, nunca por la extensión."""
from django.core.exceptions import ValidationError
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

# Formatos que producen las cámaras de celular (iPhone usa HEIC; algunos Android, AVIF).
FORMATOS_PERMITIDOS = ('JPEG', 'PNG', 'WEBP', 'HEIF', 'AVIF')
MAX_PIXELES = 40_000_000
MENSAJE_FORMATOS = 'Selecciona una imagen JPG, PNG, WebP, HEIC o AVIF.'

Image.MAX_IMAGE_PIXELS = MAX_PIXELES


def abrir_imagen(archivo):
    # `formats` evita que Pillow pruebe otros decodificadores (TIFF, EPS, etc.).
    archivo.seek(0)
    return Image.open(archivo, formats=FORMATOS_PERMITIDOS)


def validar_imagen(archivo):
    try:
        with abrir_imagen(archivo) as imagen:
            if imagen.width * imagen.height > MAX_PIXELES:
                raise ValidationError('La imagen tiene demasiados píxeles.')
    except ValidationError:
        raise
    except Exception:
        raise ValidationError(MENSAJE_FORMATOS)
    finally:
        archivo.seek(0)
