from django.urls import path
from . import views

urlpatterns = [
    path('solicitud/<int:solicitud_pk>/cotizar/', views.cotizacion_crear, name='cotizacion_crear'),
    path('<int:pk>/aceptar/', views.cotizacion_aceptar, name='cotizacion_aceptar'),
    path('mis-cotizaciones/', views.mis_cotizaciones, name='mis_cotizaciones'),
    path('', views.cotizaciones_lista, name='cotizaciones_lista'),
]
