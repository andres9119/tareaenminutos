import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger('tareaenminutos')


def crear_notificacion(destinatario, tipo, titulo, mensaje, url_accion='', solicitud_id=None):
    from notificaciones.models import Notificacion
    notif = Notificacion.objects.create(
        destinatario=destinatario,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        url_accion=url_accion,
        solicitud_id=solicitud_id,
    )
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{destinatario.id}_notif",
            {
                'type': 'notificacion_nueva',
                'notif': {
                    'id': notif.pk,
                    'tipo': notif.tipo,
                    'titulo': notif.titulo,
                    'mensaje': notif.mensaje,
                    'url': notif.url_accion,
                }
            }
        )
    except Exception as e:
        logger.warning(f"Error enviando notif WebSocket a {destinatario.id}: {e}")
    return notif
