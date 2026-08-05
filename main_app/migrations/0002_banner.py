"""
Migration to add Banner model.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Banner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=200)),
                ('subtitle', models.CharField(blank=True, max_length=300)),
                ('image', models.ImageField(blank=True, null=True, upload_to='banners/')),
                ('active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['-id'],
            },
        ),
    ]
