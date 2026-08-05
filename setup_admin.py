"""
Script para configurar el usuario administrador y los grupos necesarios.
NOTA: la inicialización canónica de datos es el comando `inicializar_tem`
(`python manage.py inicializar_tem`). Este script se mantiene por compatibilidad.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tareaenminutos_web.settings')
django.setup()

from django.contrib.auth.models import User, Group
from accounts.models import AreaConocimiento, PerfilUsuario
from solicitudes.models import EstadoSolicitud

def setup():
    print("Configurando el sistema TEM...")

    # Crear grupos
    admin_group, created = Group.objects.get_or_create(name='Administrador')
    if created:
        print("Grupo 'Administrador' creado")
    else:
        print("Grupo 'Administrador' ya existe")

    tutor_group, created = Group.objects.get_or_create(name='Tutor')
    if created:
        print("Grupo 'Tutor' creado")
    else:
        print("Grupo 'Tutor' ya existe")

    # Crear estados de solicitud
    estados_data = [
        ('nueva', 'Nueva', '#3b82f6', 1),
        ('en_cotizacion', 'En Cotización', '#f59e0b', 2),
        ('cotizada', 'Cotizada', '#8b5cf6', 3),
        ('asignada', 'Asignada', '#8b5cf6', 4),
        ('en_progreso', 'En Progreso', '#10b981', 5),
        ('en_revision', 'En Revisión', '#f59e0b', 6),
        ('completada', 'Completada', '#059669', 7),
        ('cancelada', 'Cancelada', '#ef4444', 8),
        ('en_disputa', 'En Disputa', '#dc2626', 9),
        ('en_correccion', 'En Corrección', '#f97316', 10),
    ]

    for nombre, etiqueta, color, orden in estados_data:
        estado, created = EstadoSolicitud.objects.get_or_create(
            nombre=nombre,
            defaults={'etiqueta': etiqueta, 'color_hex': color, 'orden': orden}
        )
        if created:
            print(f"Estado '{etiqueta}' creado")
        else:
            print(f"Estado '{etiqueta}' ya existe")

    # Crear áreas de conocimiento
    areas_data = [
        'Ingeniería',
        'Derecho',
        'Medicina',
        'Administración',
        'Economía',
        'Arquitectura',
        'Psicología',
        'Educación',
        'Comunicación',
        'Contabilidad',
    ]

    for area_nombre in areas_data:
        area, created = AreaConocimiento.objects.get_or_create(
            nombre=area_nombre,
            defaults={'icono': 'fa-book-open'}
        )
        if created:
            print(f"Área '{area_nombre}' creada")
        else:
            print(f"Área '{area_nombre}' ya existe")

    # Verificar usuarios
    print("\nUsuarios del sistema:")
    for user in User.objects.all():
        grupos = [g.name for g in user.groups.all()]
        es_super = " (Superuser)" if user.is_superuser else ""
        print(f"  - {user.username} | Grupos: {grupos if grupos else 'Ninguno'}{es_super}")

    print("\nConfiguración completada!")
    print("\nPara asignar un usuario como administrador, ejecuta:")
    print("   python manage.py shell")
    print("   from django.contrib.auth.models import User, Group")
    print("   user = User.objects.get(username='tu_usuario')")
    print("   admin_group = Group.objects.get(name='Administrador')")
    print("   user.groups.add(admin_group)")
    print("   user.is_staff = True")
    print("   user.save()")

if __name__ == '__main__':
    setup()
