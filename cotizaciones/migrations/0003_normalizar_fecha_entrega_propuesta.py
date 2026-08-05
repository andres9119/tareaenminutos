from django.db import migrations


def normalizar_fechas(apps, schema_editor):
    """Quitar la parte de hora de las fechas existentes (antes DateTimeField)."""
    connection = schema_editor.connection
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE cotizaciones_cotizacion "
            "SET fecha_entrega_propuesta = DATE(fecha_entrega_propuesta) "
            "WHERE fecha_entrega_propuesta IS NOT NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('cotizaciones', '0002_alter_cotizacion_fecha_entrega_propuesta'),
    ]

    operations = [
        migrations.RunPython(normalizar_fechas, migrations.RunPython.noop),
    ]
