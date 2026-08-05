from django.db import migrations


def normalizar_fechas(apps, schema_editor):
    """Quitar la parte de hora de las fechas existentes (antes DateTimeField)."""
    connection = schema_editor.connection
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE solicitudes_solicitudacademica "
            "SET fecha_entrega_cliente = DATE(fecha_entrega_cliente) "
            "WHERE fecha_entrega_cliente IS NOT NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0005_alter_solicitudacademica_fecha_entrega_cliente'),
    ]

    operations = [
        migrations.RunPython(normalizar_fechas, migrations.RunPython.noop),
    ]
