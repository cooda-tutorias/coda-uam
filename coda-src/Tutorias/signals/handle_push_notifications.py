# ==========================================
# 3. SUSCRIPTOR: NOTIFICACIONES PUSH
# ==========================================

import logging
import json
from django.conf import settings
from typing import Any

from django.dispatch import receiver
from urllib.parse import urlencode, urlparse
from pywebpush import webpush, WebPushException
from requests.exceptions import RequestException

from django.urls import reverse
from Usuarios.models import PushDevice

from .signals_definitions import tutoria_notification_requested
from .events import EventoTutoria
from ..constants import (
    ACEPTADO,
    CANCELADO,
    PENDIENTE,
    PROPUESTA,
    REALIZADA,
    RECHAZADO,
    REPORTADA,
    VENCIDA,
)

logger = logging.getLogger(__name__)


# Información para construir y dirigir las notificaciones push de cada evento.
# ``recipients`` contiene nombres de relaciones de Tutoria (alumno/tutor).
PUSH_EVENT_INFO: dict[EventoTutoria, dict[str, object]] = {
    EventoTutoria.ALU_AGENDA_POR_QR: {
        "recipients": ("tutor",),
        "head": "📱 Tutoría registrada por QR",
        "body": "{actor} registró una tutoría contigo mediante código QR.",
        "url": {"tutor": ("Panel-tutorias-tutor", "agendadas")},
    },
    EventoTutoria.ALU_SOLICITA_TUTORIA: {
        "recipients": ("tutor",),
        "head": "🙏 Nueva solicitud de tutoría",
        "body": "{actor} solicitó una tutoría y sugirió una fecha.",
        "url": {"tutor": ("Panel-tutorias-tutor", "solicitadas")},
    },
    EventoTutoria.ALU_AGENDA_TUTORIA: {
        "recipients": ("tutor",),
        "head": "📅 Nueva tutoría agendada",
        "body": "{actor} eligió uno de tus horarios disponibles.",
        "url": {"tutor": ("Panel-tutorias-tutor", "agendadas")},
    },
    EventoTutoria.TUT_ACEPTA_SOLICITUD: {
        "recipients": ("alumno",),
        "head": "✅ Solicitud aceptada",
        "body": "{actor} aceptó la fecha que propusiste.",
        "url": {"alumno": ("Tutorias-alumno", "agendadas")},
    },
    EventoTutoria.TUT_PROPONE_1_FECHA: {
        "recipients": ("alumno",),
        "head": "📅 Tutoría agendada",
        "body": "{actor} agendó tu tutoría en una nueva fecha.",
        "url": {"alumno": ("Tutorias-alumno", "agendadas")},
    },
    EventoTutoria.TUT_PROPONE_2_FECHAS: {
        "recipients": ("alumno",),
        "head": "📅 Elige una fecha",
        "body": "{actor} propuso dos opciones para tu tutoría.",
        "url": {"alumno": ("Tutorias-alumno", "solicitadas")},
    },
    EventoTutoria.TUT_REACTIVA_1_FECHA: {
        "recipients": ("alumno",),
        "head": "🔄 Solicitud reactivada",
        "body": "{actor} reactivó tu solicitud y asignó una nueva fecha.",
        "url": {"alumno": ("Tutorias-alumno", "agendadas")},
    },
    EventoTutoria.TUT_REACTIVA_2_FECHAS: {
        "recipients": ("alumno",),
        "head": "🔄 Solicitud reactivada",
        "body": "{actor} propuso nuevas fechas; elige una opción.",
        "url": {"alumno": ("Tutorias-alumno", "solicitadas")},
    },
    EventoTutoria.TUT_RECHAZA_SOLICITUD: {
        "recipients": ("alumno",),
        "head": "⚠️ Solicitud rechazada",
        "body": "{actor} no pudo aceptar tu solicitud de tutoría.",
        "url": {"alumno": ("Tutorias-alumno", "historial")},
    },
    EventoTutoria.ALU_SOL_CAMBIO_FECHA_SUG: {
        "recipients": ("tutor",),
        "head": "🔄 Cambio de fecha solicitado",
        "body": "{actor} sugirió otra fecha para la tutoría.",
        "url": {"tutor": ("Panel-tutorias-tutor", "solicitadas")},
    },
    EventoTutoria.ALU_SOL_CAMBIO_FECHA_AGEN: {
        "recipients": ("tutor",),
        "head": "📅 Tutoría reagendada",
        "body": "{actor} eligió otro de tus horarios disponibles.",
        "url": {"tutor": ("Panel-tutorias-tutor", "agendadas")},
    },
    EventoTutoria.ALU_CANCELA_SOLICITUD: {
        "recipients": ("tutor",),
        "head": "❌ Solicitud cancelada",
        "body": "{actor} canceló su solicitud de tutoría.",
        "url": {"tutor": ("Panel-tutorias-tutor", "historial")},
    },
    EventoTutoria.TUTORIA_VENCIDA: {
        "recipients": ("alumno", "tutor"),
        "head": "⏰ Solicitud vencida",
        "body": "La solicitud de tutoría venció sin una respuesta.",
        "url": {
            "alumno": ("Tutorias-alumno", "solicitadas"),
            "tutor": ("Panel-tutorias-tutor", "solicitadas"),
        },
    },
    EventoTutoria.ALU_CANCELA_AGENDADA: {
        "recipients": ("tutor",),
        "head": "❌ Tutoría cancelada",
        "body": "{actor} canceló la tutoría agendada.",
        "url": {"tutor": ("Panel-tutorias-tutor", "historial")},
    },
    EventoTutoria.TUT_CANCELA_AGENDADA: {
        "recipients": ("alumno",),
        "head": "❌ Tutoría cancelada",
        "body": "{actor} canceló la tutoría agendada.",
        "url": {"alumno": ("Tutorias-alumno", "historial")},
    },
    EventoTutoria.TUT_REAGENDA_1_FECHA: {
        "recipients": ("alumno",),
        "head": "📅 Tutoría reagendada",
        "body": "{actor} confirmó una nueva fecha para tu tutoría.",
        "url": {"alumno": ("Tutorias-alumno", "agendadas")},
    },
    EventoTutoria.TUT_REAGENDA_2_FECHAS: {
        "recipients": ("alumno",),
        "head": "📅 Elige una nueva fecha",
        "body": "{actor} propuso opciones para reagendar tu tutoría.",
        "url": {"alumno": ("Tutorias-alumno", "solicitadas")},
    },
    EventoTutoria.ALU_ELIGE_FECHA_PROPUESTA: {
        "recipients": ("tutor",),
        "head": "✅ Fecha confirmada",
        "body": "{actor} eligió una de las fechas que propusiste.",
        "url": {"tutor": ("Panel-tutorias-tutor", "agendadas")},
    },
    EventoTutoria.PROPUESTA_FECHAS_CANCELADA: {
        "recipients": ("alumno", "tutor"),
        "head": "⏰ Propuesta vencida",
        "body": "La propuesta se canceló porque no se eligió una fecha.",
        "url": {
            "alumno": ("Tutorias-alumno", "historial"),
            "tutor": ("Panel-tutorias-tutor", "historial"),
        },
    },
    EventoTutoria.TUTORIA_VENCIDA_CANCELADA: {
        "recipients": ("alumno", "tutor"),
        "head": "❌ Solicitud cancelada",
        "body": "La solicitud se canceló automáticamente por vencimiento.",
        "url": {
            "alumno": ("Tutorias-alumno", "historial"),
            "tutor": ("Panel-tutorias-tutor", "historial"),
        },
    },
    EventoTutoria.ALU_EDITA_INFO_TUTORIA: {
        "recipients": ("tutor",),
        "head": "📝 Tutoría actualizada",
        "body": "{actor} actualizó los detalles de la tutoría.",
        # La pestaña depende del estado que conserve la tutoría editada.
        "url": {"tutor": ("Panel-tutorias-tutor", None)},
    },
}

