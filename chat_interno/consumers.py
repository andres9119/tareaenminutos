"""
Chat Consumer — Django Channels WebSocket para chat en tiempo real.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer para el chat interno por sala."""

    async def connect(self):
        self.sala_id = self.scope['url_route']['kwargs']['sala_id']
        self.group_name = f"chat_{self.sala_id}"
        self.user = self.scope['user']

        # Rechazar conexiones de usuarios no autenticados
        if not self.user.is_authenticated:
            await self.close()
            return

        # Verificar que el usuario tiene acceso a esta sala
        tiene_acceso = await self.verificar_acceso()
        if not tiene_acceso:
            await self.close()
            return

        # Unirse al grupo del canal
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Enviar historial de mensajes recientes
        mensajes = await self.get_mensajes_recientes()
        await self.send(text_data=json.dumps({
            'type': 'historial',
            'mensajes': mensajes,
            'username_actual': self.user.get_full_name() or self.user.username,
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        """Recibir mensaje del WebSocket y distribuirlo al grupo."""
        data = json.loads(text_data)
        tipo = data.get('type', 'mensaje')

        if tipo == 'mensaje':
            contenido = data.get('message', '').strip()
            if not contenido:
                return

            # Canal general = solo anuncios de admins; salas de solicitud son de doble vía
            if not await self.puede_escribir():
                return

            # Guardar en DB
            mensaje = await self.guardar_mensaje(contenido)

            # Distribuir a todo el grupo
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'chat_message',
                    'mensaje': mensaje,
                }
            )

        elif tipo == 'typing':
            # Indicador de escritura (no se persiste); quien no puede escribir no lo envía
            if not await self.puede_escribir():
                return
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'typing_indicator',
                    'usuario': self.user.get_full_name() or self.user.username,
                    'usuario_id': self.user.id,
                }
            )

    async def chat_message(self, event):
        """Enviar mensaje a WebSocket del cliente."""
        m = event['mensaje']
        await self.send(text_data=json.dumps({
            'type': 'mensaje',
            'autor_id': m.get('autor_id'),
            'username': m.get('autor_nombre', ''),
            'message': m.get('contenido', ''),
            'created_at': m.get('created_at', ''),
            'created_at_full': m.get('created_at_full', ''),
        }))

    async def typing_indicator(self, event):
        """Enviar indicador de escritura (solo a otros usuarios)."""
        if event['usuario_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'usuario': event['usuario']
            }))

    @database_sync_to_async
    def verificar_acceso(self):
        from chat_interno.models import SalaChat
        try:
            sala = SalaChat.objects.get(pk=self.sala_id)
            # Admins tienen acceso total
            if self.user.is_staff or self.user.groups.filter(name='Administrador').exists():
                return True
            # Salas de solicitud: solo el tutor asignado (las abiertas no dan acceso)
            if sala.solicitud:
                return sala.solicitud.tutor_asignado == self.user
            # Salas generales: requiere ser participante
            return sala.participantes.filter(pk=self.user.pk).exists()
        except SalaChat.DoesNotExist:
            return False

    @database_sync_to_async
    def puede_escribir(self):
        """Canal General = anuncios: solo admins escriben.
        Las salas de solicitud son de doble vía (tutor asignado ya validado)."""
        from chat_interno.models import SalaChat
        try:
            sala = SalaChat.objects.get(pk=self.sala_id)
        except SalaChat.DoesNotExist:
            return False
        if sala.solicitud_id:
            return True
        return self.user.is_staff or self.user.groups.filter(name='Administrador').exists()

    @database_sync_to_async
    def guardar_mensaje(self, contenido):
        from chat_interno.models import SalaChat, MensajeChat
        sala = SalaChat.objects.get(pk=self.sala_id)
        mensaje = MensajeChat.objects.create(
            sala=sala,
            autor=self.user,
            contenido=contenido,
            tipo='texto'
        )
        return mensaje.to_dict()

    @database_sync_to_async
    def get_mensajes_recientes(self):
        from chat_interno.models import SalaChat
        try:
            sala = SalaChat.objects.get(pk=self.sala_id)
            mensajes = sala.mensajes.order_by('-created_at')[:50]
            return [m.to_dict() for m in reversed(list(mensajes))]
        except SalaChat.DoesNotExist:
            return []
