from django.contrib import admin
from .models import TicketReporte


@admin.register(TicketReporte)
class TicketReporteAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'seccion', 'estado', 'creado_por', 'created_at')
    list_filter = ('estado', 'seccion')
    search_fields = ('titulo', 'descripcion', 'solucion', 'creado_por__username', 'creado_por__email')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('titulo', 'seccion', 'descripcion', 'solucion', 'estado', 'creado_por'),
        }),
        ('Fechas', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
