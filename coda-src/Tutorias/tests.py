from types import SimpleNamespace
from datetime import datetime, time, timedelta
from urllib import response
import json
import random
from unittest.mock import Mock, patch
from requests.exceptions import ConnectionError as RequestsConnectionError

from django.test import RequestFactory, TestCase, SimpleTestCase
from django.urls import reverse
from django.test import override_settings
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser

from Usuarios.models import Coda, Tutor, Alumno, HorarioTutor, PushDevice
from webpush.models import PushInformation, SubscriptionInfo
from pywebpush import WebPushException
from Tutorias.models import Tutoria, HistorialCambioTutoria
from Tutorias.views import HistorialTutoriasGenerateView
from Tutorias.forms import FormSeguimiento
from Tutorias.services.docx_reportes import _tutoria_es_reportable
from Tutorias.constants import (
    BECAS,
    PENDIENTE,
    ACEPTADO,
    RECHAZADO,
    PROPUESTA,
    CANCELADO,
    VENCIDA,
    REPORTADA,
    REALIZADA,
    MOTIVO_RECHAZO_OTRO,
)
from notifications.models import Notification
from Tutorias.signals.events import EventoTutoria
from Tutorias.signals.handle_push_notifications import (
    PUSH_EVENT_INFO,
    _enviar_notificacion_push,
)
from Tutorias.signals.handle_system_notifications import (
    SYSTEM_NOTIFICATION_INFO,
    handle_inapp_notifications,
)
from Tutorias.signals.notification_service import (
    EMAIL_EVENT_CONFIG,
    notify_tutoria_event,
)
from Tutorias.signals.signals_definitions import tutoria_notification_requested


class HistorialTutoriasGenerateAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.tutor = Tutor.objects.create_user(
            first_name="Tutor",
            last_name="Propietario",
            email="tutor.historial@example.com",
            matricula="THIST001",
            password="password123",
        )
        self.otro_tutor = Tutor.objects.create_user(
            first_name="Otro",
            last_name="Tutor",
            email="otro.historial@example.com",
            matricula="THIST002",
            password="password123",
        )
        self.alumno = Alumno.objects.create_user(
            email="alumno.historial@example.com",
            matricula="AHIST001",
            password="password123",
            tutor_asignado=self.tutor,
        )
        self.tutoria_propia = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            descripcion="Tutoría propia",
            fecha=timezone.now(),
            estado=ACEPTADO,
        )
        self.tutoria_ajena = Tutoria.objects.create(
            tutor=self.otro_tutor,
            alumno=self.alumno,
            tema=["BEC"],
            descripcion="Tutoría ajena",
            fecha=timezone.now(),
            estado=ACEPTADO,
        )
        self.url = reverse("Tutorias-historial-generar")

    def get_response_for(self, user, role=None):
        request = self.factory.get(self.url)
        request.user = user
        request.session = {"role": role} if role else {}
        return HistorialTutoriasGenerateView.as_view()(request)

    def test_usuario_anonimo_no_puede_acceder(self):
        response = self.get_response_for(AnonymousUser())

        self.assertEqual(response.status_code, 302)

    def test_alumno_no_puede_acceder(self):
        with self.assertRaises(PermissionDenied):
            self.get_response_for(self.alumno, "alumno")

    def test_tutor_solo_recibe_sus_propias_tutorias(self):
        response = self.get_response_for(self.tutor, "tutor")
        tutorias = list(response.context_data["object_list"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(tutorias, [self.tutoria_propia])
        self.assertNotIn(self.tutoria_ajena, tutorias)


class ReportesAntiguosAccessTests(TestCase):
    def setUp(self):
        self.coda = Coda.objects.create_user(
            email="coda.reportes@example.com",
            matricula="CODAREP001",
            password="password123",
        )
        self.tutor = Tutor.objects.create_user(
            first_name="Tutor",
            last_name="Reportes",
            email="tutor.reportes@example.com",
            matricula="10001",
            password="password123",
            coordinacion="COM",
        )
        self.alumno = Alumno.objects.create_user(
            first_name="Alumno",
            last_name="Reportes",
            email="alumno.reportes@example.com",
            matricula="AREP001",
            password="password123",
            carrera="COM",
            tutor_asignado=self.tutor,
        )
        Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            descripcion="Información protegida del reporte",
            fecha=timezone.now(),
            estado=ACEPTADO,
        )
        self.url_carta = reverse("tutorados_pdf")
        self.url_txt = reverse("generar_txt", args=[self.tutor.pk])

    def test_anonimo_no_puede_descargar_reportes(self):
        carta = self.client.get(self.url_carta, {"tutor-id": self.tutor.matricula})
        txt = self.client.get(self.url_txt)

        self.assertEqual(carta.status_code, 302)
        self.assertEqual(txt.status_code, 302)

    def test_usuario_sin_rol_coda_no_puede_descargar_reportes(self):
        self.client.force_login(self.tutor)

        carta = self.client.get(self.url_carta, {"tutor-id": self.tutor.matricula})
        txt = self.client.get(self.url_txt)

        self.assertEqual(carta.status_code, 403)
        self.assertEqual(txt.status_code, 403)

    def test_coda_puede_descargar_carta_de_tutorados(self):
        self.client.force_login(self.coda)

        response = self.client.get(
            self.url_carta,
            {"tutor-id": self.tutor.matricula},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_coda_puede_descargar_txt_sin_crear_archivo_compartido(self):
        self.client.force_login(self.coda)

        response = self.client.get(self.url_txt)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertContains(response, "Información protegida del reporte")



from django.contrib.auth import get_user_model

User = get_user_model()


class PanelTutoriasAlumnoTests(TestCase):
    """Pruebas de las tres pestañas del panel de tutorías del alumno."""

    def setUp(self):
        self.tutor = Tutor.objects.create_user(
            first_name="Tutor",
            last_name="Prueba",
            email="tutor.panel@cua.uam.mx",
            matricula="T10001",
            password="password123",
            es_tutor=True,
        )
        self.alumno = Alumno.objects.create_user(
            first_name="Alumno",
            last_name="Prueba",
            email="alumno.panel@cua.uam.mx",
            matricula="A10001",
            password="password123",
            tutor_asignado=self.tutor,
        )
        self.otro_alumno = Alumno.objects.create_user(
            first_name="Otro",
            last_name="Alumno",
            email="otro.alumno@cua.uam.mx",
            matricula="A10002",
            password="password123",
            tutor_asignado=self.tutor,
        )
        self.url = reverse("Tutorias-alumno")
        self.client.force_login(self.alumno)

        session = self.client.session
        session["role"] = "alumno"
        session.save()

    def crear_tutoria(
        self,
        estado,
        *,
        alumno=None,
        fecha=None,
        asistencia=None,
        fecha_reporte=None,
    ):
        return Tutoria.objects.create(
            tutor=self.tutor,
            alumno=alumno or self.alumno,
            tema=["BEC"],
            descripcion=f"Tutoría con estado {estado}",
            fecha=fecha or self.fecha_futura(),
            estado=estado,
            asistencia=asistencia,
            fecha_reporte=fecha_reporte,
        )

    def fecha_futura(self):
        return timezone.now() + timedelta(days=2)

    def fecha_pasada(self):
        return timezone.now() - timedelta(days=2)

    def siguiente_fecha_con_dia(self, dia_semana, hora=11):
        fecha = timezone.localdate() + timedelta(days=1)
        while fecha.weekday() != dia_semana:
            fecha += timedelta(days=1)
        return timezone.make_aware(datetime.combine(fecha, time(hora, 0)))

    def test_requiere_autenticacion(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_utiliza_plantilla_del_panel(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "Tutorias/panel_tutorias_alumno.html",
        )

    def test_cambio_sugerido_de_agendada_vuelve_a_pendiente(self):
        tutoria = self.crear_tutoria(ACEPTADO)
        nueva_fecha = timezone.localtime(timezone.now() + timedelta(days=5)).replace(
            hour=12, minute=30, second=0, microsecond=0
        )

        response = self.client.post(
            reverse("solicitar_cambio_fecha_tutoria", args=[tutoria.pk]),
            {"fecha_sugerida": nueva_fecha.strftime("%Y-%m-%dT%H:%M")},
        )

        self.assertRedirects(
            response,
            f"{self.url}?tab=solicitadas&highlight={tutoria.pk}",
            fetch_redirect_response=False,
        )
        tutoria.refresh_from_db()
        self.assertEqual(tutoria.estado, PENDIENTE)
        self.assertEqual(timezone.localtime(tutoria.fecha), nueva_fecha)
        self.assertTrue(HistorialCambioTutoria.objects.filter(tutoria=tutoria).exists())

    def test_cambio_sugerido_rechaza_fin_de_semana(self):
        tutoria = self.crear_tutoria(ACEPTADO)
        fecha_original = tutoria.fecha
        sabado = self.siguiente_fecha_con_dia(5)

        response = self.client.post(
            reverse("solicitar_cambio_fecha_tutoria", args=[tutoria.pk]),
            {"fecha_sugerida": sabado.strftime("%Y-%m-%dT%H:%M")},
        )

        self.assertRedirects(response, self.url)
        tutoria.refresh_from_db()
        self.assertEqual(tutoria.estado, ACEPTADO)
        self.assertEqual(tutoria.fecha, fecha_original)
        self.assertFalse(HistorialCambioTutoria.objects.filter(tutoria=tutoria).exists())

    def test_nueva_solicitud_rechaza_fecha_sugerida_en_fin_de_semana(self):
        sabado = self.siguiente_fecha_con_dia(5)

        response = self.client.post(
            reverse("Tutorias-create"),
            {
                "tema": ["BEC"],
                "descripcion": "Solicitud en fin de semana",
                "fecha_sugerida": sabado.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "La fecha sugerida debe ser un día hábil.",
            response.context["form"].errors["fecha_sugerida"],
        )
        self.assertFalse(
            Tutoria.objects.filter(descripcion="Solicitud en fin de semana").exists()
        )

    def test_cambio_a_horario_libre_queda_agendado(self):
        tutoria = self.crear_tutoria(PENDIENTE)
        dia = timezone.localdate() + timedelta(days=1)
        while dia.weekday() > 4:
            dia += timedelta(days=1)
        horario = HorarioTutor.objects.create(
            tutor=self.tutor,
            dia_semana=dia.weekday(),
            hora_inicio=time(10, 0),
            hora_fin=time(11, 0),
        )

        response = self.client.post(
            reverse("solicitar_cambio_fecha_tutoria", args=[tutoria.pk]),
            {
                "horario_tutor": horario.pk,
                "franja_seleccionada": f"{dia.isoformat()}T10:30:00",
            },
        )

        self.assertRedirects(
            response,
            f"{self.url}?tab=agendadas&highlight={tutoria.pk}",
            fetch_redirect_response=False,
        )
        tutoria.refresh_from_db()
        self.assertEqual(tutoria.estado, ACEPTADO)
        self.assertEqual(timezone.localtime(tutoria.fecha).date(), dia)
        self.assertEqual(timezone.localtime(tutoria.fecha).time(), time(10, 30))

    def test_alumnos_distintos_pueden_agendar_franjas_del_mismo_dia(self):
        dia = timezone.localdate() + timedelta(days=1)
        while dia.weekday() > 4:
            dia += timedelta(days=1)
        horario = HorarioTutor.objects.create(
            tutor=self.tutor,
            dia_semana=dia.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(11, 0),
        )
        url = reverse("Tutorias-create")

        respuestas = []
        for alumno, hora in ((self.alumno, "08:00:00"), (self.otro_alumno, "10:00:00")):
            self.client.force_login(alumno)
            respuestas.append(self.client.post(url, {
                "tema": ["BEC"],
                "descripcion": "Prueba de franja independiente",
                "horario_tutor": horario.pk,
                "franja_seleccionada": f"{dia.isoformat()}T{hora}",
            }))

        self.assertTrue(all(respuesta.status_code == 302 for respuesta in respuestas))
        citas = list(Tutoria.objects.filter(fecha__date=dia).order_by("fecha"))
        self.assertEqual(len(citas), 2)
        self.assertEqual(
            [timezone.localtime(cita.fecha).strftime("%H:%M") for cita in citas],
            ["08:00", "10:00"],
        )

    def test_no_permite_cambiar_tutoria_de_otro_alumno(self):
        tutoria = self.crear_tutoria(PENDIENTE, alumno=self.otro_alumno)

        response = self.client.post(
            reverse("solicitar_cambio_fecha_tutoria", args=[tutoria.pk]),
            {"fecha_sugerida": "2030-01-01T10:00"},
        )

        self.assertEqual(response.status_code, 403)

    def test_clasifica_tutorias_en_las_tres_pestanas(self):
        pendiente = self.crear_tutoria(PENDIENTE)
        propuesta = self.crear_tutoria(PROPUESTA)
        aceptada = self.crear_tutoria(ACEPTADO)
        rechazada = self.crear_tutoria(RECHAZADO)
        cancelada = self.crear_tutoria(CANCELADO)
        realizada = self.crear_tutoria(REALIZADA)
        reportada = self.crear_tutoria(REPORTADA)

        response = self.client.get(self.url)

        self.assertCountEqual(
            response.context["tutorias_solicitadas"],
            [pendiente, propuesta],
        )
        self.assertCountEqual(
            response.context["tutorias_agendadas"],
            [aceptada],
        )
        self.assertCountEqual(
            response.context["tutorias_historial"],
            [realizada, reportada, rechazada, cancelada],
        )

    def test_historial_muestra_motivos_en_badges_clicables(self):
        cancelada = self.crear_tutoria(CANCELADO)
        cancelada.origen_cancelacion = "ALUMNO"
        cancelada.motivo_cancelacion = "ALU_PERSO"
        cancelada.save(update_fields=["origen_cancelacion", "motivo_cancelacion"])

        rechazada = self.crear_tutoria(RECHAZADO)
        rechazada.motivo_rechazo = "SIN_DISPONIBILIDAD_FECHAS"
        rechazada.save(update_fields=["motivo_rechazo"])

        response = self.client.get(self.url)

        self.assertContains(response, 'data-bs-toggle="popover"')
        self.assertContains(response, "Cancelada por el alumno")
        self.assertContains(response, "Imprevisto personal o de salud")
        self.assertContains(response, "Rechazada por el tutor")
        self.assertContains(
            response,
            "No tengo disponibilidad y no puedo proponer otro horario.",
        )

    def test_alumno_no_puede_elegir_propuesta_de_otro_alumno(self):
        tutoria = self.crear_tutoria(PROPUESTA, alumno=self.otro_alumno)
        tutoria.fecha_propuesta_1 = self.fecha_futura()
        tutoria.save(update_fields=["fecha_propuesta_1"])

        response = self.client.post(
            reverse("seleccionar_propuesta_tutoria", args=[tutoria.pk]),
            {"opcion_elegida": "1"},
        )

        self.assertEqual(response.status_code, 403)
        tutoria.refresh_from_db()
        self.assertEqual(tutoria.estado, PROPUESTA)

    def test_tutor_no_puede_elegir_propuesta_del_alumno(self):
        tutoria = self.crear_tutoria(PROPUESTA)
        tutoria.fecha_propuesta_1 = self.fecha_futura()
        tutoria.save(update_fields=["fecha_propuesta_1"])
        self.client.force_login(self.tutor)

        response = self.client.post(
            reverse("seleccionar_propuesta_tutoria", args=[tutoria.pk]),
            {"opcion_elegida": "1"},
        )

        self.assertEqual(response.status_code, 403)
        tutoria.refresh_from_db()
        self.assertEqual(tutoria.estado, PROPUESTA)

    def test_seleccionar_propuesta_no_admite_get(self):
        tutoria = self.crear_tutoria(PROPUESTA)

        response = self.client.get(
            reverse("seleccionar_propuesta_tutoria", args=[tutoria.pk]),
        )

        self.assertEqual(response.status_code, 405)

    def test_anonimo_no_puede_elegir_propuesta(self):
        tutoria = self.crear_tutoria(PROPUESTA)
        self.client.logout()

        response = self.client.post(
            reverse("seleccionar_propuesta_tutoria", args=[tutoria.pk]),
            {"opcion_elegida": "1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_clasifica_estados_efectivos_segun_fecha(self):
        pendiente_vencida = self.crear_tutoria(
            PENDIENTE,
            fecha=self.fecha_pasada(),
        )
        propuesta_vencida = self.crear_tutoria(
            PROPUESTA,
            fecha=self.fecha_pasada(),
        )
        aceptada_realizada = self.crear_tutoria(
            ACEPTADO,
            fecha=self.fecha_pasada(),
            asistencia=None,
        )
        aceptada_reportada = self.crear_tutoria(
            ACEPTADO,
            fecha=self.fecha_pasada(),
            asistencia=True,
            fecha_reporte=timezone.now(),
        )

        response = self.client.get(self.url)

        solicitadas = response.context["tutorias_solicitadas"]
        agendadas = response.context["tutorias_agendadas"]
        historial = response.context["tutorias_historial"]

        self.assertEqual(pendiente_vencida.estado_efectivo, VENCIDA)
        self.assertEqual(propuesta_vencida.estado_efectivo, VENCIDA)
        self.assertEqual(aceptada_realizada.estado_efectivo, REALIZADA)
        self.assertEqual(aceptada_reportada.estado_efectivo, REPORTADA)
        self.assertIn(pendiente_vencida, solicitadas)
        self.assertIn(propuesta_vencida, solicitadas)
        self.assertNotIn(aceptada_realizada, agendadas)
        self.assertNotIn(aceptada_reportada, agendadas)
        self.assertIn(aceptada_realizada, historial)
        self.assertIn(aceptada_reportada, historial)

    def test_no_muestra_tutorias_de_otro_alumno(self):
        propia = self.crear_tutoria(PENDIENTE)
        ajena = self.crear_tutoria(
            PENDIENTE,
            alumno=self.otro_alumno,
        )

        response = self.client.get(self.url)

        self.assertIn(propia, response.context["tutorias"])
        self.assertNotIn(ajena, response.context["tutorias"])
        self.assertNotIn(
            ajena,
            response.context["tutorias_solicitadas"],
        )

    def test_una_tutoria_no_aparece_en_mas_de_una_pestana(self):
        for estado in [
            PENDIENTE,
            PROPUESTA,
            ACEPTADO,
            RECHAZADO,
            CANCELADO,
            REALIZADA,
            REPORTADA,
        ]:
            self.crear_tutoria(estado)

        response = self.client.get(self.url)

        clasificadas = (
            response.context["tutorias_solicitadas"]
            + response.context["tutorias_agendadas"]
            + response.context["tutorias_historial"]
        )
        ids = [tutoria.pk for tutoria in clasificadas]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertCountEqual(clasificadas, response.context["tutorias"])

    def test_muestra_panel_si_no_existen_tutorias(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tutorias_solicitadas"], [])
        self.assertEqual(response.context["tutorias_agendadas"], [])
        self.assertEqual(response.context["tutorias_historial"], [])

    def test_pendiente_muestra_boton_del_modal_de_edicion(self):
        tutoria = self.crear_tutoria(PENDIENTE)

        response = self.client.get(self.url)

        url_modal = reverse("Tutorias-update-modal", args=[tutoria.pk])
        self.assertContains(response, f'data-url="{url_modal}"')
        self.assertContains(response, "js-abrir-editar-tutoria")

    def test_aceptada_muestra_boton_del_modal_de_edicion(self):
        tutoria = self.crear_tutoria(ACEPTADO)

        response = self.client.get(self.url)

        self.assertContains(
            response,
            reverse("Tutorias-update-modal", args=[tutoria.pk]),
        )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class MatrizTransicionesTutoriaIntegrationTests(TestCase):
    """Matriz funcional de estados y pestañas para tutor y alumno."""

    def setUp(self):
        self.tutor = Tutor.objects.create_user(
            first_name="Tutor",
            last_name="Matriz",
            email="tutor.matriz@cua.uam.mx",
            matricula="T17001",
            password="password123",
            es_tutor=True,
        )
        self.alumno = Alumno.objects.create_user(
            first_name="Alumno",
            last_name="Matriz",
            email="alumno.matriz@cua.uam.mx",
            matricula="A17001",
            password="password123",
            tutor_asignado=self.tutor,
            estado=1,
        )
        self.tutoria = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            descripcion="Tutoría para matriz de integración",
            fecha=timezone.now() + timedelta(days=3),
            estado=PENDIENTE,
        )

    def siguiente_fecha_habil(self, fecha):
        while fecha.weekday() >= 5:
            fecha += timedelta(days=1)
        return fecha

    def proponer(self, *, segunda=False, reagendacion=False):
        self.client.force_login(self.tutor)
        propuesta_1 = self.siguiente_fecha_habil(
            timezone.localtime() + timedelta(days=5),
        )
        # Se deriva de la primera para garantizar que las opciones sean
        # distintas incluso cuando una o ambas fechas iniciales caigan en fin
        # de semana.
        propuesta_2 = self.siguiente_fecha_habil(
            propuesta_1 + timedelta(days=1),
        )
        datos = {
            'propuesta_1': propuesta_1.strftime('%Y-%m-%dT%H:%M'),
            'propuesta_2': (
                propuesta_2.strftime('%Y-%m-%dT%H:%M') if segunda else ''
            ),
        }
        if reagendacion:
            datos['es_reagendacion'] = '1'
        response = self.client.post(
            reverse('proponer_fechas_tutoria', args=[self.tutoria.pk]),
            datos,
        )
        pestana = 'solicitadas' if segunda else 'agendadas'
        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab={pestana}"
            f"&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        return response

    def seleccionar(self, opcion='1'):
        self.client.force_login(self.alumno)
        response = self.client.post(
            reverse('seleccionar_propuesta_tutoria', args=[self.tutoria.pk]),
            {'opcion_elegida': opcion},
        )
        self.assertRedirects(
            response,
            f"{reverse('Tutorias-alumno')}?tab=agendadas"
            f"&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        return response

    def assert_en_pestana(self, nombre_pestana, estado_efectivo):
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado_efectivo, estado_efectivo)

        claves = {
            'solicitadas': 'tutorias_solicitadas',
            'agendadas': 'tutorias_agendadas',
            'historial': 'tutorias_historial',
        }
        for usuario, rol, url in (
            (self.tutor, 'tutor', reverse('Panel-tutorias-tutor')),
            (self.alumno, 'alumno', reverse('Tutorias-alumno')),
        ):
            self.client.force_login(usuario)
            session = self.client.session
            session['role'] = rol
            session.save()
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for pestana, clave_contexto in claves.items():
                if pestana == nombre_pestana:
                    self.assertIn(self.tutoria, response.context[clave_contexto])
                else:
                    self.assertNotIn(self.tutoria, response.context[clave_contexto])

    def test_caso_01_tutor_acepta_solicitud(self):
        self.client.force_login(self.tutor)
        self.client.post(reverse('aceptar_tutoria', args=[self.tutoria.pk]))

        self.assert_en_pestana('agendadas', ACEPTADO)

    def test_caso_02_tutor_rechaza_solicitud(self):
        self.client.force_login(self.tutor)
        self.client.post(
            reverse('rechazar_tutoria', args=[self.tutoria.pk]),
            {'motivo_rechazo': 'SIN_DISPONIBILIDAD_FECHAS'},
        )

        self.assert_en_pestana('historial', RECHAZADO)

    def test_caso_03_tutor_propone_una_fecha_para_solicitud(self):
        self.proponer()

        self.assert_en_pestana('agendadas', ACEPTADO)

    def test_caso_04_tutor_propone_dos_fechas_para_solicitud(self):
        self.proponer(segunda=True)

        self.assert_en_pestana('solicitadas', PROPUESTA)

    def test_caso_05_alumno_cancela_tutoria_solicitada(self):
        self.client.force_login(self.alumno)
        self.client.post(
            reverse('cancelar-tutoria', args=[self.tutoria.pk]),
            {'motivo_cancelacion': 'ALU_RESOL'},
        )

        self.assert_en_pestana('historial', CANCELADO)

    def test_caso_06_alumno_cancela_tutoria_agendada(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.save(update_fields=['estado'])
        self.client.force_login(self.alumno)
        self.client.post(
            reverse('cancelar-tutoria', args=[self.tutoria.pk]),
            {'motivo_cancelacion': 'ALU_PERSO'},
        )

        self.assert_en_pestana('historial', CANCELADO)

    def test_caso_07_tutor_cancela_tutoria_agendada(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.save(update_fields=['estado'])
        self.client.force_login(self.tutor)
        self.client.post(
            reverse('cancelar-tutoria', args=[self.tutoria.pk]),
            {'motivo_cancelacion': 'TUT_ACADE'},
        )

        self.assert_en_pestana('historial', CANCELADO)

    def test_caso_08_tutor_reactiva_vencida_con_una_fecha(self):
        self.tutoria.fecha = timezone.now() - timedelta(days=1)
        self.tutoria.save(update_fields=['fecha'])
        self.proponer()

        self.assert_en_pestana('agendadas', ACEPTADO)

    def test_caso_09_tutor_reactiva_vencida_con_dos_fechas(self):
        self.tutoria.fecha = timezone.now() - timedelta(days=1)
        self.tutoria.save(update_fields=['fecha'])
        self.proponer(segunda=True)

        self.assert_en_pestana('solicitadas', PROPUESTA)

    def test_caso_10_tutor_reagenda_agendada_con_una_fecha(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.save(update_fields=['estado'])
        self.proponer(reagendacion=True)

        self.assert_en_pestana('agendadas', ACEPTADO)

    def test_caso_11_tutor_reagenda_agendada_con_dos_fechas(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.save(update_fields=['estado'])
        self.proponer(segunda=True, reagendacion=True)

        self.assert_en_pestana('solicitadas', PROPUESTA)

    def test_caso_12_alumno_elige_fecha_de_solicitud(self):
        self.proponer(segunda=True)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PROPUESTA)
        self.assertIsNotNone(self.tutoria.fecha_propuesta_1)
        self.assertIsNotNone(self.tutoria.fecha_propuesta_2)
        fecha_elegida = self.tutoria.fecha_propuesta_2
        self.seleccionar('2')

        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.fecha, fecha_elegida)
        self.assertIsNone(self.tutoria.fecha_propuesta_1)
        self.assertIsNone(self.tutoria.fecha_propuesta_2)
        self.assert_en_pestana('agendadas', ACEPTADO)

    def test_caso_13_alumno_elige_fecha_de_reagendacion(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.save(update_fields=['estado'])
        self.proponer(segunda=True, reagendacion=True)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PROPUESTA)
        self.assertTrue(self.tutoria.reagendacion_pendiente)
        self.assertIsNotNone(self.tutoria.fecha_propuesta_1)
        self.assertIsNotNone(self.tutoria.fecha_propuesta_2)
        self.seleccionar('1')

        self.tutoria.refresh_from_db()
        self.assertFalse(self.tutoria.reagendacion_pendiente)
        self.assert_en_pestana('agendadas', ACEPTADO)

    def test_caso_14_agendada_pasada_se_muestra_realizada(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.fecha = timezone.now() - timedelta(minutes=1)
        self.tutoria.save(update_fields=['estado', 'fecha'])

        self.assert_en_pestana('historial', REALIZADA)

    def test_caso_15_tutor_registra_reporte_de_tutoria_realizada(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.fecha = timezone.now() - timedelta(minutes=1)
        self.tutoria.save(update_fields=['estado', 'fecha'])
        self.client.force_login(self.tutor)
        response = self.client.post(
            reverse('save_seguimiento', args=[self.tutoria.pk]),
            {
                'estado_alumno_actual': 1,
                'asistencia': True,
                'duracion': '2',
                'firma_documentos_beca': False,
                'asesoria_especializada': False,
                'impacto_tutoria': 4,
                'resultados_tutoria': 'Seguimiento registrado',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.tutoria.refresh_from_db()
        self.assertIsNotNone(self.tutoria.fecha_reporte)
        self.assert_en_pestana('historial', REPORTADA)

    def test_caso_16_solicitud_pendiente_vence(self):
        self.tutoria.fecha = timezone.now() - timedelta(minutes=1)
        self.tutoria.save(update_fields=['fecha'])

        self.assert_en_pestana('solicitadas', VENCIDA)

    def test_caso_17_vencen_las_dos_fechas_propuestas(self):
        self.tutoria.estado = PROPUESTA
        self.tutoria.fecha_propuesta_1 = timezone.now() - timedelta(days=2)
        self.tutoria.fecha_propuesta_2 = timezone.now() - timedelta(days=1)
        self.tutoria.save(update_fields=[
            'estado',
            'fecha_propuesta_1',
            'fecha_propuesta_2',
        ])

        self.assert_en_pestana('solicitadas', VENCIDA)


class EditarTutoriaModalTests(TestCase):
    """Pruebas de la edición de temas y descripción desde el modal."""

    def setUp(self):
        self.tutor = Tutor.objects.create_user(
            first_name="Tutor",
            last_name="Modal",
            email="tutor.modal@cua.uam.mx",
            matricula="T20001",
            password="password123",
            es_tutor=True,
        )
        self.alumno = Alumno.objects.create_user(
            first_name="Alumno",
            last_name="Modal",
            email="alumno.modal@cua.uam.mx",
            matricula="A20001",
            password="password123",
            tutor_asignado=self.tutor,
        )
        self.otro_alumno = Alumno.objects.create_user(
            first_name="Otro",
            last_name="Modal",
            email="otro.modal@cua.uam.mx",
            matricula="A20002",
            password="password123",
            tutor_asignado=self.tutor,
        )
        self.fecha_original = timezone.now() + timedelta(days=3)
        self.tutoria = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            descripcion="Descripción original",
            fecha=self.fecha_original,
            estado=PENDIENTE,
        )
        self.url = reverse(
            "Tutorias-update-modal",
            args=[self.tutoria.pk],
        )
        self.client.force_login(self.alumno)

        session = self.client.session
        session["role"] = "alumno"
        session.save()

    def test_get_carga_valores_actuales_y_solo_campos_permitidos(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "Tutorias/includes/_modal_editar_tutoria.html",
        )
        self.assertEqual(response.context["form"].initial["tema"], ["BEC"])
        self.assertEqual(
            response.context["form"].initial["descripcion"],
            "Descripción original",
        )
        self.assertEqual(
            set(response.context["form"].fields),
            {"tema", "descripcion"},
        )
        self.assertNotContains(response, 'name="fecha"')

    def test_post_actualiza_tema_y_descripcion_sin_cambiar_fecha(self):
        response = self.client.post(
            self.url,
            {
                "tema": ["INS", "ING"],
                "descripcion": "Descripción actualizada",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {
                "ok": True,
                "message": "La tutoría se actualizó correctamente.",
            },
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.tema, ["INS", "ING"])
        self.assertEqual(
            self.tutoria.descripcion,
            "Descripción actualizada",
        )
        self.assertEqual(self.tutoria.fecha, self.fecha_original)

    def test_post_invalido_responde_422_y_muestra_errores(self):
        response = self.client.post(
            self.url,
            {
                "tema": [],
                "descripcion": "",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.context["form"].errors)
        self.assertIn("tema", response.context["form"].errors)
        self.assertIn("descripcion", response.context["form"].errors)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.tema, ["BEC"])
        self.assertEqual(self.tutoria.descripcion, "Descripción original")

    def test_alumno_no_puede_editar_tutoria_de_otro_alumno(self):
        tutoria_ajena = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.otro_alumno,
            tema=["BEC"],
            descripcion="Tutoría ajena",
            fecha=self.fecha_original,
            estado=PENDIENTE,
        )
        url_ajena = reverse(
            "Tutorias-update-modal",
            args=[tutoria_ajena.pk],
        )

        response_get = self.client.get(url_ajena)
        response_post = self.client.post(
            url_ajena,
            {
                "tema": ["INS"],
                "descripcion": "Intento de modificación",
            },
        )

        self.assertEqual(response_get.status_code, 404)
        self.assertEqual(response_post.status_code, 404)
        tutoria_ajena.refresh_from_db()
        self.assertEqual(tutoria_ajena.tema, ["BEC"])
        self.assertEqual(tutoria_ajena.descripcion, "Tutoría ajena")

    def test_usuario_no_autenticado_no_puede_abrir_modal(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_post_valido_crea_registro_en_historial(self):
        response = self.client.post(
            self.url,
            {
                "tema": ["INS"],
                "descripcion": "Cambio registrado",
            },
        )

        self.assertEqual(response.status_code, 200)
        cambio = HistorialCambioTutoria.objects.get(tutoria=self.tutoria)
        self.assertEqual(cambio.correo_editor, self.alumno.email)
        self.assertIn("Tema(s)", cambio.cambios_realizados)
        self.assertIn("Observaciones", cambio.cambios_realizados)


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

    def test_lista_solicitadas_vacia_si_no_hay_pendientes_ni_propuestas(self):
        """Muestra las tutorías pendientes y las que esperan elección del alumno."""
        tutoria_pen = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            fecha=timezone.now(),
            estado=PENDIENTE,
        )
        tutoria_pro = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            fecha=timezone.now(),
            estado=PROPUESTA,
        )
        tutoria_ace = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            fecha=timezone.now(),
            estado=ACEPTADO,
        )
        tutoria_rej = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            fecha=timezone.now(),
            estado=RECHAZADO,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        solicitadas = response.context["object_list"]

        self.assertEqual(len(solicitadas), 2)
        self.assertIn(tutoria_pen, solicitadas)
        self.assertIn(tutoria_pro, solicitadas)
        self.assertNotIn(tutoria_ace, solicitadas)
        self.assertNotIn(tutoria_rej, solicitadas)

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


class PropuestasFechaTutoriaTests(TestCase):
    """Pruebas del flujo de fechas alternativas propuestas por el tutor."""

    def setUp(self):
        self.tutor = Tutor.objects.create_user(
            first_name='Antonio',
            last_name='López',
            email='tutor.propuestas@cua.uam.mx',
            matricula='123457',
            password='password123',
            es_tutor=True,
        )
        self.alumno = Alumno.objects.create_user(
            first_name='Estudiante',
            last_name='Gómez',
            email='alumno.propuestas@cua.uam.mx',
            matricula='654322',
            password='password123',
            tutor_asignado=self.tutor,
        )
        self.tutoria = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=timezone.make_aware(datetime(2030, 1, 10, 10, 0)),
            estado=PENDIENTE,
        )

    def fecha_habil_futura(self, dias=7, hora=11):
        fecha = timezone.localdate() + timedelta(days=dias)
        while fecha.weekday() >= 5:
            fecha += timedelta(days=1)
        return timezone.make_aware(datetime.combine(fecha, time(hora, 0)))

    def enviar_propuestas(self, propuesta_1, propuesta_2='', **datos_extra):
        datos = {
            'propuesta_1': propuesta_1.strftime('%Y-%m-%dT%H:%M'),
            'propuesta_2': (
                propuesta_2.strftime('%Y-%m-%dT%H:%M') if propuesta_2 else ''
            ),
            **datos_extra,
        }
        return self.client.post(
            reverse('proponer_fechas_tutoria', args=[self.tutoria.pk]),
            datos,
        )

    def assert_propuesta_rechazada(self, response, mensaje):
        self.assertRedirects(
            response,
            reverse('Panel-tutorias-tutor'),
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)
        self.assertIsNone(self.tutoria.fecha_propuesta_1)
        self.assertIsNone(self.tutoria.fecha_propuesta_2)
        self.assertTrue(
            any(mensaje in str(item) for item in response.wsgi_request._messages),
        )

    def test_rechaza_una_fecha_anterior_al_siguiente_dia_habil(self):
        self.client.force_login(self.tutor)
        response = self.enviar_propuestas(timezone.localtime() - timedelta(days=1))
        self.assert_propuesta_rechazada(response, 'siguiente día hábil')

    def test_rechaza_fechas_en_fin_de_semana(self):
        self.client.force_login(self.tutor)
        fecha = timezone.localdate() + timedelta(days=7)
        while fecha.weekday() != 5:
            fecha += timedelta(days=1)
        sabado = timezone.make_aware(datetime.combine(fecha, time(11, 0)))

        response = self.enviar_propuestas(sabado)

        self.assert_propuesta_rechazada(response, 'días hábiles')

    def test_rechaza_dos_propuestas_iguales(self):
        self.client.force_login(self.tutor)
        propuesta = self.fecha_habil_futura()

        response = self.enviar_propuestas(propuesta, propuesta)

        self.assert_propuesta_rechazada(response, 'deben ser diferentes')

    def test_reagendacion_rechaza_dos_propuestas_iguales(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.save(update_fields=['estado'])
        fecha_original = self.tutoria.fecha
        self.client.force_login(self.tutor)
        propuesta = self.fecha_habil_futura()

        response = self.enviar_propuestas(
            propuesta,
            propuesta,
            es_reagendacion='1',
        )

        self.assertRedirects(
            response,
            reverse('Panel-tutorias-tutor'),
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertEqual(self.tutoria.fecha, fecha_original)
        self.assertIsNone(self.tutoria.fecha_propuesta_1)
        self.assertIsNone(self.tutoria.fecha_propuesta_2)

    def test_reactivacion_rechaza_dos_propuestas_iguales(self):
        self.tutoria.fecha = timezone.now() - timedelta(days=1)
        self.tutoria.save(update_fields=['fecha'])
        self.client.force_login(self.tutor)
        propuesta = self.fecha_habil_futura()

        response = self.enviar_propuestas(propuesta, propuesta)

        self.assert_propuesta_rechazada(response, 'deben ser diferentes')
        self.assertEqual(self.tutoria.estado_efectivo, VENCIDA)

    def test_una_fecha_propuesta_acepta_directamente_la_tutoria(self):
        self.client.force_login(self.tutor)

        response = self.client.post(
            reverse('proponer_fechas_tutoria', args=[self.tutoria.pk]),
            {
                'propuesta_1': '2030-01-15T11:30',
                'propuesta_2': '',
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=agendadas&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertEqual(
            self.tutoria.fecha,
            timezone.make_aware(datetime(2030, 1, 15, 11, 30)),
        )
        self.assertIsNone(self.tutoria.fecha_propuesta_1)
        self.assertIsNone(self.tutoria.fecha_propuesta_2)

    def test_dos_fechas_dejan_la_tutoria_en_propuesta_hasta_que_el_alumno_elija(self):
        self.client.force_login(self.tutor)

        response = self.client.post(
            reverse('proponer_fechas_tutoria', args=[self.tutoria.pk]),
            {
                'propuesta_1': '2030-01-15T11:30',
                'propuesta_2': '2030-01-16T12:00',
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=solicitadas&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PROPUESTA)
        self.assertEqual(
            self.tutoria.fecha_propuesta_1,
            timezone.make_aware(datetime(2030, 1, 15, 11, 30)),
        )
        self.assertEqual(
            self.tutoria.fecha_propuesta_2,
            timezone.make_aware(datetime(2030, 1, 16, 12, 0)),
        )

        self.client.force_login(self.alumno)
        response = self.client.post(
            reverse('seleccionar_propuesta_tutoria', args=[self.tutoria.pk]),
            {'opcion_elegida': '2'},
        )

        self.assertRedirects(
            response,
            f"{reverse('Tutorias-alumno')}?tab=agendadas&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertEqual(
            self.tutoria.fecha,
            timezone.make_aware(datetime(2030, 1, 16, 12, 0)),
        )
        self.assertIsNone(self.tutoria.fecha_propuesta_1)
        self.assertIsNone(self.tutoria.fecha_propuesta_2)

    def test_dos_fechas_reactivan_una_tutoria_vencida(self):
        self.tutoria.fecha = timezone.now() - timedelta(days=1)
        self.tutoria.save(update_fields=['fecha'])
        self.assertEqual(self.tutoria.estado_efectivo, VENCIDA)
        self.client.force_login(self.tutor)

        propuesta_1 = self.fecha_habil_futura()
        fecha_propuesta_2 = propuesta_1.date() + timedelta(
            days=random.randint(1, 10),
        )
        while fecha_propuesta_2.weekday() >= 5:
            fecha_propuesta_2 += timedelta(days=1)
        propuesta_2 = timezone.make_aware(
            datetime.combine(fecha_propuesta_2, propuesta_1.time()),
        )
        self.assertNotEqual(propuesta_1, propuesta_2)
        response = self.client.post(
            reverse('proponer_fechas_tutoria', args=[self.tutoria.pk]),
            {
                'propuesta_1': propuesta_1.strftime('%Y-%m-%dT%H:%M'),
                'propuesta_2': propuesta_2.strftime('%Y-%m-%dT%H:%M'),
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=solicitadas&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PROPUESTA)
        self.assertEqual(self.tutoria.estado_efectivo, PROPUESTA)
        notification = Notification.objects.filter(recipient=self.alumno).latest('timestamp')
        self.assertEqual(
            notification.verb,
            "reactivó tu solicitud y propuso opciones de fecha",
        )
        self.assertEqual(
            notification.description,
            "Solicitud de tutoría reactivada; elige una fecha",
        )

    def test_una_fecha_reactiva_y_agenda_una_tutoria_vencida(self):
        self.tutoria.fecha = timezone.now() - timedelta(days=1)
        self.tutoria.save(update_fields=['fecha'])
        self.assertEqual(self.tutoria.estado_efectivo, VENCIDA)
        self.client.force_login(self.tutor)

        response = self.client.post(
            reverse('proponer_fechas_tutoria', args=[self.tutoria.pk]),
            {
                'propuesta_1': '2030-01-15T11:30',
                'propuesta_2': '',
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=agendadas&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertEqual(
            self.tutoria.fecha,
            timezone.make_aware(datetime(2030, 1, 15, 11, 30)),
        )
        notification = Notification.objects.filter(recipient=self.alumno).latest('timestamp')
        self.assertEqual(
            notification.verb,
            "reactivó y agendó tu solicitud de tutoría en una nueva fecha",
        )
        self.assertEqual(
            notification.description,
            "Solicitud de tutoría reactivada y agendada",
        )

    def test_dos_fechas_marcan_una_tutoria_agendada_por_reagendar(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.save(update_fields=['estado'])
        self.client.force_login(self.tutor)

        response = self.client.post(
            reverse('proponer_fechas_tutoria', args=[self.tutoria.pk]),
            {
                'propuesta_1': '2030-01-15T11:30',
                'propuesta_2': '2030-01-16T12:00',
                'es_reagendacion': '1',
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=solicitadas&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PROPUESTA)
        self.assertTrue(self.tutoria.reagendacion_pendiente)

    def test_una_fecha_reagenda_directamente_la_tutoria(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.save(update_fields=['estado'])
        self.client.force_login(self.tutor)

        response = self.client.post(
            reverse('proponer_fechas_tutoria', args=[self.tutoria.pk]),
            {
                'propuesta_1': '2030-01-15T11:30',
                'propuesta_2': '',
                'es_reagendacion': '1',
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=agendadas&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertEqual(
            self.tutoria.fecha,
            timezone.make_aware(datetime(2030, 1, 15, 11, 30)),
        )
        self.assertIsNone(self.tutoria.fecha_propuesta_1)
        self.assertIsNone(self.tutoria.fecha_propuesta_2)
        self.assertFalse(self.tutoria.reagendacion_pendiente)

    def test_alumno_elige_reagenda_y_limpia_la_marca(self):
        self.tutoria.estado = PROPUESTA
        self.tutoria.reagendacion_pendiente = True
        self.tutoria.fecha_propuesta_1 = timezone.make_aware(datetime(2030, 1, 15, 11, 30))
        self.tutoria.fecha_propuesta_2 = timezone.make_aware(datetime(2030, 1, 16, 12, 0))
        self.tutoria.save()
        self.client.force_login(self.alumno)

        self.client.post(
            reverse('seleccionar_propuesta_tutoria', args=[self.tutoria.pk]),
            {'opcion_elegida': '2'},
        )

        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertFalse(self.tutoria.reagendacion_pendiente)

class MotivosRechazoTutoriaTests(TestCase):
    """Pruebas del registro del motivo al rechazar una tutoría."""

    def setUp(self):
        self.tutor = Tutor.objects.create_user(
            first_name='Antonio',
            last_name='López',
            email='tutor.rechazo@cua.uam.mx',
            matricula='123458',
            password='password123',
            es_tutor=True,
        )
        self.otro_tutor = Tutor.objects.create_user(
            first_name='Otro',
            last_name='Tutor',
            email='otro.tutor.rechazo@cua.uam.mx',
            matricula='123459',
            password='password123',
            es_tutor=True,
        )
        self.alumno = Alumno.objects.create_user(
            first_name='Estudiante',
            last_name='Gómez',
            email='alumno.rechazo@cua.uam.mx',
            matricula='654323',
            password='password123',
            tutor_asignado=self.tutor,
        )
        self.tutoria = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=['BEC'],
            fecha=timezone.make_aware(datetime(2030, 1, 10, 10, 0)),
            estado=PENDIENTE,
        )
        self.url = reverse('rechazar_tutoria', args=[self.tutoria.pk])

    def test_rechazo_con_motivo_predefinido(self):
        self.client.force_login(self.tutor)
        motivo = 'FUERA_AMBITO'
        descripcion = 'El tema está fuera de mi ámbito de atención.'

        response = self.client.post(
            self.url,
            {'motivo_rechazo': motivo},
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=historial&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, RECHAZADO)
        self.assertEqual(self.tutoria.motivo_rechazo, motivo)
        self.assertFalse(self.tutoria.detalle_motivo_rechazo)
        self.assertEqual(self.tutoria.motivo_rechazo_legible, descripcion)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(f"Motivo: {descripcion}", mail.outbox[0].body)
        self.assertNotIn(motivo, mail.outbox[0].body)

    def test_rechazo_con_otro_motivo_guarda_el_texto_escrito(self):
        self.client.force_login(self.tutor)
        motivo_personalizado = (
            'La solicitud requiere una revisión previa por parte de la '
            'coordinación.'
        )

        response = self.client.post(
            self.url,
            {
                'motivo_rechazo': MOTIVO_RECHAZO_OTRO,
                'motivo_rechazo_otro': motivo_personalizado,
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=historial&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, RECHAZADO)
        self.assertEqual(self.tutoria.motivo_rechazo, MOTIVO_RECHAZO_OTRO)
        self.assertEqual(
            self.tutoria.detalle_motivo_rechazo,
            motivo_personalizado,
        )
        self.assertEqual(
            self.tutoria.motivo_rechazo_legible,
            motivo_personalizado,
        )

    def test_rechazo_sin_motivo_no_modifica_la_tutoria(self):
        self.client.force_login(self.tutor)

        response = self.client.post(self.url, {})

        self.assertRedirects(
            response,
            reverse('Panel-tutorias-tutor'),
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)
        self.assertFalse(self.tutoria.motivo_rechazo)
        mensajes = list(response.wsgi_request._messages)
        self.assertEqual(len(mensajes), 1)
        self.assertIn(
            'Debes seleccionar un motivo de rechazo válido',
            str(mensajes[0]),
        )

    def test_rechazo_con_opcion_otro_vacia_no_modifica_la_tutoria(self):
        self.client.force_login(self.tutor)

        self.client.post(
            self.url,
            {
                'motivo_rechazo': MOTIVO_RECHAZO_OTRO,
                'motivo_rechazo_otro': '   ',
            },
        )

        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)
        self.assertFalse(self.tutoria.motivo_rechazo)

    def test_otro_tutor_no_puede_rechazar_la_tutoria(self):
        self.client.force_login(self.otro_tutor)

        response = self.client.post(
            self.url,
            {'motivo_rechazo': 'Motivo no autorizado'},
        )

        self.assertEqual(response.status_code, 403)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)
        self.assertFalse(self.tutoria.motivo_rechazo)


class CancelarTutoriaTests(TestCase):
    """Pruebas de la cancelación de tutorías."""

    def setUp(self):
        self.tutor = Tutor.objects.create_user(
            first_name="Tutor",
            last_name="Cancelación",
            email="tutor.cancelacion@cua.uam.mx",
            matricula="T30001",
            password="password123",
            es_tutor=True,
        )
        self.otro_tutor = Tutor.objects.create_user(
            first_name="Otro",
            last_name="Tutor",
            email="otro.tutor.cancelacion@cua.uam.mx",
            matricula="T30002",
            password="password123",
            es_tutor=True,
        )
        self.alumno = Alumno.objects.create_user(
            first_name="Alumno",
            last_name="Cancelación",
            email="alumno.cancelacion@cua.uam.mx",
            matricula="A30001",
            password="password123",
            tutor_asignado=self.tutor,
        )
        self.tutoria = Tutoria.objects.create(
            tutor=self.tutor,
            alumno=self.alumno,
            tema=["BEC"],
            descripcion="Solicitud vencida",
            fecha=timezone.now() - timedelta(days=1),
            estado=PENDIENTE,
        )
        self.url = reverse("cancelar-tutoria", args=[self.tutoria.pk])

    def test_tutor_propietario_no_puede_cancelar_tutoria_vencida(self):
        self.client.force_login(self.tutor)

        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse("Panel-tutorias-tutor"),
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)

    def test_otro_tutor_no_puede_cancelar_la_tutoria(self):
        self.client.force_login(self.otro_tutor)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)

    def test_no_permite_cancelar_tutoria_que_no_esta_vencida(self):
        self.tutoria.fecha = timezone.now() + timedelta(days=1)
        self.tutoria.save(update_fields=["fecha"])
        self.client.force_login(self.tutor)

        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse("Panel-tutorias-tutor"),
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)

    def test_cancela_agendada_con_motivo_predefinido(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.fecha = timezone.now() + timedelta(days=1)
        self.tutoria.save(update_fields=["estado", "fecha"])
        self.client.force_login(self.tutor)

        response = self.client.post(
            self.url,
            {"motivo_cancelacion": "TUT_ACADE"},
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=historial&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, CANCELADO)
        self.assertEqual(
            self.tutoria.motivo_cancelacion,
            "TUT_ACADE",
        )

    def test_cancela_agendada_con_otro_motivo(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.fecha = timezone.now() + timedelta(days=1)
        self.tutoria.save(update_fields=["estado", "fecha"])
        self.client.force_login(self.tutor)

        response = self.client.post(
            self.url,
            {
                "motivo_cancelacion": "TUT_OTRO",
                "detalle_motivo_cancelacion": "Actividad institucional urgente",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=historial&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, CANCELADO)
        self.assertEqual(
            self.tutoria.detalle_motivo_cancelacion,
            "Actividad institucional urgente",
        )

    def test_agendada_sin_motivo_no_se_cancela(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.fecha = timezone.now() + timedelta(days=1)
        self.tutoria.save(update_fields=["estado", "fecha"])
        self.client.force_login(self.tutor)

        response = self.client.post(self.url, {})

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=agendadas",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertFalse(self.tutoria.motivo_cancelacion)

    def test_otro_sin_detalle_no_cancela_la_tutoria(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.fecha = timezone.now() + timedelta(days=1)
        self.tutoria.save(update_fields=["estado", "fecha"])
        self.client.force_login(self.tutor)

        self.client.post(
            self.url,
            {"motivo_cancelacion": "TUT_OTRO"},
        )

        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertFalse(self.tutoria.motivo_cancelacion)

    def test_alumno_no_puede_usar_un_codigo_reservado_al_tutor(self):
        self.tutoria.fecha = timezone.now() + timedelta(days=1)
        self.tutoria.save(update_fields=["fecha"])
        self.client.force_login(self.alumno)

        self.client.post(
            self.url,
            {"motivo_cancelacion": "TUT_ACADE"},
        )

        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)
        self.assertFalse(self.tutoria.motivo_cancelacion)

    def test_alumno_cancela_solicitud_pendiente_con_motivo(self):
        self.tutoria.fecha = timezone.now() + timedelta(days=1)
        self.tutoria.save(update_fields=["fecha"])
        self.client.force_login(self.alumno)

        response = self.client.post(
            self.url,
            {"motivo_cancelacion": "ALU_RESOL"},
        )

        self.assertRedirects(
            response,
            f"{reverse('Tutorias-alumno')}?tab=historial&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, CANCELADO)
        self.assertEqual(self.tutoria.origen_cancelacion, "ALUMNO")
        self.assertEqual(self.tutoria.cancelado_por_id, self.alumno.pk)
        self.assertEqual(
            self.tutoria.motivo_cancelacion,
            "ALU_RESOL",
        )

    def test_alumno_cancela_tutoria_agendada_con_otro_motivo(self):
        self.tutoria.estado = ACEPTADO
        self.tutoria.fecha = timezone.now() + timedelta(days=1)
        self.tutoria.save(update_fields=["estado", "fecha"])
        self.client.force_login(self.alumno)

        self.client.post(
            self.url,
            {
                "motivo_cancelacion": "ALU_OTRO",
                "detalle_motivo_cancelacion": "Ya no podré asistir ese día",
            },
        )

        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, CANCELADO)
        self.assertEqual(
            self.tutoria.detalle_motivo_cancelacion,
            "Ya no podré asistir ese día",
        )

    def test_otro_alumno_no_puede_cancelar_la_tutoria(self):
        otro_alumno = Alumno.objects.create_user(
            first_name="Otro",
            last_name="Alumno",
            email="otro.alumno.cancelacion@cua.uam.mx",
            matricula="A30002",
            password="password123",
            tutor_asignado=self.tutor,
        )
        self.client.force_login(otro_alumno)

        response = self.client.post(
            self.url,
            {"motivo_cancelacion": "ALU_PERSO"},
        )

        self.assertEqual(response.status_code, 403)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, PENDIENTE)


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

        self.assertRedirects(
            response,
            f"{reverse('Panel-tutorias-tutor')}?tab=agendadas&highlight={self.tutoria.pk}",
            fetch_redirect_response=False,
        )
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, ACEPTADO)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.alumno,
                verb="aceptó tu solicitud de tutoría",
                description="Solicitud de tutoría aceptada",
            ).count(),
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

    def test_editar_fecha_guarda_el_cambio(self):
        self.client.force_login(self.tutor)
        nueva_fecha = '2030-01-01T10:30'

        response = self.client.post(
            reverse('Tutorias-update', args=[self.tutoria.pk]),
            {
                'tema': [self.tema_codigo],
                'fecha': nueva_fecha,
                'descripcion': 'Se agenda cita',
                'fecha_sugerida': nueva_fecha,
            },
        )

        self.assertEqual(response.status_code, 302)

    def test_guardar_seguimiento_registra_el_informe(self):
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
                'fecha_sugerida': '2030-01-01T10:30',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.tutoria.refresh_from_db()
        self.assertEqual(self.tutoria.estado, RECHAZADO)
        last_history = HistorialCambioTutoria.objects.filter(tutoria=self.tutoria).order_by('-fecha_cambio').first()
        self.assertIsNotNone(last_history)
        self.assertIn("Estado de la tutoría", last_history.cambios_realizados)
        self.assertIn("Aceptada", last_history.cambios_realizados)
        self.assertIn("Rechazada", last_history.cambios_realizados)


class CanalesNotificacionTutoriaTests(TestCase):
    """Verifica cada canal sin contactar servicios externos."""

    def setUp(self):
        self.tutor = Tutor.objects.create(
            matricula="NT1001",
            email="tutor.canales@example.com",
            password="x",
            first_name="Tutor",
            last_name="Canales",
            cubiculo=1,
            coordinacion="COM",
            sexo="M",
            notificaciones_habilitadas=True,
        )
        self.alumno = Alumno.objects.create(
            matricula="NA1001",
            email="alumno.canales@example.com",
            password="x",
            first_name="Alumno",
            last_name="Canales",
            carrera="COM",
            estado=1,
            tutor_asignado=self.tutor,
        )
        self.tutoria = Tutoria.objects.create(
            alumno=self.alumno,
            tutor=self.tutor,
            tema=["BEC"],
            fecha=timezone.now() + timedelta(days=1),
            descripcion="Prueba de los tres canales",
            estado=PENDIENTE,
        )

    def crear_dispositivo_push(self):
        subscription = SubscriptionInfo.objects.create(
            endpoint="https://fcm.googleapis.com/push/test",
            p256dh="p256dh-test",
            auth="auth-test",
            browser="Chrome",
        )
        PushInformation.objects.create(user=self.tutor, subscription=subscription)
        return PushDevice.objects.create(
            user=self.tutor,
            subscription=subscription,
            status=PushDevice.Status.ACTIVE,
            browser="Chrome",
            operating_system="Linux",
            device_name="Chrome · Linux",
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        TUTORIAS_SITE_URL="https://tutorias.test",
    )
    def test_correo_incluye_destinatario_html_y_url_de_accion(self):
        notify_tutoria_event(
            event=EventoTutoria.ALU_SOLICITA_TUTORIA,
            tutoria=self.tutoria,
            actor=self.alumno,
        )

        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, [self.tutor.email])
        self.assertEqual(correo.subject, "Nueva solicitud de tutoría")
        self.assertTrue(correo.alternatives)
        html = correo.alternatives[0][0]
        self.assertIn("Revisar solicitud", html)
        self.assertIn(
            "https://tutorias.test/panel-tutorias-tutor/"
            f"?tab=solicitadas&amp;highlight={self.tutoria.pk}",
            html,
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        TUTORIAS_SITE_URL="https://tutorias.test",
    )
    def test_confirmacion_incluye_calendarios_para_el_alumno(self):
        notify_tutoria_event(
            event=EventoTutoria.TUT_ACEPTA_SOLICITUD,
            tutoria=self.tutoria,
            actor=self.tutor,
        )

        correo = mail.outbox[0]
        self.assertEqual(correo.to, [self.alumno.email])
        html = correo.alternatives[0][0]
        self.assertIn("Google Calendar", html)
        self.assertIn("Apple Calendar", html)
        self.assertIn("Tutor%C3%ADa+con+Tutor+Canales", html)
        self.assertIn(
            f"https://tutorias.test{reverse('descargar_ics', kwargs={'tutoria_id': self.tutoria.pk})}",
            html,
        )

    def test_ics_personaliza_el_titulo_segun_el_usuario(self):
        self.client.force_login(self.alumno)
        response = self.client.get(
            reverse("descargar_ics", kwargs={"tutoria_id": self.tutoria.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("SUMMARY:Tutoría con Tutor Canales", response.content.decode())

        self.client.force_login(self.tutor)
        response = self.client.get(
            reverse("descargar_ics", kwargs={"tutoria_id": self.tutoria.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("SUMMARY:Tutoría con Alumno Canales", response.content.decode())

    def test_campana_usa_el_contrato_del_evento_actual(self):
        handle_inapp_notifications(
            sender=self.__class__,
            event=EventoTutoria.ALU_SOLICITA_TUTORIA,
            tutoria=self.tutoria,
            actor=self.alumno,
            recipient=self.tutor,
        )

        notificacion = Notification.objects.get(recipient=self.tutor)
        self.assertEqual(notificacion.actor, self.alumno)
        self.assertEqual(notificacion.verb, "solicitó una tutoría")
        self.assertEqual(notificacion.description, "Nueva solicitud de tutoría")

    @patch("Tutorias.signals.handle_push_notifications.webpush")
    def test_push_envia_payload_y_url_relativa(self, webpush_mock):
        self.crear_dispositivo_push()
        webpush_mock.return_value = Mock(status_code=201)

        _enviar_notificacion_push(
            EventoTutoria.ALU_SOLICITA_TUTORIA,
            self.tutoria,
            self.alumno,
        )

        webpush_mock.assert_called_once()
        payload = json.loads(webpush_mock.call_args.kwargs["data"])
        self.assertEqual(payload["head"], "🙏 Nueva solicitud de tutoría")
        self.assertEqual(
            payload["url"],
            f"{reverse('Panel-tutorias-tutor')}?tab=solicitadas"
            f"&highlight={self.tutoria.pk}",
        )

    @patch("Tutorias.signals.handle_push_notifications.webpush")
    def test_error_de_conexion_push_no_interrumpe_la_operacion(self, webpush_mock):
        self.crear_dispositivo_push()
        webpush_mock.side_effect = RequestsConnectionError(
            "Temporary failure in name resolution"
        )

        _enviar_notificacion_push(
            EventoTutoria.ALU_SOLICITA_TUTORIA,
            self.tutoria,
            self.alumno,
        )

        webpush_mock.assert_called_once()

    @patch("Tutorias.signals.handle_push_notifications.webpush")
    def test_push_elimina_suscripcion_expirada(self, webpush_mock):
        device = self.crear_dispositivo_push()
        webpush_mock.side_effect = WebPushException(
            "Suscripción expirada",
            response=Mock(status_code=410),
        )

        _enviar_notificacion_push(
            EventoTutoria.ALU_SOLICITA_TUTORIA,
            self.tutoria,
            self.alumno,
        )

        self.assertFalse(PushDevice.objects.filter(pk=device.pk).exists())

    @patch("Tutorias.signals.handle_push_notifications.webpush")
    def test_preferencia_global_desactivada_evitar_envio_push(self, webpush_mock):
        self.crear_dispositivo_push()
        self.tutor.notificaciones_habilitadas = False
        self.tutor.save(update_fields=["notificaciones_habilitadas"])

        _enviar_notificacion_push(
            EventoTutoria.ALU_SOLICITA_TUTORIA,
            self.tutoria,
            self.alumno,
        )

        webpush_mock.assert_not_called()

    @patch("Tutorias.signals.handle_push_notifications.webpush")
    def test_dispositivo_pausado_no_recibe_push(self, webpush_mock):
        device = self.crear_dispositivo_push()
        device.status = PushDevice.Status.PAUSED
        device.save(update_fields=["status"])

        _enviar_notificacion_push(
            EventoTutoria.ALU_SOLICITA_TUTORIA,
            self.tutoria,
            self.alumno,
        )

        webpush_mock.assert_not_called()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        TUTORIAS_SITE_URL="https://tutorias.test",
    )
    @patch("Tutorias.signals.handle_push_notifications._enviar_notificacion_push")
    def test_una_senal_activa_los_tres_canales(self, push_mock):
        tutoria_notification_requested.send(
            sender=self.__class__,
            event=EventoTutoria.ALU_SOLICITA_TUTORIA,
            tutoria=self.tutoria,
            actor=self.alumno,
            recipient=self.tutor,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.tutor,
                verb="solicitó una tutoría",
            ).exists()
        )
        push_mock.assert_called_once_with(
            event=EventoTutoria.ALU_SOLICITA_TUTORIA,
            tutoria=self.tutoria,
            actor=self.alumno,
        )


class ConfiguracionCanalesNotificacionTests(SimpleTestCase):
    def test_acciones_de_calendario_solo_aparecen_en_fechas_confirmadas(self):
        eventos_con_calendario = {
            EventoTutoria.ALU_AGENDA_TUTORIA,
            EventoTutoria.TUT_ACEPTA_SOLICITUD,
            EventoTutoria.TUT_PROPONE_1_FECHA,
            EventoTutoria.ALU_SOL_CAMBIO_FECHA_AGEN,
            EventoTutoria.TUT_REAGENDA_1_FECHA,
            EventoTutoria.ALU_ELIGE_FECHA_PROPUESTA,
            EventoTutoria.TUT_REACTIVA_1_FECHA,
        }

        self.assertEqual(
            {
                event for event, config in EMAIL_EVENT_CONFIG.items()
                if config.get("show_calendar_actions")
            },
            eventos_con_calendario,
        )

    def test_configuraciones_solo_contienen_eventos_y_roles_validos(self):
        eventos = set(EventoTutoria.values)
        roles = {"alumno", "tutor"}

        for config in (EMAIL_EVENT_CONFIG, SYSTEM_NOTIFICATION_INFO, PUSH_EVENT_INFO):
            self.assertTrue(set(config).issubset(eventos))

        for event, config in EMAIL_EVENT_CONFIG.items():
            self.assertIn("template", config, event)
            self.assertIn("subject", config, event)
            self.assertTrue(set(config["recipients"]).issubset(roles), event)

        for event, config in SYSTEM_NOTIFICATION_INFO.items():
            self.assertTrue(config["verb"], event)
            self.assertTrue(config["description"], event)

        for event, config in PUSH_EVENT_INFO.items():
            recipients = set(config["recipients"])
            self.assertTrue(recipients.issubset(roles), event)
            self.assertEqual(set(config["url"]), recipients, event)
            for url_name, tab in config["url"].values():
                self.assertIn(tab, {None, "solicitadas", "agendadas", "historial"})
                reverse(url_name)


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
