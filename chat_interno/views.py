"""
Views para chat interno en tiempo real.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from .models import SalaChat, MensajeChat
from solicitudes.models import SolicitudAcademica
from accounts.decorators import admin_o_tutor_required
from accounts.utils import es_admin
from .context_processors import _salas_con_datos


@admin_o_tutor_required
def sala_chat(request, pk):
    """Vista de una sala de chat específica."""
    from django.http import Http404
    user_is_admin = es_admin(request.user)

    sala = get_object_or_404(SalaChat, pk=pk)

    if not user_is_admin:
        # Salas de solicitud: solo el tutor asignado. Salas generales: participantes.
        if sala.solicitud:
            if sala.solicitud.tutor_asignado != request.user:
                raise Http404('No tienes acceso a esta sala.')
        else:
            if not sala.participantes.filter(pk=request.user.pk).exists():
                raise Http404('No tienes acceso a esta sala.')

    # Agregar usuario como participante si aún no está
    sala.participantes.add(request.user)

    # Marcar como leídos los mensajes ajenos al abrir la sala
    for m in sala.mensajes.exclude(autor=request.user):
        m.leido_por.add(request.user)

    # Últimos 50 mensajes (se actualizan via WebSocket)
    mensajes = sala.mensajes.select_related('autor').order_by('created_at')[:50]

    # Si es sala de solicitud, agregar al tutor asignado si existe
    if sala.solicitud and sala.solicitud.tutor_asignado:
        sala.participantes.add(sala.solicitud.tutor_asignado)

    from datetime import timedelta
    from django.utils import timezone
    hoy = timezone.localdate()
    ayer = hoy - timedelta(days=1)
    # Agrupar estilo WhatsApp: separadores de fecha y autor solo al cambiar
    entradas = []
    ultimo_autor = None
    fecha_anterior = None
    for m in mensajes:
        local = timezone.localtime(m.created_at)
        fecha = local.date()
        etiqueta_fecha = None
        if fecha != fecha_anterior:
            if fecha == hoy:
                etiqueta_fecha = 'Hoy'
            elif fecha == ayer:
                etiqueta_fecha = 'Ayer'
            else:
                etiqueta_fecha = fecha.strftime('%d/%m/%Y')
        propio = m.autor_id == request.user.pk
        mostrar_autor = False
        if not propio and m.autor_id != ultimo_autor:
            mostrar_autor = True
            ultimo_autor = m.autor_id
        entradas.append({
            'mensaje': m,
            'propio': propio,
            'mostrar_autor': mostrar_autor,
            'etiqueta_fecha': etiqueta_fecha,
            'hora': local.strftime('%H:%M'),
        })
        fecha_anterior = fecha

    context = {
        'sala': sala,
        'mensajes': mensajes,
        'entradas': entradas,
        'es_admin': user_is_admin,
        'user_id': request.user.pk,
    }
    return render(request, 'private/chat_interno/sala.html', context)


@admin_o_tutor_required
def sala_general(request):
    """Sala de chat general (el primero que entra la crea)."""
    sala, created = SalaChat.objects.get_or_create(
        tipo='general',
        defaults={'nombre': 'Canal General TEM'}
    )
    sala.participantes.add(request.user)
    return redirect('sala_chat', pk=sala.pk)


@admin_o_tutor_required
def mis_chats(request):
    """Lista de salas de chat en las que participa el usuario."""
    user_is_admin = es_admin(request.user)

    if user_is_admin:
        salas = SalaChat.objects.all().order_by('-created_at')
    else:
        salas = SalaChat.objects.filter(
            participantes=request.user
        ).order_by('-created_at')

    context = {'salas': salas, 'es_admin': user_is_admin}
    return render(request, 'private/chat_interno/mis_chats.html', context)


@admin_o_tutor_required
def datos_messenger(request):
    """Endpoint JSON con los chats del usuario y sus no leídos (polling del flotante)."""
    from django.utils import timezone
    chats = _salas_con_datos(request.user)
    return JsonResponse({
        'total_no_leidos': sum(d['no_leidos'] for d in chats),
        'chats': [{
            'id': d['id'],
            'nombre': d['nombre'],
            'tipo': d['tipo'],
            'codigo': d['codigo'],
            'titulo': d['titulo'],
            'ultimo_mensaje': d['ultimo_mensaje'],
            'ultimo_autor': d['ultimo_autor'],
            'ultimo_tiempo': d['ultimo_tiempo'].isoformat() if d['ultimo_tiempo'] else None,
            'es_propio_ultimo': d['es_propio_ultimo'],
            'no_leidos': d['no_leidos'],
        } for d in chats],
    })
