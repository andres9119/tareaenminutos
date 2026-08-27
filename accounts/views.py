"""
Views para accounts — Dashboards, perfiles y gestión de usuarios.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django.db.models import Q, Count, F, Min, Max
from django.core.paginator import Paginator
from .models import PerfilUsuario, AreaConocimiento
from .forms import UsuarioCrearForm, UsuarioEditarForm, PerfilEditarForm, PerfilPropioForm, AreaForm
from .decorators import admin_required, admin_o_tutor_required
from .utils import es_admin, qs_base_sin_pagina


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
    estados_filtro_ocultos = {'cotizada', 'en_disputa'}
    estados = [est for est in estados if est['nombre'] not in estados_filtro_ocultos]
    conteo_map = {r['estado__nombre']: r['cantidad'] for r in conteo_por_estado}
    for est in estados:
        est['cantidad'] = conteo_map.get(est['nombre'], 0)
    total_por_estados = sum(conteo_map.values())

    tutores_activos = User.objects.filter(
        groups__name='Tutor', is_active=True
    ).count()

    # Solicitudes recientes (paginadas, 5 por página, filtrables por estado)
    estado_reci = request.GET.get('estado_reci', '')
    etiqueta_reci = None
    rec_queryset = SolicitudAcademica.objects.select_related(
        'estado', 'area_conocimiento', 'tutor_asignado', 'creado_por'
    )
    if estado_reci:
        est_filtro = EstadoSolicitud.objects.filter(nombre=estado_reci).first()
        if est_filtro is None:
            estado_reci = ''
        else:
            etiqueta_reci = est_filtro.etiqueta
            rec_queryset = rec_queryset.filter(estado__nombre=estado_reci)
    solicitudes_recientes = Paginator(rec_queryset.order_by('-created_at'), 5).get_page(
        request.GET.get('rec', 1)
    )

    # Solicitudes asignadas activas, próximas a vencer primero (paginadas, 5)
    solicitudes_asignadas = Paginator(
        SolicitudAcademica.objects.select_related(
            'estado', 'area_conocimiento', 'tutor_asignado'
        ).filter(tutor_asignado__isnull=False).exclude(
            estado__nombre__in=SolicitudAcademica.ESTADOS_CERRADOS_TUTOR
        ).order_by(
            F('fecha_entrega_cliente').asc(nulls_last=True), '-updated_at'
        ),
        5,
    ).get_page(request.GET.get('asig', 1))

    # Cotizaciones pendientes de revisión
    cotizaciones_pendientes = Cotizacion.objects.filter(
        estado='pendiente'
    ).select_related('solicitud', 'tutor').count()

    from main_app.models import ContactMessage
    total_mensajes_contacto = ContactMessage.objects.count()
    mensajes_no_leidos = ContactMessage.objects.filter(read=False).count()

    from tickets.models import TicketReporte
    tickets_abiertos = TicketReporte.objects.filter(estado__in=['abierto', 'en_progreso']).count()

    context = {
        'total_solicitudes': total_solicitudes,
        'total_por_estados': total_por_estados,
        'estados': estados,
        'tutores_activos': tutores_activos,
        'solicitudes_recientes': solicitudes_recientes,
        'qs_base_rec': qs_base_sin_pagina(request, 'rec'),
        'estado_reci': estado_reci,
        'etiqueta_reci': etiqueta_reci,
        'solicitudes_asignadas': solicitudes_asignadas,
        'qs_base_asig': qs_base_sin_pagina(request, 'asig'),
        'cotizaciones_pendientes': cotizaciones_pendientes,
        'total_mensajes_contacto': total_mensajes_contacto,
        'mensajes_no_leidos': mensajes_no_leidos,
        'tickets_abiertos': tickets_abiertos,
    }
    return render(request, 'private/accounts/dashboard_admin.html', context)


@admin_o_tutor_required
def dashboard_tutor(request):
    """Panel del Tutor con sus solicitudes asignadas y disponibles."""
    from solicitudes.models import SolicitudAcademica, EstadoSolicitud
    from cotizaciones.models import Cotizacion

    # Mis solicitudes asignadas: priorizadas (correcciones → asignadas → demás)
    # y paginadas a 5 por página (parámetro propio `tareas`).
    mis_solicitudes_qs = SolicitudAcademica.objects.filter(
        tutor_asignado=request.user
    ).select_related('estado', 'area_conocimiento').annotate(
        prio=SolicitudAcademica.orden_prioridad_tutor()
    ).order_by(
        'prio',
        F('fecha_entrega_cliente').asc(nulls_last=True),
        '-updated_at',
    )
    mis_solicitudes = Paginator(mis_solicitudes_qs, 5).get_page(request.GET.get('tareas', 1))

    # Solicitudes disponibles para cotizar (sin tutor, estado nueva/en_cotizacion).
    # Incluye las ya cotizadas por el tutor (marcadas con `ya_cotizo`) para que
    # pueda ver el rango de cotizaciones recibidas.
    from django.db.models import Count, Min, Max, Exists, OuterRef
    ya_cotizo_subq = Cotizacion.objects.filter(solicitud=OuterRef('pk'), tutor=request.user)

    estados_abiertos = EstadoSolicitud.objects.filter(
        nombre__in=['nueva', 'en_cotizacion']
    )
    solicitudes_disponibles = SolicitudAcademica.objects.filter(
        estado__in=estados_abiertos,
        tutor_asignado__isnull=True
    ).select_related('estado', 'area_conocimiento').annotate(
        ya_cotizo=Exists(ya_cotizo_subq),
        num_cotizaciones=Count('cotizaciones'),
        monto_min=Min('cotizaciones__monto'),
        monto_max=Max('cotizaciones__monto'),
    ).order_by('-created_at')
    solicitudes_disponibles = Paginator(solicitudes_disponibles, 5).get_page(request.GET.get('disp', 1))

    # Mis cotizaciones enviadas
    mis_cotizaciones = list(Cotizacion.objects.filter(
        tutor=request.user
    ).select_related('solicitud').order_by('-created_at')[:5])
    # Agregados de cotizaciones por solicitud (para el modal "Ver" rango)
    if mis_cotizaciones:
        sol_ids = {c.solicitud_id for c in mis_cotizaciones}
        agg = Cotizacion.objects.filter(solicitud_id__in=sol_ids).values(
            'solicitud_id'
        ).annotate(n=Count('id'), mn=Min('monto'), mx=Max('monto'))
        agg_map = {f['solicitud_id']: f for f in agg}
        for c in mis_cotizaciones:
            a = agg_map.get(c.solicitud_id)
            c.sol_num = a['n'] if a else 0
            c.sol_min = a['mn'] if a else None
            c.sol_max = a['mx'] if a else None

    # Estadísticas del tutor
    perfil = getattr(request.user, 'perfil', None)
    en_progreso_count = mis_solicitudes_qs.filter(estado__nombre='en_progreso').count()
    completadas_count = SolicitudAcademica.objects.filter(
        tutor_asignado=request.user, estado__nombre='completada'
    ).count()

    # Límite de solicitudes activas para cotizar
    num_activas = SolicitudAcademica.activas_de_tutor(request.user).count()
    max_activas = SolicitudAcademica.MAX_SOLICITUDES_ACTIVAS_TUTOR

    # Distribución de MIS TAREAS por estado (gráfica donut del panel).
    # Se calculan los segmentos aquí para que el template solo pinte el SVG.
    tareas_por_estado = (
        SolicitudAcademica.objects.filter(tutor_asignado=request.user)
        .values('estado__nombre', 'estado__etiqueta', 'estado__color_hex')
        .annotate(cantidad=Count('id'))
        .order_by('estado__orden')
    )
    total_tareas = sum(f['cantidad'] for f in tareas_por_estado)
    tareas_segmentos = []
    acumulado = 0.0
    for fila in tareas_por_estado:
        pct = (fila['cantidad'] * 100.0 / total_tareas) if total_tareas else 0.0
        tareas_segmentos.append({
            'nombre': fila['estado__nombre'],
            'etiqueta': fila['estado__etiqueta'],
            'color': fila['estado__color_hex'],
            'cantidad': fila['cantidad'],
            'pct': pct,
            'resto': max(100.0 - pct, 0.0),
            'offset': (25.0 - acumulado) % 100.0,
        })
        acumulado += pct

    # Próximas entregas: tareas activas con fecha límite, las más cercanas primero
    proximas_entregas = (
        SolicitudAcademica.objects.filter(tutor_asignado=request.user)
        .exclude(estado__nombre__in=SolicitudAcademica.ESTADOS_CERRADOS_TUTOR)
        .filter(fecha_entrega_cliente__isnull=False)
        .select_related('estado', 'area_conocimiento')
        .order_by('fecha_entrega_cliente')[:5]
    )

    context = {
        'mis_solicitudes': mis_solicitudes,
        'solicitudes_disponibles': solicitudes_disponibles,
        'qs_base_tareas': qs_base_sin_pagina(request, 'tareas', 'disp'),
        'qs_base_disp': qs_base_sin_pagina(request, 'tareas', 'disp'),
        'mis_cotizaciones': mis_cotizaciones,
        'perfil': perfil,
        'en_progreso_count': en_progreso_count,
        'completadas_count': completadas_count,
        'num_solicitudes_activas': num_activas,
        'max_solicitudes_activas': max_activas,
        'puede_cotizar': num_activas < max_activas,
        'tareas_segmentos': tareas_segmentos,
        'total_tareas': total_tareas,
        'proximas_entregas': proximas_entregas,
    }
    return render(request, 'private/accounts/dashboard_tutor.html', context)


@admin_o_tutor_required
def perfil_view(request):
    """Ver y editar el perfil propio.

    El Admin conserva la edición completa (nombre, bio, áreas...). El Tutor
    solo puede cambiar su correo, teléfono y foto; el resto lo gestiona el
    Admin desde la edición de usuarios.
    """
    perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)
    es_admin_usuario = es_admin(request.user)
    FormClass = PerfilEditarForm if es_admin_usuario else PerfilPropioForm

    if request.method == 'POST':
        form = FormClass(request.POST, request.FILES, instance=perfil, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil actualizado correctamente.')
            return redirect('perfil')
    else:
        form = FormClass(instance=perfil, user=request.user)

    context = {'form': form, 'perfil': perfil, 'es_admin': es_admin_usuario}
    return render(request, 'private/accounts/perfil.html', context)


@admin_required
def usuarios_list(request):
    """Lista de todos los usuarios del sistema (solo Admin)."""
    q = request.GET.get('q', '')
    rol = request.GET.get('rol', '')

    usuarios = User.objects.filter(is_active=True).select_related('perfil').prefetch_related('groups', 'perfil__especialidades').order_by('-date_joined')

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
    context = {'usuarios': usuarios_page, 'pagina': usuarios_page, 'q': q, 'rol': rol, 'is_paginated': usuarios_page.has_other_pages(), 'qs_base': qs_base_sin_pagina(request, 'page'), 'usuario_actual_pk': request.user.pk}
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
                especialidades = list(perfil_form.cleaned_data.get('especialidades') or [])
                nueva = perfil_form.procesar_nueva_especialidad()
                if nueva and nueva not in especialidades:
                    especialidades.append(nueva)
                perfil.especialidades.set(especialidades)

            messages.success(request, f'Usuario @{user.username} creado correctamente.')
            return redirect('usuarios_list')
    else:
        form = UsuarioCrearForm()
        perfil_form = PerfilEditarForm()

    return render(request, 'private/accounts/usuario_crear.html', {'form': form, 'perfil_form': perfil_form})


@admin_required
def usuario_editar(request, pk):
    """Editar los datos de un usuario del sistema (solo Admin)."""
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'Usa "Mi Perfil" para editar tu propia cuenta.')
        return redirect('usuarios_list')
    # Protección: un admin que no sea superuser no puede editar a un superuser.
    if not request.user.is_superuser and user.is_superuser:
        messages.error(request, 'No puedes editar un usuario superusuario.')
        return redirect('usuarios_list')
    perfil, _ = PerfilUsuario.objects.get_or_create(user=user)

    if request.method == 'POST':
        form = UsuarioEditarForm(request.POST, instance=user)
        perfil_form = PerfilEditarForm(request.POST, request.FILES, instance=perfil, user=user)
        if form.is_valid() and perfil_form.is_valid():
            form.save()
            perfil_form.save()
            # Sincronizar especialidades (incluye el área nueva si se digitó).
            especialidades = list(perfil_form.cleaned_data.get('especialidades') or [])
            nueva = perfil_form.procesar_nueva_especialidad()
            if nueva and nueva not in especialidades:
                especialidades.append(nueva)
            perfil.especialidades.set(especialidades)
            messages.success(request, f'Usuario @{user.username} actualizado correctamente.')
            return redirect('usuarios_list')
    else:
        form = UsuarioEditarForm(instance=user)
        perfil_form = PerfilEditarForm(instance=perfil, user=user)

    return render(request, 'private/accounts/usuario_editar.html', {
        'form': form,
        'perfil_form': perfil_form,
        'usuario_editado': user,
        'perfil': perfil,
    })


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
    # Protección: un admin que no sea superuser no puede eliminar a un superuser.
    if not request.user.is_superuser and user.is_superuser:
        messages.error(request, 'No puedes eliminar un usuario superusuario.')
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


# ─── Gestión de Áreas de Conocimiento (catálogo) ────────────────────────────

def _es_ajax(request):
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.GET.get('json') == '1'
    )


@admin_required
def areas_list(request):
    """Catálogo de áreas de conocimiento: listar + crear (solo Admin)."""
    areas = AreaConocimiento.objects.all()
    if request.method == 'POST':
        form = AreaForm(request.POST)
        if form.is_valid():
            form.save()
            if _es_ajax(request):
                area = form.instance
                from django.http import JsonResponse
                return JsonResponse({'ok': True, 'id': area.pk, 'nombre': area.nombre})
            messages.success(request, f'Área "{form.instance.nombre}" creada correctamente.')
            return redirect('areas_list')
    else:
        form = AreaForm()
    return render(request, 'private/accounts/areas_list.html', {'areas': areas, 'area_form': form})


@admin_o_tutor_required
def area_crear(request):
    """Crea un área de conocimiento. Disponible para admins (página y AJAX)
    y para tutores vía el modal 'Otra' de su perfil."""
    if request.method != 'POST':
        return redirect('areas_list')
    nombre = (request.POST.get('nombre') or '').strip()
    icono = (request.POST.get('icono') or '').strip() or 'fa-book-open'
    activa = request.POST.get('activa') in ('on', 'true', '1')
    from django.http import JsonResponse
    if not nombre:
        if _es_ajax(request):
            return JsonResponse({'ok': False, 'error': 'El nombre es obligatorio.'}, status=400)
        messages.error(request, 'El nombre del área es obligatorio.')
        return redirect('areas_list')
    area, created = AreaConocimiento.objects.get_or_create(nombre=nombre)
    area.icono = icono or area.icono
    area.activa = activa
    area.save()
    if _es_ajax(request):
        return JsonResponse({'ok': True, 'id': area.pk, 'nombre': area.nombre, 'reutilizada': not created})
    messages.success(request, f'Área "{area.nombre}" {"creada" if created else "ya existía (se actualizó)"}.')
    return redirect('areas_list')


@admin_required
def area_editar(request, pk):
    """Renombra y actualiza un área de conocimiento (solo Admin)."""
    area = get_object_or_404(AreaConocimiento, pk=pk)
    if request.method == 'POST':
        nombre = (request.POST.get('nombre') or '').strip()
        if nombre:
            area.nombre = nombre
            area.icono = (request.POST.get('icono') or '').strip() or area.icono
            area.activa = request.POST.get('activa') in ('on', 'true', '1') or area.activa
            area.save()
            if _es_ajax(request):
                from django.http import JsonResponse
                return JsonResponse({'ok': True})
            messages.success(request, f'Área actualizada a "{area.nombre}".')
            return redirect('areas_list')
        if _es_ajax(request):
            from django.http import JsonResponse
            return JsonResponse({'ok': False, 'error': 'El nombre es obligatorio.'}, status=400)
    return redirect('areas_list')


@admin_required
def area_eliminar(request, pk):
    """Elimina un área de conocimiento (solo Admin)."""
    area = get_object_or_404(AreaConocimiento, pk=pk)
    from django.db.models.deletion import ProtectedError
    from django.http import JsonResponse
    if request.method == 'POST':
        try:
            area.delete()
        except ProtectedError:
            if _es_ajax(request):
                return JsonResponse({'ok': False, 'error': 'No se puede eliminar: está en uso por solicitudes existentes.'}, status=400)
            messages.error(request, f'No se puede eliminar el área "{area.nombre}" porque está en uso por solicitudes existentes.')
            return redirect('areas_list')
        if _es_ajax(request):
            return JsonResponse({'ok': True})
        messages.success(request, f'Área "{area.nombre}" eliminada.')
        return redirect('areas_list')
    return redirect('areas_list')


# ─── Usuarios Online (Admin) ──────────────────────────────────────────────────

@admin_required
def usuarios_online(request):
    """Lista de usuarios conectados en tiempo real (solo Admin)."""
    from accounts.presence import get_online_users_sync
    
    online = get_online_users_sync()
    
    # Enriquecer con datos del modelo User
    from django.contrib.auth.models import User
    user_ids = [u['id'] for u in online]
    users_map = {u.id: u for u in User.objects.filter(id__in=user_ids).select_related('perfil')}
    
    for u in online:
        user_obj = users_map.get(u['id'])
        if user_obj:
            u['username'] = user_obj.username
            u['full_name'] = user_obj.get_full_name() or user_obj.username
            u['email'] = user_obj.email
            u['is_staff'] = user_obj.is_staff
            u['groups'] = [g.name for g in user_obj.groups.all()]
            u['perfil_foto'] = user_obj.perfil.foto.url if hasattr(user_obj, 'perfil') and user_obj.perfil.foto else None
            u['perfil_es_tutor'] = hasattr(user_obj, 'perfil') and user_obj.groups.filter(name='Tutor').exists()
    
    context = {'usuarios_online': online}
    return render(request, 'private/accounts/usuarios_online.html', context)
