import logging

from django.dispatch import Signal, receiver
from notifications.signals import notify

from .notification_service import notify_student_tutoria_event

logger = logging.getLogger(__name__)


tutoria_notification_requested = Signal()

EMAIL_NOTIFICATION_EVENTS = {
	"aceptada",
	"rechazada",
	"cita_programada",
	"seguimiento_registrado",
}


@receiver(tutoria_notification_requested, dispatch_uid="Tutorias.tutoria_notification_requested")
def handle_tutoria_notification(sender, event=None, tutoria=None, actor=None, **kwargs):
	"""Orquesta el envío de notificaciones de tutoría a partir de un evento explícito.

	Recibe la solicitud desde las vistas, decide si corresponde enviar
	notificación por sistema o correo, y delega el envío real al servicio
	centralizado para evitar duplicar lógica en múltiples puntos.
	"""
	if not event or tutoria is None or actor is None:
		logger.warning(
			"Se intento disparar una notificacion de tutoria sin los datos minimos: sender=%s, event=%s",
			sender,
			event,
		)
		return

	if event in EMAIL_NOTIFICATION_EVENTS:
		notify_student_tutoria_event(event, tutoria, actor)
		return

	recipient = kwargs.get("recipient")
	if recipient is None:
		logger.warning(
			"No se pudo enviar la notificacion de sistema para el evento %s porque falta recipient",
			event,
		)
		return

	if event == "solicitud_creada":
		notify.send(
			actor,
			recipient=recipient,
			verb=kwargs.get("verb", "Nueva solicitud de tutoria"),
			description=kwargs.get("description", ""),
		)
		return

	if event == "tutoria_modificada":
		notify.send(
			actor,
			recipient=recipient,
			verb=kwargs.get("verb", "Tutoria Modificada"),
		)
		return

	if event == "qr_generada":
		notify.send(
			actor,
			recipient=recipient,
			verb=kwargs.get("verb", "Tutoria registrada con QR"),
		)
		return

	if event == "estado_historico_actualizado":
		notify.send(
			actor,
			recipient=recipient,
			verb=kwargs.get("verb", "Estado histórico de tutoría actualizado"),
			description=kwargs.get("description", ""),
		)
		return

	logger.warning("Evento de notificacion no soportado: %s", event)