"""
Benchmark para la función T28: generación masiva de reportes de tutorías.

Este script se ejecuta dentro del contenedor web con Django shell:

    docker compose exec -T web env FASE_T28=DB_B \
        python manage.py shell < coda-src/scripts/benchmark_reportes_t28.py

Propósito:
- Restaurada una base sintética DB_0, DB_A, DB_B, DB_C o DB_D,
  genera los reportes masivos por tutor sin usar la interfaz web.
- Mide tiempo de generación, tamaño de DOCX individuales y tamaño del ZIP.
- Guarda un TXT con resultados y un ZIP temporal en /tmp.

Relación con archivos principales:
- coda-src/Usuarios/models.py
  - Modelo Tutor: usado para obtener tutores sintéticos.
  - Modelo Alumno: usado para contar alumnos sintéticos.
  - Modelo Documento: usado para recuperar la plantilla DOCX.
- coda-src/Tutorias/models.py
  - Modelo Tutoria: usado para obtener tutorías sintéticas por tutor.
- coda-src/Tutorias/constants.py
  - TEMAS: usado para traducir claves de temas a etiquetas legibles.
- coda-src/Tutorias/services/docx_reportes.py
  - generar_docx_reporte_tutorias_brindadas(): función real de generación DOCX.
- coda-src/Tutorias/views.py
  - ReporteTutoriasBrindadasMasivoView.form_valid(): contiene la lógica web equivalente
    que procesa formulario, genera DOCX y arma ZIP.
"""

import os
from io import BytesIO
from zipfile import ZipFile
from time import perf_counter
from pathlib import Path

# Modelos base del sistema.
# Estos modelos están definidos en coda-src/Usuarios/models.py.
from Usuarios.models import Tutor, Alumno, Documento

# Modelo de tutorías.
# Definido en coda-src/Tutorias/models.py.
from Tutorias.models import Tutoria

# Catálogo de temas de tutoría.
# Definido en coda-src/Tutorias/constants.py.
from Tutorias.constants import TEMAS

# Función real que genera cada DOCX individual.
# Definida en coda-src/Tutorias/services/docx_reportes.py.
from Tutorias.services.docx_reportes import generar_docx_reporte_tutorias_brindadas


# Fase de prueba recibida desde benchmark_t28.sh.
# Ejemplo: DB_0, DB_A, DB_B, DB_C o DB_D.
FASE = os.environ.get("FASE_T28", "DB_B")

# Marcador usado por generar_db_pruebas_reportes.py para identificar tutorías sintéticas.
MARCADOR = f"[PRUEBA_T28]_{FASE}"

# Nombre lógico de la plantilla en la tabla Usuarios_documento.
PLANTILLA_NOMBRE = os.environ.get(
    "PLANTILLA_T28",
    "Reporte tutorías atendidas (carta anual)"
)

# Columnas que se generan en el reporte.
# Deben coincidir con las opciones que usa FormReporteTutoriasMasivo en Tutorias/forms.py.
COLUMNAS = ["Alumno", "Fecha", "Tema", "Notas"]

# Licenciaturas usadas por la función T28.
COORDINACIONES = ["COM", "MAT", "IB", "BM"]

# Carpeta donde se guardará el TXT de resultados dentro del contenedor web.
# Como el shell se ejecuta desde /app, esto corresponde a:
# /app/scripts/resultados_t28
RESULTADOS_DIR = Path("scripts/resultados_t28")
RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

# Archivos de salida del benchmark.
TXT_SALIDA = RESULTADOS_DIR / f"benchmark_{FASE}.txt"
ZIP_SALIDA = Path("/tmp") / f"benchmark_{FASE}.zip"


def mb(n):
    """Convierte bytes a megabytes."""
    return n / (1024 * 1024)


def normalizar_oficio(numero, anio):
    """
    Genera un número de oficio sintético.

    En la vista web real, este dato viene del formulario masivo.
    Aquí se genera automáticamente para no depender de entrada manual.
    """
    return f"DCNI_CODDAA_{numero}_{anio}"


