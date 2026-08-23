def es_admin(user):
    return user.is_superuser or user.groups.filter(name='Administrador').exists()


def es_tutor(user):
    return user.groups.filter(name='Tutor').exists()


def qs_base_sin_pagina(request, *claves):
    """Querystring GET actual sin las claves de paginacion indicadas.
    Se usa para que los enlaces de paginacion conserven los filtros."""
    params = request.GET.copy()
    for clave in ('page',) + tuple(claves):
        params.pop(clave, None)
    return (params.urlencode() + '&') if params else ''
