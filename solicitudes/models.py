"""
App: solicitudes
Núcleo del negocio TEM - Gestión completa de solicitudes académicas.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from accounts.models import AreaConocimiento


def generar_codigo_solicitud():
    """Genera código único tipo TEM### basado en el ID auto-incremental.

    Ejemplo: TEM001, TEM002, ...
    Usa select_for_update para evitar race conditions en concurrencia.
    Al basarse en el id (nunca se reusa), no hay riesgo de duplicados
    aunque se borren registros.
    """
    from django.db import transaction
    from .models import SolicitudAcademica
    with transaction.atomic():
        last = SolicitudAcademica.objects.select_for_update().order_by('-id').first()
        if last:
            next_num = last.id + 1
        else:
            next_num = 1
        return f"TEM{next_num:03d}"


class EstadoSolicitud(models.Model):
    """Estados del flujo de una solicitud académica."""
    ESTADOS = [
        ('nueva', 'Nueva'),
        ('en_cotizacion', 'Cotización'),
        ('cotizada', 'Cotizada'),
        ('asignada', 'Asignada'),
        ('en_progreso', 'En Progreso'),
        ('en_revision', 'En Revisión'),
        ('completada', 'Completada'),
        ('cancelada', 'Cancelada'),
        ('en_disputa', 'En Disputa'),
        ('en_correccion', 'En Corrección'),
    ]
    nombre = models.CharField(max_length=30, choices=ESTADOS, unique=True)
    etiqueta = models.CharField(max_length=50)  # Display name
    color_hex = models.CharField(max_length=7, default='#6366f1', help_text='Color HEX ej: #6366f1')
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Estado de Solicitud'
        verbose_name_plural = 'Estados de Solicitud'
        ordering = ['orden']

    def __str__(self):
        return self.etiqueta


class SolicitudAcademica(models.Model):
    """
    Solicitud académica - entidad central del sistema TEM.
    Representa un trabajo académico solicitado por un cliente.
    """

    NIVEL_ACADEMICO = [
        ('pregrado', 'Pregrado'),
        ('especializacion', 'Especialización'),
        ('maestria', 'Maestría'),
        ('doctorado', 'Doctorado'),
        ('tecnico', 'Técnico / Tecnólogo'),
    ]

    TIPO_ENTREGA = [
        ('tarea', 'Tarea'),
        ('taller', 'Taller'),
        ('examen', 'Examen / Parcial'),
        ('proyecto', 'Proyecto'),
        ('ensayo', 'Ensayo'),
        ('tesis', 'Tesis / Trabajo de Grado'),
        ('informe', 'Informe / Reporte'),
        ('presentacion', 'Presentación'),
        ('otro', 'Otro'),
    ]

    # Identificación
    codigo = models.CharField(max_length=30, unique=True, editable=False)

    # Información del cliente (opcionales, el admin decide qué completar)
    cliente_nombre = models.CharField(max_length=150, verbose_name='Nombre del Cliente', blank=True, null=True)
    cliente_email = models.EmailField(verbose_name='Email del Cliente', blank=True, null=True)
    cliente_telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name='Teléfono del Cliente')
    cliente_universidad = models.CharField(max_length=150, blank=True, null=True, verbose_name='Universidad')

    # Detalles académicos
    titulo = models.CharField(max_length=300, verbose_name='Título del Trabajo', blank=True, null=True)
    descripcion = models.TextField(verbose_name='Descripción Detallada', blank=True, null=True)
    area_conocimiento = models.ForeignKey(
        AreaConocimiento, on_delete=models.PROTECT,
        verbose_name='Área de Conocimiento', null=True, blank=True
    )
    nivel_academico = models.CharField(
        max_length=50, verbose_name='Nivel Académico', blank=True, null=True
    )
    tipo_entrega = models.CharField(
        max_length=50, verbose_name='Tipo de Entrega', blank=True, null=True
    )
    materia = models.CharField(max_length=150, blank=True, verbose_name='Materia/Asignatura')

    # Tiempos y precios
    fecha_entrega_cliente = models.DateField(verbose_name='Fecha Límite del Cliente', null=True, blank=True)
    fecha_limite_correccion = models.DateField(
        null=True, blank=True,
        verbose_name='Fecha Límite de Corrección',
        help_text='Se fija automáticamente al devolver la tarea al tutor (reactivación).'
    )
    presupuesto_cliente = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name='Presupuesto del Cliente (COP)'
    )
    precio_final = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name='Precio Final Acordado (COP)'
    )

    # Estado y asignación
    estado = models.ForeignKey(
        EstadoSolicitud, on_delete=models.PROTECT,
        verbose_name='Estado Actual'
    )
    creado_por = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='solicitudes_creadas',
        verbose_name='Creado por'
    )
    tutor_asignado = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='solicitudes_asignadas',
        verbose_name='Tutor Asignado'
    )

    # Calificación
    nota_obtenida = models.DecimalField(
        max_digits=3, decimal_places=1,
        null=True, blank=True,
        verbose_name='Nota obtenida (0.0-5.0)',
        help_text='Calificación que el estudiante obtuvo en el trabajo, escala universitaria 0.0 a 5.0'
    )
    calificacion_tutor = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name='Puntuación del tutor (0-100)',
        help_text='Se calcula automáticamente a partir de la nota obtenida (nota × 20)'
    )
    fecha_calificacion = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Fecha de calificación'
    )

    # Notas
    notas_internas = models.TextField(
        blank=True,
        verbose_name='Notas Internas (solo Admin)'
    )

    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Solicitud Académica'
        verbose_name_plural = 'Solicitudes Académicas'
        ordering = ['-created_at']
        permissions = [
            ('asignar_tutor', 'Puede asignar tutor a solicitud'),
            ('ver_notas_internas', 'Puede ver notas internas'),
            ('cambiar_estado', 'Puede cambiar estado de solicitud'),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.titulo[:50]}"

    def save(self, *args, **kwargs):
        if not self.codigo or self.codigo.strip() == '':
            self.codigo = generar_codigo_solicitud()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('solicitud_detalle', kwargs={'pk': self.pk})

    @property
    def dias_para_entrega(self):
        from django.utils import timezone
        if not self.fecha_entrega_cliente:
            return None
        delta = self.fecha_entrega_cliente - timezone.localdate()
        return delta.days

    @property
    def es_urgente(self):
        if self.dias_para_entrega is None:
            return False
        return self.dias_para_entrega <= 1

    @property
    def dias_para_correccion(self):
        """Días restantes para la fecha límite de corrección (None si no hay)."""
        from django.utils import timezone
        if not self.fecha_limite_correccion:
            return None
        delta = self.fecha_limite_correccion - timezone.localdate()
        return delta.days

    @property
    def correccion_vencida(self):
        if self.dias_para_correccion is None:
            return False
        return self.dias_para_correccion < 0

    # ─── Límite de carga de trabajo por tutor ───
    # Un tutor puede tener máximo 3 solicitudes activas simultáneas y necesita
    # tener máximo 2 para poder cotizar una nueva.
    MAX_SOLICITUDES_ACTIVAS_TUTOR = 3
    ESTADOS_CERRADOS_TUTOR = ['completada', 'cancelada']

    # Días automáticos que tiene el tutor para corregir cuando el admin
    # devuelve la tarea (reactivación → en_correccion).
    DIAS_LIMITE_CORRECCION = 3

    @classmethod
    def orden_prioridad_tutor(cls):
        """Expresión de anotación para ordenar listas del tutor:
        primero las correcciones (en_correccion), después las asignadas
        activas (asignada/en_progreso/en_revision), después las demás."""
        from django.db.models import Case, Value, When, IntegerField
        return Case(
            When(estado__nombre='en_correccion', then=Value(0)),
            When(estado__nombre__in=['asignada', 'en_progreso', 'en_revision'], then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )


    @classmethod
    def activas_de_tutor(cls, tutor):
        """Solicitudes asignadas al tutor que aún no finalizan.

        Cuenta como activas todas las asignadas cuyo estado no sea
        completada ni cancelada (incluye en_progreso, en_revision,
        en_correccion, en_disputa, etc.).
        """
        return cls.objects.filter(tutor_asignado=tutor).exclude(
            estado__nombre__in=cls.ESTADOS_CERRADOS_TUTOR
        )


class HistorialEstado(models.Model):
    """
    Audit trail de cambios de estado en solicitudes.
    Permite trazabilidad completa del flujo de trabajo.
    """
    solicitud = models.ForeignKey(
        SolicitudAcademica, on_delete=models.CASCADE,
        related_name='historial_estados'
    )
    estado_anterior = models.ForeignKey(
        EstadoSolicitud, on_delete=models.PROTECT,
        related_name='transiciones_desde', null=True, blank=True
    )
    estado_nuevo = models.ForeignKey(
        EstadoSolicitud, on_delete=models.PROTECT,
        related_name='transiciones_hacia'
    )
    cambiado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    comentario = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Historial de Estado'
        verbose_name_plural = 'Historial de Estados'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.solicitud.codigo}: {self.estado_anterior} → {self.estado_nuevo}"
