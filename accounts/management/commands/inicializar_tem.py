"""
Management command para inicializar los datos base del sistema TEM:
- Grupos: Administrador, Tutor
- Estados de solicitud
- Áreas de conocimiento
- Sala de chat General

Uso: python manage.py inicializar_tem
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = 'Inicializa los datos base del sistema TEM (grupos, estados, áreas).'

    def handle(self, *args, **options):
        self.stdout.write('Inicializando datos base TEM...\n')

        # 1. Crear grupos de roles
        self.stdout.write('  - Creando grupos...')
        admin_group, _ = Group.objects.get_or_create(name='Administrador')
        tutor_group, _ = Group.objects.get_or_create(name='Tutor')
        self.stdout.write(self.style.SUCCESS('    [OK] Grupos: Administrador, Tutor'))

        # 2. Estados de solicitud
        self.stdout.write('  - Creando estados de solicitud...')
        from solicitudes.models import EstadoSolicitud
        estados = [
            ('nueva',          'Nueva',           '#3b82f6', 1),
            ('en_cotizacion',  'Cotización',   '#f59e0b', 2),
            ('cotizada',       'Cotizada',         '#8b5cf6', 3),
            ('asignada',       'Asignada',         '#6366f1', 4),
            ('en_progreso',    'En Progreso',      '#10b981', 5),
            ('en_revision',    'En Revisión',      '#f97316', 6),
            ('completada',     'Completada',       '#22c55e', 7),
            ('cancelada',      'Cancelada',        '#ef4444', 8),
            ('en_disputa',     'En Disputa',       '#dc2626', 9),
            ('en_correccion',  'En Corrección',    '#f97316', 10),
        ]
        for nombre, etiqueta, color, orden in estados:
            obj, created = EstadoSolicitud.objects.get_or_create(
                nombre=nombre,
                defaults={'etiqueta': etiqueta, 'color_hex': color, 'orden': orden}
            )
            if not created:
                obj.etiqueta = etiqueta
                obj.color_hex = color
                obj.orden = orden
                obj.save()
        self.stdout.write(self.style.SUCCESS(f'    [OK] {len(estados)} estados creados/actualizados'))

        # 3. Áreas de conocimiento
        self.stdout.write('  - Creando áreas de conocimiento...')
        from accounts.models import AreaConocimiento
        areas = [
            ('Ingeniería y Tecnología', 'fa-gears'),
            ('Matemáticas y Estadística', 'fa-calculator'),
            ('Física y Química', 'fa-flask'),
            ('Programación y Sistemas', 'fa-code'),
            ('Derecho y Ciencias Jurídicas', 'fa-scale-balanced'),
            ('Administración y Contabilidad', 'fa-briefcase'),
            ('Economía y Finanzas', 'fa-chart-line'),
            ('Medicina y Ciencias de la Salud', 'fa-stethoscope'),
            ('Psicología y Ciencias Sociales', 'fa-brain'),
            ('Educación y Pedagogía', 'fa-graduation-cap'),
            ('Humanidades y Filosofía', 'fa-book'),
            ('Arquitectura y Diseño', 'fa-building'),
            ('Biología y Ciencias Naturales', 'fa-leaf'),
            ('Comunicación y Marketing', 'fa-comments'),
            ('Idiomas y Traducción', 'fa-language'),
            ('Otro / General', 'fa-folder-open'),
        ]
        for nombre, icono in areas:
            AreaConocimiento.objects.get_or_create(nombre=nombre, defaults={'icono': icono})
        self.stdout.write(self.style.SUCCESS(f'    [OK] {len(areas)} áreas creadas'))

        # 4. Sala de chat General
        self.stdout.write('  - Creando sala de chat General...')
        from chat_interno.models import SalaChat
        SalaChat.objects.get_or_create(
            tipo='general',
            defaults={'nombre': 'Canal General TEM'}
        )
        self.stdout.write(self.style.SUCCESS('    [OK] Sala General creada'))

        self.stdout.write('\n' + self.style.SUCCESS(
            'Sistema TEM inicializado correctamente.\n'
            '   Ahora puedes crear usuarios en /admin/ y asignarlos a los grupos Administrador o Tutor.'
        ))
