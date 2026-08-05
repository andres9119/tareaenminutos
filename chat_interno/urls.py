from django.urls import path
from . import views

urlpatterns = [
    path('', views.mis_chats, name='mis_chats'),
    path('general/', views.sala_general, name='sala_general'),
    path('datos/', views.datos_messenger, name='datos_messenger'),
    path('<int:pk>/', views.sala_chat, name='sala_chat'),
]