def escribir(lineas, texto=""):
    """
    Agrega una línea al reporte TXT.

    Se usa esta función pequeña para centralizar la escritura lógica del reporte
    y evitar imprimir demasiado en terminal.
    """
    lineas.append(texto)


def main():
    print(f"[1/3] Preparando benchmark {FASE}...")

    # Recupera la plantilla DOCX desde la tabla Documento.
    # Equivale a la plantilla seleccionada en el formulario web.
    plantilla = Documento.objects.get(nombre=PLANTILLA_NOMBRE)

    # Diccionario para traducir temas de tutoría.
    # Se pasa a generar_docx_reporte_tutorias_brindadas().
    tema_dict = dict(TEMAS)

    # Selecciona únicamente tutores sintéticos generados para pruebas T28.
    # Los correos sintéticos contienen ".t28".
    tutores = list(
        Tutor.objects.filter(
            email__contains=".t28",
            coordinacion__in=COORDINACIONES,
        ).order_by("coordinacion", "matricula")
    )

    # Conteos generales para el resumen del benchmark.
    alumnos_total = Alumno.objects.filter(email__contains=".t28").count()
    tutorias_total = Tutoria.objects.filter(descripcion__contains=MARCADOR).count()

    # Banderas equivalentes a las columnas seleccionadas en el formulario web.
    mostrar_col_alumno = "Alumno" in COLUMNAS
    mostrar_col_fecha = "Fecha" in COLUMNAS
    mostrar_col_hora = "Hora" in COLUMNAS
    mostrar_col_tema = "Tema" in COLUMNAS
    mostrar_col_notas = "Notas" in COLUMNAS

    # Construcción inicial del reporte TXT.
    lineas = []
    escribir(lineas, "=" * 90)
    escribir(lineas, f"BENCHMARK T28 - {FASE}")
    escribir(lineas, "=" * 90)
    escribir(lineas, f"Marcador: {MARCADOR}")
    escribir(lineas, f"Plantilla: {plantilla.nombre}")
    escribir(lineas, f"Archivo plantilla: {plantilla.archivo.name}")
    escribir(lineas, f"Tutores sintéticos: {len(tutores)}")
    escribir(lineas, f"Alumnos sintéticos: {alumnos_total}")
    escribir(lineas, f"Tutorías sintéticas: {tutorias_total}")
    escribir(lineas, f"Columnas: {', '.join(COLUMNAS)}")
    escribir(lineas, "=" * 90)

    print(f"[2/3] Generando reportes para {len(tutores)} tutores...")

    # ZIP en memoria. Esto reproduce el comportamiento principal de la vista masiva:
    # generar muchos DOCX y empacarlos en un solo archivo comprimido.
    zip_buffer = BytesIO()

    # Listas para métricas.
    tamanios_docx = []
    tiempos = []
    total_tutorias_reportadas = 0

    # perf_counter se usa para medir tiempos de forma precisa.
    inicio_total = perf_counter()

    with ZipFile(zip_buffer, "w") as zip_file:
        for idx, tutor in enumerate(tutores, start=1):
            inicio_tutor = perf_counter()

            # Tutorías sintéticas del tutor actual.
            # Este filtro reproduce el subconjunto que se espera para cada fase.
            tutorias = Tutoria.objects.filter(
                tutor=tutor,
                descripcion__contains=MARCADOR,
            ).select_related("alumno", "tutor").order_by("fecha")

            num_tutorias = tutorias.count()
            total_tutorias_reportadas += num_tutorias

            # Generación real del DOCX.
            # Esta es la función productiva del servicio docx_reportes.py,
            # por lo que el benchmark mide el comportamiento real del generador.
            response = generar_docx_reporte_tutorias_brindadas(
                tutor=tutor,
                tutorias=tutorias,
                plantilla=plantilla,
                oficio=normalizar_oficio(900 + idx, 2026),
                fecha_emision="2026-06-30T12:00",
                columnas_activas=COLUMNAS,
                mostrar_col_alumno=mostrar_col_alumno,
                mostrar_col_fecha=mostrar_col_fecha,
                mostrar_col_hora=mostrar_col_hora,
                mostrar_col_tema=mostrar_col_tema,
                mostrar_col_notas=mostrar_col_notas,
                tema_dict=tema_dict,
            )

            contenido = response.content
            tamanio = len(contenido)
            tiempo_tutor = perf_counter() - inicio_tutor

            # Carpeta interna del ZIP según licenciatura.
            # Debe coincidir conceptualmente con la organización usada en views.py.
            carpeta = {
                "COM": "Ingenieria_en_Computacion",
                "MAT": "Matematicas_Aplicadas",
                "IB": "Ingenieria_Biologica",
                "BM": "Biologia_Molecular",
            }.get(tutor.coordinacion, "Sin_licenciatura")

            # Nombre del archivo DOCX dentro del ZIP.
            nombre = f"{tutor.matricula}_{tutor.last_name}_{tutor.first_name}_TUTORIAS_BRINDADAS.docx"

            # Escritura del DOCX en el ZIP.
            zip_file.writestr(f"{carpeta}/{nombre}", contenido)

            # Métricas por tutor.
            tamanios_docx.append(tamanio)
            tiempos.append(tiempo_tutor)

            escribir(
                lineas,
                f"{idx:04d} | {tutor.coordinacion} | {tutor.matricula} | "
                f"tutorias={num_tutorias} | docx={mb(tamanio):.3f} MB | "
                f"tiempo={tiempo_tutor:.3f}s"
            )

            # Progreso mínimo en terminal para saber que el proceso no se congeló.
            if idx % 25 == 0 or idx == len(tutores):
                print(f"      progreso: {idx}/{len(tutores)} tutores")

    tiempo_total = perf_counter() - inicio_total
    zip_bytes = zip_buffer.getvalue()

    # Guarda el ZIP dentro del contenedor.
    # benchmark_t28.sh después lo copia al host con docker cp.
    with open(ZIP_SALIDA, "wb") as f:
        f.write(zip_bytes)

    # Resumen final del TXT.
    escribir(lineas, "=" * 90)
    escribir(lineas, "RESUMEN")
    escribir(lineas, "=" * 90)
    escribir(lineas, f"Fase: {FASE}")
    escribir(lineas, f"Tutores procesados: {len(tutores)}")
    escribir(lineas, f"Alumnos sintéticos en base: {alumnos_total}")
    escribir(lineas, f"Tutorías sintéticas en base: {tutorias_total}")
    escribir(lineas, f"Tutorías incluidas en reportes: {total_tutorias_reportadas}")
    escribir(lineas, f"Tamaño ZIP: {mb(len(zip_bytes)):.3f} MB")
    escribir(lineas, f"Tiempo total: {tiempo_total:.3f}s")

    if tamanios_docx:
        escribir(lineas, f"DOCX mínimo: {mb(min(tamanios_docx)):.3f} MB")
        escribir(lineas, f"DOCX máximo: {mb(max(tamanios_docx)):.3f} MB")
        escribir(lineas, f"DOCX promedio: {mb(sum(tamanios_docx) / len(tamanios_docx)):.3f} MB")

    if tiempos:
        escribir(lineas, f"Tiempo promedio por tutor: {sum(tiempos) / len(tiempos):.3f}s")
        escribir(lineas, f"Tiempo máximo por tutor: {max(tiempos):.3f}s")

    escribir(lineas, f"ZIP generado: {ZIP_SALIDA}")
    escribir(lineas, f"Reporte TXT: {TXT_SALIDA}")
    escribir(lineas, "=" * 90)

    # Guarda el reporte TXT.
    TXT_SALIDA.write_text("\n".join(lineas), encoding="utf-8")

    print("[3/3] Benchmark terminado.")
    print(f"      TXT: {TXT_SALIDA}")
    print(f"      ZIP: {ZIP_SALIDA}")


main()