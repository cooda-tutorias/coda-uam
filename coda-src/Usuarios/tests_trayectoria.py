import hashlib
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from Usuarios.constants import ALUMNO, TUTOR
from Usuarios.models import Alumno, Tutor, TrayectoriaVersion


class TrayectoriaBackendTests(TestCase):
    pdf = b'%PDF-1.4\ncontenido de prueba\n%%EOF'

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.tutor = Tutor.objects.create_user(
            email='trayectoria.tutor@example.com',
            matricula='TUTTRAJ001',
            password='password123',
            rol=[TUTOR],
            coordinacion='COM',
        )
        self.otro_tutor = Tutor.objects.create_user(
            email='trayectoria.otro@example.com',
            matricula='TUTTRAJ002',
            password='password123',
            rol=[TUTOR],
            coordinacion='COM',
        )
        self.alumno = Alumno.objects.create_user(
            email='trayectoria.alumno@example.com',
            matricula='ALUTRAJ001',
            password='password123',
            rol=[ALUMNO],
            carrera='COM',
            tutor_asignado=self.tutor,
        )
        self.otro_alumno = Alumno.objects.create_user(
            email='trayectoria.otro-alumno@example.com',
            matricula='ALUTRAJ002',
            password='password123',
            rol=[ALUMNO],
            carrera='COM',
            tutor_asignado=self.otro_tutor,
        )
        self.url_subir = reverse('subir-trayectoria', kwargs={'pk': self.alumno.pk})
        self.url_ver = reverse('ver-trayectoria', kwargs={'pk': self.alumno.pk})

    def _archivo_pdf(self, nombre='historial.pdf', contenido=None):
        return SimpleUploadedFile(
            nombre,
            contenido if contenido is not None else self.pdf,
            content_type='application/pdf',
        )

    def _subir(self, nombre='historial.pdf', contenido=None):
        return self.client.post(
            self.url_subir,
            {'archivo': self._archivo_pdf(nombre, contenido)},
        )

    def test_alumno_puede_subir_pdf_y_se_guarda_hash_y_legacy(self):
        self.client.force_login(self.alumno)

        response = self._subir()

        self.assertRedirects(
            response,
            reverse('perfil-alumno', kwargs={'pk': self.alumno.pk}),
            fetch_redirect_response=False,
        )
        version = TrayectoriaVersion.objects.get(alumno=self.alumno)
        self.assertTrue(version.is_active)
        self.assertEqual(version.original_filename, 'historial.pdf')
        self.assertEqual(version.size_bytes, len(self.pdf))
        self.assertEqual(version.sha256, hashlib.sha256(self.pdf).hexdigest())
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.trayectoria.name, version.archivo.name)

    def test_solo_una_version_permanece_activa_al_subir_otra(self):
        self.client.force_login(self.alumno)
        self._subir('primera.pdf')
        primera = TrayectoriaVersion.objects.get(alumno=self.alumno)

        self._subir('segunda.pdf')

        primera.refresh_from_db()
        segunda = TrayectoriaVersion.objects.get(alumno=self.alumno, is_active=True)
        self.assertFalse(primera.is_active)
        self.assertEqual(segunda.original_filename, 'segunda.pdf')
        self.assertEqual(
            TrayectoriaVersion.objects.filter(alumno=self.alumno, is_active=True).count(),
            1,
        )

    def test_rechaza_archivo_con_extension_pdf_sin_firma_pdf(self):
        self.client.force_login(self.alumno)

        response = self._subir(contenido=b'no es un PDF')

        self.assertRedirects(
            response,
            reverse('perfil-alumno', kwargs={'pk': self.alumno.pk}),
            fetch_redirect_response=False,
        )
        self.assertFalse(TrayectoriaVersion.objects.filter(alumno=self.alumno).exists())

    def test_alumno_no_puede_subir_archivo_a_otro_perfil(self):
        self.client.force_login(self.otro_alumno)

        response = self._subir()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(TrayectoriaVersion.objects.filter(alumno=self.alumno).exists())

    def test_primera_carga_preserva_el_archivo_legado_en_el_historial(self):
        contenido_legado = b'%PDF-1.4\ntrayectoria anterior\n%%EOF'
        self.alumno.trayectoria.save(
            'legado.pdf',
            ContentFile(contenido_legado),
            save=True,
        )
        self.client.force_login(self.alumno)

        self._subir('actual.pdf')

        version_legada = TrayectoriaVersion.objects.get(
            alumno=self.alumno,
            original_filename='legado.pdf',
        )
        self.assertFalse(version_legada.is_active)
        self.assertEqual(
            version_legada.sha256,
            hashlib.sha256(contenido_legado).hexdigest(),
        )
        self.assertTrue(version_legada.archivo.storage.exists(version_legada.archivo.name))

    def test_solo_el_tutor_asignado_puede_consultar_el_pdf(self):
        self.client.force_login(self.alumno)
        self._subir()

        self.client.force_login(self.tutor)
        response = self.client.get(self.url_ver)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(b''.join(response.streaming_content), self.pdf)

        self.client.force_login(self.otro_tutor)
        response = self.client.get(self.url_ver)
        self.assertEqual(response.status_code, 403)

    def test_borrar_version_activa_restaura_la_anterior(self):
        self.client.force_login(self.alumno)
        self._subir('primera.pdf')
        primera = TrayectoriaVersion.objects.get(alumno=self.alumno)
        self._subir('segunda.pdf')
        segunda = TrayectoriaVersion.objects.get(alumno=self.alumno, is_active=True)

        response = self.client.post(reverse(
            'eliminar-version-trayectoria',
            kwargs={'pk': self.alumno.pk, 'version_id': segunda.pk},
        ))

        self.assertEqual(response.status_code, 302)
        primera.refresh_from_db()
        self.assertTrue(primera.is_active)
        self.assertFalse(TrayectoriaVersion.objects.filter(pk=segunda.pk).exists())
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.trayectoria.name, primera.archivo.name)
