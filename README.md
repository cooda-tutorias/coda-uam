# CODA UAM

Aplicación Django para la gestión de tutorías. Se ejecuta con Docker y está formada por tres servicios:

| Servicio | Qué hace |
|---|---|
| `web` | Aplicación Django (puerto 8000) |
| `db` | PostgreSQL |
| `seaweedfs` | Almacenamiento de archivos (fotos, PDFs, documentos). Sólo es accesible desde `web` |

Hay dos métodos de instalación: **Docker Compose** (recomendado) y **Docker manual**. Usa solamente uno.

## Requisitos

- Docker con el plugin Compose (Docker Desktop en Windows/macOS).
- En Linux, los comandos `docker` requieren pertenecer al grupo `docker` o usar `sudo`.

## Inicio rápido

```sh
cp .env.example .env          # edita los valores; ver "Variables de entorno"
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Abre `http://localhost:8000`. Para detener todo: `docker compose down`.

Siempre usa `--build` al levantar: `web` y `seaweedfs` se construyen desde este repositorio, y sin `--build` Docker puede reutilizar una imagen vieja.

## Versionado y actualizaciones

Nada se actualiza solo. Cada pieza tiene una versión fija, para que el proyecto se comporte igual hoy y dentro de seis meses. Para actualizar algo, se cambia un número y se reconstruye.

| Pieza | Dónde está la versión | Cómo actualizar |
|---|---|---|
| Código de la aplicación | Git (rama `main`) | `git pull` y luego `docker compose up -d --build` |
| Base de datos (esquema) | Migraciones en `coda-src/*/migrations/` | `docker compose exec web python manage.py migrate` después de cada `git pull` |
| Python y Django | `coda-src/Dockerfile` y `coda-src/requirements.txt` | Cambiar la versión, reconstruir y correr las pruebas |
| PostgreSQL | `image: postgres:17` en `compose.yaml` | No cambies de versión mayor sobre `data/db` sin respaldo y migración de datos |
| SeaweedFS | `SEAWEEDFS_VERSION` en `.env` | Ver abajo |

### Actualizar SeaweedFS

1. Respalda `data/seaweedfs`.
2. Cambia `SEAWEEDFS_VERSION` en `.env` (por ejemplo `4.48` a la versión nueva).
3. Ejecuta `docker compose up -d --build seaweedfs`.
4. Espera a que `docker compose ps` muestre `healthy`, y revisa que una foto de perfil y un PDF de trayectoria sigan abriendo.
5. Si falla, regresa el número anterior y vuelve a ejecutar el paso 3.

Por qué no se usa `latest`: SeaweedFS puede cambiar sus opciones entre versiones, y el servicio guarda las que usó en `data/seaweedfs/mini.options`. Con `latest`, una actualización inesperada podría romper el proyecto sin que nadie haya tocado el código.

### Qué se regenera en cada arranque

- **Certificado TLS de SeaweedFS:** se emite uno nuevo en cada inicio del contenedor (válido 30 días), firmado por una CA interna que persiste en el volumen `seaweedfs-server-tls`. No hay que renovar nada a mano.
- **Archivos antiguos:** las versiones de trayectoria se conservan como historial y no se sobrescriben; no hay migración de archivos entre versiones de SeaweedFS.

## Variables de entorno

Copia `.env.example` a `.env` y revisa al menos:

- `DJANGO_SECRET_KEY`: genera una con `python3 -c 'import secrets; print(secrets.token_hex(100))'`.
- `EMAIL_HOST_PASSWORD` y `EMAIL_DOMAIN`.
- `POSTGRES_PASSWORD` y `RDS_PASSWORD` (deben coincidir).
- `OBJECT_STORAGE_*` y `SEAWEEDFS_VERSION`: déjalos como vienen para desarrollo local.
- No subas `.env` a Git.

## Almacenamiento de archivos con SeaweedFS

SeaweedFS es el backend S3-compatible de archivos de la aplicación (fotos, documentos y trayectorias) y se puede usar en pruebas de integración y producción. El modo de despliegue depende del entorno:

### Pruebas automatizadas

La configuración `ssocial.settings_test` usa SQLite en memoria y almacenamiento local temporal. La suite unitaria no necesita conectarse a SeaweedFS ni descargar servicios externos; los tests del cliente S3 usan respuestas simuladas.

### Desarrollo y pruebas de integración

Compose levanta `weed mini` en un solo nodo, crea el bucket de `S3_BUCKET` y conserva sus datos en `data/seaweedfs`. El gateway S3 sólo escucha HTTPS dentro de la red privada de Compose. En cada inicio se emite un certificado servidor nuevo firmado por una CA interna persistente. Esta configuración sirve para desarrollo y pruebas de integración; no representa una topología de alta disponibilidad.

1. Copia `.env.example` a `.env`. Las credenciales incluidas son únicamente valores locales de ejemplo; usa valores propios.
2. Deja `OBJECT_STORAGE_ENABLED=True`, `OBJECT_STORAGE_USE_TLS=True`, `OBJECT_STORAGE_ENDPOINT_URL=https://seaweedfs:8333` y `OBJECT_STORAGE_CA_BUNDLE=/run/seaweedfs-ca/ca.crt`.
3. Ejecuta `docker compose up --build`. El endpoint S3 no publica puertos al host y el bucket no permite acceso anónimo.
4. Para ejecutar pruebas funcionales sin escribir fixtures en el bucket compartido, usa `docker compose run --rm --no-deps -e OBJECT_STORAGE_ENABLED=False web python manage.py test Usuarios Tutorias`.

