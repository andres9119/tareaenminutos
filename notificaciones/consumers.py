"""
Notification Consumer — WebSocket para notificaciones en tiempo real.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer


class NotificacionConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer para notificaciones push de usuario."""

    async def connect(self):
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        # Canal personal del usuario
        self.group_name = f"user_{self.user.id}_notif"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        """Marcar notificación como leída."""
        data = json.loads(text_data)
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
