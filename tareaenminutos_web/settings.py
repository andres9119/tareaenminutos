"""
Django settings for tareaenminutos_web project.
Expandido para la plataforma privada TEM con:
- Django Channels + Redis (WebSockets)
- PostgreSQL (producción) / SQLite (desarrollo)
- Auth por grupos (Administrador, Tutor)
- Gestión de medios y archivos privados
"""

from pathlib import Path
import os
from decouple import config
from django.core.files.storage import FileSystemStorage

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-v@phu1fx953*2t^h(rpf(f1@t@m#m+y@kc$4l9=y%e*&x8)jdp')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*', cast=lambda v: [h.strip() for h in v.split(',')])

# ─── SEO: Analytics y Search Console ──────────────────────────────────────────
# ID de Google Analytics 4 (gtag.js). Vacío = no se carga el script.
GOOGLE_ANALYTICS_ID = config('GOOGLE_ANALYTICS_ID', default='')
# Token de verificación de Google Search Console (sin el sufijo "google-site-verification=")
GOOGLE_SITE_VERIFICATION = config('GOOGLE_SITE_VERIFICATION', default='')


# ─── Application definition ──────────────────────────────────────────────────

INSTALLED_APPS = [
    # Apps propias (primero para que los templates se encuentren)
    'main_app',
    'accounts',
    'solicitudes',
    'cotizaciones',
    'documentos',
    'notificaciones',
    'chat_interno',
    'reportes',

    # Django Channels (WebSockets) — daphne MUST be before staticfiles
    'daphne',
    'channels',

    # Django contrib
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Whitenoise: sirve estáticos en producción (compresión + cache headers)
    'whitenoise.runserver_nostatic',
    'whitenoise',

    # Rate limiting / brute-force protection
    'axes',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Whitenoise: debe ir después de SecurityMiddleware y antes del resto
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'tareaenminutos_web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # Directorio global de templates
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Context processor global para notificaciones
                'notificaciones.context_processors.notificaciones_no_leidas',
                # Context processor global para variables de SEO (GA / Search Console)
                'main_app.context_processors.seo_settings',
                # Context processor global para el messenger flotante de chat
                'chat_interno.context_processors.messenger',
            ],
        },
    },
]

# ASGI - necesario para Django Channels
ASGI_APPLICATION = 'tareaenminutos_web.asgi.application'
WSGI_APPLICATION = 'tareaenminutos_web.wsgi.application'


# ─── Database ─────────────────────────────────────────────────────────────────
# SQLite por defecto (desarrollo). Configura DATABASE_URL en .env
# para usar PostgreSQL en producción con el formato:
#   DATABASE_URL=postgres://usuario:password@host:5432/nombre_db
DATABASE_URL = os.getenv('DATABASE_URL', '')

if DATABASE_URL:
    import re
    match = re.match(r'postgres://(.+):(.+)@(.+):(\d+)/(.+)', DATABASE_URL)
    if match:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': match.group(5),
                'USER': match.group(1),
                'PASSWORD': match.group(2),
                'HOST': match.group(3),
                'PORT': match.group(4),
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# ─── Django Channels / Redis ───────────────────────────────────────────────────
# Channel layer con Redis para WebSockets en producción.
# Configura REDIS_URL en .env para usar Redis, o usa InMemoryChannelLayer por defecto.
REDIS_URL = os.getenv('REDIS_URL', '')

if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }


# ─── Password validation ───────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ─── Internationalization ─────────────────────────────────────────────────────

LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True


# ─── Static files ─────────────────────────────────────────────────────────────

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Directorio donde `collectstatic` agrupa los estáticos para producción.
# Whitenoise los sirve desde aquí (no requiere nginx para /static/).
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Compresión y cache headers de estáticos (Whitenoise).
# En producción usamos ManifestStorage: genera nombres con hash inmutable, lo que
# permite servir /static/ con caché de 1 año + `immutable` sin riesgo de contenido
# obsoleto tras un despliegue. En desarrollo se mantiene la versión simple (no
# requiere collectstatic para que runserver sirva los estáticos).
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

if not DEBUG:
    STORAGES['staticfiles']['BACKEND'] = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ─── Media files (imágenes, documentos subidos) ───────────────────────────────

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Directorio para documentos privados de solicitudes (no accesibles directamente)
PRIVATE_MEDIA_ROOT = os.path.join(BASE_DIR, 'media_privada')

# Almacenamiento privado para archivos de solicitudes: fuera de MEDIA_URL,
# por lo que NO se sirven por la URL pública /media/. Solo se descargan a
# través de la vista autorizada `documento_descargar`.
PRIVATE_STORAGE = FileSystemStorage(
    location=PRIVATE_MEDIA_ROOT,
    base_url=None,
)


# ─── Auth Configuration ───────────────────────────────────────────────────────

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard_redirect'
LOGOUT_REDIRECT_URL = 'index'

# Axes: rate limiting (lock after 5 failed attempts in 10 minutes)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.167  # ~10 minutes
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]


# ─── File Upload Limits ───────────────────────────────────────────────────────

DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024   # 20 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024    # 20 MB

# Extensiones permitidas para documentos de solicitudes
ALLOWED_UPLOAD_EXTENSIONS = [
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.jpg', '.jpeg', '.png', '.gif',
    '.zip', '.rar', '.7z',
    '.txt', '.csv',
]


# ─── SEO / site defaults ──────────────────────────────────────────────────────

SITE_META_DESCRIPTION = (
    'Tarea en Minutos - Asesoría académica profesional para estudiantes universitarios '
    'de pregrado y posgrado en Colombia. Tareas, talleres, tesis, exámenes y proyectos.'
)
SITE_META_KEYWORDS = (
    'tareas universitarias colombia, tutores academicos colombia, ayuda con tareas colombia, '
    'trabajos de grado, asesoría tesis, resolver examenes colombia'
)
WHATSAPP_PHONE = '+573217039617'
SITE_BASE_URL = config('SITE_BASE_URL', default='http://localhost:8000')

# ─── HTTPS / Security Settings (for production) ───────────────────────────────

# Detrás de nginx (que termina SSL), Django confía en el header X-Forwarded-Proto
# que nginx ya envía. Sin esto, SECURE_SSL_REDIRECT crea un bucle 301 en HTTPS.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)

# Sesión: expira por inactividad (20 minutos). SESSION_SAVE_EVERY_REQUEST
# renueva el contador en cada petición, por lo que el timeout es de inactividad
# real (no desde el inicio de sesión).
SESSION_COOKIE_AGE = 1200
SESSION_SAVE_EVERY_REQUEST = True

SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)

# ─── Email (SMTP outbound) ─────────────────────────────────────────────────────────

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@tareaenminutos.com')

# ─── Logging ───────────────────────────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'django.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'tareaenminutos': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# ─── Default primary key ──────────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
