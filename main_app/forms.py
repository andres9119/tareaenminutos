from django import forms
from .models import ContactMessage, ChatMessage

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
