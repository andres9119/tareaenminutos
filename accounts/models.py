"""
App: accounts
Gestión de perfiles de usuario y áreas de conocimiento.
"""

from django.db import models
from django.contrib.auth.models import User


class AreaConocimiento(models.Model):
    """Área académica de conocimiento (Ingeniería, Derecho, Medicina, etc.)"""
    nombre = models.CharField(max_length=100, unique=True)
    icono = models.CharField(max_length=50, default='fa-book-open', help_text='Clase FontAwesome del icono')
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Área de Conocimiento'
        verbose_name_plural = 'Áreas de Conocimiento'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class PerfilUsuario(models.Model):
    """Perfil extendido para usuarios del sistema (Admin y Tutores)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')

    # Información personal
    telefono = models.CharField(max_length=20, blank=True)
    foto = models.ImageField(upload_to='perfiles/', blank=True, null=True)
    bio = models.TextField(max_length=500, blank=True, verbose_name='Descripción / Bio')

    # Solo para tutores
    especialidades = models.ManyToManyField(
        AreaConocimiento,
        blank=True,
        verbose_name='Áreas de Especialidad'
    )
    calificacion_promedio = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        verbose_name='Calificación Promedio'
    )
    trabajos_completados = models.PositiveIntegerField(
        default=0,
        verbose_name='Trabajos Completados'
    )
    disponible = models.BooleanField(
        default=True,
        verbose_name='Disponible para nuevas solicitudes'
    )

    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuario'

    def __str__(self):
        return f"Perfil de {self.user.get_full_name() or self.user.username}"

    @property
    def es_admin(self):
        return self.user.groups.filter(name='Administrador').exists() or self.user.is_superuser

    @property
    def es_tutor(self):
        return self.user.groups.filter(name='Tutor').exists()

    @property
    def nombre_completo(self):
        return self.user.get_full_name() or self.user.username

    @property
    def trabajos_asignados(self):
        """Solicitudes activas asignadas al tutor (no terminadas)."""
        from solicitudes.models import SolicitudAcademica
        return SolicitudAcademica.activas_de_tutor(self.user).count()

    def get_foto_url(self):
        """Retorna URL de foto o placeholder."""
        if self.foto:
            return self.foto.url
        initials = (self.user.first_name[:1] + self.user.last_name[:1]).upper() or self.user.username[:2].upper()
        return f"https://ui-avatars.com/api/?name={initials}&background=6366f1&color=fff&size=128"
