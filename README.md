# Tarea en Minutos (TEM)

Plataforma Django para asesoría académica en Colombia. Tiene dos caras:

1. **Sitio público**: landing, blog, contacto y login (SEO optimizado).
2. **Plataforma privada** para roles **Administrador** y **Tutor**: gestión de solicitudes académicas, cotizaciones, documentos, chat en tiempo real, notificaciones (incluido email) y reportes.

> Stack: Django 5.2 + Django Channels (WebSockets) + Axes (anti fuerza bruta). SQLite en dev / PostgreSQL en prod; Redis para el channel layer de WebSockets; Daphne como servidor ASGI.

---

## Requisitos

- Python 3.11+
- Django 5.2+
- (Opcional en prod) PostgreSQL, Redis

## Instalación (desarrollo)

```bash
cd tareaenminutos_web
python -m venv venv
# Windows: venv\Scripts\activate   |  Linux/mac: source venv/bin/activate
pip install -r requirements.txt

# Copia la plantilla de entorno y ajústala si hace falta
copy .env  # (si ya existe) — los defaults de settings ya sirven para dev

python manage.py migrate
python manage.py inicializar_tem   # grupos, estados, áreas y sala general
python manage.py createsuperuser
python manage.py runserver
```

Accesos:
- Sitio público: `http://localhost:8000/`
- Admin de Django: `http://localhost:8000/admin/`
- Plataforma: inicia sesión → dashboard según tu rol (`/app/`)

> Para WebSockets (chat/notificaciones) el `runserver` de Django no basta. Usa:
> `daphne -b 127.0.0.1 -p 8000 tareaenminutos_web.asgi:application`

## Configuración de entorno (`.env`)

Variables leídas en `tareaenminutos_web/settings.py` via `python-decouple`. Los defaults están pensados para desarrollo. Copia `deploy/.env.prod` como `.env` en producción.

| Variable | Uso |
| --- | --- |
| `SECRET_KEY` | Clave secreta (¡cambiar en prod!) |
| `DEBUG` | `True` en dev, `False` en prod |
| `ALLOWED_HOSTS` | Coma separada (nunca `*` en prod) |
| `DATABASE_URL` | Vacío = SQLite; `postgres://user:pass@host:5432/db` para PostgreSQL |
| `REDIS_URL` | Vacío = `InMemoryChannelLayer`; `redis://host:6379/0` para Redis |
| `SITE_BASE_URL` | URL canónica (canonical/OG y emails) |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_*` | HTTPS en producción |
| `GOOGLE_ANALYTICS_ID` | ID de GA4; vacío = no se carga |
| `GOOGLE_SITE_VERIFICATION` | Token de Search Console; vacío = no se emite |
| `EMAIL_BACKEND/HOST/PORT/USE_TLS/HOST_USER/HOST_PASSWORD/DEFAULT_FROM_EMAIL` | SMTP. Sin `EMAIL_HOST_USER` **no salen los emails** de notificación |

---

## Estructura

```
tareaenminutos_web/
├── manage.py
├── requirements.txt
├── setup_admin.py              # script manual (duplica inicialización de datos)
├── media/                      # archivos subidos (¡se sirven en /media/!)
├── media_privada/              # documentos privados de solicitudes (no públicos)
├── static/                     # CSS/JS/imágenes globales
├── templates/                  # global: main_app/ + private/ (vistas internas)
├── deploy/                     # nginx.conf, systemd, .env.prod, DEPLOY.md
├── accounts/                   # usuarios, perfiles, áreas, dashboards
├── main_app/                   # landing pública, blog, contacto, login, sitemap
├── solicitudes/                # núcleo del negocio
├── cotizaciones/               # propuestas económicas de tutores
├── documentos/                 # archivos adjuntos a solicitudes
├── notificaciones/             # notificaciones internas + WebSocket + email
├── chat_interno/               # chat en tiempo real por sala
├── reportes/                   # métricas, dashboard y exportación CSV
└── tareaenminutos_web/         # settings, urls, asgi, wsgi
```

## Apps

### `accounts`
- `PerfilUsuario` (OneToOne a `User`) con propiedades `es_admin`/`es_tutor`; `AreaConocimiento`.
- Decoradores `admin_required`, `tutor_required`, `admin_o_tutor_required`.
- **Rol único**: un usuario es Admin **o** Tutor, nunca ambos (`UsuarioCrearForm.save()` limpia grupos de rol).
- Comando `inicializar_tem` (grupos, estados, áreas, sala general).

### `solicitudes` (núcleo)
- `SolicitudAcademica` (código `TEM###`, estado, asignación, calificación), `EstadoSolicitud` (catálogo), `HistorialEstado` (audit).
- Flujo: admin crea → tutor cotiza → admin acepta → tutor trabaja → entrega (`en_revision`) → admin completa y califica.
- Signals: crea `SalaChat`, notifica (y envía email) a tutores/administrador, recalcula calificación/trabajos.

