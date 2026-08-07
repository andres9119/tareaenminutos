"""
Views para accounts — Dashboards, perfiles y gestión de usuarios.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django.db.models import Q, Count
from django.core.paginator import Paginator
from .models import PerfilUsuario, AreaConocimiento
from .forms import UsuarioCrearForm, PerfilEditarForm
from .decorators import admin_required, admin_o_tutor_required
from .utils import es_admin


@admin_o_tutor_required
def dashboard_redirect(request):
    """Redirige al dashboard correspondiente según el rol del usuario."""
    if es_admin(request.user):
        return redirect('dashboard_admin')
    return redirect('dashboard_tutor')


@admin_required
def dashboard_admin(request):
    """Panel principal del Administrador con métricas y resumen."""
    from solicitudes.models import SolicitudAcademica, EstadoSolicitud
    from cotizaciones.models import Cotizacion

    # KPIs principales
    from django.db.models import Count

    total_solicitudes = SolicitudAcademica.objects.count()
    conteo_por_estado = (
        SolicitudAcademica.objects.values('estado__nombre', 'estado__etiqueta')
        .annotate(cantidad=Count('id'))
        .order_by('estado__orden')
    )
    # Estado por estado para las tarjetas
    estados = list(EstadoSolicitud.objects.order_by('orden').values('id', 'nombre', 'etiqueta', 'color_hex'))
    conteo_map = {r['estado__nombre']: r['cantidad'] for r in conteo_por_estado}
    for est in estados:
        est['cantidad'] = conteo_map.get(est['nombre'], 0)
    total_por_estados = sum(est['cantidad'] for est in estados)

    tutores_activos = User.objects.filter(
        groups__name='Tutor', is_active=True
    ).count()

    # Solicitudes recientes
    solicitudes_recientes = SolicitudAcademica.objects.select_related(
        'estado', 'area_conocimiento', 'tutor_asignado', 'creado_por'
    ).order_by('-created_at')[:8]

    # Cotizaciones pendientes de revisión
    cotizaciones_pendientes = Cotizacion.objects.filter(
        estado='pendiente'
    ).select_related('solicitud', 'tutor').count()

    from main_app.models import ContactMessage
    total_mensajes_contacto = ContactMessage.objects.count()
    mensajes_no_leidos = ContactMessage.objects.filter(read=False).count()

    context = {
        'total_solicitudes': total_solicitudes,
        'total_por_estados': total_por_estados,
        'estados': estados,
        'tutores_activos': tutores_activos,
        'solicitudes_recientes': solicitudes_recientes,
        'cotizaciones_pendientes': cotizaciones_pendientes,
        'total_mensajes_contacto': total_mensajes_contacto,
        'mensajes_no_leidos': mensajes_no_leidos,
    }
    return render(request, 'private/accounts/dashboard_admin.html', context)


@admin_o_tutor_required
def dashboard_tutor(request):
    """Panel del Tutor con sus solicitudes asignadas y disponibles."""
    from solicitudes.models import SolicitudAcademica, EstadoSolicitud
    from cotizaciones.models import Cotizacion

    # Mis solicitudes asignadas
    mis_solicitudes_qs = SolicitudAcademica.objects.filter(
        tutor_asignado=request.user
    ).select_related('estado', 'area_conocimiento').order_by('-updated_at')
    mis_solicitudes = mis_solicitudes_qs[:10]

    # Solicitudes disponibles para cotizar (sin tutor, estado nueva/en_cotizacion)
    ya_cotizadas_ids = Cotizacion.objects.filter(
        tutor=request.user
    ).values_list('solicitud_id', flat=True)

    estados_abiertos = EstadoSolicitud.objects.filter(
        nombre__in=['nueva', 'en_cotizacion']
    )
    solicitudes_disponibles = SolicitudAcademica.objects.filter(
        estado__in=estados_abiertos,
        tutor_asignado__isnull=True
    ).exclude(
        id__in=ya_cotizadas_ids
    ).select_related('estado', 'area_conocimiento').order_by('-created_at')[:6]

    # Mis cotizaciones enviadas
    mis_cotizaciones = Cotizacion.objects.filter(
        tutor=request.user
    ).select_related('solicitud').order_by('-created_at')[:5]

    # Estadísticas del tutor
    perfil = getattr(request.user, 'perfil', None)
    en_progreso_count = mis_solicitudes_qs.filter(estado__nombre='en_progreso').count()
    completadas_count = SolicitudAcademica.objects.filter(
        tutor_asignado=request.user, estado__nombre='completada'
    ).count()

    context = {
        'mis_solicitudes': mis_solicitudes,
        'solicitudes_disponibles': solicitudes_disponibles,
        'mis_cotizaciones': mis_cotizaciones,
        'perfil': perfil,
        'en_progreso_count': en_progreso_count,
        'completadas_count': completadas_count,
    }
    return render(request, 'private/accounts/dashboard_tutor.html', context)


@admin_o_tutor_required
def perfil_view(request):
    """Ver y editar el perfil propio."""
    perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = PerfilEditarForm(request.POST, request.FILES, instance=perfil, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil actualizado correctamente.')
            return redirect('perfil')
    else:
        form = PerfilEditarForm(instance=perfil, user=request.user)

    context = {'form': form, 'perfil': perfil}
    return render(request, 'private/accounts/perfil.html', context)


@admin_required
def usuarios_list(request):
    """Lista de todos los usuarios del sistema (solo Admin)."""
    q = request.GET.get('q', '')
    rol = request.GET.get('rol', '')

    usuarios = User.objects.filter(is_active=True).select_related('perfil').prefetch_related('groups').order_by('-date_joined')

    if q:
        usuarios = usuarios.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q)
        )
    if rol:
        usuarios = usuarios.filter(groups__name=rol)

    paginator = Paginator(usuarios, 20)
    page = request.GET.get('page', 1)
    usuarios_page = paginator.get_page(page)
    context = {'usuarios': usuarios_page, 'q': q, 'rol': rol, 'is_paginated': usuarios_page.has_other_pages()}
    return render(request, 'private/accounts/usuarios_list.html', context)


@admin_required
def usuario_crear(request):
    """Crear un nuevo usuario del sistema (solo Admin)."""
    if request.method == 'POST':
        form = UsuarioCrearForm(request.POST)
        perfil_form = PerfilEditarForm(request.POST, request.FILES)
        if form.is_valid() and (perfil_form.is_valid() or form.cleaned_data.get('rol') != 'Tutor'):
            user = form.save()

            # If created as Tutor, save profile fields
            if form.cleaned_data.get('rol') == 'Tutor':
                perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
                # populate perfil fields from perfil_form
                perfil.telefono = perfil_form.cleaned_data.get('telefono', '')
                perfil.bio = perfil_form.cleaned_data.get('bio', '')
                # handle foto if uploaded
                foto = request.FILES.get('foto')
                if foto:
                    perfil.foto = foto
                perfil.save()
                # M2M especialidades
                especialidades = perfil_form.cleaned_data.get('especialidades')
                if especialidades:
                    perfil.especialidades.set(especialidades)

            messages.success(request, f'Usuario @{user.username} creado correctamente.')
            return redirect('usuarios_list')
    else:
        form = UsuarioCrearForm()
        perfil_form = PerfilEditarForm()

    return render(request, 'private/accounts/usuario_crear.html', {'form': form, 'perfil_form': perfil_form})


@admin_required
def usuario_toggle_activo(request, pk):
    """Activar/desactivar un usuario (solo Admin)."""
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('usuarios_list')
    user.is_active = not user.is_active
    user.save()
    estado = 'activado' if user.is_active else 'desactivado'
    messages.success(request, f'Usuario @{user.username} {estado} correctamente.')
    return redirect('usuarios_list')


@admin_required
def usuario_eliminar(request, pk):
    """Eliminar un usuario definitivamente de la base de datos (solo Admin)."""
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'No puedes eliminar tu propia cuenta.')
        return redirect('usuarios_list')
    if request.user.is_superuser or request.user.groups.filter(name='Administrador').exists():
        if user.is_superuser or user.groups.filter(name='Administrador').exists():
            messages.error(request, 'No puedes eliminar un administrador.')
            return redirect('usuarios_list')
    username = user.username
    user.delete()
    messages.success(request, f'Usuario @{username} eliminado definitivamente de la base de datos.')
    return redirect('usuarios_list')


@admin_required
def tutor_detalle(request, pk):
    """Detalle de un tutor con sus estadísticas (solo Admin)."""
    from solicitudes.models import SolicitudAcademica

    tutor = get_object_or_404(User, pk=pk, groups__name='Tutor')
    perfil = getattr(tutor, 'perfil', None)

    solicitudes = SolicitudAcademica.objects.filter(
        tutor_asignado=tutor
    ).select_related('estado', 'area_conocimiento').order_by('-created_at')

    context = {
        'tutor': tutor,
        'perfil': perfil,
        'solicitudes': solicitudes,
    }
    return render(request, 'private/accounts/tutor_detalle.html', context)
