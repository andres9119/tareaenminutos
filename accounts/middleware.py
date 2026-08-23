"""
Middleware de inactividad real (10 minutos, pedido del cliente 22 Ago 2026).

La sesión solo se mantiene viva con NAVIGACIÓN REAL. El tráfico en background
que genera el propio JavaScript (polling del messenger cada 20 s, fetch de
historial de las ventanas de chat) NO cuenta como actividad y NO renueva la
sesión: antes, con SESSION_SAVE_EVERY_REQUEST=True, una pestaña abierta
jamás expiraba aunque el usuario no estuviera presente.

Funcionamiento:
- Peticiones autenticadas a rutas "reales" (no background): si pasaron más de
  settings.SESSION_COOKIE_AGE segundos desde la última navegación real,
  se cierra la sesión (logout). Si no, se actualiza _ultima_actividad.
- Rutas background: no tocan la sesión en absoluto (ni evalúan ni renuevan).
- La sesión además tiene su propia caducidad (SESSION_COOKIE_AGE desde el
  último guardado), por lo que un usuario inactivo queda anónimo aunque solo
  use rutas background.
"""

import re
import time

from django.conf import settings
from django.contrib.auth import logout

# Tráfico generado por JS en background: polling del messenger flotante e
# historial JSON de las ventanas de chat. No debe mantener la sesión viva.
_RUTAS_BACKGROUND = (
    re.compile(r'^/app/chat/datos/$'),
    re.compile(r'^/app/chat/\d+/mensajes/$'),
)


class InactividadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            ruta = request.path
            if not any(p.match(ruta) for p in _RUTAS_BACKGROUND):
                ahora = int(time.time())
                ultima = request.session.get('_ultima_actividad')
                if ultima and (ahora - ultima) > settings.SESSION_COOKIE_AGE:
                    # Inactivo demasiado tiempo sin navegación real: fuera.
                    logout(request)
                else:
                    # Marca actividad; como modifica la sesión, Django la
                    # guarda al final del ciclo y renueva la cookie.
                    request.session['_ultima_actividad'] = ahora
        return self.get_response(request)
