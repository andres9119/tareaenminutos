from django.contrib import admin
from .models import Documento


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ['nombre_original', 'solicitud', 'tipo', 'subido_por', 'tamaño_bytes', 'created_at']
    list_filter = ['tipo']
    search_fields = ['nombre_original', 'solicitud__codigo']
    readonly_fields = ['created_at', 'tamaño_bytes', 'nombre_original']
