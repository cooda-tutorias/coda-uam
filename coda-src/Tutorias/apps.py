from django.apps import AppConfig


class TutoriasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Tutorias'

    def ready(self):
        """Carga las señales de Tutorías al inicializar la aplicación."""
        from . import signals  # noqa: F401
