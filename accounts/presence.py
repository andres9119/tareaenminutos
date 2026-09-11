"""
Presence tracking para usuarios online — usa Redis directamente (channel layer).
Guarda user_id con TTL renovable. Admin puede consultar lista de usuarios online.
"""
import json
import time
from django.conf import settings
from django.core.cache import cache


PRESENCE_KEY = "presence:online_users"
PRESENCE_TTL = 90  # 90 segundos (debe ser mayor que el heartbeat de 30s;
# si el socket muere sin aviso, el fantasma dura máximo ~90s, no 5 min)

# Ventana de actividad HTTP que también cuenta como "en línea" (minutos).
# Respaldo cuando el WebSocket no conecta (pestaña sin socket, caché
# fragmentada entre procesos, etc.): si el usuario navegó hace poco,
# está en línea aunque no tenga socket abierto.
ONLINE_ACTIVIDAD_MINUTOS = 1


def _get_redis():
    """Obtener cliente Redis del channel layer o cache backend."""
    try:
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if hasattr(layer, 'connection') and layer.connection:
            return layer.connection
    except Exception:
        pass
    # Fallback: usar Django cache (Redis si está configurado)
    return cache.client.get_client() if hasattr(cache, 'client') else cache


async def mark_online(user_id: int, user_info: dict = None):
    """Marcar usuario como online. Renueva TTL."""
    key = f"{PRESENCE_KEY}:{user_id}"
    data = {
        'id': user_id,
        'last_seen': int(time.time()),
    }
    if user_info:
        data.update(user_info)
    
    # Usar cache backend (Redis en prod, locmem en dev)
    cache.set(key, json.dumps(data), PRESENCE_TTL)
    
    # Mantener set global de usuarios online
    online_set = cache.get(PRESENCE_KEY, set())
    online_set.add(user_id)
    cache.set(PRESENCE_KEY, online_set, PRESENCE_TTL * 2)


async def mark_offline(user_id: int):
    """Marcar usuario como offline."""
    key = f"{PRESENCE_KEY}:{user_id}"
    cache.delete(key)

    online_set = cache.get(PRESENCE_KEY, set())
    online_set.discard(user_id)
    cache.set(PRESENCE_KEY, online_set, PRESENCE_TTL * 2)
    # OJO: aquí NO se toca ultima_conexion a propósito. Antes se estampaba
    # con "ahora" al desconectar y eso regalaba 1 min fantasma en línea
    # (la ventana HTTP). La última conexión real la escribe el middleware
    # en cada navegación; para mostrar es igual de válida.


async def get_online_users():
    """Obtener lista de usuarios online con su info."""
    online_set = cache.get(PRESENCE_KEY, set())
    if not online_set:
        return []
    
    users = []
    for uid in list(online_set):
        key = f"{PRESENCE_KEY}:{uid}"
        data = cache.get(key)
        if data:
            try:
                users.append(json.loads(data))
            except Exception:
                pass
        else:
            # Cleanup: usuario en set pero sin data (TTL expiró)
            online_set.discard(uid)
    
    cache.set(PRESENCE_KEY, online_set, PRESENCE_TTL * 2)
    return users


async def is_online(user_id: int) -> bool:
    """Verificar si un usuario específico está online."""
    key = f"{PRESENCE_KEY}:{user_id}"
    return cache.get(key) is not None


async def heartbeat(user_id: int):
    """Renovar TTL del usuario (llamar periódicamente desde WebSocket)."""
    key = f"{PRESENCE_KEY}:{user_id}"
    data = cache.get(key)
    if data:
        try:
            d = json.loads(data)
            d['last_seen'] = int(time.time())
            cache.set(key, json.dumps(d), PRESENCE_TTL)
        except Exception:
            pass


# Funciones sync para uso en vistas Django normales
def mark_online_sync(user_id: int, user_info: dict = None):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(mark_online(user_id, user_info))


def mark_offline_sync(user_id: int):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(mark_offline(user_id))


def get_online_users_sync():
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(get_online_users())


