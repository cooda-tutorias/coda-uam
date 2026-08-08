from types import SimpleNamespace
from datetime import datetime, time, timedelta
from urllib import response

from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.test import override_settings
from django.core import mail
from django.utils import timezone

from Usuarios.models import Tutor, Alumno
from Tutorias.models import Tutoria, HistorialCambioTutoria
from Tutorias.forms import FormSeguimiento
from Tutorias.services.docx_reportes import _tutoria_es_reportable
from Tutorias.constants import BECAS, PENDIENTE, ACEPTADO, RECHAZADO
from notifications.models import Notification



from django.contrib.auth import get_user_model

User = get_user_model()

class ListaTutoriasProximasTest(TestCase):
    """
    Test para la vista TutorProximasListView.
    Verifica que el tutor vea únicamente sus tutorías ACEPTADAS con fecha futura.
    """
    def setUp(self):
        # 1. Crear las instancias reales de Tutor y Alumno
        self.tutor = Tutor.objects.create_user(
            first_name='Antonio',
            last_name='López',
            email='tutor@cua.uam.mx',
            matricula='123456',
            password='password123',
            es_tutor=True,
        )

        self.alumno = Alumno.objects.create_user(
            first_name='Alumno',
            last_name='Gómez',
            email='alumno@cua.uam.mx',
            matricula='654321',
            password='password123',
            tutor_asignado=self.tutor,
        )

        # 2. Iniciar sesión con el usuario Tutor creado
        self.client.login(email='tutor@cua.uam.mx', password='password123')

        # 3. Inyectar el rol en la sesión del cliente de prueba
        session = self.client.session
        session['role'] = 'tutor'
        session.save()

        # 4. URL de la vista
        self.url = reverse('Tutorias-proximas')

    def _futura(self, dias=1):
        """Helper para crear datetime futuro con timezone."""
        fecha = timezone.localdate() + timedelta(days=dias)
        return timezone.make_aware(datetime.combine(fecha, time(10, 0)))

    def _pasada(self, dias=1):
        """Helper para crear datetime pasado con timezone."""
        fecha = timezone.localdate() - timedelta(days=dias)
        return timezone.make_aware(datetime.combine(fecha, time(10, 0)))

    def test_no_hay_proximas_si_solo_hay_aceptadas_pasadas(self):
        """
        Caso 1: El tutor no tiene próximas porque sus aceptadas son de fechas pasadas
        (o no tiene ninguna).
        """
        # Aceptada pero ya pasó
        Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=self._pasada(2),
            estado='ACE'
        )
        # Pendiente futura (no cuenta)
        Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=self._futura(3),
            estado='PEN'
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        proximas = response.context['object_list']
        self.assertEqual(len(proximas), 0)

    def test_solo_muestra_aceptadas_futuras_entre_mixtas(self):
        """
        Caso 2: Mezcla de estados y fechas.
        Solo deben aparecer las ACEPTADAS con fecha futura.
        """
        # Sin aceptar, pasada
        Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=self._pasada(3),
            estado='PEN'
        )
        # Aceptada, pasada
        Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=self._pasada(1),
            estado='ACE'
        )
        # Aceptada, futura 1
        t1 = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=self._futura(1),
            estado='ACE'
        )
        # Aceptada, futura 2
        t2 = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=self._futura(2),
            estado='ACE'
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        proximas = response.context['object_list']
        self.assertEqual(len(proximas), 2)
        self.assertIn(t1, proximas)
        self.assertIn(t2, proximas)
        # Asegurar ordenamiento por fecha
        self.assertEqual(proximas[0].fecha, t1.fecha)
        self.assertEqual(proximas[1].fecha, t2.fecha)

    def test_todas_son_proximas_cuando_estan_aceptadas_y_futuras(self):
        """
        Caso 3: Todas las registradas están ACEPTADAS y aún no suceden.
        La lista debe traer todas.
        """
        t1 = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=self._futura(1),
            estado='ACE'
        )
        t2 = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=self._futura(4),
            estado='ACE'
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        proximas = response.context['object_list']
        self.assertEqual(len(proximas), 2)
        self.assertIn(t1, proximas)
        self.assertIn(t2, proximas)

