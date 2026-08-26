import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

logger = logging.getLogger('tareaenminutos')


@receiver(post_save, sender='chat_interno.MensajeChat')
def notificar_mensaje_chat(sender, instance, created, **kwargs):
    """Los mensajes de chat ya llegan por el icono de mensajes y ventanas flotantes.
    No se crea Notificacion para evitar duplicados con la campana."""
    pass
