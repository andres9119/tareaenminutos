"""
Views para chat interno en tiempo real.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q, Max
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
        # Salas de solicitud: solo el tutor asignado.
        # Salas generales (canal de anuncios): todo el personal interno.
        # Salas directas: solo participantes.
        if sala.tipo == 'directa':
            if not sala.participantes.filter(pk=request.user.pk).exists():
                raise Http404('No tienes acceso a esta sala.')
        elif sala.solicitud and sala.solicitud.tutor_asignado != request.user:
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
        # Canal General = anuncios: solo admins escriben; salas de solicitud/directa son de doble vía
        'puede_escribir': user_is_admin or bool(sala.solicitud_id) or sala.tipo == 'directa',
    }
    return render(request, 'private/chat_interno/sala.html', context)


@admin_o_tutor_required
def chat_mensajes_json(request, pk):
    """Historial de una sala en JSON para las ventanas flotantes.
    Marca los mensajes ajenos como leídos (igual que sala_chat)."""
    from django.http import Http404, JsonResponse
    from django.utils import timezone
    user_is_admin = es_admin(request.user)

    sala = get_object_or_404(SalaChat, pk=pk)
    if not user_is_admin:
        if sala.tipo == 'directa':
            if not sala.participantes.filter(pk=request.user.pk).exists():
                raise Http404('No tienes acceso a esta sala.')
        elif sala.solicitud and sala.solicitud.tutor_asignado != request.user:
            raise Http404('No tienes acceso a esta sala.')

    sala.participantes.add(request.user)
    for m in sala.mensajes.exclude(autor=request.user):
        m.leido_por.add(request.user)

    mensajes = sala.mensajes.select_related('autor').order_by('-created_at')[:50]
    hoy = timezone.localdate()
    datos = []
    for m in reversed(list(mensajes)):
        local = timezone.localtime(m.created_at)
        autor_nombre = ''
        if m.autor:
            autor_nombre = m.autor.get_full_name() or m.autor.username
        else:
            autor_nombre = 'Usuario eliminado'
        datos.append({
            'autor_id': m.autor_id,
            'autor_nombre': autor_nombre,
            'contenido': m.contenido,
            'hora': local.strftime('%H:%M'),
            'fecha': local.strftime('%d/%m/%Y'),
            'created_at_full': m.created_at.isoformat(),
        })

    return JsonResponse({
        'id': sala.pk,
        'nombre': sala.nombre,
        'tipo': sala.tipo,
        'puede_escribir': user_is_admin or bool(sala.solicitud_id) or sala.tipo == 'directa',
        'mensajes': datos,
    })


@admin_o_tutor_required
def iniciar_chat_directo(request, user_id):
    """Crea o reutiliza un chat directo entre el usuario actual y el usuario indicado."""
    from django.contrib.auth.models import User
    from django.db.models import Q
    from django.http import Http404

    otro = get_object_or_404(User, pk=user_id, is_active=True)
    if otro == request.user:
        raise Http404('No puedes chatear contigo mismo.')

    # Buscar sala directa existente entre ambos usuarios
    sala = SalaChat.objects.filter(
        tipo='directa',
        participantes=request.user
    ).filter(
        participantes=otro
    ).first()

    if not sala:
        nombre = f"Chat: {request.user.get_full_name() or request.user.username} - {otro.get_full_name() or otro.username}"
        sala = SalaChat.objects.create(tipo='directa', nombre=nombre)
        sala.participantes.add(request.user, otro)

    return redirect('sala_chat', pk=sala.pk)


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
    """Lista de chats con buscador, filtro Activos/Cerradas/Todos y paginación.
    Pensada para cientos de salas: el flotante muestra lo caliente,
    aquí se busca y archiva."""
    from django.core.paginator import Paginator
    from django.db.models import F
    from accounts.utils import qs_base_sin_pagina

    user_is_admin = es_admin(request.user)
    q = (request.GET.get('q') or '').strip()
    filtro = request.GET.get('filtro') or 'activos'

    if user_is_admin:
        base = SalaChat.objects.all()
    else:
        base = SalaChat.objects.filter(
            Q(solicitud__isnull=True) | Q(solicitud__tutor_asignado=request.user) |
            Q(tipo='directa', participantes=request.user)
        ).distinct()

    CERRADAS = ['completada', 'cancelada']
    if filtro == 'cerradas':
        base = base.exclude(solicitud__isnull=True).filter(
            solicitud__estado__nombre__in=CERRADAS)
    elif filtro == 'activos':
        # El General siempre entra; las solicitudes cerradas van al archivo
        base = base.filter(
            Q(solicitud__isnull=True) |
            ~Q(solicitud__estado__nombre__in=CERRADAS))

    if q:
        base = base.filter(
            Q(nombre__icontains=q) |
            Q(solicitud__codigo__icontains=q) |
            Q(solicitud__titulo__icontains=q) |
            Q(solicitud__cliente_nombre__icontains=q)
        )

    salas_qs = (base.select_related('solicitud', 'solicitud__estado')
                .annotate(ultima_act=Max('mensajes__created_at'))
                .order_by(F('ultima_act').desc(nulls_last=True), '-created_at'))

    pagina = Paginator(salas_qs, 15).get_page(request.GET.get('page'))

    salas_datos = []
    for s in pagina.object_list:
        ultimo = s.last_message()
        cerrada = bool(s.solicitud and s.solicitud.estado.nombre in CERRADAS)
        autor_ultimo = ''
        if ultimo:
            if ultimo.autor:
                autor_ultimo = ultimo.autor.get_full_name() or ultimo.autor.username
            else:
                autor_ultimo = 'Usuario eliminado'
        salas_datos.append({
            'sala': s,
            'no_leidos': s.unread_count(request.user),
            'cerrada': cerrada,
            'estado': (s.solicitud.estado if s.solicitud else None),
            'codigo': s.solicitud.codigo if s.solicitud else None,
            'titulo_sol': s.solicitud.titulo if s.solicitud else None,
            'cliente': (s.solicitud.cliente_nombre if s.solicitud else '') or '',
            'ultimo': ultimo,
            'autor_ultimo': autor_ultimo,
        })

    context = {
        'salas_datos': salas_datos,
        'pagina': pagina,
        'qs_base': qs_base_sin_pagina(request, 'page'),
        'es_admin': user_is_admin,
        'q': q,
        'filtro': filtro,
    }
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
            'cerrada': d.get('cerrada', False),
            'codigo': d['codigo'],
            'titulo': d['titulo'],
            'ultimo_mensaje': d['ultimo_mensaje'],
            'ultimo_autor': d['ultimo_autor'],
            'ultimo_tiempo': d['ultimo_tiempo'].isoformat() if d['ultimo_tiempo'] else None,
            'es_propio_ultimo': d['es_propio_ultimo'],
            'no_leidos': d['no_leidos'],
        } for d in chats],
    })