def _nombre_actor(actor: Any) -> str:
    return getattr(actor, "nombre_completo", None) or "Sistema CODDAA"


def _pestana_por_estado(tutoria: Any) -> str:
    """Devuelve la pestaña que contiene actualmente la tutoría."""
    estado = tutoria.estado_efectivo
    if estado in (PENDIENTE, PROPUESTA, VENCIDA):
        return "solicitadas"
    if estado == ACEPTADO:
        return "agendadas"
    if estado in (REALIZADA, REPORTADA, RECHAZADO, CANCELADO):
        return "historial"
    return "solicitadas"


def _url_para_destinatario(info_noti: dict[str, object], role: str, tutoria: Any) -> str:
    """Construye la URL del panel y pestaña configurados para el rol."""
    url_name, tab = info_noti["url"][role]
    tab = tab or _pestana_por_estado(tutoria)
    return f"{reverse(url_name)}?{urlencode({'tab': tab, 'highlight': tutoria.pk})}"


def _deliver_push(device, payload, *, ttl=1000):
    """Envía a un dispositivo sin permitir que el canal push rompa la operación."""
    subscription = device.subscription
    parsed = urlparse(subscription.endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"

    try:
        response = webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth,
                },
            },
            data=json.dumps(payload),
            vapid_private_key=settings.WEBPUSH_SETTINGS["VAPID_PRIVATE_KEY"],
            vapid_claims={
                "sub": settings.WEBPUSH_SETTINGS["VAPID_ADMIN_EMAIL"],
                "aud": audience,
            },
            ttl=ttl,
        )
        logger.info(
            "Push aceptada para usuario=%s dispositivo=%s status=%s servicio=%s",
            device.user_id,
            device.pk,
            response.status_code,
            parsed.netloc,
        )
        return True, "Notificación enviada."
    except WebPushException as error:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        if status_code in (404, 410):
            logger.info(
                "Se eliminó la suscripción inválida %s del usuario %s (HTTP %s)",
                device.pk,
                device.user_id,
                status_code,
            )
            subscription.delete()
            return False, "La suscripción ya no era válida y fue eliminada."
        logger.warning(
            "El servicio push rechazó el dispositivo %s del usuario %s: %s",
            device.pk,
            device.user_id,
            error,
        )
        return False, "El servicio de notificaciones rechazó el envío."
    except RequestException as error:
        logger.warning(
            "No se pudo contactar %s para el dispositivo %s del usuario %s: %s",
            parsed.netloc,
            device.pk,
            device.user_id,
            error,
        )
        return False, "No fue posible contactar el servicio de notificaciones."
    except Exception:
        logger.exception(
            "Error inesperado enviando push al dispositivo %s del usuario %s",
            device.pk,
            device.user_id,
        )
        return False, "Ocurrió un error inesperado al enviar la notificación."