### Producción

En producción la aplicación se conecta por HTTPS interno a una instalación SeaweedFS administrada y persistente; no uses el `weed mini` de Compose como sustituto de la topología productiva. El despliegue genera/rota el certificado servidor y monta la CA interna en Django para validar TLS. Configura `DJANGO_ENV=production`, `OBJECT_STORAGE_ENABLED=True` y `OBJECT_STORAGE_USE_TLS=True`:

- `OBJECT_STORAGE_ENDPOINT_URL`: endpoint S3 interno accesible desde Django.
- `OBJECT_STORAGE_CA_BUNDLE`: ruta al certificado CA interno que Django usa para validar el servidor SeaweedFS.
- `OBJECT_STORAGE_ACCESS_KEY` y `OBJECT_STORAGE_SECRET_KEY`: credenciales de aplicación privadas, distintas de las credenciales administrativas.
- `OBJECT_STORAGE_BUCKET_NAME`: bucket privado usado por la aplicación.

Todas las lecturas y descargas de fotos, PDFs y documentos pasan por vistas autenticadas de Django; el navegador no recibe el endpoint ni credenciales de SeaweedFS. Los datos deben residir en almacenamiento persistente con respaldos y una política de disponibilidad adecuada al servicio. No publiques el endpoint interno ni uses las credenciales de ejemplo en producción.

## Docker compose
Detalle de los pasos del inicio rápido. La configuración del entorno está en `compose.yaml`; no lo modifiques para cambiar valores, usa `.env`.

### Inicialización de base de datos
Para entrar al admin de Django necesitas un superusuario. Los comandos se ejecutan en el servicio `web`, sin necesidad de copiar IDs de contenedor:

```sh
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Para un esquema de pruebas necesitarás perfiles de todos los roles; pide apoyo al `Product Owner / Project Manager` para llenar la base de datos.

### Migraciones al actualizar el código

Después de cada `git pull` (o cuando una funcionalidad cambia los modelos) ejecuta:

```sh
docker compose up -d --build
docker compose exec web python manage.py migrate
```

> **Nota:** Las tutorías creadas **antes** de una migración que agrega campos opcionales mostrarán `Sin registro` en esos campos. Es normal; las tutorías nuevas capturan el dato automáticamente.


## Docker manual
Antes de empezar, descomenta la línea 17 del archivo `coda-src/ssocial/settings.py` como se muestra a continuación:
```python
# TODO: mochar esto en prod
from .env_vars import *
```

### Creación de archivo de variables de entorno

1. En el directorio `coda-src/ssocial` Crea un archivo llamado `env_vars.py`.
2. Copia y pega el siguiente código en el archivo:

```python
import os

os.environ.setdefault('DJANGO_SECRET_KEY', '<key>')
os.environ.setdefault('RDS_DB_NAME', 'coda')
os.environ.setdefault('RDS_USERNAME', 'postgres')
os.environ.setdefault('RDS_PASSWORD', '<contraseña>')
os.environ.setdefault('RDS_HOSTNAME', 'margarito-contenedor')
os.environ.setdefault('RDS_PORT', '5432')
os.environ.setdefault('DJANGO_DEBUG', 'True')
os.environ.setdefault('TUTORIAS_DOMINIO', '<dominio>')
os.environ.setdefault('IP_COMPUTADORA', 'localhost')
os.environ.setdefault('EMAIL_HOST_PASSWORD', '<email>')
```
3. Reemplaza los valores entre `*** CAMBIAR VALORES ***` con la información correspondiente al entorno de produccion.


### Creación de la base de datos

1. Cambia al directorio `DB`.
2. Modifica las líneas 5 y 10 del archivo `Dockerfile` para que coincidan con tu configuración.
3. Ejecuta los siguientes comandos:

```
docker network create <nombre-red>
docker build -t margarito .
docker run -d --network <nombre-red> -p 5432:5432 --name margarito-contenedor margarito
docker exec -it margarito-contenedor psql -U postgres -c 'CREATE DATABASE coda;'
```

### Creación del servidor Django

1. Cambia al directorio `coda-src`.
2. Ejecuta el siguiente comando:

```
docker build -t djangarito .
```

3. Inicia el servidor Django:

```
docker run -d --network <nombre-red> -p 8000:8000 --name djangarito_contenedor djangarito
```

### Implementación del servidor

1. En Docker Desktop, selecciona la pestaña "Contenedores".
2. Busca y selecciona el contenedor `djangarito_contenedor`.
3. Selecciona la pestaña "Exec".
4. Ejecuta los siguientes comandos:

```
python3 manage.py migrate
python3 manage.py createsuperuser
```

## Notas adicionales

* Asegúrate de reemplazar los valores predeterminados en el archivo `env_vars.py` con la información de tu proyecto.
* Puedes cambiar el nombre de la red y los nombres de los contenedores según tus preferencias.
* Para obtener más información sobre cómo usar Docker y Django, consulta la documentación oficial:
    * [docs.docker.com](https://docs.docker.com/)
    * [docs.djangoproject.com](https://docs.djangoproject.com/en/4.2/)
* En linux, los comandos `docker` en terminal requieren como permiso de acceso ser parte del grupo `docker` que se crea automaticamente con la instalación de Docker. En caso de que no se quiera agregar el usuario al grupo, debera usarse `sudo` antes de cada comando.