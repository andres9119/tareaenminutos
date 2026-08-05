"""
Forms para solicitudes académicas.
"""

from django import forms
from django.utils import timezone
from .models import SolicitudAcademica, EstadoSolicitud
from accounts.models import AreaConocimiento


class SolicitudForm(forms.ModelForm):
    """Formulario para crear y editar solicitudes académicas."""

    class Meta:
        model = SolicitudAcademica
        fields = [
            'cliente_nombre', 'cliente_email', 'cliente_telefono', 'cliente_universidad',
            'titulo', 'descripcion', 'area_conocimiento', 'nivel_academico',
            'tipo_entrega', 'materia', 'fecha_entrega_cliente',
            'presupuesto_cliente', 'notas_internas',
        ]
        widgets = {
            'cliente_nombre': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Nombre completo del cliente'}),
            'cliente_email': forms.EmailInput(attrs={'class': 'form-control-tem', 'placeholder': 'correo@ejemplo.com'}),
            'cliente_telefono': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': '+57 300 000 0000'}),
            'cliente_universidad': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Ej: Universidad Nacional de Colombia'}),
            'titulo': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Título descriptivo del trabajo'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control-tem', 'rows': 5, 'placeholder': 'Describe detalladamente el trabajo, requisitos, formato, normas, etc.'}),
            'area_conocimiento': forms.Select(attrs={'class': 'form-select-tem'}),
            'nivel_academico': forms.Select(attrs={'class': 'form-select-tem'}),
            'tipo_entrega': forms.Select(attrs={'class': 'form-select-tem'}),
            'materia': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Ej: Cálculo Diferencial, Derecho Comercial'}),
            'fecha_entrega_cliente': forms.DateInput(
                attrs={'class': 'form-control-tem', 'type': 'date'},
                format='%Y-%m-%d'
            ),
            'presupuesto_cliente': forms.NumberInput(attrs={'class': 'form-control-tem', 'placeholder': '0', 'min': '0', 'step': '1000'}),
            'notas_internas': forms.Textarea(attrs={'class': 'form-control-tem', 'rows': 3, 'placeholder': 'Notas privadas (solo visible para administradores)'}),
        }
        labels = {
            'cliente_nombre': 'Nombre del Cliente',
            'cliente_email': 'Email del Cliente',
            'cliente_telefono': 'Teléfono del Cliente',
            'cliente_universidad': 'Universidad',
            'presupuesto_cliente': 'Presupuesto del Cliente (COP)',
        }

    # Campos "Otro" para las listas desplegables (se muestran al elegir "Otro...")
    nivel_academico_otro = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control-tem other-field', 'placeholder': 'Especifica el nivel académico'})
    )
    tipo_entrega_otro = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control-tem other-field', 'placeholder': 'Especifica el tipo de entrega'})
    )
    area_conocimiento_otro = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control-tem other-field', 'placeholder': 'Especifica el área'})
    )

    VALOR_OTRO = '__otro__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make form fields non-required by default so admin can decide which to fill.
        for name, field in self.fields.items():
            field.required = False

        # Preserve input format for date field if provided
        self.fields['fecha_entrega_cliente'].input_formats = ['%Y-%m-%d']

        # Agregar la opción "Otro..." a los desplegables de opciones fijas
        for name in ['nivel_academico', 'tipo_entrega']:
            constantes = getattr(SolicitudAcademica, {
                'nivel_academico': 'NIVEL_ACADEMICO',
                'tipo_entrega': 'TIPO_ENTREGA',
            }[name])
            base = [c for c in constantes if c[0] != self.VALOR_OTRO and c[0] != 'otro']
            self.fields[name] = forms.ChoiceField(
                required=False,
                choices=[('', '---------')] + base + [(self.VALOR_OTRO, 'Otro...')],
                widget=forms.Select(attrs={'class': 'form-select-tem'})
            )
            self._habilitar_otro(name)

        # área de conocimiento: convertir a ChoiceField con opción "Otro..."
        self.fields['area_conocimiento'] = forms.ChoiceField(
            required=False,
            choices=[('', '---------')]
            + [(a.pk, a.nombre) for a in AreaConocimiento.objects.filter(activa=True).order_by('nombre')]
            + [(self.VALOR_OTRO, 'Otro...')],
            widget=forms.Select(attrs={'class': 'form-select-tem'})
        )
        self._habilitar_otro('area_conocimiento')

    def _habilitar_otro(self, name):
        """Marca el select para que el JS muestre el campo de texto 'Otro'."""
        attrs = self.fields[name].widget.attrs
        attrs['data-other'] = f'id_{name}_otro'
        attrs['class'] = attrs.get('class', '') + ' other-enabled'

    def _valor_otro(self, field_name, otro_name, etiqueta):
        """Si el desplegable eligió 'Otro...', devuelve el texto digitado."""
        valor = self.cleaned_data.get(field_name)
        if valor != self.VALOR_OTRO:
            return valor
        texto = (self.cleaned_data.get(otro_name) or self.data.get(otro_name, '') or '').strip()
        if not texto:
            raise forms.ValidationError(f'Indica el valor en "{etiqueta}".')
        return texto

    def clean_nivel_academico(self):
        return self._valor_otro('nivel_academico', 'nivel_academico_otro', 'nivel académico')

    def clean_tipo_entrega(self):
        return self._valor_otro('tipo_entrega', 'tipo_entrega_otro', 'tipo de entrega')

    def clean_area_conocimiento(self):
        valor = self.cleaned_data.get('area_conocimiento')
        if not valor or valor == self.VALOR_OTRO:
            if valor == self.VALOR_OTRO:
                nombre = (self.cleaned_data.get('area_conocimiento_otro') or self.data.get('area_conocimiento_otro', '') or '').strip()
                if not nombre:
                    raise forms.ValidationError('Indica el nombre del área.')
                area, _ = AreaConocimiento.objects.get_or_create(
                    nombre=nombre, defaults={'icono': 'fa-book-open'}
                )
                return area
            return None
        try:
            return AreaConocimiento.objects.get(pk=valor)
        except AreaConocimiento.DoesNotExist:
            return None

    def clean_fecha_entrega_cliente(self):
        fecha = self.cleaned_data.get('fecha_entrega_cliente')
        if fecha and fecha < timezone.localdate():
            raise forms.ValidationError('La fecha de entrega no puede ser en el pasado.')
        return fecha


