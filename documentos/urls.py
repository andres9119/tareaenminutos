from django.urls import path
from . import views

urlpatterns = [
    path('solicitud/<int:solicitud_pk>/subir/', views.documento_subir, name='documento_subir'),
    path('solicitud/<int:solicitud_pk>/subir-comprobante/', views.documento_subir_comprobante, name='documento_subir_comprobante'),
    path('<int:pk>/descargar/', views.documento_descargar, name='documento_descargar'),
    path('<int:pk>/eliminar/', views.documento_eliminar, name='documento_eliminar'),
]
