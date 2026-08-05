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
        # Los tutores no pueden ver comprobantes de pago
        if documento.tipo == 'comprobante':
            raise Http404('No tienes acceso a este tipo de documento.')


    try:
        response = FileResponse(
            open(documento.archivo.path, 'rb'),
            as_attachment=True,
            filename=documento.nombre_original
        )
        return response
    except FileNotFoundError:
        raise Http404('El archivo no existe en el servidor.')


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
