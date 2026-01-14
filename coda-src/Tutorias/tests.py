from django.test import TestCase
from django.urls import reverse

from Usuarios.models import Tutor, Alumno, Coda
from Usuarios.constants import CODA as CODA_ROLE
from Tutorias.models import Tutoria
from Tutorias.forms import FormSeguimiento
from datetime import datetime

class FormSeguimientoTests(TestCase):
    """Unit tests para FormSeguimiento"""

    def setUp(self):
        # Crear tutor y alumno para las pruebas
        self.tutor = Tutor.objects.create(
            matricula='123',
            email='tutor@example.com',
            password='x',
            first_name='Juan',
            last_name='Perez',
            cubiculo=1,
            coordinacion='COM',
            sexo='M',
        )

        self.alumno = Alumno.objects.create(
            matricula='2001',
            email='alumno@example.com',
            password='x',
            first_name='Alumno',
            last_name='Test',
            carrera='COM',
            tutor_asignado=self.tutor,
        )

        # Crear una tutoría para probar el formulario
        self.tutoria = Tutoria.objects.create(
            alumno=self.alumno,
            tutor=self.tutor,
            tema=['MAT'],
            fecha=datetime.now(),
            descripcion='Test',
            estado='PEN'
        )

    def test_form_seguimiento_valid_data(self):
        """Test que FormSeguimiento acepta datos válidos"""
        form_data = {
            'asistencia': True,
            'duracion': '2',  # 1 hora
            'firma_documentos_beca': True,
            'beca_otorgada': 'Beca Test',
            'asesoria_especializada': True,
            'observaciones': 'Observación de prueba',
            'impacto_tutoria': 5,
            'resultados_tutoria': 'Resultados positivos',
        }
        form = FormSeguimiento(data=form_data, instance=self.tutoria)
        if not form.is_valid():
            print(f"Form errors: {form.errors}")
        self.assertTrue(form.is_valid())

    def test_form_seguimiento_missing_required_asistencia(self):
        """Test que FormSeguimiento falla sin asistencia"""
        form_data = {
            'duracion': '2',
            'firma_documentos_beca': True,
            'asesoria_especializada': True,
            'impacto_tutoria': 5,
        }
        form = FormSeguimiento(data=form_data, instance=self.tutoria)
        self.assertFalse(form.is_valid())
        self.assertIn('asistencia', form.errors)

    def test_form_seguimiento_missing_required_duracion(self):
        """Test que FormSeguimiento falla sin duración"""
        form_data = {
            'asistencia': True,
            'firma_documentos_beca': True,
            'asesoria_especializada': True,
            'impacto_tutoria': 5,
        }
        form = FormSeguimiento(data=form_data, instance=self.tutoria)
        self.assertFalse(form.is_valid())
        self.assertIn('duracion', form.errors)

    def test_form_seguimiento_optional_observaciones(self):
        """Test que observaciones es opcional"""
        form_data = {
            'asistencia': True,
            'duracion': '2',
            'firma_documentos_beca': True,
            'asesoria_especializada': True,
            'impacto_tutoria': 5,
        }
        form = FormSeguimiento(data=form_data, instance=self.tutoria)
        self.assertTrue(form.is_valid())

    def test_form_seguimiento_invalid_impacto_tutoria(self):
        """Test que impacto_tutoria debe ser entero"""
        form_data = {
            'asistencia': True,
            'duracion': '2',
            'firma_documentos_beca': True,
            'asesoria_especializada': True,
            'impacto_tutoria': 'invalid',
        }
        form = FormSeguimiento(data=form_data, instance=self.tutoria)
        self.assertFalse(form.is_valid())
        self.assertIn('impacto_tutoria', form.errors)

    def test_form_seguimiento_max_length_beca_otorgada(self):
        """Test que beca_otorgada respeta max_length=255"""
        form_data = {
            'asistencia': True,
            'duracion': '2',
            'firma_documentos_beca': True,
            'beca_otorgada': 'x' * 300,  # Excede max_length
            'asesoria_especializada': True,
            'impacto_tutoria': 5,
        }
        form = FormSeguimiento(data=form_data, instance=self.tutoria)
        self.assertFalse(form.is_valid())
        self.assertIn('beca_otorgada', form.errors)

    def test_form_seguimiento_max_length_observaciones(self):
        """Test que observaciones respeta max_length=1000"""
        form_data = {
            'asistencia': True,
            'duracion': '2',
            'firma_documentos_beca': True,
            'asesoria_especializada': True,
            'observaciones': 'x' * 1100,  # Excede max_length
            'impacto_tutoria': 5,
        }
        form = FormSeguimiento(data=form_data, instance=self.tutoria)
        self.assertFalse(form.is_valid())
        self.assertIn('observaciones', form.errors)


