import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from notificaciones.utils import crear_notificacion

logger = logging.getLogger('tareaenminutos')


@receiver(post_save, sender='chat_interno.MensajeChat')
def notificar_mensaje_chat(sender, instance, created, **kwargs):
    """Crea notificación interna + email + push WebSocket para mensajes de chat.
    Cubre: canal general, chat directo admin-tutor, chat de solicitud."""
    if not created:
        return

    mensaje = instance
    sala = mensaje.sala
    autor = mensaje.autor

    # Determinar destinatarios según tipo de sala
    destinatarios = []

    if sala.tipo == 'general':
        # Canal general: notificar a TODO el personal activo (admins + tutores)
        from django.contrib.auth.models import User
        from django.db.models import Q
        destinatarios = User.objects.filter(
            Q(is_staff=True) | Q(groups__name='Tutor'), is_active=True
        ).exclude(pk=autor.pk if autor else None).distinct()

    elif sala.tipo == 'directa':
        # Chat directo: solo el otro participante
        otro = sala.get_otro_participante(autor) if autor else None
        if otro:
            destinatarios = [otro]

    elif sala.tipo == 'solicitud' and sala.solicitud:
        # Chat de solicitud: tutor asignado + admins (excepto autor)
        from django.contrib.auth.models import User
        from django.db.models import Q
        tutores_admins = User.objects.filter(
            Q(is_staff=True) | Q(groups__name='Tutor'), is_active=True
        ).exclude(pk=autor.pk if autor else None).distinct()
        # Filtrar: solo tutor asignado de ESTA solicitud + admins
        tutor_asignado = sala.solicitud.tutor_asignado
        destinatarios = tutores_admins.filter(
            Q(pk=tutor_asignado.pk) if tutor_asignado else Q(pk__in=[]) | Q(is_staff=True)
        )

    # Crear notificación para cada destinatario
    for dest in destinatarios:
        titulo = f'Nuevo mensaje en {sala.nombre}'
        texto = mensaje.contenido[:100] + ('…' if len(mensaje.contenido) > 100 else '')
        url = reverse('sala_chat', args=[sala.pk])

        crear_notificacion(
            destinatario=dest,
            tipo='mensaje_chat',
            titulo=titulo,
            mensaje=texto,
            url_accion=url,
            solicitud_id=sala.solicitud_id,
        )