class ListaTutoriasSolicitadasTest(TestCase):
    """
    Test para la vista que lista las tutorías solicitadas (estado 'PEN') de un tutor.
    Entre todas las tutorías de un tutor, solo deben mostrarse las que están pendientes.
    """
    def setUp(self):
        # 1. Crear las instancias reales de Tutor y Alumno
        self.tutor = Tutor.objects.create_user(
            first_name='Antonio',
            last_name='López',
            email='tutor@cua.uam.mx',
            matricula='123456', 
            password='password123',
            es_tutor=True,
        )
        
        self.alumno = Alumno.objects.create_user(
            first_name='Alumno',
            last_name='Gómez',
            email='alumno@cua.uam.mx',
            matricula='654321',
            password='password123',
            tutor_asignado=self.tutor,
        )

        # 2. Iniciar sesión con el usuario Tutor creado
        self.client.login(email='tutor@cua.uam.mx', password='password123')

        # 3. Inyectar el rol en la sesión del cliente de prueba
        session = self.client.session
        session['role'] = 'tutor'
        session.save()

        # 4. URL de la vista
        self.url = reverse('Tutorias-tutor')

    def test_lista_solicitadas_solo_filtra_estado_pendiente_en_estados_mixtos(self):
        """Verifica que teniendo estados variados solo traiga las pendientes."""
        tutoria_pen = Tutoria.objects.create(tutor=self.tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='PEN')
        tutoria_ace = Tutoria.objects.create(tutor=self.tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='ACE')
        tutoria_rec = Tutoria.objects.create(tutor=self.tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='REC')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        solicitadas = response.context['object_list']

        self.assertEqual(len(solicitadas), 1)
        self.assertIn(tutoria_pen, solicitadas)
        self.assertNotIn(tutoria_ace, solicitadas)
        self.assertNotIn(tutoria_rec, solicitadas)

    def test_lista_solicitadas_vacia_si_no_hay_pendientes(self):
        """Verifica que si hay tutorías pero ninguna es PEN, la lista regrese vacía."""
        Tutoria.objects.create(tutor=self.tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='ACE')
        Tutoria.objects.create(tutor=self.tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='CAN')

        response = self.client.get(self.url)

        solicitadas = response.context['object_list']
        self.assertEqual(len(solicitadas), 0)

    def test_lista_solicitadas_muestra_todas_si_todas_son_pendientes(self):
        """Verifica que retorne todos los elementos cuando todos están en PEN."""
        t1 = Tutoria.objects.create(tutor=self.tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='PEN')
        t2 = Tutoria.objects.create(tutor=self.tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='PEN')

        response = self.client.get(self.url)

        solicitadas = response.context['object_list']
        self.assertEqual(len(solicitadas), 2)
        self.assertIn(t1, solicitadas)
        self.assertIn(t2, solicitadas)

    def test_lista_solicitadas_no_muestra_pendientes_de_otros_tutores(self):
        """Verifica el aislamiento de datos entre tutores."""
        otro_tutor = Tutor.objects.create_user(
            first_name='Inoki',
            last_name='Atocha',
            email='otro_tutor@cua.uam.mx',
            matricula='78910', 
            password='password123',
            es_tutor=True,
        )

        mi_tutoria = Tutoria.objects.create(tutor=self.tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='PEN')
        otra_tutoria = Tutoria.objects.create(tutor=otro_tutor, alumno=self.alumno, tema=['BEC'], fecha=timezone.now(), estado='PEN')

        response = self.client.get(self.url)

        solicitadas = response.context['object_list']
        self.assertIn(mi_tutoria, solicitadas)
        self.assertNotIn(otra_tutoria, solicitadas)


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


class CartaAnualEstadoHistoricoTests(SimpleTestCase):
    """
    Pruebas de la regla de inclusión de tutorías en la carta anual.

    La decisión debe depender del estado histórico guardado en la tutoría,
    no del estado actual del alumno.
    """

    def test_incluye_tutoria_con_asistencia_y_estado_historico_activo(self):
        tutoria = SimpleNamespace(
            asistencia=True,
            estado_alumno_historico=1,
        )

        self.assertTrue(_tutoria_es_reportable(tutoria))

    def test_excluye_tutoria_con_estado_historico_no_reinscrito(self):
        tutoria = SimpleNamespace(
            asistencia=True,
            estado_alumno_historico=2,
        )

        self.assertFalse(_tutoria_es_reportable(tutoria))

    def test_excluye_tutoria_con_estado_historico_sin_carga_academica(self):
        tutoria = SimpleNamespace(
            asistencia=True,
            estado_alumno_historico=10,
        )

        self.assertFalse(_tutoria_es_reportable(tutoria))

    def test_excluye_tutoria_sin_asistencia(self):
        tutoria = SimpleNamespace(
            asistencia=False,
            estado_alumno_historico=1,
        )

        self.assertFalse(_tutoria_es_reportable(tutoria))

    def test_excluye_tutoria_con_asistencia_sin_registrar(self):
        tutoria = SimpleNamespace(
            asistencia=None,
            estado_alumno_historico=1,
        )

        self.assertFalse(_tutoria_es_reportable(tutoria))

    def test_excluye_tutoria_sin_estado_historico(self):
        tutoria = SimpleNamespace(
            asistencia=True,
            estado_alumno_historico=None,
        )

        self.assertFalse(_tutoria_es_reportable(tutoria))

    def test_incluye_si_historico_es_activo_aunque_estado_actual_no_lo_sea(self):
        alumno = SimpleNamespace(estado=2)

        tutoria = SimpleNamespace(
            alumno=alumno,
            asistencia=True,
            estado_alumno_historico=1,
        )

        self.assertTrue(_tutoria_es_reportable(tutoria))

    def test_excluye_si_historico_no_es_activo_aunque_estado_actual_si_lo_sea(self):
        alumno = SimpleNamespace(estado=1)

        tutoria = SimpleNamespace(
            alumno=alumno,
            asistencia=True,
            estado_alumno_historico=2,
        )

        self.assertFalse(_tutoria_es_reportable(tutoria))
