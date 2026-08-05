"""
Views para reportes y estadísticas — App reportes.
"""

import csv
from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from datetime import timedelta
from accounts.decorators import admin_required
from solicitudes.models import SolicitudAcademica, EstadoSolicitud
from cotizaciones.models import Cotizacion
from accounts.models import AreaConocimiento
from django.contrib.auth.models import User


@admin_required
def dashboard_reportes(request):
    """Dashboard de reportes y métricas (solo Admin)."""
    hoy = timezone.now()
    hace_30_dias = hoy - timedelta(days=30)

    # KPIs del mes
    solicitudes_mes = SolicitudAcademica.objects.filter(created_at__gte=hace_30_dias)
    ingresos_mes = solicitudes_mes.filter(
        estado__nombre='completada'
    ).aggregate(total=Sum('precio_final'))['total'] or 0

    # Solicitudes por estado (para gráfica de torta)
    por_estado = EstadoSolicitud.objects.annotate(
        total=Count('solicitudacademica')
    ).values('etiqueta', 'color_hex', 'total').order_by('-total')

    # Solicitudes por área de conocimiento
    por_area = AreaConocimiento.objects.annotate(
        total=Count('solicitudacademica')
    ).filter(total__gt=0).values('nombre', 'icono', 'total').order_by('-total')[:8]

    # Top tutores por solicitudes completadas
    top_tutores = User.objects.filter(
        groups__name='Tutor',
        solicitudes_asignadas__estado__nombre='completada'
    ).annotate(
        completadas=Count('solicitudes_asignadas'),
    ).select_related('perfil').order_by('-completadas')[:5]

    # Solicitudes por nivel académico
    por_nivel = SolicitudAcademica.objects.values('nivel_academico').annotate(
        total=Count('id')
    ).order_by('-total')

    # Tendencia últimos 7 días (solicitudes por día)
    tendencia_dias = []
    for i in range(6, -1, -1):
        dia = hoy - timedelta(days=i)
        inicio = dia.replace(hour=0, minute=0, second=0, microsecond=0)
        fin = dia.replace(hour=23, minute=59, second=59)
        count = SolicitudAcademica.objects.filter(created_at__range=(inicio, fin)).count()
        tendencia_dias.append({
            'dia': dia.strftime('%d/%m'),
            'count': count,
        })

    context = {
        'solicitudes_mes': solicitudes_mes.count(),
        'ingresos_mes': ingresos_mes,
        'por_estado': list(por_estado),
        'por_area': list(por_area),
        'top_tutores': top_tutores,
        'por_nivel': list(por_nivel),
        'tendencia_dias': tendencia_dias,
        'hoy': hoy,
    }
    return render(request, 'private/reportes/dashboard.html', context)


@admin_required
def exportar_solicitudes_csv(request):
    """Exportar solicitudes a CSV para Excel."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="solicitudes_TEM.csv"'
    response.write('\ufeff')  # BOM para que Excel reconozca UTF-8

    writer = csv.writer(response)
    writer.writerow([
        'Código', 'Fecha Creación', 'Cliente', 'Email', 'Universidad',
        'Título', 'Área', 'Nivel', 'Tipo', 'Estado',
        'Tutor Asignado', 'Precio Final (COP)', 'Fecha Entrega'
    ])

    solicitudes = SolicitudAcademica.objects.select_related(
        'estado', 'area_conocimiento', 'tutor_asignado'
    ).all().order_by('-created_at')

    for s in solicitudes:
        writer.writerow([
            s.codigo,
            s.created_at.strftime('%Y-%m-%d %H:%M'),
            s.cliente_nombre,
            s.cliente_email,
            s.cliente_universidad,
            s.titulo,
            str(s.area_conocimiento),
            s.get_nivel_academico_display(),
            s.get_tipo_entrega_display(),
            s.estado.etiqueta,
            s.tutor_asignado.get_full_name() if s.tutor_asignado else '',
            str(s.precio_final) if s.precio_final else '',
            s.fecha_entrega_cliente.strftime('%Y-%m-%d') if s.fecha_entrega_cliente else '',
        ])

    return response
