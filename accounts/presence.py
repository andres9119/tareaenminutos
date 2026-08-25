"""
Presence tracking para usuarios online — usa Redis directamente (channel layer).
Guarda user_id con TTL renovable. Admin puede consultar lista de usuarios online.
"""
import json
import time
from django.conf import settings
from django.core.cache import cache


PRESENCE_KEY = "presence:online_users"
PRESENCE_TTL = 300  # 5 minutos (debe ser mayor que heartbeat interval)


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