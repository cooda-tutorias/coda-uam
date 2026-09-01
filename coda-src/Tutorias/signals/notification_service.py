"""Construcción y envío de correos para eventos del ciclo de una tutoría."""

import logging
import re
from threading import Thread
from typing import Any, Optional
from urllib.parse import urlencode, urljoin

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .events import EventoTutoria

logger = logging.getLogger(__name__)

ACTION_TEMPLATE = "correos/tutoria_accion_requerida.html"
CONFIRMATION_TEMPLATE = "correos/tutoria_confirmacion.html"
ADVERSE_TEMPLATE = "correos/tutoria_estado_adverso.html"


# La variación pertenece a la configuración, no a condicionales en HTML.
# Los diccionarios por rol personalizan los eventos enviados a ambas partes.
EMAIL_EVENT_CONFIG: dict[str, dict[str, Any]] = {
    EventoTutoria.ALU_AGENDA_POR_QR: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("tutor",),
        "subject": "Tutoría registrada mediante código QR",
        "title": "Se registró una tutoría in situ",
        "message": "El alumno registró una tutoría contigo mediante código QR.",
        "confirmation_type": "agendada", "origin": "qr",
    },
    EventoTutoria.ALU_SOLICITA_TUTORIA: {
        "template": ACTION_TEMPLATE, "recipients": ("tutor",),
        "subject": "Nueva solicitud de tutoría", "title": "Tienes una nueva solicitud",
        "message": "El alumno solicitó una tutoría y sugirió una fecha.",
        "action_type": "responder_solicitud", "action_text": "Revisar solicitud",
        "action_url_name": "Panel-tutorias-tutor", "action_tab": "solicitadas",
    },
    EventoTutoria.ALU_AGENDA_TUTORIA: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("tutor",),
        "subject": "Nueva tutoría agendada", "title": "El alumno agendó una tutoría",
        "message": "El alumno eligió uno de tus horarios disponibles.",
        "confirmation_type": "agendada", "origin": "slot",
        "show_calendar_actions": True,
    },
    EventoTutoria.TUT_ACEPTA_SOLICITUD: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("alumno",),
        "subject": "Tu solicitud de tutoría fue aceptada", "title": "Tutoría confirmada",
        "message": "El tutor aceptó la solicitud con la fecha que sugeriste.",
        "confirmation_type": "aceptada", "origin": "solicitud",
        "show_calendar_actions": True,
    },
    EventoTutoria.TUT_PROPONE_1_FECHA: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("alumno",),
        "subject": "Tu tutoría fue agendada en otra fecha", "title": "Tutoría confirmada",
        "message": "El tutor agendó tu solicitud en una nueva fecha.",
        "confirmation_type": "agendada", "origin": "propuesta",
        "show_calendar_actions": True,
    },
    EventoTutoria.TUT_PROPONE_2_FECHAS: {
        "template": ACTION_TEMPLATE, "recipients": ("alumno",),
        "subject": "Elige una fecha para tu tutoría", "title": "Tu tutor propuso dos fechas",
        "message": "Selecciona la opción que más te convenga para confirmar la tutoría.",
        "action_type": "elegir_fecha", "action_text": "Elegir fecha",
        "action_url_name": "Tutorias-alumno", "action_tab": "solicitadas",
        "show_proposals": True,
    },
    EventoTutoria.TUT_REACTIVA_1_FECHA: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("alumno",),
        "subject": "Tu solicitud de tutoría fue reactivada",
        "title": "Solicitud reactivada y confirmada",
        "message": "El tutor reactivó tu solicitud vencida y asignó una nueva fecha.",
        "confirmation_type": "reactivada", "origin": "reactivacion",
        "show_calendar_actions": True,
    },
    EventoTutoria.TUT_REACTIVA_2_FECHAS: {
        "template": ACTION_TEMPLATE, "recipients": ("alumno",),
        "subject": "Elige una fecha para reactivar tu tutoría", "title": "Tu solicitud fue reactivada",
        "message": "El tutor propuso nuevas fechas para reactivar la solicitud vencida.",
        "action_type": "elegir_fecha", "action_text": "Elegir fecha",
        "action_url_name": "Tutorias-alumno", "action_tab": "solicitadas",
        "show_proposals": True,
    },
    EventoTutoria.TUT_RECHAZA_SOLICITUD: {
        "template": ADVERSE_TEMPLATE, "recipients": ("alumno",),
        "subject": "Tu solicitud de tutoría fue rechazada", "title": "Solicitud rechazada",
        "message": "El tutor no pudo aceptar la solicitud de tutoría.",
        "status_type": "rechazada", "show_rejection_reason": True, "is_final": True,
    },
    EventoTutoria.ALU_SOL_CAMBIO_FECHA_SUG: {
        "template": ACTION_TEMPLATE, "recipients": ("tutor",),
        "subject": "Solicitud de cambio de fecha", "title": "El alumno solicitó cambiar la fecha",
        "message": "Revisa la nueva fecha sugerida y responde la solicitud.",
        "action_type": "responder_cambio_fecha", "action_text": "Revisar solicitud",
        "action_url_name": "Panel-tutorias-tutor", "action_tab": "solicitadas",
    },
    EventoTutoria.ALU_SOL_CAMBIO_FECHA_AGEN: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("tutor",),
        "subject": "Tutoría reagendada por el alumno", "title": "Se actualizó la fecha de una tutoría",
        "message": "El alumno eligió otro de tus horarios disponibles.",
        "confirmation_type": "reagendada", "origin": "slot",
        "show_calendar_actions": True,
    },
    EventoTutoria.ALU_CANCELA_SOLICITUD: {
        "template": ADVERSE_TEMPLATE, "recipients": ("tutor",),
        "subject": "Solicitud de tutoría cancelada", "title": "El alumno canceló la solicitud",
        "message": "La solicitud ya no requiere una respuesta.",
        "status_type": "cancelada", "show_cancellation_reason": True, "is_final": True,
    },
    EventoTutoria.TUTORIA_VENCIDA: {
        "template": ADVERSE_TEMPLATE, "recipients": ("alumno", "tutor"),
        "subject": {"alumno": "Tu solicitud de tutoría venció", "tutor": "Una solicitud de tutoría venció"},
        "title": "Solicitud vencida",
        "message": {
            "alumno": "Pasó la fecha sugerida sin que el tutor registrara una respuesta.",
            "tutor": "Pasó la fecha sugerida por el alumno sin que se registrara una respuesta.",
        },
        "status_type": "vencida", "is_final": False,
        "action_text": {"tutor": "Revisar solicitud"},
        "action_url_name": {"tutor": "Panel-tutorias-tutor"},
        "action_tab": {"tutor": "solicitadas"},
    },
    EventoTutoria.ALU_CANCELA_AGENDADA: {
        "template": ADVERSE_TEMPLATE, "recipients": ("tutor",),
        "subject": "Tutoría cancelada por el alumno", "title": "El alumno canceló la tutoría",
        "message": "La tutoría agendada fue cancelada por el alumno.",
        "status_type": "cancelada", "show_cancellation_reason": True, "is_final": True,
    },
    EventoTutoria.TUT_CANCELA_AGENDADA: {
        "template": ADVERSE_TEMPLATE, "recipients": ("alumno",),
        "subject": "Tu tutoría fue cancelada", "title": "El tutor canceló la tutoría",
        "message": "La tutoría agendada fue cancelada por el tutor.",
        "status_type": "cancelada", "show_cancellation_reason": True, "is_final": True,
    },
    EventoTutoria.TUT_REAGENDA_1_FECHA: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("alumno",),
        "subject": "Tu tutoría fue reagendada", "title": "Nueva fecha confirmada",
        "message": "El tutor reagendó la tutoría en una nueva fecha.",
        "confirmation_type": "reagendada", "origin": "propuesta",
        "show_calendar_actions": True,
    },
    EventoTutoria.TUT_REAGENDA_2_FECHAS: {
        "template": ACTION_TEMPLATE, "recipients": ("alumno",),
        "subject": "Elige una fecha para reagendar tu tutoría", "title": "Tu tutor propuso nuevas fechas",
        "message": "Selecciona una de las opciones para reagendar la tutoría.",
        "action_type": "elegir_fecha", "action_text": "Elegir fecha",
        "action_url_name": "Tutorias-alumno", "action_tab": "solicitadas",
        "show_proposals": True,
    },
    EventoTutoria.TUTORIA_REALIZADA: {
        "template": ACTION_TEMPLATE, "recipients": ("tutor",),
        "subject": "Registra el informe de la tutoría", "title": "La fecha de la tutoría ya pasó",
        "message": "Registra el informe y la asistencia correspondientes a la sesión.",
        "action_type": "registrar_informe", "action_text": "Registrar informe",
        "action_url_name": "Reporte2-create", "action_url_uses_pk": True,
    },
    EventoTutoria.ALU_ELIGE_FECHA_PROPUESTA: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("tutor",),
        "subject": "El alumno confirmó la fecha de tutoría", "title": "Fecha de tutoría confirmada",
        "message": "El alumno eligió una de las fechas que propusiste.",
        "confirmation_type": "fecha_elegida", "origin": "propuesta",
        "show_calendar_actions": True,
    },
    EventoTutoria.PROPUESTA_FECHAS_CANCELADA: {
        "template": ADVERSE_TEMPLATE, "recipients": ("alumno", "tutor"),
        "subject": "Propuesta de fechas cancelada", "title": "Las fechas propuestas vencieron",
        "message": {
            "alumno": "La propuesta fue cancelada porque no se eligió una fecha dentro del plazo.",
            "tutor": "La propuesta fue cancelada porque el alumno no eligió una fecha dentro del plazo.",
        },
        "status_type": "propuesta_vencida", "is_final": True,
    },
    EventoTutoria.TUTORIA_VENCIDA_CANCELADA: {
        "template": ADVERSE_TEMPLATE, "recipients": ("alumno", "tutor"),
        "subject": "Solicitud de tutoría cancelada automáticamente", "title": "La solicitud fue cancelada",
        "message": {
            "alumno": "La solicitud se canceló automáticamente porque no fue atendida dentro del plazo.",
            "tutor": "La solicitud se canceló automáticamente porque no registraste una respuesta dentro del plazo.",
        },
        "status_type": "cancelada", "is_final": True,
    },
    EventoTutoria.TUTORIA_INFORME_REGISTRADO: {
        "template": CONFIRMATION_TEMPLATE, "recipients": ("tutor",),
        "subject": "Informe de tutoría registrado", "title": "El informe se registró correctamente",
        "message": "El sistema guardó el informe de la tutoría.",
        "confirmation_type": "informe_registrado", "origin": "sistema",
    },
}


