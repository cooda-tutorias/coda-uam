"""Suscriptor del canal de notificaciones por correo."""

import logging

from django.dispatch import receiver

from .notification_service import EMAIL_EVENT_CONFIG, notify_tutoria_event
from .signals_definitions import tutoria_notification_requested

logger = logging.getLogger(__name__)


@receiver(tutoria_notification_requested, dispatch_uid="Tutorias.handle_email_notifications")
def handle_email_notifications(sender, event=None, tutoria=None, actor=None, **kwargs):
    """Envía correo únicamente para eventos declarados por este canal."""
    if event not in EMAIL_EVENT_CONFIG:
        return
    if tutoria is None:
        logger.warning("Se ignoró el evento de correo %s: no incluye tutoría", event)
        return
    
    notify_tutoria_event(event=event, tutoria=tutoria, actor=actor)
