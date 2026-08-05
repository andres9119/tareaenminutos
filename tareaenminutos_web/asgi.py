"""
ASGI config para tareaenminutos_web con soporte WebSocket via Django Channels.
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tareaenminutos_web.settings')

# Importar el routing de WebSockets
import chat_interno.routing
import notificaciones.routing

application = ProtocolTypeRouter({
    # HTTP requests → Django WSGI app
    'http': get_asgi_application(),

    # WebSocket connections → Channels consumers
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                chat_interno.routing.websocket_urlpatterns +
                notificaciones.routing.websocket_urlpatterns
            )
        )
    ),
})
