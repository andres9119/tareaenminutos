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
from accounts.utils import qs_base_sin_pagina

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

    # Límite de carga: máximo 2 solicitudes activas para poder cotizar otra
    num_activas = SolicitudAcademica.activas_de_tutor(request.user).count()
    if num_activas >= SolicitudAcademica.MAX_SOLICITUDES_ACTIVAS_TUTOR:
        messages.warning(
            request,
            f'Tienes {num_activas} solicitudes activas. '
            'Debes completar al menos una antes de poder cotizar otra.'
        )
        return redirect('solicitudes_disponibles')

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
                    defaults={'etiqueta': 'Cotización', 'color_hex': '#f59e0b', 'orden': 2}
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

    # Documentos de la solicitud (instrucciones/referencias) visibles para cotizar
    documentos = solicitud.documentos.exclude(tipo='entrega').order_by('-created_at')
    context = {'form': form, 'solicitud': solicitud, 'documentos': documentos}
    return render(request, 'private/cotizaciones/crear.html', context)


@admin_required
def cotizacion_aceptar(request, pk):
    """Aceptar una cotización y poner la solicitud en 'En Negociación' (solo Admin).

    Etapa 1 de 2: el equipo acepta la propuesta, pero el tutor NO empieza a
    trabajar hasta que el cliente acepte (ver `cotizacion_confirmar_asignacion`).
    Las demás cotizaciones pendientes quedan rechazadas de una vez, con aviso
    a sus tutores de que otra propuesta fue seleccionada.
    """
    cotizacion = get_object_or_404(Cotizacion, pk=pk, estado='pendiente')

    # Límite de carga: el tutor no puede superar el máximo de solicitudes activas
    num_activas = SolicitudAcademica.activas_de_tutor(cotizacion.tutor).count()
    if num_activas >= SolicitudAcademica.MAX_SOLICITUDES_ACTIVAS_TUTOR:
        nombre_tutor = cotizacion.tutor.get_full_name() or cotizacion.tutor.username
        messages.error(
            request,
            f'El tutor {nombre_tutor} ya tiene {num_activas} solicitudes activas. '
            'Debe completar al menos una antes de recibir una nueva asignación.'
        )
        return redirect('solicitud_detalle', pk=cotizacion.solicitud.pk)

    # Cambiar estado de la cotización a aceptada
    cotizacion.estado = 'aceptada'
    cotizacion.save(update_fields=['estado', 'updated_at'])

    # Cambiar solicitud a "En Negociación" (NO asignada aún)
    estado_negociacion, _ = EstadoSolicitud.objects.get_or_create(
        nombre='en_negociacion',
        defaults={'etiqueta': 'En Negociación', 'color_hex': '#f59e0b', 'orden': 4}
    )
    estado_anterior = cotizacion.solicitud.estado
    cotizacion.solicitud._notif_actor = request.user
    cotizacion.solicitud._skip_estado_notif = True
    cotizacion.solicitud.estado = estado_negociacion
    cotizacion.solicitud.tutor_asignado = cotizacion.tutor
    cotizacion.solicitud.precio_final = cotizacion.monto
    cotizacion.solicitud.save()

    # Registrar en historial
    HistorialEstado.objects.create(
        solicitud=cotizacion.solicitud,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_negociacion,
        cambiado_por=request.user,
        comentario=f'Cotización aceptada. En negociación con el cliente. Tutor: {cotizacion.tutor.get_full_name() or cotizacion.tutor.username}. Precio: ${cotizacion.monto:,.0f}'
    )

    # Agregar tutor a la sala de chat
    from chat_interno.models import SalaChat
    sala = getattr(cotizacion.solicitud, 'sala_chat', None)
    if sala:
        sala.participantes.add(cotizacion.tutor)

    # Notificar al tutor seleccionado: etapa 1 de 2 (aceptada por el equipo,
    # pendiente de negociación final con el cliente; NO debe empezar todavía)
    from notificaciones.utils import crear_notificacion
    crear_notificacion(
        destinatario=cotizacion.tutor,
        tipo='cotizacion_aceptada',
        titulo=f'Tu cotización fue aceptada por el equipo — {cotizacion.solicitud.codigo} (etapa 1 de 2)',
        mensaje=f'El equipo administrativo aceptó tu propuesta de ${cotizacion.monto:,.0f} COP para "{cotizacion.solicitud.titulo}". Ahora está en negociación final con el cliente. NO empieces a trabajar todavía: te avisaremos cuando la asignación quede en firme o si el cliente no acepta.',
        url_accion=reverse('solicitud_detalle', args=[cotizacion.solicitud.pk]),
        solicitud_id=cotizacion.solicitud.pk,
    )

    # Las demás cotizaciones pendientes quedan rechazadas de una vez: sus
    # tutores reciben el aviso de que otra propuesta fue seleccionada.
    for otra_cot in Cotizacion.objects.filter(
        solicitud=cotizacion.solicitud, estado='pendiente'
    ).exclude(pk=cotizacion.pk):
        otra_cot.estado = 'rechazada'
        otra_cot.motivo_rechazo = 'Se seleccionó otra propuesta para esta solicitud.'
        otra_cot.save(update_fields=['estado', 'motivo_rechazo', 'updated_at'])
        crear_notificacion(
            destinatario=otra_cot.tutor,
            tipo='cotizacion_rechazada',
            titulo=f'Tu cotización no fue seleccionada — {cotizacion.solicitud.codigo}',
            mensaje=(f'El administrador seleccionó otra propuesta para "{cotizacion.solicitud.titulo}". '
                     f'Motivo: Se seleccionó otra propuesta para esta solicitud. ¡Sigue participando!'),
            url_accion=reverse('solicitud_detalle', args=[cotizacion.solicitud.pk]),
            solicitud_id=cotizacion.solicitud.pk,
        )

    messages.success(request, f'Cotización aceptada. Solicitud {cotizacion.solicitud.codigo} en "En Negociación". Tutor {cotizacion.tutor.get_full_name()} asignado provisionalmente.')
    return redirect('solicitud_detalle', pk=cotizacion.solicitud.pk)


