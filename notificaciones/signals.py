import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger('tareaenminutos')

TIPO_A_ENVIAR = {
    'nueva_solicitud',
    'cotizacion_recibida',
    'cotizacion_aceptada',
    'cotizacion_rechazada',
    'solicitud_asignada',
    'cambio_estado',
    'entrega_recibida',
    'comprobante_pago',
    'mensaje_chat',
    'ticket_reportado',
    'ticket_resuelto',
}

# Anti-spam de emails de chat: el primer mensaje de la ventana avisa de
# inmediato; los siguientes se acumulan y salen en UN solo correo resumen
# con el conteo (ver flush_resumenes_chat). Solo aplica a 'mensaje_chat'.
CHAT_EMAIL_VENTANA_SEG = 10 * 60


@receiver(post_save, sender='notificaciones.Notificacion')
def enviar_email_notificacion(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.tipo not in TIPO_A_ENVIAR:
        return
    if not settings.EMAIL_HOST_USER:
        return

    usuario = instance.destinatario
    if not usuario.email:
        logger.info(f"Sin email para {usuario.username}, saltando notif {instance.pk}")
        return

    # Chat: un solo correo por ventana (inmediato el primero, resumen el resto)
    if instance.tipo == 'mensaje_chat':
        _email_chat_agrupado(instance, usuario)
        return

    url = instance.url_accion or settings.LOGIN_URL
    if url.startswith('/'):
        url = f"{settings.SITE_BASE_URL or 'https://tareaenminutos.com'}{url}"

    try:
        send_mail(
            subject=f"TEM - {instance.titulo}",
            message=f"{instance.mensaje}\n\nIr a: {url}\n\n---\nTarea en Minutos",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[usuario.email],
            fail_silently=False,
        )
        logger.info(f"Email enviado a {usuario.email} — {instance.titulo}")
    except Exception as e:
        logger.warning(f"Error enviando email a {usuario.email}: {e}")


def _marcar_ventana_chat(usuario):
    """Estampa ultimo_email_chat=ahora (anti-spam). Crea perfil si falta."""
    from django.utils import timezone
    from accounts.models import PerfilUsuario
    perfil, _ = PerfilUsuario.objects.get_or_create(user=usuario)
    perfil.ultimo_email_chat = timezone.now()
    perfil.save(update_fields=['ultimo_email_chat'])


def _email_chat_agrupado(instance, usuario):
    """Email de chat con ventana anti-spam por destinatario.

    - Sin ventana activa (o vencida): envía este mensaje de inmediato y abre
      la ventana (estampa ultimo_email_chat).
    - Dentro de la ventana: no envía nada; el mensaje queda acumulado como
      notificación sin leer y saldrá en el resumen de flush_resumenes_chat.
    """
    from datetime import timedelta
    from django.utils import timezone
    from accounts.models import PerfilUsuario

    perfil, _ = PerfilUsuario.objects.get_or_create(user=usuario)
    ahora = timezone.now()
    ultimo = perfil.ultimo_email_chat
    if ultimo and (ahora - ultimo) < timedelta(seconds=CHAT_EMAIL_VENTANA_SEG):
        logger.info(f"Email chat suprimido (ventana) para {usuario.email} — notif {instance.pk}")
        return

    url = instance.url_accion or settings.LOGIN_URL
    if url.startswith('/'):
        url = f"{settings.SITE_BASE_URL or 'https://tareaenminutos.com'}{url}"
    try:
        send_mail(
            subject=f"TEM - {instance.titulo}",
            message=f"{instance.mensaje}\n\nIr a: {url}\n\n---\nTarea en Minutos",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[usuario.email],
            fail_silently=False,
        )
        logger.info(f"Email chat enviado a {usuario.email} — {instance.titulo}")
    except Exception as e:
        logger.warning(f"Error enviando email a {usuario.email}: {e}")
    _marcar_ventana_chat(usuario)


def flush_resumenes_chat():
    """Envía UN correo resumen por usuario con mensajes de chat acumulados.

    Para cada destinatario con notificaciones 'mensaje_chat' sin leer cuya
    ventana anti-spam ya venció: envía "Recibiste N mensajes de chat sin
    leer" (con el último como adelanto) y reabre la ventana. Se llama desde
    el polling de chats (datos_messenger), así lo dispara el tráfico normal
    del sistema aunque el destinatario esté desconectado.
    """
    from datetime import timedelta
    from django.utils import timezone

    from notificaciones.models import Notificacion
    from accounts.models import PerfilUsuario

    ahora = timezone.now()
    limite = ahora - timedelta(seconds=CHAT_EMAIL_VENTANA_SEG)
    pendientes = (
        Notificacion.objects.filter(tipo='mensaje_chat', leida=False)
        .exclude(destinatario__email='')
        .values_list('destinatario_id', flat=True)
        .distinct()
    )
    if not pendientes:
        return
    if not settings.EMAIL_HOST_USER:
        return

    for uid in list(pendientes):
        try:
            perfil = PerfilUsuario.objects.select_related('user').get(user_id=uid)
        except PerfilUsuario.DoesNotExist:
            continue
        if perfil.ultimo_email_chat and perfil.ultimo_email_chat > limite:
            continue  # ventana activa: el inmediato ya avisó
        sin_leer = Notificacion.objects.filter(
            destinatario_id=uid, tipo='mensaje_chat', leida=False
        ).order_by('-created_at')
        total = sin_leer.count()
        if not total:
            continue
        ultima = sin_leer.first()
        usuario = perfil.user
        if not usuario.email:
            continue
        url = ultima.url_accion or '/app/chat/'
        if url.startswith('/'):
            url = f"{settings.SITE_BASE_URL or 'https://tareaenminutos.com'}{url}"
        plural = 's' if total != 1 else ''
        try:
            send_mail(
                subject=f"TEM - Tienes {total} mensaje{plural} de chat sin leer",
                message=(
                    f"Recibiste {total} mensaje{plural} de chat sin leer. "
                    f"Último: \"{ultima.mensaje}\"\n\n"
                    f"Entra al chat para leerlos: {url}\n\n---\nTarea en Minutos"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[usuario.email],
                fail_silently=False,
            )
            logger.info(f"Email resumen chat a {usuario.email} ({total} mensajes)")
        except Exception as e:
            logger.warning(f"Error enviando resumen chat a {usuario.email}: {e}")
        _marcar_ventana_chat(usuario)
