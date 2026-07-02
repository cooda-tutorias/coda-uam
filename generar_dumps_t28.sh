#!/usr/bin/env bash
set -e

mkdir -p dumps_t28

FASES=("DB_0" "DB_A" "DB_B" "DB_C" "DB_D")

for FASE in "${FASES[@]}"; do
    echo "=============================================="
    echo "Generando ${FASE}"
    echo "=============================================="

    docker compose exec -T web env \
        FASE_T28="${FASE}" \
        DRY_RUN_T28="false" \
        BORRAR_T28="true" \
        python manage.py shell < coda-src/scripts/generar_db_pruebas_reportes.py

    echo "Exportando dump ${FASE}.sql"
    docker compose exec -T db pg_dump -U postgres -d coda > "dumps_t28/${FASE}.sql"

    echo "[OK] dumps_t28/${FASE}.sql"
done

echo "=============================================="
echo "Dumps generados:"
ls -lh dumps_t28
echo "=============================================="
