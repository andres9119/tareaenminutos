"""
Views para chat interno en tiempo real.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q, Max
import os
from django.http import JsonResponse
from .models import SalaChat, MensajeChat
from solicitudes.models import SolicitudAcademica
from accounts.decorators import admin_o_tutor_required
from accounts.utils import es_admin
from .context_processors import _salas_con_datos


def _marcar_leidos_y_avisar(sala, user):
    """Marca como leídos los mensajes ajenos + sus notificaciones de chat.

    Además: (a) re-estampa la ventana anti-spam de emails (mientras lees
    activamente no salen correos inmediatos); (b) avisa por WebSocket al
    grupo con los ids recién leídos para que el autor vea "Leído" en vivo.
    Retorna la lista de ids recién marcados.
    """
    ajenos = sala.mensajes.exclude(autor=user).exclude(leido_por=user)
    ids = list(ajenos.values_list('pk', flat=True))
    for m in ajenos:
        m.leido_por.add(user)

    from django.urls import reverse as _reverse
    from notificaciones.models import Notificacion as _Notificacion
    _Notificacion.objects.filter(
        destinatario=user,
        tipo='mensaje_chat',
        url_accion=_reverse('sala_chat', args=[sala.pk]),
    ).update(leida=True)

    if ids:
        try:
            from notificaciones.signals import _marcar_ventana_chat
            _marcar_ventana_chat(user)
        except Exception:
            pass
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            async_to_sync(get_channel_layer().group_send)(
                f"chat_{sala.pk}",
                {'type': 'mensajes_leidos', 'lector_id': user.pk, 'mensaje_ids': ids},
            )
        except Exception:
            pass
    return ids


@admin_o_tutor_required
def sala_chat(request, pk):
    """Vista de una sala de chat específica."""
    from django.http import Http404
    user_is_admin = es_admin(request.user)

    sala = get_object_or_404(SalaChat, pk=pk)

    # Chats directos: SOLO participantes (ni admins ajenos).
    if sala.tipo == 'directa':
        if not sala.participantes.filter(pk=request.user.pk).exists():
            raise Http404('No tienes acceso a esta sala.')

    # Chat de solicitud: solo existe cuando ya hay tutor asignado (para todos,
    # incluido el admin; el consumer WebSocket aplica la misma regla).
    if sala.solicitud_id and not sala.solicitud.tutor_asignado:
        raise Http404('El chat se habilita al asignar un tutor.')

    if not user_is_admin:
        # Salas de solicitud: solo el tutor asignado.
        # Salas generales (canal de anuncios): todo el personal interno.
        # Salas directas: solo participantes.
        if not _usuario_puede_ver_sala(request.user, sala):
            raise Http404('No tienes acceso a esta sala.')

    # Agregar usuario como participante si aún no está
    sala.participantes.add(request.user)

    # Marcar como leídos los mensajes ajenos (+ avisar "Leído" en vivo)
    _marcar_leidos_y_avisar(sala, request.user)

    # Últimos 50 mensajes (se actualizan via WebSocket)
    mensajes = sala.mensajes.select_related('autor').prefetch_related('leido_por').order_by('created_at')[:50]

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
        leido = m.leido_por.exclude(pk=m.autor_id).exists() if propio else False
        motivo_bloqueo = m.motivo_no_editable(request.user) if propio else None
        entradas.append({
            'mensaje': m,
            'propio': propio,
            'mostrar_autor': mostrar_autor,
            'etiqueta_fecha': etiqueta_fecha,
            'hora': local.strftime('%H:%M'),
            'es_imagen': _adjunto_es_imagen(m),
            'es_pdf': _adjunto_es_pdf(m),
            'leido': leido,
            'editable': propio and m.puede_editar(request.user),
            'eliminable': propio and m.puede_eliminar(request.user),
            'motivo_bloqueo': motivo_bloqueo,
        })
        fecha_anterior = fecha

    context = {
        'sala': sala,
        'nombre_chat': sala.get_nombre_para(request.user),
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
    # Chats directos: SOLO participantes (ni admins ajenos).
    if sala.tipo == 'directa':
        if not sala.participantes.filter(pk=request.user.pk).exists():
            raise Http404('No tienes acceso a esta sala.')
    # Chat de solicitud: solo existe cuando ya hay tutor asignado (para todos).
    if sala.solicitud_id and not sala.solicitud.tutor_asignado:
        raise Http404('El chat se habilita al asignar un tutor.')
    if not user_is_admin:
        if sala.solicitud and sala.solicitud.tutor_asignado != request.user:
            raise Http404('No tienes acceso a esta sala.')

    sala.participantes.add(request.user)
    _marcar_leidos_y_avisar(sala, request.user)

    mensajes = sala.mensajes.select_related('autor').prefetch_related('leido_por').order_by('-created_at')[:50]
    datos = [m.to_dict() for m in reversed(list(mensajes))]

    return JsonResponse({
        'id': sala.pk,
        'nombre': sala.get_nombre_para(request.user),
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
        # Chats directos ajenos: ni los admins los ven en la lista.
        base = SalaChat.objects.filter(
            ~Q(tipo='directa') | Q(participantes=request.user)
        ).distinct()
    else:
        base = SalaChat.objects.filter(
            Q(tipo='general') | Q(solicitud__tutor_asignado=request.user) |
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
            'nombre': s.get_nombre_para(request.user),
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
    # El tráfico constante de este endpoint sirve de motor para los resúmenes
    # de email de chat pendientes (anti-spam), aunque el destinatario esté off.
    from notificaciones.signals import flush_resumenes_chat
    flush_resumenes_chat()
    chats = _salas_con_datos(request.user)
    from accounts.presence import resumen_online_para
    online_resumen, online_total = resumen_online_para(request.user)
    return JsonResponse({
        'total_no_leidos': sum(d['no_leidos'] for d in chats),
        'online': online_resumen,
        'online_total': online_total,
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


@admin_o_tutor_required
def sala_chat_pdf(request, pk):
    """Descarga de la conversación de una sala en PDF (solo autorizados)."""
    from django.http import Http404
    from django.http import HttpResponse
    from django.utils import timezone
    user_is_admin = es_admin(request.user)

    sala = get_object_or_404(SalaChat, pk=pk)
    # Chats directos: SOLO participantes (ni admins ajenos).
    if sala.tipo == 'directa':
        if not sala.participantes.filter(pk=request.user.pk).exists():
            raise Http404('No tienes acceso a esta sala.')
    if not user_is_admin:
        if sala.solicitud and sala.solicitud.tutor_asignado != request.user:
            raise Http404('No tienes acceso a esta sala.')

    mensajes = sala.mensajes.select_related('autor').order_by('created_at')

    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

    verde = HexColor('#06aa44')
    gris = HexColor('#5f6b7e')

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        'TituloChat', parent=styles['Title'],
        fontSize=18, fontName='Helvetica-Bold', textColor=verde, spaceAfter=6,
    )
    subtitulo_style = ParagraphStyle(
        'SubtituloChat', parent=styles['Normal'],
        fontSize=10, textColor=gris, spaceAfter=14,
    )
    msg_style = ParagraphStyle(
        'MensajeChat', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, leading=14, alignment=TA_LEFT,
        spaceBefore=2, spaceAfter=4,
    )
    autor_style = ParagraphStyle(
        'AutorChat', parent=msg_style,
        fontName='Helvetica-Bold', fontSize=9.5, textColor=verde, spaceBefore=8, spaceAfter=1,
    )

    nombre_sala = sala.nombre
    if sala.solicitud:
        nombre_sala = f"{sala.solicitud.codigo} — {sala.solicitud.titulo}"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=0.75 * inch, leftMargin=0.75 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title=f"Conversación - {sala.nombre}",
    )
    story = [Paragraph('Tarea en Minutos — Conversación', titulo_style),
             Paragraph(f"<b>{_esc_pdf(nombre_sala)}</b>", subtitulo_style),
             HRFlowable(width='100%', thickness=1, color=verde, spaceAfter=12)]

    for m in mensajes:
        autor = (m.autor.get_full_name() or m.autor.username) if m.autor else 'Usuario eliminado'
        local = timezone.localtime(m.created_at)
        hora = local.strftime('%d/%m/%Y %H:%M')
        story.append(Paragraph(
            _esc_pdf(f"{autor} — {hora}"), autor_style))
        story.append(Paragraph(
            _esc_pdf(m.contenido).replace('\n', '<br/>'), msg_style))

    if not mensajes.exists():
        story.append(Paragraph('<i>Sin mensajes en esta conversación.</i>', msg_style))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    filename = f"conversacion_{sala.pk}.pdf"
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _esc_pdf(texto):
    from django.utils.html import escape
    return escape(texto or '')


def _usuario_puede_ver_sala(user, sala):
    """Control de acceso a una sala (copiado de sala_chat / consumers.verificar_acceso)."""
    # Salas directas: SOLO participantes (ni admins ajenos)
    if sala.tipo == 'directa':
        return sala.participantes.filter(pk=user.pk).exists()
    # Salas de solicitud: SOLO si hay tutor asignado
    if sala.solicitud:
        if not sala.solicitud.tutor_asignado:
            return False
        if es_admin(user):
            return True
        return sala.solicitud.tutor_asignado == user
    if es_admin(user):
        return True
    # Sala general: todo el personal interno
    return user.is_staff or user.groups.filter(name__in=['Administrador', 'Tutor']).exists()


def _usuario_puede_escribir(user, sala):
    """Canal General = anuncios (solo admins). Solicitud/Directa = doble vía."""
    if sala.solicitud_id or sala.tipo == 'directa':
        return True
    return es_admin(user)


def _adjunto_es_imagen(m):
    if not m.archivo_adjunto:
        return False
    import os
    ext = os.path.splitext(m.archivo_nombre or m.archivo_adjunto.name)[1].lower().lstrip('.')
    return ext in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg')


def _adjunto_es_pdf(m):
    if not m.archivo_adjunto:
        return False
    import os
    ext = os.path.splitext(m.archivo_nombre or m.archivo_adjunto.name)[1].lower().lstrip('.')
    return ext == 'pdf'


@admin_o_tutor_required
def chat_adjunto_subir(request, pk):
    """Sube un archivo adjunto a una sala de chat y lo distribuye por WebSocket."""
    from django.http import Http404, JsonResponse
    from django.views.decorators.http import require_POST
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    sala = get_object_or_404(SalaChat, pk=pk)
    if not _usuario_puede_ver_sala(request.user, sala):
        raise Http404('No tienes acceso a esta sala.')
    if not _usuario_puede_escribir(request.user, sala):
        return JsonResponse({'ok': False, 'error': 'No puedes enviar archivos en este canal.'}, status=403)

    archivo = request.FILES.get('archivo')
    contenido = (request.POST.get('mensaje') or '').strip()
    if not archivo:
        return JsonResponse({'ok': False, 'error': 'Debes seleccionar un archivo.'}, status=400)

    from django.utils.text import get_valid_filename
    nombre = get_valid_filename(archivo.name)
    ext = os.path.splitext(nombre)[1].lower()

    _CHAT_ALLOWED = [
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg',
        '.zip', '.rar', '.7z', '.txt', '.csv',
    ]
    if archivo.size > 20 * 1024 * 1024:
        return JsonResponse({'ok': False, 'error': 'El archivo no puede superar los 20 MB.'}, status=400)
    if ext not in _CHAT_ALLOWED:
        return JsonResponse({
            'ok': False,
            'error': f'Tipo de archivo no permitido. Aceptados: {", ".join(_CHAT_ALLOWED)}'
        }, status=400)

    mensaje = MensajeChat.objects.create(
        sala=sala,
        autor=request.user,
        contenido=contenido or f"Archivo: {nombre}",
        tipo='archivo',
        archivo_adjunto=archivo,
        archivo_nombre=nombre,
    )

    paquete = mensaje.to_dict()
    # Push por WebSocket al grupo de la sala
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
    try:
        async_to_sync(channel_layer.group_send)(
            sala.channel_group_name,
            {'type': 'chat_message', 'mensaje': paquete},
        )
    except Exception:
        pass

    return JsonResponse({'ok': True, 'mensaje': paquete})


@admin_o_tutor_required
def chat_adjunto_descargar(request, mensaje_id):
    """Descarga (o preview inline) del archivo adjunto de un mensaje de chat."""
    from django.http import Http404, HttpResponse, FileResponse
    import os, mimetypes
    m = get_object_or_404(MensajeChat, pk=mensaje_id)
    sala = m.sala
    if not _usuario_puede_ver_sala(request.user, sala):
        raise Http404('No tienes acceso a este archivo.')
    if not m.archivo_adjunto:
        raise Http404('Este mensaje no tiene archivo adjunto.')

    inline = request.GET.get('inline') == '1'
    nombre = m.archivo_nombre or os.path.basename(m.archivo_adjunto.name)
    tipo_mime = mimetypes.guess_type(nombre)[0] or 'application/octet-stream'

    if inline:
        # Leer y servir inline (preview de imágenes sin forzar descarga)
        try:
            with m.archivo_adjunto.open('rb') as f:
                datos = f.read()
        except Exception:
            raise Http404('No se pudo leer el archivo.')
        response = HttpResponse(datos, content_type=tipo_mime)
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(nombre)}"'
        return response

    resp = FileResponse(m.archivo_adjunto, content_type=tipo_mime)
    resp['Content-Disposition'] = f'attachment; filename="{os.path.basename(nombre)}"'
    return resp
