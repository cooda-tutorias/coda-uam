from pathlib import Path
from unittest.mock import patch, Mock
import shutil
import subprocess

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from Usuarios.models import Documento, Coda, Tutor
from Usuarios.services.vista_previa_plantillas import obtener_pdf, convertir_pdf, ErrorVistaPrevia


class VistaPreviaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.coda = Coda.objects.create_user(email='preview@example.com', matricula='700', password='test')
        self.documento = Documento.objects.get(clave_sistema='alumno')
        self.url = reverse('vista-previa-plantilla', args=[self.documento.pk])
        self.client.force_login(self.coda)

    def test_pdf_privado_e_integrable(self):
        with patch('Usuarios.services.vista_previa_plantillas.convertir_pdf', return_value=b'%PDF-1.7 prueba') as convertir:
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
            self.assertIn('no-store', response['Cache-Control'])
            self.client.get(self.url)
            self.assertEqual(convertir.call_count, 1)

    def test_fallo_no_descarga_archivo(self):
        with patch('Usuarios.services.vista_previa_plantillas.convertir_pdf', side_effect=ErrorVistaPrevia('No disponible')):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['error'], 'No disponible')

    def test_permisos(self):
        tutor = Tutor.objects.create_user(email='preview.tutor@example.com', matricula='701', password='test', coordinacion='COM')
        self.client.force_login(tutor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_cache_cambia_con_archivo(self):
        documento = Mock()
        documento.archivo_fuente = ContentFile(b'primero', name='x.docx')
        with patch('Usuarios.services.vista_previa_plantillas.convertir_pdf', side_effect=[b'%PDF-primero', b'%PDF-segundo']) as convertir:
            self.assertEqual(obtener_pdf(documento), b'%PDF-primero')
            documento.archivo_fuente = ContentFile(b'segundo', name='x.docx')
            self.assertEqual(obtener_pdf(documento), b'%PDF-segundo')
            self.assertEqual(convertir.call_count, 2)

    def test_conversion_real_ejemplos(self):
        if not (shutil.which('libreoffice') or shutil.which('soffice')):
            self.skipTest('La imagen debe reconstruirse con LibreOffice para esta prueba.')
        for documento in Documento.objects.exclude(clave_sistema=None):
            original = documento.archivo_fuente.read()
            pdf = obtener_pdf(documento)
            self.assertTrue(pdf.startswith(b'%PDF-'))
            self.assertGreater(len(pdf), 1000)
            self.assertEqual(documento.archivo_fuente.read(), original)


class ConversionFallosTests(SimpleTestCase):
    def test_conversor_ausente(self):
        with patch('Usuarios.services.vista_previa_plantillas.shutil.which', return_value=None):
            with self.assertRaisesMessage(ErrorVistaPrevia, 'no está disponible'):
                convertir_pdf(b'archivo')

    def test_timeout_termina_proceso_y_limpia_temporales(self):
        proceso = Mock(pid=123)
        proceso.communicate.side_effect = [subprocess.TimeoutExpired('soffice', 45), (b'', b'')]
        with patch('Usuarios.services.vista_previa_plantillas.shutil.which', return_value='/usr/bin/soffice'), \
             patch('Usuarios.services.vista_previa_plantillas.subprocess.Popen', return_value=proceso) as iniciar, \
             patch('Usuarios.services.vista_previa_plantillas.os.killpg') as terminar:
            with self.assertRaisesMessage(ErrorVistaPrevia, 'tardó demasiado'):
                convertir_pdf(b'archivo')
            terminar.assert_called_once()
            entrada = Path(iniciar.call_args.args[0][-1])
            self.assertFalse(entrada.parent.exists())

    def test_salida_fallida(self):
        proceso = Mock(returncode=1)
        with patch('Usuarios.services.vista_previa_plantillas.shutil.which', return_value='/usr/bin/soffice'), \
             patch('Usuarios.services.vista_previa_plantillas.subprocess.Popen', return_value=proceso):
            with self.assertRaisesMessage(ErrorVistaPrevia, 'No se pudo convertir'):
                convertir_pdf(b'archivo')