class CambiarEstadoForm(forms.Form):
    """Formulario para cambiar el estado de una solicitud.

    Si se pasa `allowed_states` (lista de nombres), filtra el queryset
    de estados disponibles a solo esos.
    """
    estado = forms.ModelChoiceField(
        queryset=EstadoSolicitud.objects.all(),
        label='Nuevo Estado',
        widget=forms.Select(attrs={'class': 'form-select-tem'})
    )
    comentario = forms.CharField(
        required=False,
        label='Comentario',
        widget=forms.Textarea(attrs={'class': 'form-control-tem', 'rows': 3, 'placeholder': 'Comentario opcional sobre el cambio de estado'})
    )

    def __init__(self, *args, **kwargs):
        allowed_states = kwargs.pop('allowed_states', None)
        super().__init__(*args, **kwargs)
        if allowed_states:
            self.fields['estado'].queryset = EstadoSolicitud.objects.filter(
                nombre__in=allowed_states
            )


class FiltroSolicitudForm(forms.Form):
    """Formulario de filtros para la lista de solicitudes."""
    estado = forms.ModelChoiceField(
        queryset=EstadoSolicitud.objects.all(),
        required=False, empty_label='Todos los estados',
        widget=forms.Select(attrs={'class': 'form-select-tem'})
    )
    area = forms.ModelChoiceField(
        queryset=AreaConocimiento.objects.filter(activa=True),
        required=False, empty_label='Todas las áreas',
        widget=forms.Select(attrs={'class': 'form-select-tem'})
    )
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control-tem', 'type': 'date'})
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control-tem', 'type': 'date'})
    )
    buscar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Buscar por código, cliente o título...'})
    )
