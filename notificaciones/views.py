"""
Views para notificaciones internas.
"""

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from .models import Notificacion
from accounts.decorators import admin_o_tutor_required


@admin_o_tutor_required
def notificaciones_list(request):
    """Lista completa de notificaciones del usuario.

    No marca todo como leído automáticamente para que el usuario pueda
    distinguir lo pendiente. El leído se gestiona por item o con el botón
    "Marcar todas leídas".

    Los mensajes de chat no se listan aquí: viven en el icono de mensajes.
    """
    notificaciones = Notificacion.objects.filter(
        destinatario=request.user
    ).exclude(tipo='mensaje_chat').order_by('-created_at')

    paginator = Paginator(notificaciones, 20)
    page = request.GET.get('page', 1)
    notificaciones_page = paginator.get_page(page)

    return render(request, 'private/notificaciones/lista.html', {'notificaciones': notificaciones_page, 'pagina': notificaciones_page, 'is_paginated': notificaciones_page.has_other_pages()})


@require_POST
@admin_o_tutor_required
def marcar_leida(request, pk):
    """Marcar como leída (AJAX).

    Si la notificación pertenece a una solicitud (solicitud_id), se marcan
    TODAS las no leídas de ese mismo código de una vez, para no tener que
    verlas una por una (ej. varias cotizaciones del mismo TEM). Las de otros
    códigos quedan intactas. Retorna cuántas se marcaron.
    """
    notif = get_object_or_404(Notificacion, pk=pk, destinatario=request.user)
    if notif.solicitud_id:
        marcadas = Notificacion.objects.filter(
            destinatario=request.user, leida=False, solicitud_id=notif.solicitud_id
        ).update(leida=True)
        return JsonResponse({'ok': True, 'marcadas': marcadas, 'solicitud_id': notif.solicitud_id})
    notif.marcar_leida()
    return JsonResponse({'ok': True, 'marcadas': 1, 'solicitud_id': None})


@require_POST
@admin_o_tutor_required
def marcar_todas_leidas(request):
    """Marcar todas las notificaciones como leídas (AJAX)."""
    Notificacion.objects.filter(destinatario=request.user, leida=False).update(leida=True)
    return JsonResponse({'ok': True})
