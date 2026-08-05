from django.apps import AppConfig


class SolicitudesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'solicitudes'
    verbose_name = 'Solicitudes Académicas'

    def ready(self):
        import solicitudes.signals  # noqa: F401
