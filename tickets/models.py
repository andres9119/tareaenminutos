from django.db import models
from django.conf import settings


class TicketReporte(models.Model):
    ESTADO_CHOICES = [
        ('abierto', 'Abierto'),
        ('en_progreso', 'En Progreso'),
        ('resuelto', 'Resuelto'),
        ('cerrado', 'Cerrado'),
    ]

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    seccion = models.CharField(max_length=200, blank=True, help_text='Sección de la plataforma donde ocurrió')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='abierto')
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tickets_creados'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Ticket de Reporte'
        verbose_name_plural = 'Tickets de Reporte'

    def __str__(self):
        return f'[{self.get_estado_display()}] {self.titulo}'
