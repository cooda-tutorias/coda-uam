"""
Las notificaciones de tutoría se disparan de forma explícita desde las vistas
de negocio para evitar duplicados y mantener trazabilidad por evento.

Este módulo se conserva para futuras señales específicas, pero la notificación
genérica de post_save queda deshabilitada deliberadamente.
"""