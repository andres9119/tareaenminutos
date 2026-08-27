from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.models import User
from django.db.models import Q
from accounts.decorators import admin_o_tutor_required, admin_required
from notificaciones.utils import crear_notificacion
from .models import TicketReporte
from .forms import TicketReporteForm


@admin_o_tutor_required
def ticket_crear(request):
    if request.method == 'POST':
        form = TicketReporteForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.creado_por = request.user
            ticket.save()

            # Avisar a todos los admins (is_staff o grupo Administrador), excepto quien reporta.
            admins = User.objects.filter(is_active=True).filter(
                Q(is_staff=True) | Q(groups__name='Administrador')
            ).exclude(pk=request.user.pk).distinct()
            for admin in admins:
                crear_notificacion(
                    destinatario=admin,
                    tipo='ticket_reportado',
                    titulo=f'Incidente reportado: {ticket.titulo}',
                    mensaje=f'{request.user.get_full_name() or request.user.username} reportó un incidente'
                            f'{" en " + ticket.seccion if ticket.seccion else ""}.',
                    url_accion=reverse('ticket_lista'),
                )

            messages.success(request, 'Reporte enviado correctamente. Nuestro equipo lo revisará pronto.')
            return redirect('ticket_creado')
    else:
        form = TicketReporteForm()
    return render(request, 'private/tickets/crear.html', {'form': form})


@admin_o_tutor_required
def ticket_creado(request):
    return render(request, 'private/tickets/creado.html')


@admin_required
def ticket_lista(request):
    tickets = TicketReporte.objects.select_related('creado_por').all()
    return render(request, 'private/tickets/lista.html', {'tickets': tickets})


@admin_required
def ticket_cambiar_estado(request, pk):
    """El admin actualiza el estado del ticket y se avisa al reportante."""
    if request.method != 'POST':
        return redirect('ticket_lista')
    ticket = get_object_or_404(TicketReporte, pk=pk)
    nuevo_estado = request.POST.get('estado', '')
    if nuevo_estado not in dict(TicketReporte.ESTADO_CHOICES):
        messages.error(request, 'Estado inválido.')
        return redirect('ticket_lista')
    if nuevo_estado != ticket.estado:
        estado_anterior = ticket.get_estado_display()
        ticket.estado = nuevo_estado
        if nuevo_estado == 'resuelto':
            solucion = (request.POST.get('solucion') or '').strip()
            if solucion:
                ticket.solucion = solucion
        ticket.save(update_fields=['estado', 'solucion', 'updated_at'])
        messages.success(
            request,
            f'Ticket "{ticket.titulo}" cambiado de {estado_anterior} a {ticket.get_estado_display()}.'
        )
        if ticket.creado_por and ticket.creado_por_id != request.user.pk:
            crear_notificacion(
                destinatario=ticket.creado_por,
                tipo='ticket_resuelto',
                titulo=f'Tu reporte ahora está: {ticket.get_estado_display()}',
                mensaje=f'"{ticket.titulo}" cambió de {estado_anterior} a {ticket.get_estado_display()}.',
                url_accion=reverse('dashboard_redirect'),
            )
    return redirect('ticket_lista')