def send_test_push(device):
    return _deliver_push(
        device,
        {
            "head": "🔔 Notificación de prueba",
            "body": "Las notificaciones están funcionando correctamente en este dispositivo.",
            "icon": "/static/img/icon-v2.png",
            "badge": "/static/img/badge-v5.png",
            "url": reverse("configuracion_app"),
        },
    )


def _enviar_notificacion_push(event, tutoria, actor=None):
    """
    Envía la notificación push para el tutor o el alumno según el tipo
    de evento del sistema de tutorías.
    """

    info_noti = PUSH_EVENT_INFO.get(event)

    nombre_emisor = _nombre_actor(actor)

    # Confeccionamos la información que llevará la notificación.
    encabezado   = info_noti["head"]
    cuerpo_texto = info_noti["body"].format(actor=nombre_emisor)

    payload = {
        "head": encabezado,
        "body": cuerpo_texto,
        "icon": "/static/img/icon-v2.png",
        "badge": "/static/img/badge-v5.png",
        "url": None, 
    }

    # Enviamos la notificación para cada destinatario en la lista designada.
    for role in info_noti["recipients"]:

        # Obtenemos el objeto destinatario de la notificación.
        destinatario = getattr(tutoria, role, None)

        if destinatario is None:
            logger.warning(
                "La tutoría %s no tiene destinatario para el rol %s",
                tutoria.pk,
                role,
            )
            continue

        if not destinatario.notificaciones_habilitadas:
            logger.info(
                "El usuario %s desactivó globalmente las notificaciones push",
                destinatario.pk,
            )
            continue

        payload["url"] = _url_para_destinatario(info_noti, role, tutoria)

        devices = list(
            PushDevice.objects.filter(
                user_id=destinatario.pk,
                status=PushDevice.Status.ACTIVE,
            ).select_related("subscription")
        )
        logger.info(
            "Procesando push evento=%s tutoria=%s destinatario=%s dispositivos=%s",
            event,
            tutoria.pk,
            destinatario.pk,
            len(devices),
        )
        for device in devices:
            _deliver_push(device, payload)

        # =========================
        # CHROME / ANDROID (FCM)
        # =========================
        ## send_user_notification de django-webpush solamente funciona para
        ## Chrome (PC/Android) y Firefox, pero NO funciona para Safari.
        ## Comentaré este código como advertencia para recordar por qué
        ## no es buena idea usar django-webpush para enviar.
        ## El registro de las notificaciones sí funciona con django-webpush en 
        ## cualquier caso, así que el registro sí se quedó con django-webpush:
        ## Vista PushSubscriptionView en views.py de la app 'Usuarios'.
        # try:
        #     print("DEBUG PUSH: Enviando push vía django-webpush (Chrome)")
        #     send_user_notification(user=usuario, payload=payload, ttl=1000)
        # except Exception as e:
        #     # Esto es importante para que un fallo en la push notification no detenga la solicitud
        #     print(f"DEBUG PUSH: Falló la notificación vía django-webpush para {tutor.nombre_completo}: {e}")


@receiver(tutoria_notification_requested, dispatch_uid="Tutorias.push_listener")
def handle_push_notifications(sender, event=None, tutoria=None, actor=None, **kwargs):

    if event not in PUSH_EVENT_INFO or tutoria is None:
        return
    
    _enviar_notificacion_push(event=event, tutoria=tutoria, actor=actor)
