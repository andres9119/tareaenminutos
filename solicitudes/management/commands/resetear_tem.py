"""
Comando: resetear_tem

Reinicia los datos de negocio de TEM dejando la plataforma lista para empezar
de cero con el número de solicitudes en TEM001.

ELIMINA (en una sola transacción):
  - todas las SolicitudAcademica (y en cascada: HistorialEstado, Cotizacion,
    Documento y las salas de chat por-solicitud con sus mensajes)
  - todas las Notificacion
  - todos los TicketReporte

CONSERVA:
  - usuarios, PerfilUsuario, grupos/roles, contraseñas
  - AreaConocimiento, EstadoSolicitud
  - blog (BlogPost/BlogBlock), Banner, ContactMessage
  - el Canal General de chat y los chats directos con su historial

ADEMÁS reinicia las secuencias auto-incrementales de las tablas de negocio
vaciadas, de modo que el siguiente código de solicitud vuelve a ser TEM001
(no TEM280, TEM999...). Portable SQLite (dev) y PostgreSQL (prod).

Uso:
  python manage.py resetear_tem --si
  python manage.py resetear_tem --si --vaciar-archivos
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection, transaction

TABLAS_BORRADAS = [
    'solicitudes_solicitudacademica',
    'solicitudes_historialestado',
    'cotizaciones_cotizacion',
    'documentos_documento',
    'notificaciones_notificacion',
    'tickets_ticketreporte',
]

MODELOS_BORRAR = [
    'solicitudes.SolicitudAcademica',
    'notificaciones.Notificacion',
    'tickets.TicketReporte',
]


def _resetear_secuencia_sqlite(tabla):
    """SQLite: borra la entrada de sqlite_sequence para que el próximo id sea max(id)+1."""
    with connection.cursor() as cur:
        cur.execute("DELETE FROM sqlite_sequence WHERE name = %s", [tabla])


def _resetear_secuencia_postgres(tabla):
    """PostgreSQL: setval(seq, 1, false) deja el próximo id en 1."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), 1, false) FROM pg_class WHERE relname = %s",
            [tabla, tabla],
        )


def _resetear_secuencias(verbosa):
    vendor = connection.vendor
    vaciadas = []
    for tabla in TABLAS_BORRADAS:
        # Solo reiniciamos la secuencia si la tabla quedó realmente vacía.
        with connection.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{tabla}"')
            quedan = cur.fetchone()[0]
        if quedan != 0:
            if verbosa:
                print(f'  [saltada] {tabla} no quedó vacía ({quedan})')
            continue
        if vendor == 'sqlite':
            _resetear_secuencia_sqlite(tabla)
        elif vendor == 'postgresql':
            _resetear_secuencia_postgres(tabla)
        else:
            print(f'  [aviso] backend {vendor} no soportado para resetear secuencia de {tabla}')
        vaciadas.append(tabla)
    return vaciadas


class Command(BaseCommand):
    help = (
        'Elimina todos los datos de negocio TEM (solicitudes y en cascada, '
        'notificaciones y tickets) conservando usuarios, áreas, estados, blog '
        'y el chat general/directo, y reinicia la numeración de solicitudes '
        'para que la próxima vuelva a ser TEM001.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--si', action='store_true',
            help='Confirmación exigida: sin este flag el comando no ejecuta nada.',
        )
        parser.add_argument(
            '--vaciar-archivos', action='store_true',
            help='Además borra del disco los archivos (Documento y adjuntos de chat) '
                 'cuyos registros se eliminan.',
        )

    def handle(self, *args, **options):
        if not options['si']:
            self.stdout.write(
                self.style.NOTICE(
                    'Operación destructiva cancelada. Ejecuta de nuevo con --si '
                    'para confirmar.'
                )
            )
            return

        contadores = {}
        for ruta in MODELOS_BORRAR:
            contadores[ruta] = apps.get_model(ruta).objects.count()

        with transaction.atomic():
            if options['vaciar_archivos']:
                self._vaciar_archivos()
            for ruta in MODELOS_BORRAR:
                modelo = apps.get_model(ruta)
                modelo.objects.all().delete()

        secuencias = _resetear_secuencias(verbosa=True)

        self.stdout.write(self.style.SUCCESS('\nDatos de negocio ELIMINADOS:'))
        for ruta, n in contadores.items():
            self.stdout.write(f'  {ruta}: {n}')
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSecuencias reiniciadas: {", ".join(secuencias) or "ninguna"}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                'La próxima solicitud volverá a ser TEM001 (el código se genera '
                'a partir del id y este resetea a 1).'
            )
        )

    def _vaciar_archivos(self):
        from chat_interno.models import MensajeChat
        from documentos.models import Documento

        for campo, modelo in [
            ('archivo', Documento),
            ('archivo_adjunto', MensajeChat),
        ]:
            qs = modelo.objects.exclude(**{campo: ''}).exclude(**{campo + '__isnull': True})
            for obj in qs.iterator():
                archivo = getattr(obj, campo)
                try:
                    if archivo and archivo.name:
                        archivo.delete(save=False)
                except Exception as e:  # noqa: BLE001
                    print(f'  [aviso] no se pudo borrar archivo de {modelo.__name__} {obj.pk}: {e}')