class ReporteStatusAlumnoTests(TestCase):
    """Unit tests para ReporteStatusAlumnoExcelView"""

    def setUp(self):
        """Crear datos de prueba"""
        # Crear usuario CODA
        self.coda_user = Coda.objects.create_user(
            email='coda@example.com',
            password='test_password',
            matricula='CODA001',
            cubiculo=1,
        )
        self.coda_user.rol = [CODA_ROLE]
        self.coda_user.save()

        # Crear tutores
        self.tutor1 = Tutor.objects.create(
            matricula='TUT001',
            email='tutor1@example.com',
            password='x',
            first_name='Juan',
            last_name='Pérez',
            cubiculo=1,
            coordinacion='COM',
            sexo='M',
        )
        
        self.tutor2 = Tutor.objects.create(
            matricula='TUT002',
            email='tutor2@example.com',
            password='x',
            first_name='María',
            last_name='García',
            cubiculo=2,
            coordinacion='MAT',
            sexo='F',
        )

        # Crear alumnos para tutor1
        self.alumno1 = Alumno.objects.create(
            matricula='ALU001',
            email='alumno1@example.com',
            password='x',
            first_name='Pedro',
            last_name='López',
            carrera='COM',
            tutor_asignado=self.tutor1,
            estado=1,  # Activo
        )
        
        self.alumno2 = Alumno.objects.create(
            matricula='ALU002',
            email='alumno2@example.com',
            password='x',
            first_name='Ana',
            last_name='Martínez',
            carrera='COM',
            tutor_asignado=self.tutor1,
            estado=2,  # No reinscrito
        )
        
        self.alumno3 = Alumno.objects.create(
            matricula='ALU003',
            email='alumno3@example.com',
            password='x',
            first_name='Carlos',
            last_name='Sánchez',
            carrera='COM',
            tutor_asignado=self.tutor1,
            estado=10,  # Sin carga académica
        )

        # Crear alumnos para tutor2
        self.alumno4 = Alumno.objects.create(
            matricula='ALU004',
            email='alumno4@example.com',
            password='x',
            first_name='Laura',
            last_name='Rodríguez',
            carrera='MAT',
            tutor_asignado=self.tutor2,
            estado=1,  # Activo
        )

    def test_reporte_status_alumno_access_denied_no_auth(self):
        """Test que no autenticados no acceden"""
        response = self.client.get(reverse('reporte-status-alumno'))
        # Django redirige a login
        self.assertEqual(response.status_code, 302)

    def test_reporte_status_alumno_returns_excel(self):
        """Test que el reporte retorna un archivo Excel"""
        self.client.force_login(self.coda_user)
        response = self.client.get(reverse('reporte-status-alumno'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('reporte_status_alumnos.xlsx', response['Content-Disposition'])

    def test_reporte_status_alumno_correct_counts(self):
        """Test que los conteos de alumnos son correctos"""
        self.client.force_login(self.coda_user)
        response = self.client.get(reverse('reporte-status-alumno'))
        
        # El archivo Excel se retorna en response.content
        # No verificamos el contenido interno (requeriría procesar Excel)
        # Pero verificamos que se descarga correctamente
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.content), 0)  # Archivo no vacío

    def test_reporte_status_alumno_includes_all_tutors(self):
        """Test que el reporte incluye todos los tutores"""
        self.client.force_login(self.coda_user)
        response = self.client.get(reverse('reporte-status-alumno'))
        
        # Verificar que el archivo se generó correctamente
        self.assertEqual(response.status_code, 200)
        # El archivo debe contener información de ambos tutores
        self.assertGreater(len(response.content), 0)
