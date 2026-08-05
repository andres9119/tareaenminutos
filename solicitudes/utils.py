"""
Utilidades para el módulo de solicitudes.
"""


def recalcular_estadisticas_tutor(tutor):
    """Recalcula trabajos_completados y calificacion_promedio del tutor desde la BD.

    Se usa al reactivar una solicitud completada: la orden deja de contar como
    "completada" y su calificación deja de sumar al promedio del tutor.
    """
    from django.contrib.auth.models import User
    from accounts.models import PerfilUsuario
    from .models import SolicitudAcademica

    if not tutor or not isinstance(tutor, User):
        return

    perfil, _ = PerfilUsuario.objects.get_or_create(user=tutor)
    completadas = SolicitudAcademica.objects.filter(
        tutor_asignado=tutor, estado__nombre='completada'
    ).count()
    perfil.trabajos_completados = completadas

    calificadas = SolicitudAcademica.objects.filter(
        tutor_asignado=tutor, calificacion_tutor__isnull=False
    )
    total = sum(c.calificacion_tutor for c in calificadas)
    count = calificadas.count()
    if count:
        from decimal import Decimal
        perfil.calificacion_promedio = (Decimal(total) / count).quantize(Decimal('0.01'))
    else:
        perfil.calificacion_promedio = 0

    perfil.save(update_fields=['trabajos_completados', 'calificacion_promedio'])
