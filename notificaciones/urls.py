from django.urls import path
from . import views

urlpatterns = [
    path('', views.notificaciones_list, name='notificaciones_list'),
    path('<int:pk>/leida/', views.marcar_leida, name='notif_marcar_leida'),
    path('todas-leidas/', views.marcar_todas_leidas, name='notif_todas_leidas'),
]
