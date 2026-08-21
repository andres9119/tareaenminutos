"""
App: cotizaciones
Propuestas económicas de los tutores para solicitudes académicas.
"""

from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from solicitudes.models import SolicitudAcademica


class Cotizacion(models.Model):
    """Cotización enviada por un tutor para una solicitud académica."""

    ESTADO_COTIZACION = [
        ('pendiente', 'Pendiente'),
        ('aceptada', 'Aceptada'),
        ('rechazada', 'Rechazada'),
        ('vencida', 'Vencida'),
    ]

    solicitud = models.ForeignKey(
        SolicitudAcademica, on_delete=models.CASCADE,
        related_name='cotizaciones',
        verbose_name='Solicitud'
    )
    tutor = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='cotizaciones_enviadas',
        verbose_name='Tutor'
    )

    # Propuesta económica
    monto = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name='Monto propuesto (COP)'
    )
    tiempo_estimado_dias = models.PositiveSmallIntegerField(
        verbose_name='Tiempo estimado (días)'
    )
    fecha_entrega_propuesta = models.DateField(
        verbose_name='Fecha de entrega propuesta'
    )

    # Descripción de la propuesta
    descripcion_propuesta = models.TextField(
        blank=True,
        verbose_name='Descripción de la propuesta',
        help_text='Explica cómo abordarás el trabajo y tu experiencia en el área'
    )

    # Estado
    estado = models.CharField(
        max_length=10, choices=ESTADO_COTIZACION,
        default='pendiente'
    )

    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cotización'
        verbose_name_plural = 'Cotizaciones'
        ordering = ['-created_at']
        # Un tutor solo puede cotizar una vez por solicitud
        unique_together = [['solicitud', 'tutor']]

    def __str__(self):
        return f"Cotización de {self.tutor.username} para {self.solicitud.codigo} - ${self.monto:,.0f}"

    @transaction.atomic
    def aceptar(self, por_usuario):
        """
        Acepta esta cotización, rechaza las demás y asigna el tutor.

        Se actualiza la solicitud con `.update()` (sin disparar signals) para
        evitar notificaciones duplicadas: la vista `cotizacion_aceptar` es la
        encargada de notificar al tutor ganador y a los rechazados.
        """
        from solicitudes.models import EstadoSolicitud, HistorialEstado

        # Rechazar todas las otras cotizaciones de esta solicitud
        Cotizacion.objects.filter(
            solicitud=self.solicitud
        ).exclude(pk=self.pk).update(estado='rechazada')

        # Aceptar esta
        self.estado = 'aceptada'
        self.save()

        # Actualizar la solicitud (bypass de signals para no duplicar notifs)
        estado_asignada, _ = EstadoSolicitud.objects.get_or_create(
            nombre='asignada',
            defaults={'etiqueta': 'Asignada', 'color_hex': '#8b5cf6', 'orden': 4}
        )
        estado_anterior = self.solicitud.estado
        SolicitudAcademica.objects.filter(pk=self.solicitud.pk).update(
            tutor_asignado=self.tutor,
            precio_final=self.monto,
            estado=estado_asignada,
            updated_at=timezone.now(),
        )

        # Registrar en historial
        HistorialEstado.objects.create(
            solicitud=self.solicitud,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_asignada,
            cambiado_por=por_usuario,
            comentario=f'Tutor asignado: {self.tutor.get_full_name() or self.tutor.username}. Precio: ${self.monto:,.0f}'
        )
