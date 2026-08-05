# Despliegue manual — Tarea en Minutos (nginx + Daphne + PostgreSQL + Redis)

Sin Docker. Todo instalado y configurado a mano en un VPS con Ubuntu (asume Debian/Ubuntu y systemd).

Reemplaza `tareaenminutos.com` por tu dominio y ajusta rutas/usuario según tu servidor.

---

## 1. Crear usuario y estructura de carpetas

```bash
sudo useradd -m -s /bin/bash tem  # o reutiliza un usuario no-root
sudo mkdir -p /var/www/tareaenminutos
sudo chown -R $USER:www-data /var/www/tareaenminutos
```

## 2. Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nginx postgresql postgresql-contrib redis-server git certbot python3-certbot-nginx
```

## 3. Configurar PostgreSQL

```bash
sudo -u postgres createuser -P tem_user      # pon una contraseña
sudo -u postgres createdb -O tem_user tem_db
```

## 4. Configurar Redis

```bash
sudo systemctl enable --now redis-server
redis-cli ping   # debe responder PONG
```

## 4.5. Optimización para el plan S+ (2 GB RAM) — recomendado

Con 2 GB de RAM hay que afinar Postgres, Redis y activar swap para que nada se quede sin memoria (evita que el sistema mate procesos por OOM). Ejecútalo justo después de instalar Postgres y Redis.

### Swap (1-2 GB) — imprescindible en 2 GB

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf
sudo sysctl --system
```

### PostgreSQL — límites acordes a 2 GB

```bash
VER=$(ls /etc/postgresql | head -n1)
CONF=/etc/postgresql/$VER/main/postgresql.conf
sudo cp "$CONF" "$CONF.bak"
sudo sed -i "s/^#shared_buffers = .*/shared_buffers = 128MB/" "$CONF"
sudo sed -i "s/^#max_connections = .*/max_connections = 40/" "$CONF"
sudo sed -i "s/^#work_mem = .*/work_mem = 4MB/" "$CONF"
sudo sed -i "s/^#effective_cache_size = .*/effective_cache_size = 384MB/" "$CONF"
sudo sed -i "s/^#maintenance_work_mem = .*/maintenance_work_mem = 64MB/" "$CONF"
sudo systemctl restart postgresql
```

> Postgres se come ~150-200 MB de base. Estos valores dejan RAM libre para Daphne + Redis + nginx.

### Redis — solo channel layer (sin persistencia)

Redis aquí solo sirve para el channel layer de WebSockets, así que no necesita guardar nada en disco. Ahorra RAM y escrituras:

```bash
sudo tee -a /etc/redis/redis.conf <<'EOF'
maxmemory 96mb
maxmemory-policy allkeys-lru
save ""
appendonly no
EOF
sudo systemctl restart redis-server
redis-cli ping   # debe responder PONG
```

### Daphne — un solo worker

En 2 GB NO aumentes `--workers` ni `--threads` en `tareaenminutos.service` (cada worker suma ~100-200 MB). El Daphne por defecto (un proceso) basta para este tráfico. Si algún día lo necesitas, migra primero a un plan con más RAM.

### Monitoreo

```bash
free -h          # RAM + swap (vigila que swap se use poco)
sudo systemctl status tareaenminutos postgresql redis-server
nginx -t && sudo systemctl reload nginx
```

---

## 5. Subir el proyecto

```bash
cd /var/www/tareaenminutos
# copia/extrae el código (el proyecto completo, incluye requirements.txt y deploy/)
# p. ej.: git clone <repo> .  (omitir db.sqlite3, media, media_privada, .env)
# OJO: el repo DEBE clonarse con manage.py en la raíz de /var/www/tareaenminutos
# (este repo se versiona desde la carpeta del proyecto, no desde una subcarpeta tareaenminutos_web/).

python3 -m venv /var/www/tareaenminutos/venv
/var/www/tareaenminutos/venv/bin/pip install -U pip
/var/www/tareaenminutos/venv/bin/pip install -r requirements.txt
```

> OJO: si el VPS no tiene acceso a internet para pip, revisa antes en local.

## 6. Crear el `.env` de producción

```bash
cp deploy/.env.prod .env
nano .env   # rellena TODOS los valores (SECRET_KEY, DB, Redis, email, SITE_BASE_URL...)
chmod 600 .env
```

Genera un SECRET_KEY real:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 7. Migraciones, estáticos y datos iniciales

```bash
/var/www/tareaenminutos/venv/bin/python manage.py migrate
/var/www/tareaenminutos/venv/bin/python manage.py collectstatic --noinput
/var/www/tareaenminutos/venv/bin/python manage.py inicializar_tem   # grupos, estados, áreas
/var/www/tareaenminutos/venv/bin/python manage.py createsuperuser   # tu admin
```

## 8. Servicio systemd (Daphne)

```bash
sudo cp deploy/tareaenminutos.service /etc/systemd/system/
# ajusta User/Group y rutas dentro del .service si no coinciden
sudo systemctl daemon-reload
sudo systemctl enable --now tareaenminutos
sudo systemctl status tareaenminutos   # debe verse active (running)
```

Verificar que responde localmente:
```bash
curl -I http://127.0.0.1:8000/
```

## 9. nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/tareaenminutos.conf
sudo ln -s /etc/nginx/sites-available/tareaenminutos.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

> Antes de certificar, el bloque HTTP ya sirve en el puerto 80 (necesario para el desafío ACME).

## 10. Certificado HTTPS (Let's Encrypt)

```bash
sudo certbot --nginx -d tareaenminutos.com -d www.tareaenminutos.com
```

certbot ajustará nginx para servir HTTPS. Vuelve a validar:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## Rutas/archivos que debes revisar tras el despliegue

| Cosa | Dónde |
|---|---|
| `.env` (producción) | `/var/www/tareaenminutos/.env` |
| `/media/` (subidas) | nginx lo sirve de `.../media/` — crea la carpeta y dale permisos |
| `/static/` | Whitenoise lo sirve desde Daphne (`STATIC_ROOT`) |
| WebSockets `/ws/` | nginx hace proxy → Daphne (ya configurado) |
| `django.log` | `.../tareaenminutos/django.log` (añade rotación si gustas) |

## Notas y errores comunes

- **No llegan correos**: `EMAIL_HOST_USER` vacío en `.env`. Para Gmail usa una *contraseña de aplicación*, no la de la cuenta.
- **Estáticos en blanco (404)**: corre `collectstatic` y confirma `STATIC_ROOT`.
- **WebSockets caídos**: asegura que nginx tiene el bloque `location /ws/` con `proxy_set_header Upgrade`.
- **`ALLOWED_HOSTS`**: nunca lo dejes en `*` en producción.
- Los documentos privados (`media_privada/`) solo se sirven por la vista autorizada, no por nginx.

## Actualizar tras cada cambio

```bash
# (en el server, desde /var/www/tareaenminutos/)
git pull                                          # si usas git
/var/www/tareaenminutos/venv/bin/pip install -r requirements.txt
/var/www/tareaenminutos/venv/bin/python manage.py migrate
/var/www/tareaenminutos/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart tareaenminutos
```
