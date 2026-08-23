"""
Context processor y helpers para el messenger flotante de chat.
Inyecta en todas las vistas internas la lista de conversaciones del usuario
con su último mensaje y el conteo de no leídos.
"""

from datetime import datetime
from django.db.models import Q, F, Max
from django.utils import timezone
from .models import SalaChat

CERRADAS = ('completada', 'cancelada')


def _es_admin(user):
    return user.is_superuser or user.groups.filter(name='Administrador').exists()


def _base_salas(user):
    """Queryset de salas visibles para el usuario (sin evaluar)."""
    if _es_admin(user):
        return SalaChat.objects.all()
    # Tutores: TODAS las salas generales (canal de anuncios) + solicitudes asignadas.
    return SalaChat.objects.filter(
        Q(solicitud__isnull=True) | Q(solicitud__tutor_asignado=user)
    ).distinct()


def _construir_datos_sala(sala, user):
    ultimo = sala.last_message()
    cerrada = bool(
        sala.solicitud
        and sala.solicitud.estado
        and sala.solicitud.estado.nombre in CERRADAS
    )
    return {
        'id': sala.pk,
        'nombre': sala.nombre,
        'tipo': sala.tipo,
        'cerrada': cerrada,
        'codigo': sala.solicitud.codigo if sala.solicitud else None,
        'titulo': sala.solicitud.titulo if sala.solicitud else None,
        'ultimo_mensaje': ultimo.contenido if ultimo else None,
        'ultimo_autor': (ultimo.autor.get_full_name() or ultimo.autor.username) if (ultimo and ultimo.autor) else None,
        'ultimo_tiempo': ultimo.created_at if ultimo else None,
        'es_propio_ultimo': bool(ultimo and ultimo.autor_id == user.pk),
        'no_leidos': sala.unread_count(user),
    }


def _salas_con_datos(user, limite=25):
    # Trae un grupo amplio y ordena por relevancia para el flotante:
    # 1) con mensajes sin leer, 2) chats abiertos, 3) actividad reciente.
    # Así las cientos de salas cerradas no tapan lo importante.
    pool_size = max(limite * 4, 80)
    salas = list(_base_salas(user)
                 .select_related('solicitud', 'solicitud__estado')
                 .annotate(ultima_act=Max('mensajes__created_at'))
                 .order_by(F('ultima_act').desc(nulls_last=True), '-created_at')[:pool_size])

    datos = [_construir_datos_sala(s, user) for s in salas]
    _sent = timezone.make_aware(datetime.min)
    datos.sort(key=lambda d: (
        bool(d['no_leidos']),
        not d['cerrada'],
        d['ultimo_tiempo'] or _sent,
    ), reverse=True)
    return datos[:limite]


def mensajes_no_leidos_chats(user):
    """Total de mensajes no leídos en todos los chats del usuario."""
    total = 0
    for s in _base_salas(user):
        total += s.unread_count(user)
    return total


def messenger(request):
    """Context processor: expone los chats del usuario para el messenger flotante."""
    if not (request.user.is_authenticated and (
        request.user.is_superuser
        or request.user.groups.filter(name='Administrador').exists()
        or request.user.groups.filter(name='Tutor').exists()
    )):
        return {'user_chats': [], 'total_chats_unread': 0}

    user_chats = _salas_con_datos(request.user)
    return {
        'user_chats': user_chats,
        'total_chats_unread': sum(d['no_leidos'] for d in user_chats),
    }
