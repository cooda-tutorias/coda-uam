from io import BytesIO

import pillow_heif
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from .imagenes import validar_imagen


def _imagen(formato):
    salida = BytesIO()
    imagen = Image.new('RGB', (32, 32), 'red')
    if formato == 'HEIF':
        pillow_heif.from_pillow(imagen).save(salida, format='HEIF')
    else:
        imagen.save(salida, format=formato)
    return salida.getvalue()


class ValidarImagenTests(SimpleTestCase):
    def test_acepta_formatos_de_celular_aunque_la_extension_mienta(self):
        for formato in ('JPEG', 'PNG', 'WEBP', 'HEIF'):
            with self.subTest(formato=formato):
                archivo = SimpleUploadedFile('foto.dat', _imagen(formato))
                validar_imagen(archivo)

    def test_rechaza_formatos_de_imagen_no_permitidos(self):
        for formato in ('GIF', 'TIFF', 'BMP'):
            with self.subTest(formato=formato):
                archivo = SimpleUploadedFile('foto.png', _imagen(formato), content_type='image/png')
                with self.assertRaises(ValidationError):
                    validar_imagen(archivo)

    def test_rechaza_contenido_que_no_es_imagen_aunque_diga_serlo(self):
        contenidos = (
            b'<?php system($_GET["c"]); ?>',
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            b'%PDF-1.4 contenido',
            b'MZ\x90\x00 ejecutable',
        )
        for contenido in contenidos:
            with self.subTest(contenido=contenido[:10]):
                archivo = SimpleUploadedFile('foto.jpg', contenido, content_type='image/jpeg')
                with self.assertRaises(ValidationError):
                    validar_imagen(archivo)

    def test_rechaza_imagen_truncada(self):
        archivo = SimpleUploadedFile('foto.png', _imagen('PNG')[:20], content_type='image/png')
        with self.assertRaises(ValidationError):
            validar_imagen(archivo)
