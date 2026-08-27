from django.shortcuts import render, redirect
from django.contrib import messages
from accounts.decorators import admin_o_tutor_required, admin_required
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
