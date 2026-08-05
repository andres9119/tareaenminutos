from django.contrib import admin
from .models import SolicitudAcademica, EstadoSolicitud, HistorialEstado


@admin.register(EstadoSolicitud)
class EstadoSolicitudAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'etiqueta', 'color_hex', 'orden']
    list_editable = ['etiqueta', 'color_hex', 'orden']
    ordering = ['orden']


@admin.register(SolicitudAcademica)
class SolicitudAcademicaAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'titulo', 'cliente_nombre', 'area_conocimiento', 'estado', 'tutor_asignado', 'created_at']
    list_filter = ['estado', 'area_conocimiento', 'nivel_academico']
    search_fields = ['codigo', 'titulo', 'cliente_nombre', 'cliente_email']
    readonly_fields = ['codigo', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']


@admin.register(HistorialEstado)
class HistorialEstadoAdmin(admin.ModelAdmin):
    list_display = ['solicitud', 'estado_anterior', 'estado_nuevo', 'cambiado_por', 'created_at']
    list_filter = ['estado_nuevo']
    readonly_fields = ['created_at']