### `cotizaciones`
- `Cotizacion` (un tutor cotiza una vez por solicitud). `aceptar()` es transaccional: rechaza las demás, asigna tutor, fija `precio_final`.

### `documentos`
- `Documento` con tipos (instrucción/referencia/entrega/revisión/comprobante/otro). Los archivos van a `media_privada/` (storage privado, sin URL pública); se descargan solo por vista autorizada. Máx 20 MB, extensiones permitidas.

### `notificaciones`
- `Notificacion` + push WebSocket (grupo `user_<id>_notif`). `crear_notificacion()` persiste y emite.
- Email automático (vía signal) para: `nueva_solicitud`, `cotizacion_aceptada`, `cotizacion_rechazada`, `solicitud_asignada`, `cambio_estado` — **solo si `EMAIL_HOST_USER` está configurado**.

### `chat_interno`
- `SalaChat` por solicitud o general; `MensajeChat` (texto/archivo/sistema). Consumer con reconexión, historial e indicador de escritura. Acceso solo a admins o participantes (o solicitudes abiertas para cotizar).

### `reportes`
- KPIs del mes, desglose por estado, top tutores, tendencia y exportación CSV.

### `main_app` (público)
- `BlogPost`, `Banner`, `ContactMessage`. Páginas con canonical/OG/JSON-LD dinámicos; `robots.txt` bloquea la plataforma privada; `sitemap.xml`.

---

## URLs principales

| Ruta | Descripción |
| --- | --- |
| `/` `/login/` `/logout/` | Landing, login (redirige por rol), logout |
| `/admin/` | Admin de Django |
| `/app/` `/app/perfil/` `/app/usuarios/...` | Dashboard por rol, perfil, usuarios |
| `/solicitudes/` | Lista/crear/detalle/editar/disponibles/estado/entregar/calificar/reasignar |
| `/cotizaciones/` | Lista, mis-cotizaciones, aceptar, crear |
| `/documentos/` | Subir, descargar, eliminar |
| `/notificaciones/` | Lista de notificaciones |
| `/app/chat/` | Mis chats, sala general, sala por solicitud |
| `/reportes/` | KPIs + exportación CSV |
| `/app/mensajes-contacto/` | Mensajes de contacto (solo admin) |

**WebSockets:** `ws/chat/<sala_id>/` · `ws/notificaciones/`

---

## Despliegue (producción)

Manual, con **nginx + Daphne + PostgreSQL + Redis**. Sin Docker.

1. Sigue la guía paso a paso: `deploy/DEPLOY.md`.
2. Configuración de nginx y systemd: `deploy/nginx.conf` y `deploy/tareaenminutos.service`.
3. Entorno de producción: copia `deploy/.env.prod` a `.env`.

Resumen del flujo en prod:
- **nginx** sirve `/media/` y hace proxy al resto + WebSockets `/ws/` → Daphne (`127.0.0.1:8000`).
- **Daphne** (ASGI, systemd) sirve la app y los estáticos vía **Whitenoise**.
- **PostgreSQL** para datos, **Redis** para el channel layer, **SMTP** para emails.
- HTTPS con Let's Encrypt (certbot).

---

## Notas de desarrollo

- **Estados del negocio**: se crean/actualizan con `get_or_create` + `defaults` (`inicializar_tem`, `solicitud_crear`, `Cotizacion.aceptar`).
- **Notificaciones**: usar siempre `notificaciones.utils.crear_notificacion()` (persiste + WebSocket). Los emails salen solos por signal si SMTP está configurado.
- **Estilo**: sin emojis → iconos FontAwesome. Variables de color en `static/base_styles.css` y `static/private_styles.css`.
- **Fechas**: `America/Bogota`, `es-co`; las fechas "solo día" son `DateField` con `type="date"`.

---

## Licencia

Proyecto propiedad de Tarea en Minutos. Todos los derechos reservados.