def _institutional_contact() -> dict[str, str]:
    return {
        "logo_url": getattr(settings, "NOTIFICATIONS_EMAIL_LOGO_URL", ""),
        "address": getattr(settings, "NOTIFICATIONS_UAM_ADDRESS", "Av. Vasco de Quiroga 4871, Santa Fe Cuajimalpa, Cuajimalpa de Morelos, 05348, Ciudad de México, CDMX"),
        "maps_url": getattr(settings, "NOTIFICATIONS_UAM_MAPS_URL", "https://maps.google.com/?q=UAM+Cuajimalpa"),
        "uam_phone": getattr(settings, "NOTIFICATIONS_UAM_PHONE", "(55) 5814 6500"),
        "coddaa_phone": getattr(settings, "NOTIFICATIONS_CODDAA_PHONE", "(55) 5814 6500"),
    }


def _phone_href(phone: str) -> str:
    return re.sub(r"[^\d+]", "", phone or "")


def _format_datetime(value: Any) -> str:
    """Formatea fechas aware y normaliza datos legacy sin zona horaria."""
    if not value:
        return ""

    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())

    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")


def _recipient_emails(recipient: Any) -> list[str]:
    emails: list[str] = []
    for candidate in (getattr(recipient, "email", None), getattr(recipient, "correo_personal", None)):
        if candidate and candidate not in emails:
            emails.append(candidate)
    return emails


