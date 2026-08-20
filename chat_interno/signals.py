import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

logger = logging.getLogger('tareaenminutos')


@receiver(post_save, sender='chat_interno.MensajeChat')
def notificar_mensaje_chat(sender, instance, created, **kwargs):
    """Notifica a los participantes de la sala cuando hay un nuevo mensaje."""
    if not created or instance.tipo == 'sistema':
        return

    from notificaciones.utils import crear_notificacion
    sala = instance.sala
    autor = instance.autor
    mensaje_corto = instance.contenido[:100]

    for participante in sala.participantes.all():
        if participante == autor:
            continue

        url = reverse('sala_chat', args=[sala.pk])
        nombre_autor = autor.get_full_name() or autor.username if autor else 'Usuario eliminado'
        crear_notificacion(
            destinatario=participante,
            tipo='mensaje_chat',
            titulo=f'Mensaje en {sala.nombre}',
            mensaje=f'{nombre_autor}: {mensaje_corto}',
            url_accion=url,
            solicitud_id=sala.solicitud_id if sala.solicitud else None,
        )
