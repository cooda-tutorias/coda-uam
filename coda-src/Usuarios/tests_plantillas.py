from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import TestCase, override_settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.db import IntegrityError, transaction

from Usuarios.models import Documento, Coda, Tutor
from Usuarios.forms import DocumentoForm
from Tutorias.forms import FormLoteAsignacion, FormReporteDeTutorias, FormReporteTutoriasMasivo


class PlantillasDocumentoTests(TestCase):
    def setUp(self):
        Documento.objects.update(activa=False)
        self.temporal = TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        config = override_settings(MEDIA_ROOT=self.temporal.name)
        config.enable()
        self.addCleanup(config.disable)
        self.coda = Coda.objects.create_user(email='plantillas@example.com', matricula='990', password='test')
        self.client.force_login(self.coda)
        self.ejemplos = Path(__file__).resolve().parent.parent / 'plantillas_ejemplo'

    def contenido(self, tipo):
        nombre = 'reporte_tutorias_plantilla.docx' if tipo == 'reporte' else f'carta_asignacion_{tipo}_plantilla.docx'
        return (self.ejemplos / nombre).read_bytes()

    def documento(self, nombre, tipo, activa=False):
        return Documento.objects.create(nombre=nombre, tipo=tipo, activa=activa,
            archivo=ContentFile(self.contenido(tipo or 'alumno'), name=nombre + '.docx'))

    def test_subida_valida_cada_tipo_y_conserva_bytes(self):
        for tipo in ('alumno', 'tutor', 'reporte'):
            original = self.contenido(tipo)
            form = DocumentoForm({'nombre': tipo, 'tipo': tipo}, {'archivo': SimpleUploadedFile(tipo+'.docx', original)})
            self.assertTrue(form.is_valid(), form.errors)
            obj = form.save()
            with obj.archivo.open('rb') as archivo:
                self.assertEqual(archivo.read(), original)

    def test_tipo_incorrecto_y_archivo_invalido(self):
        for contenido in (self.contenido('tutor'), b'archivo corrupto'):
            form = DocumentoForm({'nombre': 'mala', 'tipo': 'alumno'}, {'archivo': SimpleUploadedFile('mala.docx', contenido)})
            self.assertFalse(form.is_valid())
            self.assertIn('archivo', form.errors)

    def test_clasificar_existente_sin_resubir(self):
        obj = self.documento('Anterior', '')
        form = DocumentoForm({'nombre': obj.nombre, 'tipo': 'alumno'}, instance=obj)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        obj.refresh_from_db()
        self.assertEqual(obj.tipo, 'alumno')

    def test_activacion_reemplaza_solo_mismo_tipo(self):
        anterior = self.documento('Anterior', 'alumno', True)
        nueva = self.documento('Nueva', 'alumno')
        tutor = self.documento('Tutor', 'tutor', True)
        response = self.client.post(reverse('activar-plantilla', args=[nueva.pk]))
        self.assertEqual(response.status_code, 302)
        for obj in (anterior, nueva, tutor): obj.refresh_from_db()
        self.assertFalse(anterior.activa)
        self.assertTrue(nueva.activa)
        self.assertTrue(tutor.activa)

    def test_restriccion_base_de_datos(self):
        self.documento('Primera', 'alumno', True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Documento.objects.create(nombre='Duplicada', tipo='alumno', activa=True, archivo='x.docx')

    def test_predeterminadas_y_alternativas_por_tipo(self):
        alumno = self.documento('Alumno activa', 'alumno', True)
        alternativa = self.documento('Alumno alternativa', 'alumno')
        tutor = self.documento('Tutor activa', 'tutor', True)
        reporte = self.documento('Reporte nombre libre', 'reporte', True)
        form = FormLoteAsignacion()
        self.assertEqual(form['plantilla_alumno'].value(), alumno.pk)
        self.assertEqual(form['plantilla_tutor'].value(), tutor.pk)
        self.assertTrue({alumno, alternativa}.issubset(set(form.fields['plantilla_alumno'].queryset)))
        self.assertNotIn(tutor, form.fields['plantilla_alumno'].queryset)
        self.assertEqual(FormReporteDeTutorias()['plantilla'].value(), reporte.nombre)
        self.assertEqual(FormReporteTutoriasMasivo()['plantilla'].value(), reporte.pk)
        datos = {'seleccion': '1', 'destinatarios': 'alumno', 'plantilla_alumno': alternativa.pk, 'oficio_alumno': 1, 'fecha': '2026-09-15'}
        self.assertTrue(FormLoteAsignacion(datos).is_valid())
        alumno.refresh_from_db()
        self.assertTrue(alumno.activa)
        datos['plantilla_alumno'] = tutor.pk
        self.assertFalse(FormLoteAsignacion(datos).is_valid())

    def test_no_permite_borrar_o_reclasificar_activa(self):
        obj = self.documento('Activa', 'alumno', True)
        self.client.post(reverse('eliminar_documento', args=[obj.pk]))
        self.assertTrue(Documento.objects.filter(pk=obj.pk).exists())
        form = DocumentoForm({'nombre': obj.nombre, 'tipo': 'tutor'}, instance=obj)
        self.assertFalse(form.is_valid())
        self.assertIn('tipo', form.errors)

    def test_ajustes_y_descarga_de_ejemplos(self):
        self.documento('Carta alumno', 'alumno')
        self.assertContains(self.client.get(reverse('ajustes')), 'Carta alumno')
        for tipo in ('alumno', 'tutor', 'reporte'):
            response = self.client.get(reverse('ejemplo-plantilla', args=[tipo]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), self.contenido(tipo))
        self.client.logout()
        self.assertEqual(self.client.get(reverse('ejemplo-plantilla', args=['alumno'])).status_code, 302)

    def test_activar_requiere_post_y_rol_coda(self):
        obj = self.documento('Alumno', 'alumno')
        self.assertEqual(self.client.get(reverse('activar-plantilla', args=[obj.pk])).status_code, 405)
        tutor = Tutor.objects.create_user(email='tutor.plantilla@example.com', matricula='991', password='test', coordinacion='COM')
        self.client.force_login(tutor)
        self.assertEqual(self.client.post(reverse('activar-plantilla', args=[obj.pk])).status_code, 403)

    def test_aviso_sin_predeterminada(self):
        self.assertIn('No hay plantilla predeterminada', FormLoteAsignacion().fields['plantilla_alumno'].help_text)

    def test_reporte_masivo_usa_nombre_libre_y_otra_opcion(self):
        from io import BytesIO
        from zipfile import ZipFile
        predeterminada = self.documento('Mi reporte preferido', 'reporte', True)
        alternativa = self.documento('Formato alternativo', 'reporte')
        tutor = Tutor.objects.create_user(email='reporte.plantilla@example.com', matricula='992', password='test',
                                          first_name='Tutor', last_name='Ejemplo', coordinacion='COM')
        url = reverse('Reporte-tutorias-masivo')
        response = self.client.get(url)
        self.assertEqual(response.context['form']['plantilla'].value(), predeterminada.pk)
        datos = {'plantilla': alternativa.pk, 'tutores': [tutor.pk], 'oficio_inicial': 7,
                 'fecha_inicio': '2026-01-01', 'fecha_fin': '2026-09-15', 'fecha': '2026-09-15T12:00',
                 'col_alumno': 'on'}
        response = self.client.post(url, datos)
        self.assertEqual(response['Content-Type'], 'application/zip')
        with ZipFile(BytesIO(response.content)) as archivo:
            self.assertEqual(len(archivo.namelist()), 1)
            self.assertTrue(archivo.namelist()[0].endswith('.docx'))
        predeterminada.refresh_from_db()
        self.assertTrue(predeterminada.activa)

    def test_reemplazo_invalido_no_modifica_activa(self):
        obj = self.documento('Activa original', 'alumno', True)
        response = self.client.post(reverse('ver_plantilla', args=[obj.pk]),
            {'nombre': obj.nombre, 'tipo': 'alumno', 'archivo': SimpleUploadedFile('mala.docx', b'invalido')})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se pudo abrir')
        obj.refresh_from_db()
        self.assertTrue(obj.activa)
        self.assertTrue(obj.archivo.name.endswith('Activa_original.docx'))
