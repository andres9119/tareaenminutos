# Generated manually: make documento.archivo storage portable again.
# 0004 hardcoded the local Windows path; this re-aligns the state with
# settings.PRIVATE_MEDIA_ROOT (same portable pattern as 0002).
import django.core.files.storage
import documentos.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documentos', '0004_archivo_max_length_500'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documento',
            name='archivo',
            field=models.FileField(
                max_length=500,
                storage=django.core.files.storage.FileSystemStorage(
                    base_url=None,
                    location=settings.PRIVATE_MEDIA_ROOT,
                ),
                upload_to=documentos.models.documento_upload_path,
                verbose_name='Archivo',
            ),
        ),
    ]