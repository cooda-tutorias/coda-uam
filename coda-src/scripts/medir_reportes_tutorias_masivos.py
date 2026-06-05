"""
Script para medir generación masiva de reportes de tutorías.

Ejecución desde la raíz del proyecto:

    docker compose exec -T web python manage.py shell < coda-src/scripts/medir_reportes_tutorias_masivos.py

Mide:
- número de tutores procesados
- alumnos asignados por tutor
- tutorías por tutor
- tamaño de cada DOCX generado
- tamaño total del ZIP
- tiempo total
- tiempo promedio por tutor
"""

from io import BytesIO
from zipfile import ZipFile
from datetime import datetime, timedelta
from time import perf_counter

from django.utils import timezone
from django.http import HttpResponse

from Usuarios.models import Tutor, Alumno, Documento
from Tutorias.models import Tutoria
from Tutorias.constants import TEMAS
from Tutorias.services.docx_reportes import generar_docx_reporte_tutorias_brindadas


CONFIG = {
    # Si quieres limitar por licenciatura, usa códigos: COM, MAT, IB, BM.
    # Si lo dejas vacío, toma todas.
    "COORDINACIONES": ["COM", "MAT"],

    # Si quieres limitar por tutores específicos, pon sus matrículas.
    # Si lo dejas vacío, toma todos los tutores de las coordinaciones.
    "TUTORES_MATRICULAS": [],

    # Rango de fechas del reporte.
    "FECHA_INICIO": "2025-01-01",
    "FECHA_FIN": "2026-12-31",

    # Fecha de emisión del oficio.
    "FECHA_EMISION": "2026-04-19T14:44",

    # Número de oficio inicial.
    "OFICIO_INICIAL": 900,

    # Nombre exacto del Documento en la base de datos.
    # Si falla, revisa en admin el nombre de la plantilla.
    "PLANTILLA_NOMBRE": "Reporte tutorías atendidas (carta anual)",

    # Columnas activas.
    "COLUMNAS": ["Alumno", "Fecha", "Tema", "Notas"],

    # Guardar ZIP de prueba en /tmp dentro del contenedor.
    "GUARDAR_ZIP": True,
    "RUTA_ZIP_SALIDA": "/tmp/medicion_reportes_tutorias_masivos.zip",
}


CARPETAS_LICENCIATURA = {
    "COM": "Ingenieria_en_Computacion",
    "MAT": "Matematicas_Aplicadas",
    "IB": "Ingenieria_Biologica",
    "BM": "Biologia_Molecular",
}


def mb(num_bytes):
    return num_bytes / (1024 * 1024)


def normalizar_numero_oficio(oficio_ingresado, fecha_documento):
    if oficio_ingresado in (None, ""):
        return ""
    anio = fecha_documento.year
    return f"DCNI_CODDAA_{int(oficio_ingresado)}_{anio}"


def obtener_plantilla():
    nombre = CONFIG["PLANTILLA_NOMBRE"]

    plantilla = Documento.objects.filter(nombre=nombre).first()
    if plantilla:
        return plantilla

    print(f"[WARN] No se encontró plantilla con nombre exacto: {nombre}")
    print("[INFO] Plantillas disponibles:")

    for doc in Documento.objects.all().order_by("nombre"):
        print(f"  - {doc.nombre}")

    raise SystemExit("[ERROR] Ajusta CONFIG['PLANTILLA_NOMBRE'].")


def obtener_tutores():
    qs = Tutor.objects.all()

    coordinaciones = CONFIG["COORDINACIONES"]
    if coordinaciones:
        qs = qs.filter(coordinacion__in=coordinaciones)

    matriculas = CONFIG["TUTORES_MATRICULAS"]
    if matriculas:
        qs = qs.filter(matricula__in=matriculas)

    return qs.order_by("coordinacion", "last_name", "first_name").distinct()


