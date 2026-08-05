"""
Forms para gestión de documentos adjuntos a solicitudes.
"""

from django import forms
from django.conf import settings
import os
from .models import Documento


class DocumentoSubirForm(forms.ModelForm):
    """Formulario para subir un documento a una solicitud."""

    class Meta:
        model = Documento
        fields = ['tipo', 'archivo', 'descripcion']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select-tem'}),
            'archivo': forms.FileInput(attrs={'class': 'form-control-tem'}),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control-tem',
                'rows': 2,
                'placeholder': 'Descripción opcional del archivo...',
            }),
        }
        labels = {
            'tipo': 'Tipo de documento',
            'archivo': 'Seleccionar archivo',
            'descripcion': 'Descripción',
        }

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if archivo:
            # Validar tamaño (20 MB máx.)
            if archivo.size > 20 * 1024 * 1024:
                raise forms.ValidationError('El archivo no puede superar los 20 MB.')

            # Validar extensión
            _, ext = os.path.splitext(archivo.name)
            extensiones_permitidas = getattr(
                settings, 'ALLOWED_UPLOAD_EXTENSIONS',
                ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.zip', '.txt']
            )
            if ext.lower() not in extensiones_permitidas:
                raise forms.ValidationError(
                    f'Tipo de archivo no permitido. Extensiones aceptadas: {", ".join(extensiones_permitidas)}'
                )
        return archivo
