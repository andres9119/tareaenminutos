from django.contrib import admin
from .models import Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'destinatario', 'tipo', 'leida', 'created_at']
    list_filter = ['tipo', 'leida']
    search_fields = ['titulo', 'destinatario__username']
    readonly_fields = ['created_at']
    list_editable = ['leida']
