"""
Forms para cotizaciones de tutores.
"""

from django import forms
from django.utils import timezone
from .models import Cotizacion


class CotizacionForm(forms.ModelForm):
    """Formulario para que un tutor envíe una cotización."""

    class Meta:
        model = Cotizacion
        fields = ['monto', 'tiempo_estimado_dias', 'fecha_entrega_propuesta', 'descripcion_propuesta']
        widgets = {
            'monto': forms.NumberInput(attrs={
                'class': 'form-control-tem',
                'placeholder': '0',
                'min': '1000',
                'step': '500',
            }),
            'tiempo_estimado_dias': forms.NumberInput(attrs={
                'class': 'form-control-tem',
                'placeholder': 'Ej: 3',
                'min': '1',
                'max': '60',
            }),
            'fecha_entrega_propuesta': forms.DateInput(
                attrs={'class': 'form-control-tem', 'type': 'date'},
                format='%Y-%m-%d'
            ),
            'descripcion_propuesta': forms.Textarea(attrs={
                'class': 'form-control-tem',
                'rows': 5,
                'placeholder': 'Describe tu enfoque, experiencia en el tema, metodología y cualquier información relevante para el cliente...',
            }),
        }
        labels = {
            'monto': 'Tu precio (COP)',
            'tiempo_estimado_dias': 'Tiempo estimado (días)',
            'fecha_entrega_propuesta': 'Fecha de entrega que propones',
            'descripcion_propuesta': 'Descripción de tu propuesta',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_entrega_propuesta'].input_formats = ['%Y-%m-%d']

    def clean_fecha_entrega_propuesta(self):
        fecha = self.cleaned_data.get('fecha_entrega_propuesta')
        if fecha and fecha < timezone.localdate():
            raise forms.ValidationError('La fecha de entrega propuesta no puede ser en el pasado.')
        return fecha

    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if monto and monto < 1000:
            raise forms.ValidationError('El monto mínimo de cotización es $1.000 COP.')
        return monto
