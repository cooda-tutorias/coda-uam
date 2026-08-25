# ==========================================
# 2. SUSCRIPTOR: NOTIFICACIONES DE SISTEMA (CAMPANA)
# ==========================================

import logging
from django.dispatch import receiver
from notifications.signals import notify
from .signals_definitions import tutoria_notification_requested
from .events import EventoTutoria

logger = logging.getLogger(__name__)


# Información para mostrar la notificación según cada evento.
# En los eventos que comienzan con ALU o TUT el actor (emisor) es
# el ALUmno o el TUTor. 
# En los eventos que comienzan con otro sujeto (TUTORIA o PROPUESTA) el
# actor es el sistema.
SYSTEM_NOTIFICATION_INFO: dict[EventoTutoria, dict[str, str]] = {
    EventoTutoria.ALU_AGENDA_POR_QR: {
        "verb": "registró una tutoría mediante código QR",
        "description": "Tutoría registrada por QR",
    },
    EventoTutoria.ALU_SOLICITA_TUTORIA: {
        "verb": "solicitó una tutoría",
        "description": "Nueva solicitud de tutoría",
    },
    EventoTutoria.ALU_AGENDA_TUTORIA: {
        "verb": "agendó una sesión de tutoría",
        "description": "Tutoría agendada",
    },
    EventoTutoria.TUT_ACEPTA_SOLICITUD: {
        "verb": "aceptó tu solicitud de tutoría",
        "description": "Solicitud de tutoría aceptada",
    },
    EventoTutoria.TUT_PROPONE_1_FECHA: {
        "verb": "agendó tu sesión de tutoría en un nueva fecha",
        "description": "Tutoría agendada en otra fecha",
    },
    EventoTutoria.TUT_PROPONE_2_FECHAS: {
        "verb": "propuso opciones de fecha para la tutoría",
        "description": "Propuestas de fecha de tutoría",
    },
    EventoTutoria.TUT_REACTIVA_1_FECHA: {
        "verb": "reactivó y agendó tu solicitud de tutoría en una nueva fecha",
        "description": "Solicitud de tutoría reactivada y agendada",
    },
    EventoTutoria.TUT_REACTIVA_2_FECHAS: {
        "verb": "reactivó tu solicitud y propuso opciones de fecha",
        "description": "Solicitud de tutoría reactivada; elige una fecha",
    },
    EventoTutoria.TUT_RECHAZA_SOLICITUD: {
        "verb": "rechazó la solicitud de tutoría",
        "description": "Solicitud de tutoría rechazada",
    },
    EventoTutoria.ALU_SOL_CAMBIO_FECHA_SUG: {
        "verb": "solicitó cambiar la fecha de tutoría pendiente",
        "description": "Cambio de fecha en solicitud pendiente",
    },
    EventoTutoria.ALU_SOL_CAMBIO_FECHA_AGEN: {
        "verb": "reprogramó su tutoría solicitada/agendada",
        "description": "Reprogramación de tutoría",
    },
    EventoTutoria.ALU_CANCELA_SOLICITUD: {
        "verb": "canceló la solicitud de tutoría",
        "description": "Solicitud de tutoría cancelada",
    },
    EventoTutoria.TUTORIA_VENCIDA: {
        "verb": "ha vencido por falta de confirmación",
        "description": "Tutoría vencida",
    },
    EventoTutoria.ALU_CANCELA_AGENDADA: {
        "verb": "canceló la tutoría agendada",
        "description": "Tutoría agendada cancelada",
    },
    EventoTutoria.TUT_CANCELA_AGENDADA: {
        "verb": "canceló la tutoría agendada",
        "description": "Tutoría agendada cancelada",
    },
    EventoTutoria.TUT_REAGENDA_1_FECHA: {
        "verb": "reprogramó la tutoría agendada",
        "description": "Reprogramación de tutoría agendada",
    },
    EventoTutoria.TUT_REAGENDA_2_FECHAS: {
        "verb": "propuso opciones de fecha para reagendar la tutoría",
        "description": "Opciones para reagendar tutoría",
    },
    EventoTutoria.TUTORIA_REALIZADA: {
        "verb": "marcó la tutoría como realizada",
        "description": "Tutoría realizada",
    },
    EventoTutoria.ALU_ELIGE_FECHA_PROPUESTA: {
        "verb": "seleccionó una de las fechas propuestas",
        "description": "Fecha de tutoría confirmada",
    },
    EventoTutoria.PROPUESTA_FECHAS_CANCELADA: {
        "verb": "ha cancelado la solicitud por falta de confirmación",
        "description": "Propuesta de fechas cancelada",
    },
    EventoTutoria.TUTORIA_VENCIDA_CANCELADA: {
        "verb": "fue cancelada automáticamente por vencimiento",
        "description": "Tutoría cancelada por vencimiento",
    },
    EventoTutoria.TUTORIA_INFORME_REGISTRADO: {
        "verb": "registró el informe de la tutoría",
        "description": "Informe de tutoría registrado",
    },
    EventoTutoria.ALU_EDITA_INFO_TUTORIA: {
        "verb": "actualizó los detalles de la tutoría",
        "description": "Información de tutoría actualizada",
    },
}

# Método para manejar los eventos de tutorías que se publican con
# tutoria_notification_requested.send
@receiver(tutoria_notification_requested, dispatch_uid="Tutorias.inapp_listener")
def handle_inapp_notifications(sender, event=None, tutoria=None, actor=None, recipient=None, **kwargs):

    if not recipient:
        return

    # Si el evento no está en la lista de eventos que se notifican dentro de la app, ignorarlo.
    info_noti = SYSTEM_NOTIFICATION_INFO.get(event)
    if not info_noti:
        return

    # Enviar la notificación interna del sistema.
    notify.send(
        sender=actor,
        recipient=recipient,
        verb=info_noti["verb"],
        description=info_noti["description"],
    )
