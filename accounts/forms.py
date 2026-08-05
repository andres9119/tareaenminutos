"""
Forms para la app accounts - Gestión de usuarios y perfiles.
"""

from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm
from .models import PerfilUsuario, AreaConocimiento


class UsuarioCrearForm(UserCreationForm):
    """Formulario para crear nuevos usuarios del sistema TEM."""
    first_name = forms.CharField(
        max_length=100, required=True, label='Nombre',
        widget=forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Nombre'})
    )
    last_name = forms.CharField(
        max_length=100, required=True, label='Apellido',
        widget=forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Apellido'})
    )
    email = forms.EmailField(
        required=True, label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-control-tem', 'placeholder': 'correo@ejemplo.com'})
    )
    rol = forms.ChoiceField(
        choices=[('Administrador', 'Administrador'), ('Tutor', 'Tutor')],
        label='Rol',
        widget=forms.Select(attrs={'class': 'form-select-tem'})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'usuario'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control-tem'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control-tem'})
        self.fields['password1'].label = 'Contraseña'
        self.fields['password2'].label = 'Confirmar contraseña'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            rol = self.cleaned_data['rol']
            # Rol único: un usuario es Administrador O Tutor, nunca ambos.
            for grupo_rol in user.groups.filter(name__in=['Administrador', 'Tutor']):
                user.groups.remove(grupo_rol)
            group, _ = Group.objects.get_or_create(name=rol)
            user.groups.add(group)
        return user


class PerfilEditarForm(forms.ModelForm):
    """Formulario para editar el perfil del usuario."""
    first_name = forms.CharField(
        max_length=100, required=False, label='Nombre',
        widget=forms.TextInput(attrs={'class': 'form-control-tem'})
    )
    last_name = forms.CharField(
        max_length=100, required=False, label='Apellido',
        widget=forms.TextInput(attrs={'class': 'form-control-tem'})
    )
    email = forms.EmailField(
        required=False, label='Correo',
        widget=forms.EmailInput(attrs={'class': 'form-control-tem'})
    )

    class Meta:
        model = PerfilUsuario
        fields = ['telefono', 'foto', 'bio', 'especialidades', 'disponible']
        widgets = {
            'telefono': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': '+57 300 000 0000'}),
            'bio': forms.Textarea(attrs={'class': 'form-control-tem', 'rows': 3}),
            'especialidades': forms.CheckboxSelectMultiple(),
            'disponible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'foto': forms.FileInput(attrs={'class': 'form-control-tem'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email
            self._user = user

    def save(self, commit=True):
        perfil = super().save(commit=False)
        if hasattr(self, '_user'):
            self._user.first_name = self.cleaned_data.get('first_name', '')
            self._user.last_name = self.cleaned_data.get('last_name', '')
            self._user.email = self.cleaned_data.get('email', '')
            self._user.save()
        if commit:
            perfil.save()
            self.save_m2m()
        return perfil
