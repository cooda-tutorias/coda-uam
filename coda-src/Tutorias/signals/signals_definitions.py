# Tutorias/signals/signals_definitions.py
from django.dispatch import Signal

# Señal única para todos los canales (email, sistema, push)
tutoria_notification_requested = Signal()