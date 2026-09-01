def notificaciones(request):
    if not request.user.is_authenticated:
        return {
            "unread_count": 0,
            "notificaciones_list": [],
        }

    notificaciones_sin_leer = (
        request.user.notifications
        .unread()
        .order_by("-timestamp")
    )

    notificaciones_list = []

    for notificacion in notificaciones_sin_leer[:20]:
        actor = notificacion.actor

        nombre_actor = getattr(actor, "nombre_completo", None)

        if not nombre_actor:
            nombre_actor = str(actor)

        notificaciones_list.append({
            "header": (
                notificacion.description
                or "Notificación"
            ),
            "text": f"{nombre_actor} {notificacion.verb}",
            "time": notificacion.timestamp,
        })

    return {
        "unread_count": notificaciones_sin_leer.count(),
        "notificaciones_list": notificaciones_list,
    }