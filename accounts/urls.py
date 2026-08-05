from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_redirect, name='dashboard_redirect'),
    path('dashboard/', views.dashboard_redirect, name='dashboard'),
    path('dashboard/admin/', views.dashboard_admin, name='dashboard_admin'),
    path('dashboard/tutor/', views.dashboard_tutor, name='dashboard_tutor'),
    path('perfil/', views.perfil_view, name='perfil'),
    path('usuarios/', views.usuarios_list, name='usuarios_list'),
    path('usuarios/crear/', views.usuario_crear, name='usuario_crear'),
    path('usuarios/<int:pk>/toggle/', views.usuario_toggle_activo, name='usuario_toggle_activo'),
    path('usuarios/<int:pk>/eliminar/', views.usuario_eliminar, name='usuario_eliminar'),
    path('tutores/<int:pk>/', views.tutor_detalle, name='tutor_detalle'),
]
