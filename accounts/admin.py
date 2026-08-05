from django.contrib import admin
from .models import PerfilUsuario, AreaConocimiento


@admin.register(AreaConocimiento)
class AreaConocimientoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'icono', 'activa']
    list_editable = ['activa']
    search_fields = ['nombre']


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ['user', 'telefono', 'calificacion_promedio', 'trabajos_completados', 'disponible']
    list_filter = ['disponible']
    search_fields = ['user__username', 'user__email', 'user__first_name']
    filter_horizontal = ['especialidades']
    readonly_fields = ['calificacion_promedio', 'trabajos_completados']
