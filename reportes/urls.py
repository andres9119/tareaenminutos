from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_reportes, name='dashboard_reportes'),
    path('exportar/solicitudes/', views.exportar_solicitudes_csv, name='exportar_solicitudes_csv'),
]