def obtener_en_linea():
    """Personal interno en línea (sync, para vistas).

    Unión de dos señales:
    1. Socket WebSocket activo (notificaciones o chat).
    2. Navegación HTTP reciente (ultima_conexion <= ONLINE_ACTIVIDAD_MINUTOS,
       actualizada por InactividadMiddleware en cada navegación real).

    Retorna lista de dicts {id, username, full_name, is_staff, via} donde
    via es 'ws', 'http' o 'ambas'. Solo personal interno activo
    (is_staff o grupo Administrador/Tutor).
    """
    from datetime import timedelta
    from django.contrib.auth.models import User
    from django.db.models import Q
    from django.utils import timezone

    por_id = {}
    for u in get_online_users_sync():
        por_id[u['id']] = {
            'id': u['id'],
            'username': u.get('username', ''),
            'full_name': u.get('full_name', ''),
            'is_staff': bool(u.get('is_staff', False)),
            'via': 'ws',
        }

    limite = timezone.now() - timedelta(minutes=ONLINE_ACTIVIDAD_MINUTOS)
    recientes = User.objects.filter(
        Q(is_staff=True) | Q(groups__name__in=['Administrador', 'Tutor']),
        is_active=True,
        perfil__ultima_conexion__gte=limite,
    ).distinct()
    for u in recientes:
        if u.id in por_id:
            por_id[u.id]['via'] = 'ambas'
        else:
            por_id[u.id] = {
                'id': u.id,
                'username': u.username,
                'full_name': u.get_full_name() or u.username,
                'is_staff': u.is_staff,
                'via': 'http',
            }
        # Completar nombres si el socket no los trajo
        if not por_id[u.id]['username']:
            por_id[u.id]['username'] = u.username
        if not por_id[u.id]['full_name']:
            por_id[u.id]['full_name'] = u.get_full_name() or u.username
        por_id[u.id]['is_staff'] = por_id[u.id]['is_staff'] or u.is_staff

    return list(por_id.values())


def resumen_online_para(user, limite=5):
    """Usuarios para el desplegable de mensajes (sync).

    Retorna dicts {id, nombre, directa_id, en_linea} excluyendo al propio
    usuario. `directa_id` es la sala directa existente con ese usuario
    (para abrir la ventana flotante) o None (se crea al visitar
    iniciar_chat_directo).

    Los tutores ven a TODOS los admins (en línea primero) para poder
    escribirles directo; los admins ven al personal en línea.
    """
    todos = [u for u in obtener_en_linea() if u['id'] != user.pk]
    from django.contrib.auth.models import User as _User
    from django.db.models import Q
    try:
        viewer_es_admin = (
            user.is_superuser or user.is_staff
            or _User.objects.filter(pk=user.pk).filter(
                Q(is_staff=True) | Q(groups__name='Administrador')).exists()
        )
    except Exception:
        viewer_es_admin = False
    if viewer_es_admin:
        de_linea = todos[:limite]
        base = [(u['id'], u.get('full_name') or u.get('username') or 'Usuario', True) for u in de_linea]
        total = len(todos)
    else:
        try:
            admins = list(_User.objects.filter(
                Q(is_staff=True) | Q(is_superuser=True) | Q(groups__name='Administrador'),
                is_active=True,
            ).exclude(pk=user.pk).distinct().order_by('first_name', 'username'))
        except Exception:
            admins = []
        online_ids = {u['id'] for u in todos}
        base = [(
            a.pk,
            a.get_full_name() or a.username,
            a.pk in online_ids,
        ) for a in admins]
        base.sort(key=lambda x: (not x[2], x[1].lower()))
        base = base[:limite * 2]
        total = len(online_ids)
    if not base:
        return [], 0
    from chat_interno.models import SalaChat
    mapa = {}
    for sala in SalaChat.objects.filter(
        tipo='directa', participantes=user
    ).prefetch_related('participantes'):
        for p in sala.participantes.all():
            if p.id != user.pk and p.id not in mapa:
                mapa[p.id] = sala.id
    resumen = [{
        'id': uid,
        'nombre': nombre,
        'directa_id': mapa.get(uid),
        'en_linea': en_linea,
    } for uid, nombre, en_linea in base]
    return resumen, total