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

        elif tipo == 'editar_mensaje':
            mensaje_id = data.get('mensaje_id')
            nuevo_contenido = data.get('contenido', '').strip()
            if not mensaje_id or not nuevo_contenido:
                return
            mensaje, motivo = await self.editar_mensaje(mensaje_id, nuevo_contenido)
            if mensaje:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'mensaje_editado',
                        'mensaje': mensaje,
                    }
                )
            elif motivo:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'mensaje': motivo,
                }))

        elif tipo == 'eliminar_mensaje':
            mensaje_id = data.get('mensaje_id')
            if not mensaje_id:
                return
            ok, motivo = await self.eliminar_mensaje(mensaje_id)
            if ok:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'mensaje_eliminado',
                        'mensaje_id': mensaje_id,
                    }
                )
            elif motivo:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'mensaje': motivo,
                }))

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
            'id': m.get('id'),
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
            'editado': m.get('editado'),
            'eliminado': m.get('eliminado', False),
            'leido': m.get('leido', False),
        }))

    async def typing_indicator(self, event):
        """Enviar indicador de escritura (solo a otros usuarios)."""
        if event['usuario_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'usuario': event['usuario']
            }))

    async def mensaje_editado(self, event):
        """Notificar a todos que un mensaje fue editado."""
        m = event['mensaje']
        await self.send(text_data=json.dumps({
            'type': 'mensaje_editado',
            'mensaje': m,
        }))

    async def mensaje_eliminado(self, event):
        """Notificar a todos que un mensaje fue eliminado."""
        await self.send(text_data=json.dumps({
            'type': 'mensaje_eliminado',
            'mensaje_id': event['mensaje_id'],
        }))

    async def mensajes_leidos(self, event):
        """Avisar que el lector leyó mensajes (para pintar "Leído" en vivo)."""
        if event.get('lector_id') == self.user.id:
            return
        await self.send(text_data=json.dumps({
            'type': 'mensajes_leidos',
            'mensaje_ids': event.get('mensaje_ids', []),
        }))

    @database_sync_to_async
    def editar_mensaje(self, mensaje_id, nuevo_contenido):
        from chat_interno.models import MensajeChat
        from django.utils import timezone
        try:
            mensaje = MensajeChat.objects.get(pk=mensaje_id, sala_id=self.sala_id)
            motivo = mensaje.motivo_no_editable(self.user)
            if motivo is not None:
                if motivo == 'ajeno':
                    return None, 'No puedes editar mensajes de otros usuarios.'
                if motivo == 'leido':
                    return None, 'Ya fue leído por el destinatario: no se puede editar.'
                if motivo == 'ya_editado':
                    return None, 'Este mensaje ya fue editado una vez.'
                return None, 'Ya pasó el tiempo de edición (15 minutos).'
            mensaje.contenido = nuevo_contenido
            mensaje.editado = timezone.now()
            mensaje.save(update_fields=['contenido', 'editado'])
            return mensaje.to_dict(), None
        except MensajeChat.DoesNotExist:
            return None, None

    @database_sync_to_async
    def eliminar_mensaje(self, mensaje_id):
        from chat_interno.models import MensajeChat
        try:
            mensaje = MensajeChat.objects.get(pk=mensaje_id, sala_id=self.sala_id)
            if mensaje.autor_id != self.user.pk and not mensaje._admin_override(self.user):
                return False, 'No puedes eliminar mensajes de otros usuarios.'
            if not mensaje.puede_eliminar(self.user):
                return False, 'Ya fue leído por el destinatario: no se puede eliminar.'
            mensaje.eliminado = True
            mensaje.contenido = 'Este mensaje fue eliminado.'
            mensaje.save(update_fields=['eliminado', 'contenido'])
            return True, None
        except MensajeChat.DoesNotExist:
            return False, None

    @database_sync_to_async
    def verificar_acceso(self):
        from chat_interno.models import SalaChat
        try:
            sala = SalaChat.objects.get(pk=self.sala_id)
            # Salas directas: SOLO participantes (ni admins ajenos),
            # y nunca solo entre tutores.
            if sala.tipo == 'directa':
                if not sala.participantes.filter(pk=self.user.pk).exists():
                    return False
                return not sala.es_directa_sin_admin()
            # Salas de solicitud: SOLO si hay tutor asignado (y el usuario es ese tutor o admin)
            if sala.solicitud:
                if not sala.solicitud.tutor_asignado:
                    return False
                # Admin siempre puede; tutor solo si es el asignado
                if self.user.is_staff or self.user.groups.filter(name='Administrador').exists():
                    return True
                return sala.solicitud.tutor_asignado == self.user
            # Admins tienen acceso a salas generales
            if self.user.is_staff or self.user.groups.filter(name='Administrador').exists():
                return True
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
            mensajes = sala.mensajes.select_related('autor').prefetch_related('leido_por').order_by('-created_at')[:50]
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
