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
        fields = ['monto', 'tiempo_estimado_dias', 'descripcion_propuesta']
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
            'descripcion_propuesta': forms.Textarea(attrs={
                'class': 'form-control-tem',
                'rows': 3,
                'placeholder': 'Describe tu enfoque, experiencia en el tema y metodología...',
            }),
        }
        labels = {
            'monto': 'Tu precio (COP)',
            'tiempo_estimado_dias': 'Tiempo estimado (días)',
            'descripcion_propuesta': 'Descripción de tu propuesta (opcional)',
        }

    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if monto and monto < 1000:
            raise forms.ValidationError('El monto mínimo de cotización es $1.000 COP.')
        return monto
