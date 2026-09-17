from datetime import date
from importlib import import_module
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, RequestFactory
from django.urls import reverse

from .models import Documento, Coda, Tutor, Alumno
from Tutorias.services.lotes_asignacion import generar_lote
from Tutorias.forms import FormLoteAsignacion


class PlantillasSistemaTests(TestCase):
    def setUp(self):
        self.coda = Coda.objects.create_user(email='sistema@example.com', matricula='800', password='test')
        self.client.force_login(self.coda)
        self.ejemplo = Documento.objects.get(clave_sistema='alumno')

    def test_semilla_predeterminada_y_fuente(self):
        self.assertEqual(Documento.objects.exclude(clave_sistema=None).count(), 3)
        for documento in Documento.objects.exclude(clave_sistema=None):
            self.assertTrue(documento.activa)
            self.assertFalse(documento.archivo.name)
            self.assertTrue(documento.archivo_fuente.read().startswith(b'PK'))
        self.assertEqual(FormLoteAsignacion()['plantilla_alumno'].value(), self.ejemplo.pk)

    def test_modelo_impide_edicion_y_borrado(self):
        for campo, valor in [('nombre', 'Cambio'), ('tipo', 'tutor'), ('clave_sistema', None), ('archivo', 'otro.docx')]:
            ejemplo = Documento.objects.get(pk=self.ejemplo.pk)
            setattr(ejemplo, campo, valor)
            with self.assertRaises(ValidationError): ejemplo.save()
        with self.assertRaises(ValidationError): self.ejemplo.delete()
        with self.assertRaises(ValidationError): Documento.objects.filter(pk=self.ejemplo.pk).delete()
        with self.assertRaises(ValidationError): Documento.objects.filter(pk=self.ejemplo.pk).update(nombre='Cambio')
        self.ejemplo.activa = False
        self.ejemplo.save(update_fields=['activa'])

    def test_peticion_directa_no_edita_ni_borra(self):
        self.assertEqual(self.client.post(reverse('eliminar_documento', args=[self.ejemplo.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('ver_plantilla', args=[self.ejemplo.pk]), {'nombre': 'Cambio', 'tipo': 'tutor'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('ver_plantilla', args=[self.ejemplo.pk])).status_code, 403)

    def test_se_puede_volver_a_predeterminar(self):
        Documento.objects.filter(pk=self.ejemplo.pk).update(activa=False)
        alternativa = Documento.objects.create(nombre='Alternativa', tipo='alumno', archivo='alternativa.docx', activa=True)
        self.assertEqual(self.client.post(reverse('activar-plantilla', args=[self.ejemplo.pk])).status_code, 302)
        alternativa.refresh_from_db(); self.ejemplo.refresh_from_db()
        self.assertTrue(self.ejemplo.activa)
        self.assertFalse(alternativa.activa)

    def test_admin_protegido(self):
        configuracion = admin.site._registry[Documento]
        request = RequestFactory().get('/admin/')
        request.user = self.coda
        self.assertFalse(configuracion.has_delete_permission(request, self.ejemplo))
        self.assertEqual(set(configuracion.get_readonly_fields(request, self.ejemplo)), {'nombre', 'tipo', 'archivo'})
        from unittest.mock import patch
        with patch.object(configuracion, 'message_user'):
            configuracion.delete_queryset(request, Documento.objects.filter(pk=self.ejemplo.pk))
        self.assertTrue(Documento.objects.filter(pk=self.ejemplo.pk).exists())

    def test_migracion_respeta_eleccion_e_idempotencia(self):
        Documento.objects.filter(tipo='alumno').update(activa=False)
        alternativa = Documento.objects.create(nombre='Preferida', tipo='alumno', activa=True, archivo='personal.docx')
        migracion = import_module('Usuarios.migrations.0011_registrar_plantillas_sistema')
        # Historical models deliberately bypass runtime protection for schema maintenance.
        from django.db.migrations.executor import MigrationExecutor
        estado = MigrationExecutor(connection).loader.project_state(('Usuarios', '0010_documento_clave_sistema'))
        historico = estado.apps.get_model('Usuarios', 'Documento')
        historico.objects.filter(clave_sistema='alumno').delete()
        with connection.schema_editor(atomic=False) as editor:
            migracion.registrar(estado.apps, editor)
            migracion.registrar(estado.apps, editor)
        alternativa.refresh_from_db()
        self.assertTrue(alternativa.activa)
        self.assertFalse(Documento.objects.get(clave_sistema='alumno').activa)
        self.assertEqual(Documento.objects.exclude(clave_sistema=None).count(), 3)

    def test_genera_lote_con_ejemplos_sin_archivos_subidos(self):
        tutor = Tutor.objects.create_user(email='sist.tutor@example.com', matricula='801', first_name='Ana', last_name='Tutor', password='test', coordinacion='COM')
        alumno = Alumno.objects.create_user(email='sist.alumno@example.com', matricula='802', first_name='Luis', last_name='Alumno', password='test', carrera='COM', trimestre_ingreso='26-O', tutor_asignado=tutor)
        nombre, contenido = generar_lote([alumno], {'destinatarios': 'ambas', 'plantilla_alumno': self.ejemplo,
            'plantilla_tutor': Documento.objects.get(clave_sistema='tutor'), 'oficio_alumno': 1, 'oficio_tutor': 2, 'fecha': date(2026, 9, 15)})
        from zipfile import ZipFile
        from io import BytesIO
        with ZipFile(BytesIO(contenido)) as archivo:
            self.assertEqual(len(archivo.namelist()), 2)

    def test_interfaz_y_tipo_preseleccionado(self):
        response = self.client.get(reverse('ajustes'))
        self.assertContains(response, '[Solo lectura]')
        self.assertContains(response, 'plantilla_seleccionada')
        self.assertNotContains(response, 'Descargar plantilla de ejemplo')
        response = self.client.get(reverse('cargar_plantilla'), {'tipo': 'tutor'})
        self.assertEqual(response.context['form']['tipo'].value(), 'tutor')
