"""
Decoradores de control de acceso por rol para la plataforma TEM.
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required


def admin_required(view_func):
    """Permite acceso solo a usuarios del grupo 'Administrador' o superusuarios."""
    @wraps(view_func)
    @login_required(login_url='login')
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_superuser or request.user.groups.filter(name='Administrador').exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos de administrador para acceder a esta sección.')
        return redirect('dashboard_redirect')
    return _wrapped_view


def tutor_required(view_func):
    """Permite acceso solo a usuarios del grupo 'Tutor'."""
    @wraps(view_func)
    @login_required(login_url='login')
    def _wrapped_view(request, *args, **kwargs):
        if request.user.groups.filter(name='Tutor').exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Esta sección es exclusiva para tutores.')
        return redirect('dashboard_redirect')
    return _wrapped_view


def admin_o_tutor_required(view_func):
    """Permite acceso a Admins y Tutores (usuarios autenticados del sistema interno)."""
    @wraps(view_func)
    @login_required(login_url='login')
    def _wrapped_view(request, *args, **kwargs):
        es_admin = request.user.is_superuser or request.user.groups.filter(name='Administrador').exists()
        es_tutor = request.user.groups.filter(name='Tutor').exists()
        if es_admin or es_tutor:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes acceso al sistema interno de TEM.')
        return redirect('login')
    return _wrapped_view
