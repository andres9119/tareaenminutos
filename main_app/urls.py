from django.urls import path
from django.views.generic.base import TemplateView, RedirectView
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('recuperar/', views.password_reset_request, name='password_reset'),
    path('recuperar/enviado/', views.password_reset_done, name='password_reset_done'),
    path('recuperar/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('recuperar/completado/', views.password_reset_complete, name='password_reset_complete'),
    path('administracion/', views.administracion, name='administracion'),
    path('bienvenidos/', views.bienvenidos, name='bienvenidos'),
    path('blog/', views.blog_list, name='blog_list'),
    path('blog/<slug:slug>/', views.blog_detail, name='blog_detail'),
    path('contacto/', views.contact_view, name='contact'),
    path('app/mensajes-contacto/', views.contact_mensajes_list, name='contact_mensajes_list'),
    path('app/mensajes-contacto/<int:pk>/', views.contact_mensaje_detalle, name='contact_mensaje_detalle'),
    path('chat/', RedirectView.as_view(url='/app/chat/', permanent=True), name='chat'),
    path('robots.txt', TemplateView.as_view(template_name='main_app/robots.txt', content_type='text/plain')),
    path('sitemap.xml', views.sitemap_view, name='sitemap'),
]
