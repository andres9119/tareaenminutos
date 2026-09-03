"""
Chat Consumer — Django Channels WebSocket para chat en tiempo real.
"""

import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from accounts.presence import mark_online, mark_offline, heartbeat


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer para el chat interno por sala."""

    async def connect(self):
        self.sala_id = self.scope['url_route']['kwargs']['sala_id']
        self.group_name = f"chat_{self.sala_id}"
        self.user = self.scope['user']
        self._heartbeat_task = None

        # Rechazar conexiones de usuarios no autenticados
        if not self.user.is_authenticated:
            await self.close()
            return

        # Verificar que el usuario tiene acceso a esta sala
        tiene_acceso = await self.verificar_acceso()
        if not tiene_acceso:
            await self.close()
            return

        # Marcar usuario como online
        user_info = {
            'username': self.user.username,
            'full_name': self.user.get_full_name() or self.user.username,
            'is_staff': self.user.is_staff,
        }
        await mark_online(self.user.id, user_info)

        # Iniciar heartbeat para renovar TTL
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

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
        # Cancelar heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Marcar offline solo si no tiene otras conexiones activas
        # (simplificación: marcamos offline al desconectar de esta sala)
        await mark_offline(self.user.id)
        
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
            'tipomsg': m.get('tipo', 'texto'),
            'adjunto_url': m.get('adjunto_url', ''),
            'adjunto_nombre': m.get('adjunto_nombre', ''),
            'adjunto_es_imagen': m.get('adjunto_es_imagen', False),
            'adjunto_es_pdf': m.get('adjunto_es_pdf', False),
            'created_at': m.get('created_at', ''),
            'fecha': m.get('fecha', ''),
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
            # Salas directas: solo participantes
            if sala.tipo == 'directa':
                return sala.participantes.filter(pk=self.user.pk).exists()
            # Salas de solicitud: solo el tutor asignado (las abiertas no dan acceso)
            if sala.solicitud:
                return sala.solicitud.tutor_asignado == self.user
            # Salas generales (anuncios): todo el personal interno
            return (
                self.user.is_staff
                or self.user.groups.filter(name__in=['Administrador', 'Tutor']).exists()
                or sala.participantes.filter(pk=self.user.pk).exists()
            )
        except SalaChat.DoesNotExist:
            return False

    @database_sync_to_async
    def puede_escribir(self):
        """Canal General = anuncios: solo admins escriben.
        Salas de solicitud y directas son de doble vía."""
        from chat_interno.models import SalaChat
        try:
            sala = SalaChat.objects.get(pk=self.sala_id)
        except SalaChat.DoesNotExist:
            return False
        if sala.solicitud_id or sala.tipo == 'directa':
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

    async def _heartbeat_loop(self):
        """Renovar TTL de presencia cada 30 segundos."""
        try:
            while True:
                await asyncio.sleep(30)
                await heartbeat(self.user.id)
        except asyncio.CancelledError:
            pass
