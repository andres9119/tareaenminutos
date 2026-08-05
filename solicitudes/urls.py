from django.urls import path
from . import views

urlpatterns = [
    path('', views.solicitud_lista, name='solicitud_lista'),
    path('crear/', views.solicitud_crear, name='solicitud_crear'),
    path('disponibles/', views.solicitudes_disponibles, name='solicitudes_disponibles'),
    path('<int:pk>/', views.solicitud_detalle, name='solicitud_detalle'),
    path('<int:pk>/editar/', views.solicitud_editar, name='solicitud_editar'),
    path('<int:pk>/estado-tutor/', views.solicitud_actualizar_estado_tutor, name='solicitud_actualizar_estado_tutor'),
    path('<int:pk>/reasignar/', views.solicitud_reasignar_tutor, name='solicitud_reasignar_tutor'),
    path('<int:pk>/reactivar/', views.solicitud_reactivar, name='solicitud_reactivar'),
    path('<int:pk>/entregar/', views.solicitud_entregar, name='solicitud_entregar'),
    path('<int:pk>/completada/', views.solicitud_marcar_completada, name='solicitud_marcar_completada'),
    path('<int:pk>/calificar/', views.solicitud_calificar, name='solicitud_calificar'),
]
