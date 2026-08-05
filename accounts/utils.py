def es_admin(user):
    return user.is_superuser or user.groups.filter(name='Administrador').exists()


def es_tutor(user):
    return user.groups.filter(name='Tutor').exists()
