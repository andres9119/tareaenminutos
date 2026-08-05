"""
Signals para solicitudes.
Crea la SalaChat, registra historial de estados y dispara notificaciones.
"""

import logging
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.db import transaction

logger = logging.getLogger('tareaenminutos')


@receiver(pre_save, sender='solicitudes.SolicitudAcademica')
def capturar_estado_anterior(sender, instance, **kwargs):
    """Guarda el estado y tutor anteriores ANTES del guardado.

    Necesario porque post_save corre después de escribir en la BD, así que
    consultar ahí el "estado anterior" devuelve el nuevo (impidiendo detectar
    los cambios de estado).
    """
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        instance._estado_anterior_id = old.estado_id
        instance._tutor_anterior_id = old.tutor_asignado_id
        instance._calificacion_anterior = old.calificacion_tutor
    except sender.DoesNotExist:
        pass


@receiver(post_save, sender='solicitudes.SolicitudAcademica')
def crear_sala_chat_solicitud(sender, instance, created, **kwargs):
    """Crea automáticamente una SalaChat cuando se crea una solicitud."""
    from chat_interno.models import SalaChat
    sala, _ = SalaChat.objects.get_or_create(
        solicitud=instance,
        defaults={
            'nombre': f"Chat - {instance.codigo}",
            'tipo': 'solicitud',
        }
    )
    # Agregar el creador como participante
    sala.participantes.add(instance.creado_por)
    # Agregar al tutor asignado si existe
    if instance.tutor_asignado:
        sala.participantes.add(instance.tutor_asignado)


@receiver(post_save, sender='solicitudes.SolicitudAcademica')
def notificar_nueva_solicitud(sender, instance, created, **kwargs):
    """Notifica a todos los tutores disponibles cuando se crea una solicitud."""
    if created:
        from notificaciones.utils import crear_notificacion
        from django.contrib.auth.models import Group

        # Obtener todos los tutores activos
        tutores_group = Group.objects.filter(name='Tutor').first()
        if not tutores_group:
            return

        tutores = tutores_group.user_set.filter(is_active=True)
        url = reverse('solicitud_detalle', args=[instance.pk])
        area = instance.area_conocimiento.nombre if instance.area_conocimiento else 'General'

        for tutor in tutores:
            crear_notificacion(
                destinatario=tutor,
                tipo='nueva_solicitud',
                titulo=f'Nueva solicitud disponible: {instance.codigo}',
                mensaje=f'Se ha creado una nueva solicitud "{instance.titulo}" en el área de {area}. ¡Envía tu cotización!',
                url_accion=url,
                solicitud_id=instance.pk,
            )


@receiver(post_save, sender='solicitudes.SolicitudAcademica')
def notificar_cambio_estado(sender, instance, **kwargs):
    """Notifica cambios de estado a los admins y al tutor asignado.

    Si la vista que guardó la solicitud fija `instance._notif_actor` con el
    usuario que hizo el cambio, ese usuario NO recibe una auto-notificación.
    """
    if kwargs.get('created'):
        return

    def _notificar():
        from notificaciones.utils import crear_notificacion
        from django.contrib.auth.models import User
        actor = getattr(instance, '_notif_actor', None)
        old_estado_id = getattr(instance, '_estado_anterior_id', instance.estado_id)
        if old_estado_id == instance.estado_id:
            return

        titulo_estado = instance.estado.etiqueta
        url = reverse('solicitud_detalle', args=[instance.pk])
        titulo = f'{instance.codigo}: {titulo_estado}'
        mensaje = f'La solicitud "{instance.titulo}" cambió a estado "{titulo_estado}".'

        # Notificar a todos los admins (excepto quien realizó el cambio)
        admins = User.objects.filter(groups__name='Administrador') | User.objects.filter(is_superuser=True)
        for admin in admins:
            if actor and admin.pk == actor.pk:
                continue
            crear_notificacion(
                destinatario=admin,
                tipo='cambio_estado',
                titulo=titulo,
                mensaje=mensaje,
                url_accion=url,
                solicitud_id=instance.pk,
            )

        # Notificar al tutor asignado (excepto si él mismo hizo el cambio)
        if instance.tutor_asignado and not (actor and actor.pk == instance.tutor_asignado.pk):
            crear_notificacion(
                destinatario=instance.tutor_asignado,
                tipo='cambio_estado',
                titulo=titulo,
                mensaje=mensaje,
                url_accion=url,
                solicitud_id=instance.pk,
            )

    transaction.on_commit(_notificar)


