from django.urls import path
from . import views

urlpatterns = [
    path('', views.mis_chats, name='mis_chats'),
    path('directo/<int:user_id>/', views.iniciar_chat_directo, name='iniciar_chat_directo'),
    path('general/', views.sala_general, name='sala_general'),
    path('datos/', views.datos_messenger, name='datos_messenger'),
    path('<int:pk>/mensajes/', views.chat_mensajes_json, name='chat_mensajes_json'),
    path('<int:pk>/pdf/', views.sala_chat_pdf, name='sala_chat_pdf'),
    path('<int:pk>/', views.sala_chat, name='sala_chat'),
]
