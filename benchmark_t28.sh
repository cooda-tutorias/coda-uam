#!/usr/bin/env bash
set -e

FASE="${1:-DB_B}"
DUMP="dumps_t28/${FASE}.sql"

if [ ! -f "$DUMP" ]; then
    echo "[ERROR] No existe el dump: $DUMP"
    exit 1
fi

echo "[1/4] Restaurando ${FASE}..."

docker compose stop web >/dev/null

docker compose exec -T db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS coda WITH (FORCE);" >/dev/null
docker compose exec -T db psql -U postgres -d postgres -c "CREATE DATABASE coda;" >/dev/null

docker compose exec -T db psql -U postgres -d coda < "$DUMP" >/dev/null

echo "[2/4] Levantando web..."
docker compose up -d web >/dev/null

echo "[3/4] Ejecutando benchmark ${FASE}..."
docker compose exec -T web env FASE_T28="${FASE}" \
    python manage.py shell < coda-src/scripts/benchmark_reportes_t28.py

echo "[4/4] Copiando ZIP generado..."

mkdir -p coda-src/scripts/resultados_t28

docker cp \
    coda-uam-web-1:/tmp/benchmark_${FASE}.zip \
    coda-src/scripts/resultados_t28/benchmark_${FASE}.zip >/dev/null

echo "Terminado."
echo "Reporte TXT: coda-src/scripts/resultados_t28/benchmark_${FASE}.txt"
echo "ZIP generado: coda-src/scripts/resultados_t28/benchmark_${FASE}.zip"