@receiver(post_save, sender='solicitudes.SolicitudAcademica')
def actualizar_calificacion_tutor(sender, instance, **kwargs):
    """Recalcula el promedio del tutor cuando se asigna o cambia una calificación."""
    if not instance.tutor_asignado or not instance.calificacion_tutor:
        return

    # Usar el valor capturado en pre_save para detectar si cambió (releer la BD
    # dentro de on_commit devolvería el valor nuevo e impediría detectar el cambio).
    if getattr(instance, '_calificacion_anterior', None) == instance.calificacion_tutor:
        return

    def _recalcular():
        from accounts.models import PerfilUsuario
        from decimal import Decimal
        perfil, _ = PerfilUsuario.objects.get_or_create(user=instance.tutor_asignado)
        todas = sender.objects.filter(
            tutor_asignado=instance.tutor_asignado,
            calificacion_tutor__isnull=False,
        )
        total = sum(t.calificacion_tutor for t in todas)
        count = todas.count()
        if count:
            perfil.calificacion_promedio = (Decimal(total) / count).quantize(Decimal('0.01'))
        else:
            perfil.calificacion_promedio = 0
        perfil.save(update_fields=['calificacion_promedio'])

    transaction.on_commit(_recalcular)


@receiver(post_save, sender='solicitudes.SolicitudAcademica')
def incrementar_trabajos_completados(sender, instance, **kwargs):
    """Incrementa trabajos_completados cuando una solicitud se marca como completada."""
    if kwargs.get('created') or not instance.tutor_asignado:
        return

    estado_anterior_id = getattr(instance, '_estado_anterior_id', None)
    if estado_anterior_id:
        from .models import EstadoSolicitud
        estado_anterior_nombre = EstadoSolicitud.objects.filter(
            pk=estado_anterior_id
        ).values_list('nombre', flat=True).first()
    else:
        estado_anterior_nombre = None

    # Solo incrementa cuando la transición es hacia "completada"
    if estado_anterior_nombre == 'completada' or instance.estado.nombre != 'completada':
        return

    def _incrementar():
        from accounts.models import PerfilUsuario
        perfil, _ = PerfilUsuario.objects.get_or_create(user=instance.tutor_asignado)
        completadas = sender.objects.filter(
            tutor_asignado=instance.tutor_asignado,
            estado__nombre='completada',
        ).count()
        perfil.trabajos_completados = completadas
        perfil.save(update_fields=['trabajos_completados'])

    transaction.on_commit(_incrementar)


@receiver(post_save, sender='solicitudes.SolicitudAcademica')
def notificar_asignacion_tutor(sender, instance, **kwargs):
    """Notifica al tutor cuando se le asigna una solicitud."""
    if kwargs.get('created') or not instance.tutor_asignado:
        return

    def _notificar():
        from notificaciones.utils import crear_notificacion
        actor = getattr(instance, '_notif_actor', None)
        old_tutor_id = getattr(instance, '_tutor_anterior_id', instance.tutor_asignado_id)
        if old_tutor_id == instance.tutor_asignado_id:
            return
        if actor and actor.pk == instance.tutor_asignado_id:
            return

        url = reverse('solicitud_detalle', args=[instance.pk])
        crear_notificacion(
            destinatario=instance.tutor_asignado,
            tipo='solicitud_asignada',
            titulo=f'Solicitud asignada: {instance.codigo}',
            mensaje=f'Se te ha asignado la solicitud "{instance.titulo}".',
            url_accion=url,
            solicitud_id=instance.pk,
        )

    transaction.on_commit(_notificar)


@receiver(post_delete, sender='solicitudes.SolicitudAcademica')
def limpiar_recursos_al_borrar_solicitud(sender, instance, **kwargs):
    """Elimina notificaciones y la sala de chat al borrar una solicitud.

    Evita que queden notificaciones apuntando a una solicitud inexistente
    (que antes provocaban 404 al hacer clic).
    """
    from notificaciones.models import Notificacion
    from chat_interno.models import SalaChat
    Notificacion.objects.filter(solicitud_id=instance.pk).delete()
    SalaChat.objects.filter(solicitud=instance).delete()
