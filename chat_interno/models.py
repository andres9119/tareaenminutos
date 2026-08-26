"""
App: chat_interno
Chat en tiempo real entre Admin y Tutores usando Django Channels.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from solicitudes.models import SolicitudAcademica


class SalaChat(models.Model):
    """
    Sala de chat. Cada solicitud tiene su sala privada.
    También existe el canal "General" sin solicitud.
    """
    TIPO_SALA = [
        ('general', 'General'),
        ('solicitud', 'Por Solicitud'),
        ('directa', 'Chat Directo'),
    ]

    nombre = models.CharField(max_length=200, verbose_name='Nombre de la Sala')
    tipo = models.CharField(max_length=15, choices=TIPO_SALA, default='solicitud')
    solicitud = models.OneToOneField(
        SolicitudAcademica, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='sala_chat',
        verbose_name='Solicitud asociada'
    )
    participantes = models.ManyToManyField(
        User, blank=True,
        related_name='salas_chat',
        verbose_name='Participantes'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sala de Chat'
        verbose_name_plural = 'Salas de Chat'
        ordering = ['-created_at']

    def __str__(self):
        if self.solicitud:
            return f"Chat - {self.solicitud.codigo}"
        if self.tipo == 'directa':
            nombres = [u.get_full_name() or u.username for u in self.participantes.all()[:2]]
            return f"Chat Directo - {' y '.join(nombres)}" if nombres else "Chat Directo"
        return f"Chat General"

    @property
    def channel_group_name(self):
        """Nombre del grupo de Canal para WebSocket."""
        return f"chat_{self.pk}"

    def get_ultimos_mensajes(self, limit=50):
        return self.mensajes.order_by('-created_at')[:limit][::-1]

    def last_message(self):
        return self.mensajes.order_by('-created_at').first()

    def unread_count(self, user):
        """Mensajes no leídos para un usuario (excluye los que él escribió)."""
        return self.mensajes.exclude(autor=user).exclude(leido_por=user).count()

    def get_otro_participante(self, user):
        """Para chats directos: devuelve el otro usuario. Si no es directa, None."""
        if self.tipo != 'directa':
            return None
        return self.participantes.exclude(pk=user.pk).first()


class MensajeChat(models.Model):
    """Mensaje en una sala de chat."""

    TIPO_MENSAJE = [
        ('texto', 'Texto'),
        ('archivo', 'Archivo'),
        ('sistema', 'Sistema'),
    ]

    sala = models.ForeignKey(
        SalaChat, on_delete=models.CASCADE,
        related_name='mensajes',
        verbose_name='Sala'
    )
    autor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mensajes_chat',
        verbose_name='Autor'
    )
    contenido = models.TextField(verbose_name='Contenido')
    tipo = models.CharField(max_length=10, choices=TIPO_MENSAJE, default='texto')
    archivo_adjunto = models.FileField(
        upload_to='chat_archivos/',
        null=True, blank=True,
        verbose_name='Archivo adjunto'
    )
    leido_por = models.ManyToManyField(
        User, blank=True,
        related_name='mensajes_leidos',
        verbose_name='Leído por'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mensaje de Chat'
        verbose_name_plural = 'Mensajes de Chat'
        ordering = ['created_at']

    def __str__(self):
        autor = self.autor.username if self.autor else 'Usuario eliminado'
        return f"{autor}: {self.contenido[:50]}"

    def to_dict(self):
        """Serializa el mensaje para WebSocket."""
        local = timezone.localtime(self.created_at)
        return {
            'id': self.pk,
            'sala_id': self.sala_id,
            'autor_id': self.autor_id,
            'autor_nombre': (self.autor.get_full_name() or self.autor.username) if self.autor else 'Usuario eliminado',
            'autor_foto': self.autor.perfil.get_foto_url() if hasattr(self.autor, 'perfil') else '',
            'contenido': self.contenido,
            'tipo': self.tipo,
            'created_at': local.strftime('%H:%M'),
            'created_at_full': local.isoformat(),
        }
