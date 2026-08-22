# ==========================================
# 1. SUSCRIPTOR: CORREO ELECTRÓNICO
# ==========================================

import logging
from django.dispatch import receiver
from .signals_definitions import tutoria_notification_requested
from .notification_service import notify_student_tutoria_event, EMAIL_NOTIFICATION_EVENTS

logger = logging.getLogger(__name__)

# Eventos que deben disparar un correo al alumno o tutor
EMAIL_NOTIFICATION_EVENTS = {
	"aceptada",
	"rechazada",
	"cita_programada",
	"seguimiento_registrado",
    "cancelada_por_tutor",
    "cancelada_por_alumno",
    "vencida",
    "propuesta_2_fechas",
    "propuesta_1_fecha,",
    "reagendar",
    "solicitud_cambio_fecha"
}

@receiver(tutoria_notification_requested, dispatch_uid="Tutorias.handle_email_notifications")
def handle_email_notifications(sender, event=None, tutoria=None, actor=None, **kwargs):
    if event in EMAIL_NOTIFICATION_EVENTS:
        notify_student_tutoria_event(event, tutoria, actor)

