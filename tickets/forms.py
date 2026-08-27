from django import forms
from .models import TicketReporte


class TicketReporteForm(forms.ModelForm):
    class Meta:
        model = TicketReporte
        fields = ['titulo', 'descripcion', 'seccion']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'form-control-tem',
                'placeholder': 'Breve descripción del error',
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control-tem',
                'rows': 4,
                'placeholder': 'Describe el error con el mayor detalle posible...',
            }),
            'seccion': forms.TextInput(attrs={
                'class': 'form-control-tem',
                'placeholder': 'Ej: Panel Admin, Cotizaciones, Chat...',
            }),
        }