@admin_required
def cotizacion_rechazar(request, pk):
    """Rechazar manualmente una cotización pendiente con motivo (solo Admin)."""
    cotizacion = get_object_or_404(Cotizacion, pk=pk, estado='pendiente')

    if request.method == 'POST':
        motivo = (request.POST.get('motivo_rechazo') or '').strip()
        cotizacion.estado = 'rechazada'
        cotizacion.motivo_rechazo = motivo
        cotizacion.save(update_fields=['estado', 'motivo_rechazo', 'updated_at'])

        from solicitudes.models import HistorialEstado
        nombre_rechazado = cotizacion.tutor.get_full_name() or cotizacion.tutor.username
        HistorialEstado.objects.create(
            solicitud=cotizacion.solicitud,
            estado_anterior=cotizacion.solicitud.estado,
            estado_nuevo=cotizacion.solicitud.estado,
            cambiado_por=request.user,
            comentario=(f'Cotización de {nombre_rechazado} rechazada. '
                        + (f'Motivo: {motivo}' if motivo else 'Sin motivo registrado.')),
        )

        from notificaciones.utils import crear_notificacion
        msg = f'El administrador descartó tu propuesta de ${cotizacion.monto:,.0f} COP para "{cotizacion.solicitud.titulo}".'
        if motivo:
            msg += f' Motivo: {motivo}'
        msg += ' ¡Sigue participando!'
        crear_notificacion(
            destinatario=cotizacion.tutor,
            tipo='cotizacion_rechazada',
            titulo=f'Tu cotización no fue seleccionada — {cotizacion.solicitud.codigo}',
            mensaje=msg,
            url_accion=reverse('solicitud_detalle', args=[cotizacion.solicitud.pk]),
            solicitud_id=cotizacion.solicitud.pk,
        )

        nombre_tutor = cotizacion.tutor.get_full_name() or cotizacion.tutor.username
        messages.success(request, f'Cotización de {nombre_tutor} rechazada para {cotizacion.solicitud.codigo}.')
        return redirect('solicitud_detalle', pk=cotizacion.solicitud.pk)

    # GET: mostrar modal con formulario de motivo
    return render(request, 'private/cotizaciones/rechazar_modal.html', {
        'cotizacion': cotizacion,
        'solicitud': cotizacion.solicitud,
    })


