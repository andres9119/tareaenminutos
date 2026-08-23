"""
Context processor y helpers para el messenger flotante de chat.
Inyecta en todas las vistas internas la lista de conversaciones del usuario
con su último mensaje y el conteo de no leídos.
"""

from datetime import datetime
from django.utils import timezone
from .models import SalaChat


def _construir_datos_sala(sala, user):
    ultimo = sala.last_message()
    return {
        'id': sala.pk,
        'nombre': sala.nombre,
        'tipo': sala.tipo,
        'codigo': sala.solicitud.codigo if sala.solicitud else None,
        'titulo': sala.solicitud.titulo if sala.solicitud else None,
        'ultimo_mensaje': ultimo.contenido if ultimo else None,
        'ultimo_autor': (ultimo.autor.get_full_name() or ultimo.autor.username) if (ultimo and ultimo.autor) else None,
        'ultimo_tiempo': ultimo.created_at if ultimo else None,
        'es_propio_ultimo': bool(ultimo and ultimo.autor_id == user.pk),
        'no_leidos': sala.unread_count(user),
    }


def _salas_con_datos(user, limite=25):
    if user.is_superuser or user.groups.filter(name='Administrador').exists():
        salas = list(SalaChat.objects.all())
    else:
        # Tutores: salas generales donde participa + salas de solicitudes asignadas a él.
        salas = _dedup(
            # Canal General (anuncios): visible para todo el personal,
            # sin importar si alguna vez entró a la sala.
            list(SalaChat.objects.filter(solicitud__isnull=True)) + list(
                SalaChat.objects.filter(
                    solicitud__isnull=False,
                    solicitud__tutor_asignado=user,
                )
            )
        )

    datos = [_construir_datos_sala(s, user) for s in salas]
    # Ordenar por actividad: último mensaje más reciente primero (sin mensajes al final)
    _sent = timezone.make_aware(datetime.min)
    datos.sort(key=lambda d: d['ultimo_tiempo'] or _sent, reverse=True)
    return datos[:limite]


def _dedup(salas):
    vistos = {}
    for s in salas:
        vistos[s.pk] = s
    return list(vistos.values())


def mensajes_no_leidos_chats(user):
    """Total de mensajes no leídos en todos los chats del usuario."""
    salas = _salas_con_datos(user, limite=999)
    return sum(d['no_leidos'] for d in salas)


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