def generar_medicion():
    fecha_inicio = datetime.strptime(CONFIG["FECHA_INICIO"], "%Y-%m-%d")
    fecha_fin = datetime.strptime(CONFIG["FECHA_FIN"], "%Y-%m-%d") + timedelta(days=1)
    fecha_emision = datetime.strptime(CONFIG["FECHA_EMISION"], "%Y-%m-%dT%H:%M")
    fecha_emision_str = fecha_emision.strftime("%Y-%m-%dT%H:%M")

    plantilla = obtener_plantilla()
    tutores = list(obtener_tutores())
    tema_dict = dict(TEMAS)

    mostrar_col_alumno = "Alumno" in CONFIG["COLUMNAS"]
    mostrar_col_fecha = "Fecha" in CONFIG["COLUMNAS"]
    mostrar_col_hora = "Hora" in CONFIG["COLUMNAS"]
    mostrar_col_tema = "Tema" in CONFIG["COLUMNAS"]
    mostrar_col_notas = "Notas" in CONFIG["COLUMNAS"]

    print("=" * 90)
    print("MEDICIÓN DE REPORTES MASIVOS DE TUTORÍAS")
    print("=" * 90)
    print(f"Tutores seleccionados: {len(tutores)}")
    print(f"Coordinaciones: {CONFIG['COORDINACIONES'] or 'TODAS'}")
    print(f"Rango: {CONFIG['FECHA_INICIO']} a {CONFIG['FECHA_FIN']}")
    print(f"Plantilla: {plantilla.nombre}")
    print(f"Columnas: {', '.join(CONFIG['COLUMNAS'])}")
    print("=" * 90)

    zip_buffer = BytesIO()
    consecutivo = CONFIG["OFICIO_INICIAL"]
    total_tutorias = 0
    total_alumnos_asignados = 0
    tamanios_docx = []
    tiempos_tutor = []

    inicio_total = perf_counter()

    with ZipFile(zip_buffer, "w") as zip_file:
        for index, tutor in enumerate(tutores, start=1):
            inicio_tutor = perf_counter()

            tutorias = Tutoria.objects.filter(
                tutor=tutor,
                fecha__range=(fecha_inicio, fecha_fin),
            ).select_related("alumno", "tutor").order_by("fecha")

            num_tutorias = tutorias.count()
            num_alumnos = Alumno.objects.filter(tutor_asignado=tutor).count()

            oficio = normalizar_numero_oficio(consecutivo, fecha_emision.date())

            response = generar_docx_reporte_tutorias_brindadas(
                tutor=tutor,
                tutorias=tutorias,
                plantilla=plantilla,
                oficio=oficio,
                fecha_emision=fecha_emision_str,
                columnas_activas=CONFIG["COLUMNAS"],
                mostrar_col_alumno=mostrar_col_alumno,
                mostrar_col_fecha=mostrar_col_fecha,
                mostrar_col_hora=mostrar_col_hora,
                mostrar_col_tema=mostrar_col_tema,
                mostrar_col_notas=mostrar_col_notas,
                tema_dict=tema_dict,
            )

            contenido_docx = response.content
            tamanio_docx = len(contenido_docx)

            nombre_carpeta = CARPETAS_LICENCIATURA.get(tutor.coordinacion, "Sin_licenciatura")
            nombre_archivo = f"{tutor.matricula}_{tutor.last_name}_{tutor.first_name}_TUTORIAS_BRINDADAS.docx"
            ruta_zip = f"{nombre_carpeta}/{nombre_archivo}"

            zip_file.writestr(ruta_zip, contenido_docx)

            tiempo_tutor = perf_counter() - inicio_tutor

            total_tutorias += num_tutorias
            total_alumnos_asignados += num_alumnos
            tamanios_docx.append(tamanio_docx)
            tiempos_tutor.append(tiempo_tutor)

            print(
                f"[{index:03d}] {tutor.coordinacion} | "
                f"{tutor.matricula} - {tutor.first_name} {tutor.last_name} | "
                f"alumnos={num_alumnos} | "
                f"tutorias={num_tutorias} | "
                f"docx={mb(tamanio_docx):.2f} MB | "
                f"tiempo={tiempo_tutor:.2f}s"
            )

            consecutivo += 1

    tiempo_total = perf_counter() - inicio_total
    zip_bytes = zip_buffer.getvalue()
    tamanio_zip = len(zip_bytes)

    if CONFIG["GUARDAR_ZIP"]:
        with open(CONFIG["RUTA_ZIP_SALIDA"], "wb") as f:
            f.write(zip_bytes)

    print("=" * 90)
    print("RESUMEN")
    print("=" * 90)
    print(f"Tutores procesados: {len(tutores)}")
    print(f"Alumnos asignados acumulados: {total_alumnos_asignados}")
    print(f"Tutorías procesadas: {total_tutorias}")
    print(f"Tamaño ZIP: {mb(tamanio_zip):.2f} MB")

    if tamanios_docx:
        print(f"Peso DOCX mínimo: {mb(min(tamanios_docx)):.2f} MB")
        print(f"Peso DOCX máximo: {mb(max(tamanios_docx)):.2f} MB")
        print(f"Peso DOCX promedio: {mb(sum(tamanios_docx) / len(tamanios_docx)):.2f} MB")

    print(f"Tiempo total: {tiempo_total:.2f}s")

    if tiempos_tutor:
        print(f"Tiempo promedio por tutor: {sum(tiempos_tutor) / len(tiempos_tutor):.2f}s")
        print(f"Tiempo máximo por tutor: {max(tiempos_tutor):.2f}s")

    if CONFIG["GUARDAR_ZIP"]:
        print(f"ZIP guardado en: {CONFIG['RUTA_ZIP_SALIDA']}")

    print("=" * 90)


generar_medicion()