@admin_required
def cotizacion_confirmar_asignacion(request, pk):
    """Confirmar asignación final: cambia de 'En Negociación' a 'Asignada' (solo Admin).

    Solo disponible si la solicitud está en estado 'en_negociacion' y tiene tutor_asignado.
    """
    from solicitudes.models import SolicitudAcademica, EstadoSolicitud, HistorialEstado
    solicitud = get_object_or_404(SolicitudAcademica, pk=pk)

    if solicitud.estado.nombre != 'en_negociacion':
        messages.error(request, 'Solo se puede confirmar asignación desde el estado "En Negociación".')
        return redirect('solicitud_detalle', pk=pk)

    if not solicitud.tutor_asignado:
        messages.error(request, 'No hay tutor asignado para confirmar.')
        return redirect('solicitud_detalle', pk=pk)

    if request.method == 'POST':
        estado_asignada = EstadoSolicitud.objects.get(nombre='asignada')
        estado_anterior = solicitud.estado
        solicitud._notif_actor = request.user
        solicitud.estado = estado_asignada
        solicitud.save()

        # Red de seguridad: si quedara alguna pendiente (no debería: se
        # rechazan al aceptar), se rechaza ahora con su aviso.
        from cotizaciones.models import Cotizacion
        for otra_cot in Cotizacion.objects.filter(
            solicitud=solicitud, estado='pendiente'
        ).exclude(tutor=solicitud.tutor_asignado):
            otra_cot.estado = 'rechazada'
            otra_cot.motivo_rechazo = 'Se seleccionó otra propuesta para esta solicitud.'
            otra_cot.save(update_fields=['estado', 'motivo_rechazo', 'updated_at'])
            from notificaciones.utils import crear_notificacion as _crear
            _crear(
                destinatario=otra_cot.tutor,
                tipo='cotizacion_rechazada',
                titulo=f'Tu cotización no fue seleccionada — {solicitud.codigo}',
                mensaje=f'El administrador seleccionó otra propuesta para "{solicitud.titulo}". Motivo: Se seleccionó otra propuesta para esta solicitud. ¡Sigue participando!',
                url_accion=reverse('solicitud_detalle', args=[solicitud.pk]),
                solicitud_id=solicitud.pk,
            )

        # Para el historial: todas las descartadas salvo la ganadora
        # (normalmente ya rechazadas al aceptar).
        descartadas = Cotizacion.objects.filter(
            solicitud=solicitud, estado='rechazada'
        ).exclude(tutor=solicitud.tutor_asignado)
        nombres_descartados = [
            c.tutor.get_full_name() or c.tutor.username for c in descartadas
        ]

        HistorialEstado.objects.create(
            solicitud=solicitud,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_asignada,
            cambiado_por=request.user,
            comentario=('Asignación confirmada tras negociación con el cliente. El tutor puede empezar a trabajar.'
                        + (f' Cotizaciones descartadas: {", ".join(nombres_descartados)}.' if nombres_descartados else ''))
        )

        # Notificar al tutor que ya puede empezar (etapa 2 de 2: en firme)
        from notificaciones.utils import crear_notificacion
        crear_notificacion(
            destinatario=solicitud.tutor_asignado,
            tipo='solicitud_asignada',
            titulo=f'Asignación en firme — {solicitud.codigo} (etapa 2 de 2)',
            mensaje=f'El cliente aceptó la propuesta para "{solicitud.titulo}". ¡Ya puedes empezar a trabajar!',
            url_accion=reverse('solicitud_detalle', args=[solicitud.pk]),
            solicitud_id=solicitud.pk,
        )

        messages.success(request, f'Solicitud {solicitud.codigo} confirmada como "Asignada". El tutor ha sido notificado.')
        return redirect('solicitud_detalle', pk=pk)

    return render(request, 'private/cotizaciones/confirmar_asignacion.html', {
        'solicitud': solicitud,
    })


