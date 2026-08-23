"""
Views para documentos adjuntos a solicitudes.
"""

import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import FileResponse, Http404
from .models import Documento
from .forms import DocumentoSubirForm
from solicitudes.models import SolicitudAcademica, EstadoSolicitud
from accounts.decorators import admin_o_tutor_required, admin_required


@admin_o_tutor_required
def documento_subir(request, solicitud_pk):
    """Subir un documento a una solicitud."""
    es_admin = request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()

    if es_admin:
        solicitud = get_object_or_404(SolicitudAcademica, pk=solicitud_pk)
    else:
        solicitud = get_object_or_404(SolicitudAcademica, pk=solicitud_pk, tutor_asignado=request.user)

    if request.method == 'POST':
        form = DocumentoSubirForm(request.POST, request.FILES)
        if form.is_valid():
            documento = form.save(commit=False)
            documento.solicitud = solicitud
            documento.subido_por = request.user
            documento.nombre_original = request.FILES['archivo'].name
            documento.tamaño_bytes = request.FILES['archivo'].size
            documento.save()
            messages.success(request, f'Documento "{documento.nombre_original}" subido correctamente.')
        else:
            messages.error(request, 'Error al subir el documento. Verifica el formato y tamaño.')

    return redirect('solicitud_detalle', pk=solicitud_pk)


@admin_o_tutor_required
def documento_descargar(request, pk):
    """Descargar un documento con validación de permisos."""
    documento = get_object_or_404(Documento, pk=pk)
    es_admin = request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()

    # Verificar acceso
    if not es_admin:
        solicitud = documento.solicitud
        # El tutor puede descargar documentos de solicitudes asignadas a él o
        # de solicitudes abiertas (nueva / en_cotizacion) para analizar y cotizar.
        estados_abiertos = EstadoSolicitud.objects.filter(nombre__in=['nueva', 'en_cotizacion'])
        puede_ver = (
            solicitud.tutor_asignado == request.user
            or solicitud.estado in estados_abiertos
        )
        if not puede_ver:
            raise Http404('No tienes acceso a este documento.')
        # Comprobantes de pago: solo el admin y el tutor ASIGNADO a la solicitud
        if documento.tipo == 'comprobante' and solicitud.tutor_asignado != request.user:
            raise Http404('No tienes acceso a este tipo de documento.')


    try:
        # ?inline=1 muestra el archivo en el navegador (preview de imágenes del
        # comprobante); sin él se fuerza la descarga como siempre.
        inline = request.GET.get('inline') == '1'
        response = FileResponse(
            open(documento.archivo.path, 'rb'),
            as_attachment=not inline,
            filename=documento.nombre_original
        )
        return response
    except FileNotFoundError:
        raise Http404('El archivo no existe en el servidor.')


@admin_required
def documento_subir_comprobante(request, solicitud_pk):
    """Admin carga el comprobante de pago de una tarea completada.
    El tutor asignado puede verlo/descargarlo desde el detalle."""
    from notificaciones.utils import crear_notificacion

    solicitud = get_object_or_404(SolicitudAcademica, pk=solicitud_pk)

    if solicitud.estado.nombre != 'completada':
        messages.error(request, 'El comprobante de pago se carga cuando la tarea está completada.')
        return redirect('solicitud_detalle', pk=solicitud_pk)

    if request.method == 'POST':
        data = request.POST.copy()
        data['tipo'] = 'comprobante'
        form = DocumentoSubirForm(data, request.FILES)
        if form.is_valid():
            documento = form.save(commit=False)
            documento.solicitud = solicitud
            documento.subido_por = request.user
            documento.nombre_original = request.FILES['archivo'].name
            documento.tamaño_bytes = request.FILES['archivo'].size
            documento.save()

            # Notificar al tutor asignado (push + persistencia)
            if solicitud.tutor_asignado:
                crear_notificacion(
                    destinatario=solicitud.tutor_asignado,
                    tipo='comprobante_pago',
                    titulo='Comprobante de pago disponible',
                    mensaje=(
                        f'Se registró el pago de {solicitud.codigo}. '
                        'Ya puedes ver el comprobante en el detalle de la tarea.'
                    ),
                    url_accion=f'/solicitudes/{solicitud.pk}/',
                    solicitud_id=solicitud.pk,
                )

            messages.success(
                request,
                f'Comprobante "{documento.nombre_original}" cargado correctamente.'
                + (' El tutor fue notificado.' if solicitud.tutor_asignado else '')
            )
        else:
            for errores in form.errors.values():
                for e in errores:
                    messages.error(request, e)

    return redirect('solicitud_detalle', pk=solicitud_pk)


@admin_required
def documento_eliminar(request, pk):
    """Eliminar un documento (solo Admin)."""
    documento = get_object_or_404(Documento, pk=pk)
    solicitud_pk = documento.solicitud.pk

    if request.method == 'POST':
        # Eliminar el archivo físico
        if documento.archivo and os.path.exists(documento.archivo.path):
            os.remove(documento.archivo.path)
        documento.delete()
        messages.success(request, 'Documento eliminado correctamente.')

    return redirect('solicitud_detalle', pk=solicitud_pk)
