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

# Nota: PerfilUsuario.ultimo_email_chat quedó en desuso (era la ventana
# anti-spam de correos de chat, retirada a petición: cada mensaje notifica
# una sola vez). Se conserva la columna para no crear migración.


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

    # Cada notificación dispara UN solo correo (incluido mensaje_chat, esté
    # el destinatario en línea o no). Al enviarse en el post_save de la
    # propia fila, el mismo mensaje nunca genera dos correos: no hay
    # ventanas ni resúmenes que lo re-incluyan.
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
