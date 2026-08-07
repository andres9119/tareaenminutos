from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.db.models import Q
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import ContactMessage, ChatMessage


class TutorPasswordResetForm(PasswordResetForm):
    """Recuperación de contraseña EXCLUSIVA para tutores.

    Solo los usuarios del grupo 'Tutor' reciben el enlace de restablecimiento.
    Los administradores no pueden recuperar su contraseña por esta vía.
    """

    def get_users(self, email):
        """Solo devuelve tutores activos cuyo email o username coincida."""
        active_tutors = User.objects.filter(
            is_active=True,
            groups__name='Tutor',
        ).filter(
            Q(email__iexact=email) | Q(username__iexact=email)
        )
        for user in active_tutors.distinct():
            if user.has_usable_password():
                yield user

    def clean(self):
        """Solo permite solicitar recuperación si el dato corresponde a un tutor."""
        cleaned = super().clean()
        email = cleaned.get('email')
        if email and not any(self.get_users(email)):
            raise forms.ValidationError(
                'No encontramos una cuenta de tutor con ese correo o usuario. '
                'Verifica el dato e inténtalo de nuevo.'
            )
        return cleaned

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        user = context.get('user')
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        base = settings.SITE_BASE_URL.rstrip('/')
        reset_url = f"{base}{reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})}"

        subject = "Recuperación de contraseña - Tarea en Minutos"
        body = (
            f"Hola {user.first_name or user.username},\n\n"
            "Recibimos una solicitud para restablecer la contraseña de tu cuenta "
            "de tutor en Tarea en Minutos.\n\n"
            "Ingresa al siguiente enlace para crear una nueva contraseña:\n"
            f"{reset_url}\n\n"
            "Este enlace es válido por un tiempo limitado. Si no solicitaste este "
            "cambio, puedes ignorar este correo.\n\n"
            "Equipo Tarea en Minutos"
        )

        if settings.EMAIL_HOST_USER:
            mail.send_mail(
                subject, body,
                from_email or settings.DEFAULT_FROM_EMAIL,
                [to_email],
            )
        else:
            # Entorno sin SMTP (dev): imprimir el enlace para poder probar.
            print(f"[TEM] (dev) Enlace de recuperación para {to_email}:\n{reset_url}")

class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: María González',
                'aria-label': 'Nombre completo',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: maria@universidad.edu.co',
                'aria-label': 'Correo electrónico',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: +57 312 345 6789',
                'aria-label': 'Teléfono o WhatsApp',
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Tesis de Grado en Ingeniería',
                'aria-label': 'Asunto o materia',
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control', 
                'placeholder': 'Indícanos: 1) Fecha límite de entrega, 2) Formato solicitado (Ej: APA 7), 3) Pautas específicas o archivos guía a considerar...',
                'rows': 5,
                'aria-label': 'Especificaciones del trabajo',
            }),
        }

class ChatForm(forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Escribe tu mensaje...', 'rows': 3}),
        }
