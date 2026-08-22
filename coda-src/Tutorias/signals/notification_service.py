import logging
import re
from threading import Thread
from typing import Any, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from notifications.signals import notify

from Usuarios.models import Alumno

from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


EVENT_CONFIG: dict[str, dict[str, str]] = {
    "aceptada": {
        "verb": "Solicitud de tutoría aceptada",
        "subject": "Tu solicitud de tutoría fue aceptada",
    },
    "rechazada": {
        "verb": "Solicitud de tutoría rechazada",
        "subject": "Tu solicitud de tutoría fue rechazada",
    },
    "cita_programada": {
        "verb": "Tu tutor te cito para una tutoría",
        "subject": "Tienes una cita de tutoría programada",
    },
    "seguimiento_registrado": {
        "verb": "Se registro seguimiento de tu tutoría",
        "subject": "Se registro seguimiento de tu tutoría",
    },
}


def _event_headline(event: str, tutor_nombre: str) -> str:
    """Construye el encabezado corto que resume el evento de tutoría."""
    if event == "aceptada":
        return f"El tutor acepto tu solicitud de tutoría."
    if event == "rechazada":
        return f"El tutor rechazo tu solicitud de tutoría."
    if event == "cita_programada":
        return f"El tutor actualizo la fecha y hora de tu tutoría."
    if event == "seguimiento_registrado":
        return f"El tutor registro el seguimiento de tu tutoría."
    return f"El tutor actualizo una tutoría."


def _institutional_contact() -> dict[str, str]:
    """Obtiene la información institucional usada en el pie del correo HTML."""
    return {
        "logo_url": getattr(settings, "NOTIFICATIONS_EMAIL_LOGO_URL", ""),
        "address": getattr(
            settings,
            "NOTIFICATIONS_UAM_ADDRESS",
            "Av. Vasco de Quiroga 4871, Santa Fe Cuajimalpa, Cuajimalpa de Morelos, 05348, Ciudad de México, CDMX",
        ),
        "maps_url": getattr(
            settings,
            "NOTIFICATIONS_UAM_MAPS_URL",
            "https://maps.google.com/?q=UAM+Cuajimalpa",
        ),
        "uam_phone": getattr(settings, "NOTIFICATIONS_UAM_PHONE", "(55) 5814 6500"),
        "coddaa_phone": getattr(settings, "NOTIFICATIONS_CODDAA_PHONE", "(55) 5814 6500"),
    }


def _student_emails(alumno: Alumno) -> list[str]:
    """Devuelve los correos del alumno sin duplicados, preservando el orden."""
    emails: list[str] = []
    for candidate in [alumno.email, alumno.correo_personal]:
        if candidate and candidate not in emails:
            emails.append(candidate)
    return emails


def _phone_href(phone: str) -> str:
    """Normaliza un teléfono para usarlo en un enlace tel: compatible."""
    normalized = re.sub(r"[^\d+]", "", phone or "")
    return normalized or ""


def _build_email_body(event: str, tutoria: Any) -> str:
    """Construye la versión de texto plano del correo de notificación."""
    temas = ", ".join(tutoria.get_tema_display())
    fecha_local = timezone.localtime(tutoria.fecha).strftime("%d/%m/%Y %H:%M")
    tutor_nombre = tutoria.tutor.get_full_name()
    tutor_email = tutoria.tutor.email
    alumno_nombre = tutoria.alumno.get_full_name()
    contact = _institutional_contact()
    encabezado = _event_headline(event, tutor_nombre)

    return (
        f"{encabezado}\n\n"
        f"Alumno: {alumno_nombre}\n"
        f"Tutor: {tutor_nombre}\n"
        f"Correo institucional del tutor: {tutor_email}\n"
        f"Fecha y hora: {fecha_local}\n"
        f"Tema(s): {temas}\n"
        f"Descripcion: {tutoria.descripcion or '-'}\n\n"
        "Universidad Autonoma Metropolitana Unidad Cuajimalpa\n"
        f"Direccion: {contact['address']}\n"
        f"Ubicacion: {contact['maps_url']}\n"
        f"Telefono UAM: {contact['uam_phone']}\n"
        f"Telefono CODDAA: {contact['coddaa_phone']}\n"
    )


def _build_email_html(event: str, tutoria: Any) -> str:
    """Construye el cuerpo HTML profesional del correo de notificación."""
    tutor_nombre = tutoria.tutor.nombre_completo
    contact = _institutional_contact()

    context = {
        "alumno_nombre": tutoria.alumno.nombre_completo,
        "encabezado": _event_headline(event, tutor_nombre),
        "tutor_nombre": tutor_nombre,
        "tutor_email": tutoria.tutor.email,
        "fecha_local": timezone.localtime(tutoria.fecha).strftime("%d/%m/%Y %H:%M"),
        "temas": ", ".join(tutoria.get_tema_display()),
        "tutoria": tutoria,
        "contact": contact,
        "uam_phone_href": _phone_href(contact["uam_phone"]),
        "coddaa_phone_href": _phone_href(contact["coddaa_phone"]),
    }

    return render_to_string("emails/notificacion_tutoria.html", context)


def _send_email_notification(
    *,
    subject: str,
    message: str,
    from_email: Optional[str],
    recipient_list: list[str],
    html_message: str,
    tutoria_id: int,
) -> None:
    """Envía el correo real y captura errores para no interrumpir la petición web."""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
    except Exception:
        logger.exception("Fallo al enviar correo de notificacion para tutoria %s", tutoria_id)


def _send_email_notification_async(
    *,
    subject: str,
    message: str,
    from_email: Optional[str],
    recipient_list: list[str],
    html_message: str,
    tutoria_id: int,
) -> None:
    """Despacha el envío de correo en segundo plano para evitar bloquear la respuesta."""
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if backend.endswith("locmem.EmailBackend"):
        _send_email_notification(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            tutoria_id=tutoria_id,
        )
        return

    Thread(
        target=_send_email_notification,
        kwargs={
            "subject": subject,
            "message": message,
            "from_email": from_email,
            "recipient_list": recipient_list,
            "html_message": html_message,
            "tutoria_id": tutoria_id,
        },
        daemon=True,
    ).start()


def notify_student_tutoria_event(event: str, tutoria: Any, actor: Any) -> None:
    """Envía la notificación interna y el correo al alumno para un evento de tutoría."""
    config = EVENT_CONFIG.get(event)
    if not config:
        logger.warning("Evento de notificacion no soportado: %s", event)
        return

    emails = _student_emails(tutoria.alumno)
    if not emails:
        logger.warning("Alumno %s sin correos para enviar notificacion", tutoria.alumno_id)
        return

    _send_email_notification_async(
        subject=config["subject"],
        message=_build_email_body(event, tutoria),
        from_email=getattr(settings, "EMAIL_HOST_USER", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=emails,
        html_message=_build_email_html(event, tutoria),
        tutoria_id=tutoria.pk,
    )
