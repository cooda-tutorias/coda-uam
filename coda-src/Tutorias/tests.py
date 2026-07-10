from django.test import TestCase
from django.urls import reverse
from django.test import override_settings
from django.core import mail
from django.utils import timezone

from Usuarios.models import Tutor, Alumno
from Tutorias.models import Tutoria, HistorialCambioTutoria
from Tutorias.forms import FormSeguimiento
from Tutorias.constants import PENDIENTE, ACEPTADO, RECHAZADO
from notifications.models import Notification
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
            estado=1,
            tutor_asignado=self.tutor,
        )

        # Crear una tutoría para probar el formulario
        self.tutoria = Tutoria.objects.create(
            alumno=self.alumno,
            tutor=self.tutor,
            tema=['MAT'],
            fecha=timezone.now(),
            descripcion='Test',
            estado='PEN'
        )

    def test_form_seguimiento_valid_data(self):
        """Test que FormSeguimiento acepta datos válidos"""
        form_data = {
            'estado_alumno_actual': 1,
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
            'estado_alumno_actual': 1,
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
            'estado_alumno_actual': 1,
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
            'estado_alumno_actual': 1,
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
            'estado_alumno_actual': 1,
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
            'estado_alumno_actual': 1,
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
            'estado_alumno_actual': 1,
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


class NotificacionesTutoriaTests(TestCase):
    def setUp(self):
        self.tema_codigo = 'BEC'
        self.tutor = Tutor.objects.create(
            matricula='3001',
            email='tutor1@example.com',
            password='x',
            first_name='Tutor',
            last_name='Uno',
            cubiculo=1,
            coordinacion='COM',
            sexo='M',
        )
        self.otro_tutor = Tutor.objects.create(
            matricula='3002',
            email='tutor2@example.com',
            password='x',
            first_name='Tutor',
            last_name='Dos',
            cubiculo=2,
            coordinacion='COM',
            sexo='M',
        )
        self.alumno = Alumno.objects.create(
            matricula='4001',
            email='alumno@example.com',
            correo_personal='alumno.personal@example.com',
            password='x',
            first_name='Alumno',
            last_name='Uno',
            carrera='COM',
            estado=1,
            tutor_asignado=self.tutor,
        )
        self.tutoria = Tutoria.objects.create(
            alumno=self.alumno,
            tutor=self.tutor,
            tema=[self.tema_codigo],
            fecha=timezone.now(),
            descripcion='Prueba notificaciones',
            estado=PENDIENTE,
        )

    def test_rechaza_si_tutor_no_es_propietario(self):
        self.client.force_login(self.otro_tutor)

        response = self.client.post(reverse('aceptar_tutoria', args=[self.tutoria.pk]))

        self.assertEqual(response.status_code, 403)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_aceptar_envia_notificacion_y_correo_a_ambos(self):
        self.client.force_login(self.tutor)

        response = self.client.post(reverse('aceptar_tutoria', args=[self.tutoria.pk]))

        self.assertEqual(response.status_code, 302)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertEqual(
            Notification.objects.filter(recipient=self.alumno, verb='Solicitud de tutoría aceptada').count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            sorted(mail.outbox[0].to),
            sorted(['alumno@example.com', 'alumno.personal@example.com'])
        )

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_correos_duplicados_se_envian_una_sola_vez(self):
        self.alumno.correo_personal = self.alumno.email
        self.alumno.save(update_fields=['correo_personal'])
        self.client.force_login(self.tutor)

        response = self.client.post(reverse('aceptar_tutoria', args=[self.tutoria.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['alumno@example.com'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_editar_fecha_envia_notificacion_de_cita(self):
        self.client.force_login(self.tutor)
        nueva_fecha = '2030-01-01T10:30'

        response = self.client.post(
            reverse('Tutorias-update', args=[self.tutoria.pk]),
            {
                'tema': [self.tema_codigo],
                'fecha': nueva_fecha,
                'descripcion': 'Se agenda cita',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(recipient=self.alumno, verb='Tu tutor te cito para una tutoría').count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_guardar_seguimiento_envia_notificacion(self):
        self.client.force_login(self.tutor)

        response = self.client.post(
            reverse('save_seguimiento', args=[self.tutoria.pk]),
            {
                'estado_alumno_actual': 1,
                'asistencia': True,
                'duracion': '2',
                'firma_documentos_beca': True,
                'beca_otorgada': 'Beca prueba',
                'asesoria_especializada': True,
                'observaciones': 'Seguimiento realizado',
                'impacto_tutoria': 4,
                'resultados_tutoria': 'Mejora en progreso',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(recipient=self.alumno, verb='Se registro seguimiento de tu tutoría').count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_tutor_puede_cambiar_decision_en_edicion(self):
        self.client.force_login(self.tutor)
        self.tutoria.estado = ACEPTADO
        self.tutoria.fecha = timezone.make_aware(datetime(2030, 1, 1, 10, 30), timezone.get_current_timezone())
        self.tutoria.save(update_fields=['estado', 'fecha'])

        response = self.client.post(
            reverse('Tutorias-update', args=[self.tutoria.pk]),
            {
                'tema': [self.tema_codigo],
                'fecha': '2030-01-01T10:30',
                'descripcion': 'Cambio de decisión',
                'estado_tutoria': RECHAZADO,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, RECHAZADO)
        self.assertEqual(
            Notification.objects.filter(recipient=self.alumno, verb='Solicitud de tutoría rechazada').count(),
            1,
        )
        self.assertGreaterEqual(len(mail.outbox), 1)
        last_history = HistorialCambioTutoria.objects.filter(tutoria=self.tutoria).order_by('-fecha_cambio').first()
        self.assertIsNotNone(last_history)
        self.assertIn("Estado de la tutoría", last_history.cambios_realizados)
        self.assertIn("Aceptada", last_history.cambios_realizados)
        self.assertIn("Rechazada", last_history.cambios_realizados)
