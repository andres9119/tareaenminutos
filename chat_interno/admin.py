from django.contrib import admin
from .models import SalaChat, MensajeChat


@admin.register(SalaChat)
class SalaChatAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'tipo', 'solicitud', 'created_at']
    list_filter = ['tipo']
    filter_horizontal = ['participantes']


@admin.register(MensajeChat)
class MensajeChatAdmin(admin.ModelAdmin):
    list_display = ['autor', 'sala', 'contenido', 'tipo', 'created_at']
    list_filter = ['tipo']
    search_fields = ['contenido', 'autor__username']
    readonly_fields = ['created_at']
