import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Alumno, Tutor, TrayectoriaVersion, Usuario


@override_settings(DEFAULT_FILE_STORAGE='custom_storages.PrivateFileSystemStorage')
class TrayectoriaVersionAdminTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)

        tutor = Tutor.objects.create_user(
            email='admin.tray.tutor@example.com', matricula='ADMTUT01',
            password='password123', coordinacion='COM',
        )
        self.alumno = Alumno.objects.create_user(
            email='admin.tray.alumno@example.com', matricula='ADMALU01',
            password='password123', carrera='COM', tutor_asignado=tutor,
        )
        self.version = TrayectoriaVersion.objects.create(
            alumno=self.alumno,
            archivo=SimpleUploadedFile('historial.pdf', b'%PDF-1.4 admin', content_type='application/pdf'),
            original_filename='trayectoria_ADMALU01_2026-10-04T10-00.pdf',
            size_bytes=14,
            sha256='a' * 64,
        )
        self.admin_user = Usuario.objects.create_superuser(
            email='admin.tray@example.com', matricula='ADMSUP01', password='password123',
        )
        self.client.force_login(self.admin_user)

    def test_lista_y_busca_versiones_por_matricula(self):
        url = reverse('admin:Usuarios_trayectoriaversion_changelist')

        respuesta = self.client.get(url, {'q': 'ADMALU01'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'trayectoria_ADMALU01_2026-10-04T10-00.pdf')
        self.assertEqual(self.client.get(url, {'q': 'NOEXISTE'}).context['cl'].result_count, 0)

    def test_filtra_por_estado_activa(self):
        url = reverse('admin:Usuarios_trayectoriaversion_changelist')

        self.assertEqual(self.client.get(url, {'is_active__exact': '1'}).context['cl'].result_count, 1)
        self.assertEqual(self.client.get(url, {'is_active__exact': '0'}).context['cl'].result_count, 0)

    def test_admin_es_de_solo_consulta(self):
        agregar = reverse('admin:Usuarios_trayectoriaversion_add')
        cambiar = reverse('admin:Usuarios_trayectoriaversion_change', args=[self.version.pk])
        eliminar = reverse('admin:Usuarios_trayectoriaversion_delete', args=[self.version.pk])

        self.assertEqual(self.client.get(agregar).status_code, 403)
        self.assertEqual(self.client.get(eliminar).status_code, 403)
        self.assertEqual(self.client.post(eliminar, {'post': 'yes'}).status_code, 403)
        self.assertTrue(TrayectoriaVersion.objects.filter(pk=self.version.pk).exists())
        # Sin permiso de cambio, Django muestra la ficha sólo para consulta.
        self.assertEqual(self.client.get(cambiar).status_code, 200)
        self.assertEqual(self.client.post(cambiar, {'original_filename': 'otro.pdf'}).status_code, 403)
