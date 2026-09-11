"""
Notification Consumer — WebSocket para notificaciones en tiempo real.
"""

import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from accounts.presence import mark_online, mark_offline, heartbeat

# Vida de presencia: ping cada 15 s, 8 s de gracia para el pong.
# Tráfico mínimo (2 tramas por conexión cada 15 s); una conexión muerta
# se detecta en ~23 s como máximo.
PING_CADA_SEG = 15
PONG_ESPERA_SEG = 8


class NotificacionConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer para notificaciones push de usuario."""

    async def connect(self):
        self.user = self.scope['user']
        self._heartbeat_task = None
        self._pong_ok = True

        if not self.user.is_authenticated:
            await self.close()
            return

        # Marcar usuario como online
        user_info = {
            'username': self.user.username,
            'full_name': self.user.get_full_name() or self.user.username,
            'is_staff': self.user.is_staff,
        }
        await mark_online(self.user.id, user_info)

        # Iniciar heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Canal personal del usuario
        self.group_name = f"user_{self.user.id}_notif"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Cancelar heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Marcar offline
        await mark_offline(self.user.id)

        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        """Marcar notificación como leída. También responde el ping de vida."""
        data = json.loads(text_data)
        if data.get('type') == 'pong':
            self._pong_ok = True
            return
        if data.get('type') == 'marcar_leida':
            notif_id = data.get('notif_id')
            if notif_id:
                await self.marcar_leida(notif_id)

    async def notificacion_nueva(self, event):
        """Enviar notificación push al cliente."""
        await self.send(text_data=json.dumps({
            'type': 'notificacion',
            'notif': event['notif']
        }))

    @staticmethod
    async def marcar_leida(notif_id):
        from channels.db import database_sync_to_async
        from notificaciones.models import Notificacion

        @database_sync_to_async
        def _marcar():
            try:
                n = Notificacion.objects.get(pk=notif_id)
                n.marcar_leida()
            except Notificacion.DoesNotExist:
                pass

        await _marcar()

    async def _heartbeat_loop(self):
        """Renovar TTL de presencia cada 15 segundos, exigiendo pong.

        Sin respuesta en 8 s se cierra la conexión para no dejar
        fantasmas "en línea"."""
        try:
            while True:
                await asyncio.sleep(PING_CADA_SEG)
                self._pong_ok = False
                try:
                    await self.send(text_data=json.dumps({'type': 'ping'}))
                except Exception:
                    break
                await asyncio.sleep(PONG_ESPERA_SEG)
                if not self._pong_ok:
                    try:
                        await self.close()
                    except Exception:
                        pass
                    break
                await heartbeat(self.user.id)
        except asyncio.CancelledError:
            pass
