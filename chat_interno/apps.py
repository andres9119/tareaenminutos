from django.apps import AppConfig


class ChatInternoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat_interno'

    def ready(self):
        import chat_interno.signals  # noqa: F401
