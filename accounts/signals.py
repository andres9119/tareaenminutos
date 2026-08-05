"""
Signals para el sistema TEM.
Dispara notificaciones automáticas en eventos de solicitudes y cotizaciones.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from accounts.models import PerfilUsuario


@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    """Crea automáticamente el PerfilUsuario cuando se registra un nuevo User."""
    if created:
        PerfilUsuario.objects.get_or_create(user=instance)
