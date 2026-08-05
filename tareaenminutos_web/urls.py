"""
URL configuration for tareaenminutos_web project — incluye la plataforma privada TEM.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django admin nativo
    path('admin/', admin.site.urls),

    # Sitio público (landing, blog, contacto, login)
    path('', include('main_app.urls')),

    # ─── Plataforma Privada TEM ───────────────────────────────────────────────
    path('app/', include('accounts.urls')),
    path('solicitudes/', include('solicitudes.urls')),
    path('cotizaciones/', include('cotizaciones.urls')),
    path('documentos/', include('documentos.urls')),
    path('notificaciones/', include('notificaciones.urls')),
    path('app/chat/', include('chat_interno.urls')),
    path('reportes/', include('reportes.urls')),
]

# ─── Servir archivos multimedia (imágenes subidas, documentos) ─────────────────
# En producción con nginx, comenta esta línea y configura:
#   location /media/ { alias /ruta/a/tareaenminutos_web/media/; }
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
