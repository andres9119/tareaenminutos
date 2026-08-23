"""
App: notificaciones
Sistema de notificaciones internas con soporte WebSocket.
"""

from django.db import models
from django.contrib.auth.models import User


class Notificacion(models.Model):
    """Notificación interna para usuarios del sistema TEM."""

    TIPO_NOTIFICACION = [
        ('nueva_solicitud', 'Nueva Solicitud'),
        ('cotizacion_recibida', 'Cotización Recibida'),
        ('cotizacion_aceptada', 'Cotización Aceptada'),
        ('cotizacion_rechazada', 'Cotización Rechazada'),
        ('solicitud_asignada', 'Solicitud Asignada'),
        ('cambio_estado', 'Cambio de Estado'),
        ('entrega_recibida', 'Entrega Recibida'),
        ('comprobante_pago', 'Comprobante de Pago'),
        ('mensaje_chat', 'Nuevo Mensaje'),
        ('sistema', 'Sistema'),
    ]

    destinatario = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='notificaciones',
        verbose_name='Destinatario'
    )
    tipo = models.CharField(
        max_length=30, choices=TIPO_NOTIFICACION,
        verbose_name='Tipo'
    )
    titulo = models.CharField(max_length=200, verbose_name='Título')
    mensaje = models.TextField(verbose_name='Mensaje')
    leida = models.BooleanField(default=False, verbose_name='Leída')
    url_accion = models.CharField(
        max_length=500, blank=True,
        verbose_name='URL de acción',
        help_text='URL a la que redirige al hacer click'
    )

    # Referencia opcional a la solicitud relacionada
    solicitud_id = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.titulo} → {self.destinatario.username}"

    def marcar_leida(self):
        self.leida = True
        self.save(update_fields=['leida'])
