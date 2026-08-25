# ==========================================
# 3. SUSCRIPTOR: NOTIFICACIONES PUSH
# ==========================================

import logging
import json
from django.conf import settings
from typing import Any

from django.dispatch import receiver
from webpush.models import PushInformation
from urllib.parse import urlencode, urlparse
from pywebpush import webpush, WebPushException

from django.urls import reverse

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
    return f"{reverse(url_name)}?{urlencode({'tab': tab})}"


#def _enviar_notificacion_push(tutor, alumno, alumno_sugirio, encabezado):
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
        "icon": "/static/img/icon.png",
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

        payload["url"] = _url_para_destinatario(info_noti, role, tutoria)

        logger.info("==== La URL es %s", payload["url"])

        # Obtener todas las suscripciones que tenga el tutor (Chrome, Firefox, Safari, etc.)
        push_infos = PushInformation.objects.filter(user=destinatario)

        # Para cada suscripción del tutor hacemos el envío de la notificación push.
        for push_info in push_infos:
            sub = push_info.subscription
            endpoint = sub.endpoint

            # Analizar el endpoint para obtener el 'aud' correcto según el servicio (Safari o FCM)
            parsed = urlparse(endpoint)
            aud = f"{parsed.scheme}://{parsed.netloc}"
            
            # if "web.push.apple.com" in endpoint:
            #     aud = "https://web.push.apple.com"
            # else:
            #     aud = "https://fcm.googleapis.com"

            try:
                #print("DEBUG PUSH endpoint:", endpoint)

                logger.info(
                    "====>> Procesando push evento=%s tutoria=%s destinatario=%s suscripciones=%s",
                    event,
                    tutoria.pk,
                    destinatario.pk,
                    push_infos.count(),
                )

                # Aquí enviamos la notificación para la suscripción 'sub' de la iteración actual.
                respuesta = webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {
                            "p256dh": sub.p256dh,
                            "auth": sub.auth,
                        }
                    },
                    data = json.dumps(payload),
                    vapid_private_key = settings.WEBPUSH_SETTINGS["VAPID_PRIVATE_KEY"],
                    vapid_claims = {
                        "sub": settings.WEBPUSH_SETTINGS["VAPID_ADMIN_EMAIL"],
                        "aud": aud, # Este campo es importante para Safari.
                    },
                    ttl=1000
                )

                logger.info(
                    "<<== Push aceptada para usuario=%s status=%s servicio=%s",
                    destinatario.pk,
                    respuesta.status_code,
                    parsed.netloc,
                )

            except WebPushException as e:
                print("DEBUG PUSH ERROR:", e)

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

