from django.db import models
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from io import BytesIO
from PIL import Image


class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    excerpt = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published = models.BooleanField(default=True)
    featured_image = models.ImageField(upload_to='blog/', blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Convertir la imagen de portada a WebP (reducción de peso) solo si el
        # archivo subido NO es ya WebP. Evita re-procesar en cada guardado.
        if self.featured_image and getattr(self.featured_image, '_webp_converted', False) is not True:
            if not self.featured_image.name.lower().endswith('.webp'):
                try:
                    image = Image.open(self.featured_image)
                    image = image.convert('RGB')
                    buffer = BytesIO()
                    image.save(buffer, format='WEBP', quality=82, method=4)
                    self.featured_image = ContentFile(buffer.getvalue(), name='%s.webp' % self.slug)
                    setattr(self.featured_image, '_webp_converted', True)
                except Exception:
                    # Si falla (archivo corrupto, formato no soportado), se guarda el original tal cual.
                    pass
        super().save(*args, **kwargs)


class Banner(models.Model):
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to='banners/', blank=True, null=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"Banner {self.id} - {self.title[:30]}"

class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.subject}"

class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.username} - {self.created_at}"
