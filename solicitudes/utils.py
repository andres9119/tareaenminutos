"""
Utilidades para el módulo de solicitudes.
"""

ESTADOS_CON_TUTOR = ['asignada', 'en_progreso', 'en_revision', 'en_correccion']


def reponer_activas_sin_tutor(scope=None, cambiado_por=None):
    """Devuelve a En Cotización las solicitudes activas que no tienen tutor.

    Corrige el estado inválido que deja la eliminación de un tutor (FK
    ``tutor_asignado`` pasa a NULL pero el estado quedaba ``asignada``, etc.).

    - ``scope=None``: revisa todas las huérfanas ``tutor_asignado__isnull=True``.
    - ``scope``: queryset de ``SolicitudAcademica`` (p. ej. las de un tutor que
      será eliminado); se aplica el mismo filtro de estados con tutor.

    Registra un ``HistorialEstado`` por cada solicitud repuesta. Retorna la
    lista de códigos saneados.
    """
    from .models import SolicitudAcademica, EstadoSolicitud, HistorialEstado

    qs = SolicitudAcademica.objects.filter(
        estado__nombre__in=ESTADOS_CON_TUTOR
    )
    if scope is None:
        qs = qs.filter(tutor_asignado__isnull=True)
    else:
        qs = qs.filter(pk__in=scope.values_list('pk', flat=True))

    estado_cot = EstadoSolicitud.objects.filter(nombre='en_cotizacion').first()
    if not estado_cot:
        return []

    saneados = []
    for s in qs:
        antiguo = s.estado
        s.estado = estado_cot
        s.save(update_fields=['estado', 'updated_at'])
        HistorialEstado.objects.create(
            solicitud=s,
            estado_anterior=antiguo,
            estado_nuevo=estado_cot,
            cambiado_por=cambiado_por,
            comentario='Saneo: tutor eliminado o ausente. Solicitud devuelta a cotización.',
        )
        saneados.append(s.codigo)
    return saneados


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
