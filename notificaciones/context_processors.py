"""
Context processor global para notificaciones.
Inyecta el conteo de notificaciones no leídas en todos los templates.
"""

from notificaciones.models import Notificacion


def notificaciones_no_leidas(request):
    """Añade conteo de notificaciones no leídas al contexto de todos los templates."""
    if request.user.is_authenticated:
        count = Notificacion.objects.filter(
            destinatario=request.user,
            leida=False
        ).count()
        ultimas = Notificacion.objects.filter(
            destinatario=request.user,
            leida=False
        ).order_by('-created_at')[:5]
        return {
            'notificaciones_count': count,
            'notificaciones_recientes': ultimas,
        }
    return {
        'notificaciones_count': 0,
        'notificaciones_recientes': [],
    }
