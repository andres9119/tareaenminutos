from django.urls import path
from . import views

urlpatterns = [
    path('reportar/', views.ticket_crear, name='ticket_crear'),
    path('creado/', views.ticket_creado, name='ticket_creado'),
    path('lista/', views.ticket_lista, name='ticket_lista'),
    path('<int:pk>/estado/', views.ticket_cambiar_estado, name='ticket_cambiar_estado'),
]