def _value_for_role(value: Any, role: str, default: Any = "") -> Any:
    return value.get(role, default) if isinstance(value, dict) else value if value is not None else default


def _absolute_action_url(config: dict[str, Any], role: str, tutoria: Any) -> str:
    url_name = _value_for_role(config.get("action_url_name"), role)
    site_url = settings.TUTORIAS_SITE_URL.strip()
    if not url_name or not site_url:
        return ""
    try:
        path = reverse(url_name, kwargs={"pk": tutoria.pk}) if config.get("action_url_uses_pk") else reverse(url_name)
    except Exception:
        logger.exception("No se pudo construir la URL de acción %s", url_name)
        return ""
    action_tab = _value_for_role(config.get("action_tab"), role)
    if action_tab:
        path = f"{path}?{urlencode({'tab': action_tab, 'highlight': tutoria.pk})}"
    return urljoin(f"{site_url.rstrip('/')}/", path.lstrip("/"))


def _actor_name(actor: Any) -> str:
    return getattr(actor, "nombre_completo", None) or "Sistema CODDAA"


def _cancellation_reason(tutoria: Any) -> str:
    if getattr(tutoria, "detalle_motivo_cancelacion", None):
        return tutoria.detalle_motivo_cancelacion
    display = getattr(tutoria, "get_motivo_cancelacion_display", None)
    if callable(display) and getattr(tutoria, "motivo_cancelacion", None):
        return display()
    return ""


