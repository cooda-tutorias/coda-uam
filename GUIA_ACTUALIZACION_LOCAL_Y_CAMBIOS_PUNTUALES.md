# Guia de Actualizacion Local y Cambios Puntuales

Esta guia esta pensada para estudiantes que apenas inician en desarrollo.
Usala cada vez que hagas pull de cambios o cuando tu entorno local quede desfasado.

## Caso A. Actualizacion Rapida (cambios puntuales)

Usa este flujo cuando solo bajaste cambios normales del equipo.

1. Ir al proyecto y actualizar rama

```bash
cd "<PATH_DEL_PROYECTO>"
git pull
```

2. Reconstruir contenedores

```bash
sudo docker compose up -d --build
```

3. Aplicar migraciones pendientes

```bash
sudo docker compose exec web python manage.py migrate
```

4. Validar migraciones

```bash
sudo docker compose exec web python manage.py showmigrations
```

Si todo esta bien, debes ver las migraciones nuevas como aplicadas ([X]).

## Caso B. Reinicio Total Local (si tu entorno ya no levanta)

Usa este flujo cuando hay errores por diferencias grandes de base de datos,
dependencias viejas o muchos cambios acumulados.

Importante: esto borra tu base local y datos locales.

1. Apagar y eliminar contenedores + volumenes

```bash
sudo docker compose down -v
```

2. Limpiar carpeta de datos local (opcional pero recomendado)

```bash
sudo rm -rf data/db/*
```

3. Levantar de nuevo desde cero

```bash
sudo docker compose up -d --build
```

4. Ejecutar migraciones

```bash
sudo docker compose exec web python manage.py migrate
```

5. Cargar datos base (si tu equipo usa fixtures)

```bash
# Ejemplo, solo si aplica en tu equipo
sudo docker compose exec web python manage.py loaddata <archivo_fixture>.json
```

## Reglas Practicas para no romper el entorno

- Si solo hiciste pull: normalmente basta con Caso A.
- No corras makemigrations salvo que cambies modelos.
- Si migrate falla por historial raro de migraciones: usa Caso B.
- Antes de pedir ayuda, comparte el error exacto y el comando que corriste.

## Comandos de Diagnostico Utiles

```bash
sudo docker compose ps
sudo docker compose logs --tail=100 web
sudo docker compose exec web python manage.py check
sudo docker compose exec web python manage.py showmigrations
```

## Nota para cambios de feature

Si una feature nueva agrega campos o tablas, siempre debes correr migrate
despues de hacer pull. Si no lo haces, pueden salir errores de columnas o
tablas inexistentes.