@admin_required
def cotizacion_cancelar_negociacion(request, pk):
    """Cancelar la negociación: el cliente NO aceptó (solo Admin).

    La solicitud vuelve a 'En Cotización', se libera al tutor provisional y su
    cotización aceptada vuelve a 'pendiente' (sigue en consideración). Las
    demás siguen rechazadas desde la aceptación; solo se avisa al tutor
    provisional.
    """
    from solicitudes.models import SolicitudAcademica, EstadoSolicitud, HistorialEstado
    from cotizaciones.models import Cotizacion
    solicitud = get_object_or_404(SolicitudAcademica, pk=pk)

    if solicitud.estado.nombre != 'en_negociacion':
        messages.error(request, 'Solo se puede cancelar la negociación desde el estado "En Negociación".')
        return redirect('solicitud_detalle', pk=pk)

    if request.method == 'POST':
        tutor_provisional = solicitud.tutor_asignado
        cotizacion_ganadora = Cotizacion.objects.filter(
            solicitud=solicitud, estado='aceptada'
        ).first()

        estado_cotizacion = EstadoSolicitud.objects.get(nombre='en_cotizacion')
        estado_anterior = solicitud.estado
        solicitud._notif_actor = request.user
        solicitud.estado = estado_cotizacion
        solicitud.tutor_asignado = None
        solicitud.precio_final = None
        solicitud.save()

        if cotizacion_ganadora:
            cotizacion_ganadora.estado = 'pendiente'
            cotizacion_ganadora.save(update_fields=['estado', 'updated_at'])

        nombre_tutor = (tutor_provisional.get_full_name() or tutor_provisional.username) if tutor_provisional else '—'
        HistorialEstado.objects.create(
            solicitud=solicitud,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_cotizacion,
            cambiado_por=request.user,
            comentario=f'El cliente no aceptó la propuesta en negociación. Tutor provisional liberado: {nombre_tutor}. La solicitud vuelve a cotización.'
        )

        # Avisar al tutor provisional: que NO empiece y que sigue en consideración
        if tutor_provisional:
            from notificaciones.utils import crear_notificacion
            crear_notificacion(
                destinatario=tutor_provisional,
                tipo='cotizacion_rechazada',
                titulo=f'El cliente no aceptó — {solicitud.codigo}',
                mensaje=f'El cliente no aceptó la propuesta en negociación para "{solicitud.titulo}". NO empieces a trabajar: tu cotización vuelve a estar en consideración junto a las demás. ¡Sigue participando!',
                url_accion=reverse('solicitud_detalle', args=[solicitud.pk]),
                solicitud_id=solicitud.pk,
            )

        messages.success(request, f'Negociación de {solicitud.codigo} cancelada. Volvió a "En Cotización" y se avisó al tutor provisional.')
        return redirect('solicitud_detalle', pk=pk)

    return render(request, 'private/cotizaciones/cancelar_negociacion.html', {
        'solicitud': solicitud,
    })


@tutor_required
def mis_cotizaciones(request):
    """Lista de cotizaciones enviadas por el tutor actual.

    Cada fila lleva los agregados de su solicitud (número de cotizaciones,
    monto mínimo y máximo) para el modal "Ver" con el rango de precios.
    """
    from django.db.models import Count, Min, Max
    cotizaciones = Cotizacion.objects.filter(
        tutor=request.user
    ).select_related('solicitud', 'solicitud__estado').order_by('-created_at')

    paginator = Paginator(cotizaciones, 20)
    page = request.GET.get('page', 1)
    cotizaciones_page = paginator.get_page(page)

    solicitud_ids = {c.solicitud_id for c in cotizaciones_page.object_list}
    agregados = {}
    if solicitud_ids:
        filas = Cotizacion.objects.filter(solicitud_id__in=solicitud_ids).values(
            'solicitud_id'
        ).annotate(n=Count('id'), mn=Min('monto'), mx=Max('monto'))
        agregados = {f['solicitud_id']: f for f in filas}

    for c in cotizaciones_page.object_list:
        a = agregados.get(c.solicitud_id)
        c.sol_num = a['n'] if a else 0
        c.sol_min = a['mn'] if a else None
        c.sol_max = a['mx'] if a else None

    return render(request, 'private/cotizaciones/mis_cotizaciones.html', {'cotizaciones': cotizaciones_page, 'pagina': cotizaciones_page, 'is_paginated': cotizaciones_page.has_other_pages()})


@admin_required
def cotizaciones_lista(request):
    """Lista de cotizaciones agrupadas por solicitud (solo Admin)."""
    from datetime import datetime
    from itertools import groupby
    estado = request.GET.get('estado', '')
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')

    cotizaciones = Cotizacion.objects.select_related(
        'solicitud', 'solicitud__estado', 'tutor', 'tutor__perfil'
    ).order_by('solicitud__codigo', '-created_at')

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

    # Agrupar por solicitud
    grupos = []
    for codigo, cotizaciones_grupo in groupby(cotizaciones, key=lambda c: c.solicitud):
        grupo_list = list(cotizaciones_grupo)
        grupos.append({
            'solicitud': grupo_list[0].solicitud,
            'cotizaciones': grupo_list,
        })

    paginator = Paginator(grupos, 10)
    page = request.GET.get('page', 1)
    grupos_page = paginator.get_page(page)

    context = {
        'grupos': grupos_page,
        'pagina': grupos_page,
        'qs_base': qs_base_sin_pagina(request, 'page'),
        'estado': estado,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'is_paginated': grupos_page.has_other_pages(),
    }
    return render(request, 'private/cotizaciones/lista.html', context)
