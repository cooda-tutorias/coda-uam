"""
Diagnóstico de peso para plantillas y reportes DOCX de tutorías.

Ejecución recomendada desde la raíz del proyecto:

    docker compose exec -T web python manage.py shell < coda-src/scripts/diagnosticar_peso_docx.py

Propósito:
- Medir cuánto pesa la plantilla DOCX registrada en la base de datos.
- Medir cuánto pesa la misma plantilla después de abrirla y guardarla con python-docx.
- Generar un reporte real para un tutor específico y medir el tamaño del DOCX resultante.
- Ayudar a detectar plantillas infladas por fuentes embebidas, imágenes pesadas u otros recursos.

Contexto técnico:
Durante el desarrollo de T28 se detectó que una plantilla DOCX podía pasar de
aproximadamente 53 KB a 5.4 MB si era editada y guardada desde LibreOffice.
Al descomprimir ese DOCX se encontraron fuentes embebidas en:

    word/fonts/*.odttf

Por eso este script se conserva como herramienta de diagnóstico para futuras plantillas.

Relación con archivos principales:
- coda-src/Usuarios/models.py
  - Modelo Documento: usado para obtener la plantilla DOCX registrada.
  - Modelo Tutor: usado para seleccionar el tutor de prueba.
- coda-src/Tutorias/models.py
  - Modelo Tutoria: usado para consultar las tutorías del tutor.
- coda-src/Tutorias/constants.py
  - TEMAS: usado para traducir temas de tutoría.
- coda-src/Tutorias/services/docx_reportes.py
  - generar_docx_reporte_tutorias_brindadas(): función real que genera el DOCX final.
"""

from io import BytesIO
from time import perf_counter

import docx

from Usuarios.models import Tutor, Documento
from Tutorias.models import Tutoria
from Tutorias.constants import TEMAS
from Tutorias.services.docx_reportes import generar_docx_reporte_tutorias_brindadas


CONFIG = {
    # Nombre lógico de la plantilla en la tabla Usuarios_documento.
    "PLANTILLA_NOMBRE": "Reporte tutorías atendidas (carta anual)",

    # Tutor usado para generar un documento de prueba.
    # Debe existir en la base de datos actual.
    "TUTOR_MATRICULA": "41935",

    # Datos sintéticos para la generación del reporte.
    "FECHA_EMISION": "2026-04-19T14:44",
    "OFICIO": "DCNI_CODDAA_900_2026",

    # Columnas incluidas en el reporte generado.
    "COLUMNAS": ["Alumno", "Fecha", "Tema", "Notas"],

    # Permite limitar cuántas tutorías se usan en la prueba.
    # None significa usar todas las tutorías del tutor.
    "LIMITE_TUTORIAS": None,
}


def mb(n):
    """Convierte bytes a megabytes."""
    return n / (1024 * 1024)


def medir_docx_bytes(nombre, contenido):
    """
    Imprime el peso de un contenido DOCX en bytes y MB.

    contenido debe ser bytes, por ejemplo:
    - bytes leídos desde Documento.archivo;
    - bytes generados por python-docx;
    - response.content producido por el generador de reportes.
    """
    print(f"{nombre}: {len(contenido)} bytes | {mb(len(contenido)):.2f} MB")


def guardar_documento_en_bytes(documento):
    """
    Guarda un objeto docx.Document en memoria y devuelve sus bytes.

    Esto permite medir cuánto cambia el tamaño de una plantilla
    después de abrirla y volverla a guardar con python-docx,
    sin modificar el archivo original en disco.
    """
    buffer = BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def main():
    # Obtiene la plantilla registrada en la base de datos.
    # Esta es la misma plantilla que se puede seleccionar desde el formulario web.
    plantilla = Documento.objects.get(nombre=CONFIG["PLANTILLA_NOMBRE"])

    # Obtiene el tutor de prueba.
    tutor = Tutor.objects.get(matricula=CONFIG["TUTOR_MATRICULA"])

    # Diccionario de temas requerido por generar_docx_reporte_tutorias_brindadas().
    tema_dict = dict(TEMAS)

    print("=" * 80)
    print("DIAGNÓSTICO DE PESO DOCX")
    print("=" * 80)

    # Lee los bytes originales del archivo asociado al modelo Documento.
    # Esto mide el peso real de la plantilla registrada.
    with plantilla.archivo.open("rb") as f:
        plantilla_bytes = f.read()

    medir_docx_bytes("01 Plantilla original desde Documento.archivo", plantilla_bytes)

    # Abre la plantilla en memoria con python-docx y la vuelve a guardar en memoria.
    # Si el tamaño cambia demasiado, puede indicar que la plantilla contiene elementos
    # que python-docx reescribe o normaliza.
    doc_sin_cambios = docx.Document(BytesIO(plantilla_bytes))
    bytes_sin_cambios = guardar_documento_en_bytes(doc_sin_cambios)
    medir_docx_bytes("02 Plantilla abierta y guardada sin cambios", bytes_sin_cambios)

    # Información útil para localizar el archivo físico de la plantilla.
    print(f"Documento.nombre: {plantilla.nombre}")
    print(f"Documento.archivo.name: {plantilla.archivo.name}")
    print(f"Documento.archivo.path: {plantilla.archivo.path}")

    # Consulta las tutorías del tutor.
    # Esta consulta reproduce el insumo principal que usa el generador de reportes.
    tutorias_qs = (
        Tutoria.objects.filter(tutor=tutor)
        .select_related("alumno", "tutor")
        .order_by("fecha")
    )

    # Permite limitar el número de tutorías para comparar tamaños.
    # Por ejemplo: 0, 5, 20, 100.
    if CONFIG["LIMITE_TUTORIAS"] is not None:
        tutorias_qs = tutorias_qs[:CONFIG["LIMITE_TUTORIAS"]]

    # Banderas equivalentes a las columnas seleccionadas en el formulario web.
    mostrar_col_alumno = "Alumno" in CONFIG["COLUMNAS"]
    mostrar_col_fecha = "Fecha" in CONFIG["COLUMNAS"]
    mostrar_col_hora = "Hora" in CONFIG["COLUMNAS"]
    mostrar_col_tema = "Tema" in CONFIG["COLUMNAS"]
    mostrar_col_notas = "Notas" in CONFIG["COLUMNAS"]

    inicio = perf_counter()

    # Genera un documento completo usando la función productiva real.
    # Esta es la misma función usada por la vista masiva.
    #
    # Nota:
    # Si aparece ValueError: seek of closed file, normalmente significa que
    # plantilla.archivo quedó cerrado después de una lectura previa. En ese caso,
    # puede abrirse nuevamente antes de llamar al generador.
    plantilla.archivo.open("rb")

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

    plantilla.archivo.close()

    tiempo = perf_counter() - inicio

    # Mide el tamaño final del documento generado.
    medir_docx_bytes("03 Documento generado completo", response.content)

    print(f"Tiempo generación: {tiempo:.2f}s")

    # Si tutorias_qs sigue siendo QuerySet, usa count().
    # Si fue rebanado con [:N], puede ser lista o QuerySet limitado según Django.
    print(
        "Tutorías consideradas: "
        f"{tutorias_qs.count() if hasattr(tutorias_qs, 'count') else len(tutorias_qs)}"
    )

    print("=" * 80)


main()