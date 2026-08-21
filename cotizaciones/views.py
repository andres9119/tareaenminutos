"""
Views para cotizaciones de tutores.
"""

import logging
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils import timezone
from .models import Cotizacion
from .forms import CotizacionForm
from solicitudes.models import SolicitudAcademica, EstadoSolicitud, HistorialEstado
from accounts.decorators import admin_required, tutor_required, admin_o_tutor_required

logger = logging.getLogger('tareaenminutos')


@tutor_required
def cotizacion_crear(request, solicitud_pk):
    """Enviar cotización para una solicitud disponible (solo Tutor)."""
    estados_abiertos = EstadoSolicitud.objects.filter(nombre__in=['nueva', 'en_cotizacion'])
    solicitud = get_object_or_404(
        SolicitudAcademica,
        pk=solicitud_pk,
        estado__in=estados_abiertos,
        tutor_asignado__isnull=True
    )

    # Verificar que no haya cotizado ya
    if Cotizacion.objects.filter(solicitud=solicitud, tutor=request.user).exists():
        messages.warning(request, 'Ya enviaste una cotización para esta solicitud.')
        return redirect('solicitud_detalle', pk=solicitud.pk)

    if request.method == 'POST':
        form = CotizacionForm(request.POST)
        if form.is_valid():
            cotizacion = form.save(commit=False)
            cotizacion.solicitud = solicitud
            cotizacion.tutor = request.user
            # La fecha de entrega se deriva del tiempo propuesto en días
            cotizacion.fecha_entrega_propuesta = (
                timezone.localdate() + timedelta(days=cotizacion.tiempo_estimado_dias)
            )
            cotizacion.save()

            # Cambiar estado a "en_cotizacion" si aún era "nueva"
            if solicitud.estado.nombre == 'nueva':
                estado_cotizacion, _ = EstadoSolicitud.objects.get_or_create(
                    nombre='en_cotizacion',
                    defaults={'etiqueta': 'En Cotización', 'color_hex': '#f59e0b', 'orden': 2}
                )
                estado_anterior = solicitud.estado
                solicitud.estado = estado_cotizacion
                # Suprime la notificación genérica de cambio de estado:
                # abajo se envía la notificación específica de cotización.
                solicitud._skip_estado_notif = True
                solicitud.save()
                HistorialEstado.objects.create(
                    solicitud=solicitud,
                    estado_anterior=estado_anterior,
                    estado_nuevo=estado_cotizacion,
                    cambiado_por=request.user,
                    comentario=f'Primera cotización recibida del tutor {request.user.get_full_name() or request.user.username}.'
                )

            # Notificar a los admins que el tutor envió una cotización
            from notificaciones.utils import crear_notificacion
            from django.contrib.auth.models import User
            nombre_tutor = request.user.get_full_name() or request.user.username
            admins = User.objects.filter(groups__name='Administrador') | User.objects.filter(is_superuser=True)
            for admin in admins:
                crear_notificacion(
                    destinatario=admin,
                    tipo='cotizacion_recibida',
                    titulo=f'{solicitud.codigo}: nueva cotización de {nombre_tutor}',
                    mensaje=f'El tutor {nombre_tutor} envió una cotización de ${cotizacion.monto:,.0f} COP para "{solicitud.titulo}".',
                    url_accion=reverse('solicitud_detalle', args=[solicitud.pk]),
                    solicitud_id=solicitud.pk,
                )

            messages.success(request, 'Cotización enviada correctamente. El administrador la revisará.')
            return redirect('dashboard_tutor')
    else:
        form = CotizacionForm()

    context = {'form': form, 'solicitud': solicitud}
    return render(request, 'private/cotizaciones/crear.html', context)


