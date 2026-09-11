"""
App: chat_interno
Chat en tiempo real entre Admin y Tutores usando Django Channels.
"""

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from solicitudes.models import SolicitudAcademica


def chat_upload_path(instance, filename):
    """Ruta dentro de media_privada para adjuntos del chat."""
    from django.utils.text import get_valid_filename
    return f"chat_archivos/sala_{instance.sala_id}/{get_valid_filename(filename)}"


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

    def es_directa_sin_admin(self):
        """Directa solo entre tutores (sin ningún admin participando).

        No permitidas: los chats directos son siempre con el equipo
        administrador."""
        if self.tipo != 'directa':
            return False
        from django.db.models import Q
        return not self.participantes.filter(
            Q(is_staff=True) | Q(groups__name='Administrador')
        ).exists()

    def get_nombre_para(self, user):
        """Nombre a mostrar a `user` en headers, ventanas y listas.

        Directa → nombre de la otra persona (no el "Chat: A - B" guardado,
        que queda obsoleto si cambian los nombres). Demás salas → sala.nombre.
        """
        if self.tipo == 'directa':
            otro = self.get_otro_participante(user)
            return (otro.get_full_name() or otro.username) if otro else 'Chat Directo'
        return self.nombre


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
        upload_to=chat_upload_path,
        storage=settings.PRIVATE_STORAGE,
        null=True, blank=True,
        verbose_name='Archivo adjunto'
    )
    archivo_nombre = models.CharField(
        max_length=500, blank=True, default='',
        verbose_name='Nombre original del archivo'
    )
    leido_por = models.ManyToManyField(
        User, blank=True,
        related_name='mensajes_leidos',
        verbose_name='Leído por'
    )
    # Edición y borrado suave
    editado = models.DateTimeField(null=True, blank=True, verbose_name='Editado en')
    eliminado = models.BooleanField(default=False, verbose_name='Eliminado')
    created_at = models.DateTimeField(auto_now_add=True)

    # Límite de tiempo para editar (minutos)
    TIEMPO_EDITAR_MINUTOS = 15

    class Meta:
        verbose_name = 'Mensaje de Chat'
        verbose_name_plural = 'Mensajes de Chat'
        ordering = ['created_at']

    def __str__(self):
        autor = self.autor.username if self.autor else 'Usuario eliminado'
        return f"{autor}: {self.contenido[:50]}"

    def fue_leido_por_otro(self):
        """True si alguien distinto del autor ya leyó el mensaje."""
        return self.leido_por.exclude(pk=self.autor_id).exists()

    def _admin_override(self, user):
        """True si `user` es admin y el mensaje tiene menos de 15 minutos.

        El admin puede moderar CUALQUIER mensaje (editar/eliminar sin
        restricciones de autor, lectura o edición previa), pero solo
        dentro de los 15 minutos de enviado (`TIEMPO_EDITAR_MINUTOS`).
        Pasado ese tiempo, ni el admin puede tocarlo."""
        if getattr(user, 'pk', None) is None:
            return False
        try:
            es_admin = bool(getattr(user, 'is_staff', False)) or user.groups.filter(name='Administrador').exists()
        except Exception:
            return False
        if not es_admin:
            return False
        from django.utils import timezone
        from datetime import timedelta
        try:
            return timezone.now() - self.created_at < timedelta(minutes=self.TIEMPO_EDITAR_MINUTOS)
        except Exception:
            return False

    def motivo_no_editable(self, user):
        """None si puede editar; si no, el motivo en claro para la UI."""
        if self.eliminado:
            return None
        if self._admin_override(user):
            return None
        if self.autor_id != getattr(user, 'pk', None):
            return 'ajeno'
        if self.fue_leido_por_otro():
            return 'leido'
        if self.editado:
            return 'ya_editado'
        from django.utils import timezone
        from datetime import timedelta
        if timezone.now() - self.created_at >= timedelta(minutes=self.TIEMPO_EDITAR_MINUTOS):
            return 'tiempo'
        return None

    def puede_editar(self, user):
        """Verifica si el usuario puede editar este mensaje.

        El autor, con las restricciones de motivo_no_editable.
        El admin, cualquier mensaje (moderación)."""
        if self.eliminado:
            return False
        if self._admin_override(user):
            return True
        if self.autor_id != getattr(user, 'pk', None):
            return False
        return self.motivo_no_editable(user) is None

    def puede_eliminar(self, user):
        """Verifica si el usuario puede eliminar este mensaje.

        El autor, solo mientras nadie más lo haya leído.
        El admin, cualquier mensaje (moderación)."""
        if self.eliminado:
            return False
        if self._admin_override(user):
            return True
        if self.autor_id != getattr(user, 'pk', None):
            return False
        return not self.fue_leido_por_otro()

    def to_dict(self):
        """Serializa el mensaje para WebSocket y JSON."""
        from django.urls import reverse
        import os
        local = timezone.localtime(self.created_at)
        url_adj = ''
        es_img = False
        es_pdf = False
        if self.archivo_adjunto:
            url_adj = reverse('chat_adjunto_descargar', args=[self.pk])
            ext = (os.path.splitext(self.archivo_nombre or self.archivo_adjunto.name)[1] or '').lower().lstrip('.')
            es_img = ext in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg')
            es_pdf = ext == 'pdf'
        data = {
            'id': self.pk,
            'sala_id': self.sala_id,
            'autor_id': self.autor_id,
            'autor_nombre': (self.autor.get_full_name() or self.autor.username) if self.autor else 'Usuario eliminado',
            'autor_foto': self.autor.perfil.get_foto_url() if hasattr(self.autor, 'perfil') else '',
            'contenido': self.contenido,
            'tipo': self.tipo,
            'adjunto_url': url_adj,
            'adjunto_nombre': self.archivo_nombre or '',
            'adjunto_es_imagen': es_img,
            'adjunto_es_pdf': es_pdf,
            'created_at': local.strftime('%H:%M'),
            'created_at_full': local.isoformat(),
            'fecha': local.strftime('%d/%m/%Y'),
            'editado': self.editado.isoformat() if self.editado else None,
            'eliminado': self.eliminado,
            'leido': self.fue_leido_por_otro(),
        }
        return data
