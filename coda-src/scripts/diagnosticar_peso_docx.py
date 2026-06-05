from io import BytesIO
from datetime import datetime
from zipfile import ZipFile
from time import perf_counter

import docx

from Usuarios.models import Tutor, Documento
from Tutorias.models import Tutoria
from Tutorias.constants import TEMAS
from Tutorias.services.docx_reportes import generar_docx_reporte_tutorias_brindadas


CONFIG = {
    "PLANTILLA_NOMBRE": "Reporte tutorías atendidas (carta anual)",
    "TUTOR_MATRICULA": "41935",
    "FECHA_EMISION": "2026-04-19T14:44",
    "OFICIO": "DCNI_CODDAA_900_2026",
    "COLUMNAS": ["Alumno", "Fecha", "Tema", "Notas"],
    "LIMITE_TUTORIAS": None,
}


def mb(n):
    return n / (1024 * 1024)


def medir_docx_bytes(nombre, contenido):
    print(f"{nombre}: {len(contenido)} bytes | {mb(len(contenido)):.2f} MB")


def guardar_documento_en_bytes(documento):
    buffer = BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def main():
    plantilla = Documento.objects.get(nombre=CONFIG["PLANTILLA_NOMBRE"])
    tutor = Tutor.objects.get(matricula=CONFIG["TUTOR_MATRICULA"])
    tema_dict = dict(TEMAS)

    print("=" * 80)
    print("DIAGNÓSTICO DE PESO DOCX")
    print("=" * 80)

    with plantilla.archivo.open("rb") as f:
        plantilla_bytes = f.read()

    medir_docx_bytes("01 Plantilla original desde Documento.archivo", plantilla_bytes)

    doc_sin_cambios = docx.Document(BytesIO(plantilla_bytes))
    bytes_sin_cambios = guardar_documento_en_bytes(doc_sin_cambios)
    medir_docx_bytes("02 Plantilla abierta y guardada sin cambios", bytes_sin_cambios)
    print(f"Documento.nombre: {plantilla.nombre}")
    print(f"Documento.archivo.name: {plantilla.archivo.name}")
    print(f"Documento.archivo.path: {plantilla.archivo.path}")

    tutorias_qs = Tutoria.objects.filter(tutor=tutor).select_related("alumno", "tutor").order_by("fecha")

    if CONFIG["LIMITE_TUTORIAS"] is not None:
        tutorias_qs = tutorias_qs[:CONFIG["LIMITE_TUTORIAS"]]

    mostrar_col_alumno = "Alumno" in CONFIG["COLUMNAS"]
    mostrar_col_fecha = "Fecha" in CONFIG["COLUMNAS"]
    mostrar_col_hora = "Hora" in CONFIG["COLUMNAS"]
    mostrar_col_tema = "Tema" in CONFIG["COLUMNAS"]
    mostrar_col_notas = "Notas" in CONFIG["COLUMNAS"]

    inicio = perf_counter()

    response = generar_docx_reporte_tutorias_brindadas(
        tutor=tutor,
        tutorias=tutorias_qs,
        plantilla=plantilla,
        oficio=CONFIG["OFICIO"],
        fecha_emision=CONFIG["FECHA_EMISION"],
        columnas_activas=CONFIG["COLUMNAS"],
        mostrar_col_alumno=mostrar_col_alumno,
        mostrar_col_fecha=mostrar_col_fecha,
        mostrar_col_hora=mostrar_col_hora,
        mostrar_col_tema=mostrar_col_tema,
        mostrar_col_notas=mostrar_col_notas,
        tema_dict=tema_dict,
    )

    tiempo = perf_counter() - inicio
    medir_docx_bytes("03 Documento generado completo", response.content)

    print(f"Tiempo generación: {tiempo:.2f}s")
    print(f"Tutorías consideradas: {tutorias_qs.count() if hasattr(tutorias_qs, 'count') else len(tutorias_qs)}")

    print("=" * 80)


main()
