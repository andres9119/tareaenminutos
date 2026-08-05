from django.contrib import admin
from .models import Cotizacion


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ['solicitud', 'tutor', 'monto', 'tiempo_estimado_dias', 'estado', 'created_at']
    list_filter = ['estado']
    search_fields = ['solicitud__codigo', 'tutor__username']
    readonly_fields = ['created_at']