@admin_required
def cotizacion_aceptar(request, pk):
    """Aceptar una cotización y asignar el tutor automáticamente (solo Admin)."""
    cotizacion = get_object_or_404(Cotizacion, pk=pk, estado='pendiente')
    
    # Obtener las otras cotizaciones antes de aceptar (para notificar rechazo)
    otras_cotizaciones = Cotizacion.objects.filter(
        solicitud=cotizacion.solicitud
    ).exclude(pk=cotizacion.pk)

    cotizacion.aceptar(por_usuario=request.user)

    # Notificar al tutor seleccionado
    from notificaciones.utils import crear_notificacion
    crear_notificacion(
        destinatario=cotizacion.tutor,
        tipo='cotizacion_aceptada',
        titulo=f'Tu cotización fue aceptada — {cotizacion.solicitud.codigo}',
        mensaje=f'El administrador aceptó tu propuesta de ${cotizacion.monto:,.0f} COP para "{cotizacion.solicitud.titulo}". ¡Comienza a trabajar!',
        url_accion=reverse('solicitud_detalle', args=[cotizacion.solicitud.pk]),
        solicitud_id=cotizacion.solicitud.pk,
    )

    # Notificar a los otros tutores que fueron rechazados
    for otra_cot in otras_cotizaciones:
        crear_notificacion(
            destinatario=otra_cot.tutor,
            tipo='cotizacion_rechazada',
            titulo=f'Tu cotización no fue seleccionada — {cotizacion.solicitud.codigo}',
            mensaje=f'El administrador seleccionó otra propuesta para "{cotizacion.solicitud.titulo}". ¡Sigue participando!',
            url_accion=reverse('solicitudes_disponibles'),
            solicitud_id=cotizacion.solicitud.pk,
        )

    messages.success(request, f'Cotización aceptada. Tutor {cotizacion.tutor.get_full_name()} asignado a {cotizacion.solicitud.codigo}.')
    return redirect('solicitud_detalle', pk=cotizacion.solicitud.pk)


@admin_required
def cotizacion_rechazar(request, pk):
    """Rechazar manualmente una cotización pendiente (solo Admin)."""
    cotizacion = get_object_or_404(Cotizacion, pk=pk, estado='pendiente')
    cotizacion.estado = 'rechazada'
    cotizacion.save(update_fields=['estado', 'updated_at'])

    from notificaciones.utils import crear_notificacion
    crear_notificacion(
        destinatario=cotizacion.tutor,
        tipo='cotizacion_rechazada',
        titulo=f'Tu cotización no fue seleccionada — {cotizacion.solicitud.codigo}',
        mensaje=f'El administrador descartó tu propuesta de ${cotizacion.monto:,.0f} COP para "{cotizacion.solicitud.titulo}". ¡Sigue participando!',
        url_accion=reverse('solicitudes_disponibles'),
        solicitud_id=cotizacion.solicitud.pk,
    )

    nombre_tutor = cotizacion.tutor.get_full_name() or cotizacion.tutor.username
    messages.info(request, f'Cotización de {nombre_tutor} rechazada para {cotizacion.solicitud.codigo}.')
    return redirect('solicitud_detalle', pk=cotizacion.solicitud.pk)


@tutor_required
def mis_cotizaciones(request):
    """Lista de cotizaciones enviadas por el tutor actual."""
    cotizaciones = Cotizacion.objects.filter(
        tutor=request.user
    ).select_related('solicitud', 'solicitud__estado').order_by('-created_at')

    paginator = Paginator(cotizaciones, 20)
    page = request.GET.get('page', 1)
    cotizaciones_page = paginator.get_page(page)
    
    return render(request, 'private/cotizaciones/mis_cotizaciones.html', {'cotizaciones': cotizaciones_page, 'is_paginated': cotizaciones_page.has_other_pages()})


@admin_required
def cotizaciones_lista(request):
    """Lista de todas las cotizaciones del sistema (solo Admin)."""
    from datetime import datetime
    estado = request.GET.get('estado', '')
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    
    cotizaciones = Cotizacion.objects.select_related(
        'solicitud', 'solicitud__estado', 'tutor', 'tutor__perfil'
    ).order_by('-created_at')
    
    if estado:
        cotizaciones = cotizaciones.filter(estado=estado)
    if fecha_desde:
        try:
            cotizaciones = cotizaciones.filter(created_at__date__gte=datetime.strptime(fecha_desde, '%Y-%m-%d'))
        except ValueError:
            pass
    if fecha_hasta:
        try:
            cotizaciones = cotizaciones.filter(created_at__date__lte=datetime.strptime(fecha_hasta, '%Y-%m-%d'))
        except ValueError:
            pass
    
    paginator = Paginator(cotizaciones, 20)
    page = request.GET.get('page', 1)
    cotizaciones_page = paginator.get_page(page)
    context = {
        'cotizaciones': cotizaciones_page,
        'estado': estado,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'is_paginated': cotizaciones_page.has_other_pages(),
    }
    return render(request, 'private/cotizaciones/lista.html', context)
