"""
App: documentos
Gestión segura de archivos adjuntos a solicitudes académicas.
"""

import os
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from solicitudes.models import SolicitudAcademica


def documento_upload_path(instance, filename):
    """Organiza archivos por solicitud: media_privada/solicitudes/<codigo>/<tipo>/<filename>"""
    return f"solicitudes/{instance.solicitud.codigo}/{instance.tipo}/{filename}"


class Documento(models.Model):
    """Archivo adjunto a una solicitud académica."""

    TIPO_DOCUMENTO = [
        ('instruccion', 'Instrucción / Enunciado'),
        ('referencia', 'Material de Referencia'),
        ('entrega', 'Entrega del Tutor'),
        ('revision', 'Revisión / Corrección'),
        ('comprobante', 'Comprobante de Pago'),
        ('otro', 'Otro'),
    ]

    solicitud = models.ForeignKey(
        SolicitudAcademica, on_delete=models.CASCADE,
        related_name='documentos',
        verbose_name='Solicitud'
    )
    subido_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documentos_subidos',
        verbose_name='Subido por'
    )

    tipo = models.CharField(
        max_length=20, choices=TIPO_DOCUMENTO,
        verbose_name='Tipo de Documento'
    )
    archivo = models.FileField(
        upload_to=documento_upload_path,
        storage=settings.PRIVATE_STORAGE,
        verbose_name='Archivo'
    )
    nombre_original = models.CharField(
        max_length=255,
        verbose_name='Nombre Original del Archivo'
    )
    descripcion = models.TextField(
        blank=True,
        verbose_name='Descripción'
    )
    tamaño_bytes = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nombre_original} ({self.get_tipo_display()}) - {self.solicitud.codigo}"

    @property
    def extension(self):
        _, ext = os.path.splitext(self.nombre_original)
        return ext.lower()

    @property
    def tamaño_display(self):
        """Retorna el tamaño legible (KB, MB)."""
        if self.tamaño_bytes < 1024:
            return f"{self.tamaño_bytes} B"
        elif self.tamaño_bytes < 1024 * 1024:
            return f"{self.tamaño_bytes / 1024:.1f} KB"
        else:
            return f"{self.tamaño_bytes / (1024 * 1024):.1f} MB"

    def icono_extension(self):
        """Retorna la clase FontAwesome según el tipo de archivo."""
        iconos = {
            '.pdf': 'fa-file-pdf',
            '.doc': 'fa-file-word', '.docx': 'fa-file-word',
            '.xls': 'fa-file-excel', '.xlsx': 'fa-file-excel',
            '.ppt': 'fa-file-powerpoint', '.pptx': 'fa-file-powerpoint',
            '.jpg': 'fa-file-image', '.jpeg': 'fa-file-image', '.png': 'fa-file-image',
            '.zip': 'fa-file-zipper', '.rar': 'fa-file-zipper',
            '.txt': 'fa-file-lines',
        }
        return iconos.get(self.extension, 'fa-file')
