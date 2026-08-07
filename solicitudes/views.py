"""
Views para solicitudes académicas — CRUD completo + gestión de estados.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import transaction
from django.urls import reverse
from .models import SolicitudAcademica, EstadoSolicitud, HistorialEstado
from .forms import SolicitudForm, CambiarEstadoForm, FiltroSolicitudForm
from .utils import recalcular_estadisticas_tutor
from accounts.decorators import admin_required, admin_o_tutor_required, tutor_required
from accounts.utils import es_admin
from documentos.forms import DocumentoSubirForm
from documentos.models import Documento
from cotizaciones.forms import CotizacionForm
from cotizaciones.models import Cotizacion


@admin_required
def solicitud_crear(request):
    """Crear una nueva solicitud académica (solo Admin).

    Permite adjuntar uno o varios documentos (instrucción/referencia/etc.)
    en el mismo formulario de creación.
    """
    if request.method == 'POST':
        form = SolicitudForm(request.POST)
        if form.is_valid():
            # Validar los documentos adjuntos antes de crear la solicitud
            doc_forms = _procesar_doc_forms(request)
            if any(not df.is_valid() for df in doc_forms):
                for df in doc_forms:
                    for errores in df.errors.values():
                        for e in errores:
                            messages.error(request, e)
                return render(request, 'private/solicitudes/crear.html', {
                    'form': form,
                    'doc_tipos': Documento.TIPO_DOCUMENTO,
                })

            with transaction.atomic():
                solicitud = form.save(commit=False)
                solicitud.creado_por = request.user
                # Estado inicial: nueva
                estado_nueva, _ = EstadoSolicitud.objects.get_or_create(
                    nombre='nueva',
                    defaults={'etiqueta': 'Nueva', 'color_hex': '#3b82f6', 'orden': 1}
                )
                solicitud.estado = estado_nueva
                solicitud.save()

                # Guardar documentos adjuntos
                for df in doc_forms:
                    doc = df.save(commit=False)
                    doc.solicitud = solicitud
                    doc.subido_por = request.user
                    doc.nombre_original = df.cleaned_data['archivo'].name
                    doc.tamaño_bytes = df.cleaned_data['archivo'].size
                    doc.save()

                # Registrar en historial
                HistorialEstado.objects.create(
                    solicitud=solicitud,
                    estado_nuevo=estado_nueva,
                    cambiado_por=request.user,
                    comentario='Solicitud creada.'
                )
            n_docs = len(doc_forms)
            msg = f'Solicitud {solicitud.codigo} creada correctamente.'
            if n_docs:
                msg += f' Se adjuntaron {n_docs} documento(s).'
            messages.success(request, msg)
            return redirect('solicitud_detalle', pk=solicitud.pk)
    else:
        form = SolicitudForm()

    return render(request, 'private/solicitudes/crear.html', {
        'form': form,
        'doc_tipos': Documento.TIPO_DOCUMENTO,
    })


def _procesar_doc_forms(request):
    """Construye un DocumentoSubirForm por archivo subido en el formulario de creación."""
    archivos = request.FILES.getlist('archivo')
    tipos = request.POST.getlist('tipo')
    descripciones = request.POST.getlist('descripcion')
    tipos_validos = {t for t, _ in Documento.TIPO_DOCUMENTO}
    doc_forms = []
    for i, f in enumerate(archivos):
        tipo = tipos[i] if i < len(tipos) else 'instruccion'
        if tipo not in tipos_validos:
            tipo = 'instruccion'
        descripcion = descripciones[i] if i < len(descripciones) else ''
        doc_forms.append(
            DocumentoSubirForm({'tipo': tipo, 'descripcion': descripcion}, {'archivo': f})
        )
    return doc_forms


@admin_o_tutor_required
def solicitud_lista(request):
    """Lista de solicitudes con filtros (Admin ve todas, Tutor solo las suyas)."""
    form_filtro = FiltroSolicitudForm(request.GET or None)
    user_is_admin = es_admin(request.user)

    if user_is_admin:
        solicitudes = SolicitudAcademica.objects.select_related(
            'estado', 'area_conocimiento', 'tutor_asignado', 'creado_por'
        ).all()
    else:
        solicitudes = SolicitudAcademica.objects.filter(
            tutor_asignado=request.user
        ).select_related('estado', 'area_conocimiento')

    if form_filtro.is_valid():
        if form_filtro.cleaned_data.get('estado'):
            solicitudes = solicitudes.filter(estado=form_filtro.cleaned_data['estado'])
        if form_filtro.cleaned_data.get('area'):
            solicitudes = solicitudes.filter(area_conocimiento=form_filtro.cleaned_data['area'])
        if form_filtro.cleaned_data.get('fecha_desde'):
            solicitudes = solicitudes.filter(created_at__date__gte=form_filtro.cleaned_data['fecha_desde'])
        if form_filtro.cleaned_data.get('fecha_hasta'):
            solicitudes = solicitudes.filter(created_at__date__lte=form_filtro.cleaned_data['fecha_hasta'])
        if form_filtro.cleaned_data.get('buscar'):
            q = form_filtro.cleaned_data['buscar']
            solicitudes = solicitudes.filter(
                Q(codigo__icontains=q) |
                Q(titulo__icontains=q) |
                Q(cliente_nombre__icontains=q)
            )

    solicitudes = solicitudes.order_by('-created_at')
    paginator = Paginator(solicitudes, 20)
    page = request.GET.get('page', 1)
    solicitudes_page = paginator.get_page(page)
    context = {
        'solicitudes': solicitudes_page,
        'form_filtro': form_filtro,
        'es_admin': user_is_admin,
        'is_paginated': solicitudes_page.has_other_pages(),
        'estados_leyenda': list(EstadoSolicitud.objects.order_by('orden').values('etiqueta', 'color_hex')),
    }
    return render(request, 'private/solicitudes/lista.html', context)


@admin_o_tutor_required
def solicitud_detalle(request, pk):
    """Vista 360° de una solicitud: datos, documentos, cotizaciones, historial, chat."""
    user_is_admin = es_admin(request.user)

    if user_is_admin:
        solicitud = get_object_or_404(SolicitudAcademica, pk=pk)
    else:
        # Tutor solo puede ver solicitudes disponibles o asignadas a él
        from .models import EstadoSolicitud as ES
        estados_abiertos = ES.objects.filter(nombre__in=['nueva', 'en_cotizacion'])
        solicitud = get_object_or_404(
            SolicitudAcademica,
            Q(pk=pk) & (Q(tutor_asignado=request.user) | Q(estado__in=estados_abiertos))
        )

    # Sub-componentes
    documentos = solicitud.documentos.all().order_by('-created_at')
    if user_is_admin:
        cotizaciones = solicitud.cotizaciones.select_related('tutor').order_by('monto')
    else:
        cotizaciones = solicitud.cotizaciones.filter(tutor=request.user).select_related('tutor')
    # Todas las cotizaciones (de todos los tutores) para el gráfico de rangos de precios.
    cotizaciones_todas = list(solicitud.cotizaciones.select_related('tutor').order_by('monto'))
    montos = [c.monto for c in cotizaciones_todas if c.monto]
    max_monto = max(montos) if montos else 0
    precios_resumen = None
    if montos:
        precios_resumen = {
            'min': min(montos),
            'max': max(montos),
            'promedio': sum(montos) / len(montos),
        }
    historial = solicitud.historial_estados.select_related(
        'estado_anterior', 'estado_nuevo', 'cambiado_por'
    ).order_by('-created_at')[:10]

    # Sala de chat
    sala_chat = getattr(solicitud, 'sala_chat', None)

    # Formularios
    doc_form = DocumentoSubirForm()
    cotizacion_propia = cotizaciones.filter(tutor=request.user).first() if not user_is_admin else None
    cotizacion_form = CotizacionForm(instance=cotizacion_propia) if not user_is_admin and not cotizacion_propia else None

    # Tutores disponibles para asignación (solo Admin)
    tutores_disponibles = []
    if user_is_admin:
        tutores_disponibles = User.objects.filter(
            groups__name='Tutor', is_active=True
        ).select_related('perfil').order_by('first_name')

    # Estados permitidos para que el tutor actualice
    estados_tutor = EstadoSolicitud.objects.filter(nombre__in=['en_progreso', 'en_revision', 'completada'])

    context = {
        'solicitud': solicitud,
        'documentos': documentos,
        'cotizaciones': cotizaciones,
        'cotizaciones_todas': cotizaciones_todas,
        'max_monto': max_monto,
        'precios_resumen': precios_resumen,
        'historial': historial,
        'sala_chat': sala_chat,
        'doc_form': doc_form,
        'cotizacion_form': cotizacion_form,
        'cotizacion_propia': cotizacion_propia,
        'tutores_disponibles': tutores_disponibles,
        'estados_tutor': estados_tutor,
        'es_admin': user_is_admin,
    }
    return render(request, 'private/solicitudes/detalle.html', context)


@admin_required
def solicitud_editar(request, pk):
    """Editar una solicitud existente (solo Admin)."""
    solicitud = get_object_or_404(SolicitudAcademica, pk=pk)

    if request.method == 'POST':
        form = SolicitudForm(request.POST, instance=solicitud)
        if form.is_valid():
            form.save()
            messages.success(request, f'Solicitud {solicitud.codigo} actualizada.')
            return redirect('solicitud_detalle', pk=pk)
    else:
        form = SolicitudForm(instance=solicitud)

    return render(request, 'private/solicitudes/editar.html', {'form': form, 'solicitud': solicitud})


@admin_o_tutor_required
def solicitudes_disponibles(request):
    """Lista de solicitudes abiertas disponibles para cotizar (Tutores)."""
    from cotizaciones.models import Cotizacion

    ya_cotizadas = Cotizacion.objects.filter(
        tutor=request.user
    ).values_list('solicitud_id', flat=True)

    estados_abiertos = EstadoSolicitud.objects.filter(nombre__in=['nueva', 'en_cotizacion'])
    solicitudes = SolicitudAcademica.objects.filter(
        estado__in=estados_abiertos,
        tutor_asignado__isnull=True
    ).exclude(
        id__in=ya_cotizadas
    ).select_related('estado', 'area_conocimiento')

    form_filtro = FiltroSolicitudForm(request.GET or None)
    if form_filtro.is_valid():
        if form_filtro.cleaned_data.get('estado'):
            solicitudes = solicitudes.filter(estado=form_filtro.cleaned_data['estado'])
        if form_filtro.cleaned_data.get('area'):
            solicitudes = solicitudes.filter(area_conocimiento=form_filtro.cleaned_data['area'])
        if form_filtro.cleaned_data.get('fecha_desde'):
            solicitudes = solicitudes.filter(created_at__date__gte=form_filtro.cleaned_data['fecha_desde'])
        if form_filtro.cleaned_data.get('fecha_hasta'):
            solicitudes = solicitudes.filter(created_at__date__lte=form_filtro.cleaned_data['fecha_hasta'])
        if form_filtro.cleaned_data.get('buscar'):
            q = form_filtro.cleaned_data['buscar']
            solicitudes = solicitudes.filter(
                Q(codigo__icontains=q) |
                Q(titulo__icontains=q) |
                Q(cliente_nombre__icontains=q)
            )

    solicitudes = solicitudes.order_by('-created_at')

    return render(request, 'private/solicitudes/disponibles.html', {
        'solicitudes': solicitudes,
        'form_filtro': form_filtro,
    })


@tutor_required
def solicitud_actualizar_estado_tutor(request, pk):
    """Actualizar el estado de una solicitud asignada (solo Tutor)."""
    solicitud = get_object_or_404(
        SolicitudAcademica,
        pk=pk,
        tutor_asignado=request.user
    )

    if request.method == 'POST':
        form = CambiarEstadoForm(request.POST, allowed_states=['en_progreso', 'en_revision', 'completada'])
        if form.is_valid():
            estado_anterior = solicitud.estado
            estado_nuevo = form.cleaned_data['estado']
            comentario = form.cleaned_data.get('comentario', '')

            solicitud._notif_actor = request.user
            solicitud.estado = estado_nuevo
            solicitud.save()

            HistorialEstado.objects.create(
                solicitud=solicitud,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_nuevo,
                cambiado_por=request.user,
                comentario=comentario,
            )

            messages.success(request, f'Estado cambiado a "{estado_nuevo.etiqueta}". El administrador ha sido notificado.')
            return redirect('solicitud_detalle', pk=pk)

    return redirect('solicitud_detalle', pk=pk)


@tutor_required
def solicitud_entregar(request, pk):
    """Entrega de tarea: subir archivo + cambiar estado a 'en_revision' en 1 paso."""
    from documentos.models import Documento
    from documentos.forms import DocumentoSubirForm

    solicitud = get_object_or_404(
        SolicitudAcademica,
        pk=pk,
        tutor_asignado=request.user,
    )

    if request.method == 'POST':
        form = DocumentoSubirForm(request.POST, request.FILES)
        if form.is_valid() and request.FILES.get('archivo'):
            doc = form.save(commit=False)
            doc.solicitud = solicitud
            doc.subido_por = request.user
            doc.nombre_original = request.FILES['archivo'].name
            doc.tamaño_bytes = request.FILES['archivo'].size
            doc.tipo = 'entrega'
            doc.save()

            if solicitud.estado.nombre not in ('en_revision', 'completada', 'cancelada'):
                estado_anterior = solicitud.estado
                estado_revision = EstadoSolicitud.objects.get(nombre='en_revision')
                solicitud._notif_actor = request.user
                solicitud.estado = estado_revision
                solicitud.save()

                HistorialEstado.objects.create(
                    solicitud=solicitud,
                    estado_anterior=estado_anterior,
                    estado_nuevo=estado_revision,
                    cambiado_por=request.user,
                    comentario=f'Entrega realizada: {doc.nombre_original}',
                )

            messages.success(request, f'Tarea entregada. Archivo "{doc.nombre_original}" subido correctamente.')
        else:
            messages.error(request, 'Debes seleccionar un archivo para entregar.')
        return redirect('solicitud_detalle', pk=pk)

    return redirect('solicitud_detalle', pk=pk)


@admin_required
def solicitud_marcar_completada(request, pk):
    """Marca una solicitud como completada de un solo clic (solo Admin)."""
    solicitud = get_object_or_404(SolicitudAcademica, pk=pk)

    if request.method == 'POST':
        if solicitud.estado.nombre == 'completada':
            messages.warning(request, 'La solicitud ya está completada.')
            return redirect('solicitud_detalle', pk=pk)

        estado_anterior = solicitud.estado
        estado_completada = EstadoSolicitud.objects.get(nombre='completada')
        solicitud._notif_actor = request.user
        solicitud.estado = estado_completada
        solicitud.save()

        HistorialEstado.objects.create(
            solicitud=solicitud,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_completada,
            cambiado_por=request.user,
            comentario='Marcada como completada por el administrador.',
        )

        messages.success(request, f'Solicitud {solicitud.codigo} marcada como completada.')
        return redirect('solicitud_detalle', pk=pk)

    return redirect('solicitud_detalle', pk=pk)


@admin_required
def solicitud_calificar(request, pk):
    """Calificar el desempeño del tutor en una solicitud completada (solo Admin).

    La nota obtenida se ingresa en escala universitaria 0.0-5.0 y la puntuación
    del tutor (0-100) se calcula automáticamente: nota × 20.
    """
    solicitud = get_object_or_404(SolicitudAcademica, pk=pk)

    if request.method == 'POST':
        nota = request.POST.get('nota_obtenida')

        if nota in (None, ''):
            messages.error(request, 'Debes ingresar la nota obtenida (0.0 a 5.0).')
            return redirect('solicitud_detalle', pk=pk)

        try:
            nota = float(nota)
            if not (0 <= nota <= 5):
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'La nota obtenida debe estar entre 0.0 y 5.0.')
            return redirect('solicitud_detalle', pk=pk)

        from django.utils import timezone
        solicitud.nota_obtenida = nota
        solicitud.calificacion_tutor = int(round(nota * 20))
        solicitud.fecha_calificacion = timezone.now()
        solicitud.save(update_fields=['nota_obtenida', 'calificacion_tutor', 'fecha_calificacion'])

        messages.success(
            request,
            f'Calificación guardada para {solicitud.codigo}. '
            f'Puntuación del tutor: {solicitud.calificacion_tutor}/100.'
        )
        return redirect('solicitud_detalle', pk=pk)

    return redirect('solicitud_detalle', pk=pk)


@admin_required
def solicitud_reasignar_tutor(request, pk):
    """Reasignar una solicitud a un tutor diferente (solo Admin)."""
    solicitud = get_object_or_404(SolicitudAcademica, pk=pk)
    
    if request.method == 'POST':
        tutor_id = request.POST.get('tutor_id')
        if not tutor_id:
            messages.error(request, 'Debe seleccionar un tutor.')
            return redirect('solicitud_detalle', pk=pk)
        
        nuevo_tutor = get_object_or_404(User, pk=tutor_id, groups__name='Tutor')
        
        if nuevo_tutor == solicitud.tutor_asignado:
            messages.warning(request, 'El tutor seleccionado es el mismo que el actual.')
            return redirect('solicitud_detalle', pk=pk)
        
        tutor_anterior = solicitud.tutor_asignado
        estado_anterior = solicitud.estado

        solicitud._notif_actor = request.user
        solicitud.tutor_asignado = nuevo_tutor

        # Al asignar un tutor la solicitud pasa automáticamente a "asignada".
        # No se toca el estado si la solicitud está en un estado terminal.
        estado_nuevo = estado_anterior
        if estado_anterior.nombre not in ('completada', 'cancelada', 'en_disputa', 'en_correccion'):
            estado_asignada, _ = EstadoSolicitud.objects.get_or_create(
                nombre='asignada',
                defaults={'etiqueta': 'Asignada', 'color_hex': '#6366f1', 'orden': 4}
            )
            solicitud.estado = estado_asignada
            estado_nuevo = estado_asignada

        solicitud.save()

        # Registrar en historial
        HistorialEstado.objects.create(
            solicitud=solicitud,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            cambiado_por=request.user,
            comentario=f'Tutor asignado: {nuevo_tutor.get_full_name() or nuevo_tutor.username}.'
        )

        # Notificar al tutor anterior (si existe) que perdió la asignación.
        # El nuevo tutor ya recibe su notificación automáticamente vía signal.
        if tutor_anterior:
            from notificaciones.utils import crear_notificacion
            crear_notificacion(
                destinatario=tutor_anterior,
                tipo='sistema',
                titulo=f'Tarea reasignada — {solicitud.codigo}',
                mensaje=f'El administrador ha reasignado la tarea "{solicitud.titulo}" a otro tutor.',
                url_accion=reverse('solicitudes_disponibles'),
                solicitud_id=solicitud.pk,
            )

        messages.success(request, f'Tarea reasignada a {nuevo_tutor.get_full_name()}.')
        return redirect('solicitud_detalle', pk=pk)
    
    return redirect('solicitud_detalle', pk=pk)


@admin_required
def solicitud_reactivar(request, pk):
    """Reactivar una solicitud completada para correcciones del cliente (solo Admin).

    Vuelve la solicitud al estado "en_correccion", opcionalmente la reasigna a
    un tutor (el mismo u otro), limpia la calificación previa para poder
    recalificar y ajusta las estadísticas del tutor (deja de contar la orden
    como completada).
    """
    solicitud = get_object_or_404(SolicitudAcademica, pk=pk)

    if request.method == 'POST':
        if solicitud.estado.nombre != 'completada':
            messages.warning(request, 'Solo se pueden reactivar solicitudes completadas.')
            return redirect('solicitud_detalle', pk=pk)

        tutor_id = request.POST.get('tutor_id')
        comentario = (request.POST.get('comentario') or '').strip()

        nuevo_tutor = solicitud.tutor_asignado
        if tutor_id:
            nuevo_tutor = get_object_or_404(User, pk=tutor_id, groups__name='Tutor')

        estado_anterior = solicitud.estado
        tutor_anterior = solicitud.tutor_asignado
        estado_correccion, _ = EstadoSolicitud.objects.get_or_create(
            nombre='en_correccion',
            defaults={'etiqueta': 'En Corrección', 'color_hex': '#f97316', 'orden': 8}
        )

        solicitud._notif_actor = request.user
        solicitud.estado = estado_correccion
        solicitud.tutor_asignado = nuevo_tutor
        # Limpiar la calificación previa para que se pueda recalificar
        solicitud.nota_obtenida = None
        solicitud.calificacion_tutor = None
        solicitud.fecha_calificacion = None
        solicitud.save()

        # Recalcular estadísticas del tutor (la orden ya no cuenta como completada)
        if tutor_anterior:
            recalcular_estadisticas_tutor(tutor_anterior)
        if nuevo_tutor and nuevo_tutor != tutor_anterior:
            recalcular_estadisticas_tutor(nuevo_tutor)

        HistorialEstado.objects.create(
            solicitud=solicitud,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_correccion,
            cambiado_por=request.user,
            comentario=comentario or 'Reactivada para correcciones solicitadas por el cliente.',
        )

        messages.success(
            request,
            f'Solicitud {solicitud.codigo} reactivada en estado "En Corrección". '
            f'Tutor: {nuevo_tutor.get_full_name() or nuevo_tutor.username}.'
        )
        return redirect('solicitud_detalle', pk=pk)

    return redirect('solicitud_detalle', pk=pk)
