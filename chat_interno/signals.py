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

    if sala.solicitud_id:
        destinatarios = sala.participantes.all()
    elif sala.tipo == 'directa':
        # Chat directo: no crea notificación (el mensaje ya llega por el icono de mensajes y ventana flotante)
        return
    else:
        # Canal General (anuncios): notifica a TODO el personal activo,
        # aunque nunca haya abierto la sala.
        from django.contrib.auth.models import User
        from django.db.models import Q
        destinatarios = User.objects.filter(is_active=True).filter(
            Q(is_staff=True) | Q(groups__name='Tutor')
        ).distinct()

    for participante in destinatarios:
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
