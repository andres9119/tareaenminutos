"""
Forms para la app accounts - Gestión de usuarios y perfiles.
"""

from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm
from .models import PerfilUsuario, AreaConocimiento


class AreaForm(forms.ModelForm):
    """Formulario para crear/editar un Área de Conocimiento (catálogo)."""

    class Meta:
        model = AreaConocimiento
        fields = ['nombre', 'icono', 'activa']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Ej: Ingeniería de Software'}),
            'icono': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'fa-code'}),
        }


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
        rol = self.cleaned_data['rol']
        # Rol único: un usuario es Administrador O Tutor, nunca ambos.
        # Un Administrador se crea como superuser (is_staff + is_superuser),
        # dándole acceso completo al panel de Django /admin/.
        if rol == 'Administrador':
            user.is_staff = True
            user.is_superuser = True
        if commit:
            user.save()
            for grupo_rol in user.groups.filter(name__in=['Administrador', 'Tutor']):
                user.groups.remove(grupo_rol)
            group, _ = Group.objects.get_or_create(name=rol)
            user.groups.add(group)
        return user


class UsuarioEditarForm(forms.ModelForm):
    """Formulario para que un Admin edite otro usuario del sistema.

    Permite modificar datos de cuenta (usuario, nombres, correo), cambiar el
    rol (con los mismos flags que la creación: Administrador => staff+superuser),
    y fijar una contraseña nueva opcional.
    """
    rol = forms.ChoiceField(
        choices=[('Administrador', 'Administrador'), ('Tutor', 'Tutor')],
        label='Rol',
        widget=forms.Select(attrs={'class': 'form-select-tem'})
    )
    password_nueva = forms.CharField(
        required=False,
        label='Nueva contraseña (opcional)',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control-tem',
            'placeholder': 'Dejar vacío para conservar la actual',
            'autocomplete': 'new-password',
        })
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'usuario'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Nombre'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': 'Apellido'}),
            'email': forms.EmailInput(attrs={'class': 'form-control-tem', 'placeholder': 'correo@ejemplo.com'}),
        }
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.is_superuser:
                self.initial['rol'] = 'Administrador'
            elif self.instance.groups.filter(name='Tutor').exists():
                self.initial['rol'] = 'Tutor'

    def save(self, commit=True):
        user = super().save(commit=False)
        rol = self.cleaned_data['rol']
        pwd_nueva = self.cleaned_data.get('password_nueva')
        if pwd_nueva:
            user.set_password(pwd_nueva)
        # Rol único, mismo criterio que UsuarioCrearForm:
        # Administrador => acceso a /app/ y /admin/; Tutor => sin esos flags.
        if rol == 'Administrador':
            user.is_staff = True
            user.is_superuser = True
        else:
            user.is_staff = False
            user.is_superuser = False
        if commit:
            user.save()
            for grupo_rol in user.groups.filter(name__in=['Administrador', 'Tutor']):
                user.groups.remove(grupo_rol)
            group, _ = Group.objects.get_or_create(name=rol)
            user.groups.add(group)
        return user


class PerfilPropioForm(forms.ModelForm):
    """Lo que el usuario (tutor) puede editar de su PROPIO perfil:
    solo correo, teléfono y foto.

    Nombre, apellido, bio y áreas de especialidad los gestiona el Admin
    desde la edición de usuarios; este formulario ni los muestra ni los guarda.
    """
    email = forms.EmailField(
        required=True, label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-control-tem'})
    )

    class Meta:
        model = PerfilUsuario
        fields = ['telefono', 'foto']
        widgets = {
            'telefono': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': '+57 300 000 0000'}),
            'foto': forms.FileInput(attrs={'class': 'form-control-tem'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self._user = user
        if user:
            self.fields['email'].initial = user.email

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        qs = User.objects.filter(email__iexact=email)
        if self._user:
            qs = qs.exclude(pk=self._user.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe una cuenta con ese correo.')
        return email

    def save(self, commit=True):
        perfil = super().save(commit=False)
        if self._user:
            self._user.email = self.cleaned_data['email']
            self._user.save(update_fields=['email'])
        if commit:
            perfil.save()
        return perfil


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
    nueva_especialidad = forms.CharField(
        required=False,
        label='Agregar otra área',
        widget=forms.TextInput(attrs={
            'class': 'form-control-tem',
            'placeholder': 'Si el área no está en la lista, escríbela aquí'
        })
    )

    class Meta:
        model = PerfilUsuario
        fields = ['telefono', 'foto', 'bio', 'especialidades']
        widgets = {
            'telefono': forms.TextInput(attrs={'class': 'form-control-tem', 'placeholder': '+57 300 000 0000'}),
            'bio': forms.Textarea(attrs={'class': 'form-control-tem', 'rows': 3}),
            'especialidades': forms.CheckboxSelectMultiple(),
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

    def procesar_nueva_especialidad(self):
        """Crea (o reutiliza) un AreaConocimiento a partir del campo nueva_especialidad."""
        nombre = (self.cleaned_data.get('nueva_especialidad') or '').strip()
        if not nombre:
            return None
        area, _ = AreaConocimiento.objects.get_or_create(nombre=nombre)
        return area

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
            nueva = self.procesar_nueva_especialidad()
            if nueva:
                perfil.especialidades.add(nueva)
        return perfil