def _build_context(*, event: str, config: dict[str, Any], tutoria: Any, actor: Any, recipient: Any, role: str) -> dict[str, Any]:
    contact = _institutional_contact()
    show_calendar_actions = config.get("show_calendar_actions", False)
    site_url = settings.TUTORIAS_SITE_URL.strip()
    apple_calendar_url = ""
    if show_calendar_actions and site_url:
        ics_path = reverse("descargar_ics", kwargs={"tutoria_id": tutoria.pk})
        apple_calendar_url = urljoin(f"{site_url.rstrip('/')}/", ics_path.lstrip("/"))
    proposals = []
    if config.get("show_proposals"):
        proposals = [_format_datetime(value) for value in (getattr(tutoria, "fecha_propuesta_1", None), getattr(tutoria, "fecha_propuesta_2", None)) if value]
    action_text = _value_for_role(config.get("action_text"), role)
    action_url = _absolute_action_url(config, role, tutoria) if action_text else ""
    actor_name = _actor_name(actor)
    return {
        "evento": str(event), "destinatario_nombre": recipient.nombre_completo,
        "destinatario_rol": role, "actor_nombre": actor_name,
        "actor_rol": "sistema" if actor_name == "Sistema CODDAA" else "usuario",
        "titulo": _value_for_role(config.get("title"), role),
        "mensaje": _value_for_role(config.get("message"), role),
        "accion_tipo": config.get("action_type", ""), "accion_texto": action_text,
        "accion_url": action_url, "mostrar_accion": bool(action_text and action_url),
        "tipo_confirmacion": config.get("confirmation_type", ""),
        "origen_agendamiento": config.get("origin", ""),
        "mostrar_calendarios": show_calendar_actions,
        "google_calendar_url": tutoria.google_calendar_url_for(role) if show_calendar_actions else "",
        "apple_calendar_url": apple_calendar_url,
        "tipo_estado": config.get("status_type", ""),
        "es_cancelacion_definitiva": config.get("is_final", False),
        "fecha_actual": _format_datetime(getattr(tutoria, "fecha", None)),
        "fechas_propuestas": proposals,
        "fecha_limite": _format_datetime(tutoria.fecha_cancelacion_automatica) if event == EventoTutoria.TUTORIA_VENCIDA else "",
        "temas": ", ".join(tutoria.get_tema_display()), "descripcion": tutoria.descripcion or "",
        "alumno_nombre": tutoria.alumno.nombre_completo, "alumno_email": tutoria.alumno.email,
        "tutor_nombre": tutoria.tutor.nombre_completo, "tutor_email": tutoria.tutor.email,
        "motivo": tutoria.motivo_rechazo_legible if config.get("show_rejection_reason") else _cancellation_reason(tutoria) if config.get("show_cancellation_reason") else "",
        "contact": contact, "uam_phone_href": _phone_href(contact["uam_phone"]),
        "coddaa_phone_href": _phone_href(contact["coddaa_phone"]),
    }


