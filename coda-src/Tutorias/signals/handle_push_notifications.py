# ==========================================
# 3. SUSCRIPTOR: NOTIFICACIONES PUSH
# ==========================================
@receiver(tutoria_notification_requested, dispatch_uid="Tutorias.push_listener")
def handle_push_notifications(sender, event=None, tutoria=None, actor=None, **kwargs):
    recipient = kwargs.get("recipient") or getattr(tutoria, "alumno", None)
    if not recipient:
        return

    # El suscriptor Push decide de forma independiente qué eventos le interesan
    PUSH_EVENTS = {"solicitud_creada", "aceptada", "rechazada"}
    
    if event in PUSH_EVENTS:
        send_push_notification(
            user=recipient,
            title=kwargs.get("verb", f"Notificación: {event}"),
            body=kwargs.get("description", "Abre la aplicación para más detalles.")
        )