def _build_plain_text(context: dict[str, Any]) -> str:
    lines = [context["titulo"], "", f"Hola {context['destinatario_nombre']},", context["mensaje"], "",
             f"Alumno: {context['alumno_nombre']}", f"Tutor: {context['tutor_nombre']}",
             f"Fecha y hora: {context['fecha_actual']}", f"Tema(s): {context['temas']}",
             f"Descripción: {context['descripcion'] or '-'}"]
    if context["fechas_propuestas"]:
        lines.extend(["", "Fechas propuestas:", *(f"- {value}" for value in context["fechas_propuestas"])])
    if context["motivo"]:
        lines.extend(["", f"Motivo: {context['motivo']}"])
    if context["fecha_limite"]:
        lines.extend(["", f"Fecha límite: {context['fecha_limite']}"])
    if context["mostrar_accion"]:
        lines.extend(["", f"{context['accion_texto']}: {context['accion_url']}"])
    if context["mostrar_calendarios"]:
        lines.extend([
            "", "Agregar al calendario:",
            f"- Google Calendar: {context['google_calendar_url']}",
            f"- Apple Calendar: {context['apple_calendar_url']}",
        ])
    lines.extend(["", "Universidad Autónoma Metropolitana Unidad Cuajimalpa",
                  f"Dirección: {context['contact']['address']}", f"Ubicación: {context['contact']['maps_url']}",
                  f"Teléfono UAM: {context['contact']['uam_phone']}", f"Teléfono CODDAA: {context['contact']['coddaa_phone']}"])
    return "\n".join(lines)


def _send_email_notification(*, subject: str, message: str, from_email: Optional[str], recipient_list: list[str], html_message: str, tutoria_id: int) -> None:
    try:
        send_mail(subject=subject, message=message, from_email=from_email, recipient_list=recipient_list,
                  html_message=html_message, fail_silently=False)
    except Exception:
        logger.exception("Fallo al enviar correo de notificación para tutoría %s", tutoria_id)


def _send_email_notification_async(**kwargs: Any) -> None:
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if backend.endswith("locmem.EmailBackend"):
        _send_email_notification(**kwargs)
        return
    Thread(target=_send_email_notification, kwargs=kwargs, daemon=True).start()


def notify_tutoria_event(*, event: str, tutoria: Any, actor: Any = None) -> None:
    """Envía una copia personalizada a cada rol configurado para el evento."""
    config = EMAIL_EVENT_CONFIG.get(event)
    if not config:
        logger.warning("Evento de correo no soportado: %s", event)
        return
    for role in config["recipients"]:
        recipient = getattr(tutoria, role, None)
        if recipient is None:
            logger.warning("La tutoría %s no tiene destinatario para el rol %s", tutoria.pk, role)
            continue
        emails = _recipient_emails(recipient)
        if not emails:
            logger.warning("%s %s sin correos para la tutoría %s", role.capitalize(), recipient.pk, tutoria.pk)
            continue
        context = _build_context(event=event, config=config, tutoria=tutoria, actor=actor, recipient=recipient, role=role)
        _send_email_notification_async(
            subject=_value_for_role(config["subject"], role), message=_build_plain_text(context),
            from_email=getattr(settings, "EMAIL_HOST_USER", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=emails, html_message=render_to_string(config["template"], context),
            tutoria_id=tutoria.pk,
        )


# Compatibilidad temporal con importaciones anteriores.
def notify_student_tutoria_event(event: str, tutoria: Any, actor: Any) -> None:
    notify_tutoria_event(event=event, tutoria=tutoria, actor=actor)
