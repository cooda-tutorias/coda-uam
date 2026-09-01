"""Lectura, validación e importación transaccional de alumnos."""

from collections import defaultdict
from dataclasses import dataclass, field
from numbers import Integral
from pathlib import Path
import re
from typing import Any, Optional
import unicodedata

import pandas as pd
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models.functions import Lower

from Usuarios.constants import ALUMNO, CARRERAS, ESTADOS_ALUMNO, SEXOS
from Usuarios.models import Alumno, Tutor, Usuario


ENCABEZADOS_IMPORTACION = (
    "Plan de estudios",
    "Matrícula",
    "Apellido Paterno",
    "Apellido Materno",
    "Nombres",
    "Sexo",
    "Estado académico",
    "Correo institucional",
    "Correo alterno",
    "Núm. económico tutor",
)
ENCABEZADOS_OPCIONALES = ("Nombre del tutor",)

TRIMESTRES_INGRESO = {
    "1": "I",
    "2": "P",
    "3": "O",
}

ESTADOS_VALIDOS = {codigo for codigo, _ in ESTADOS_ALUMNO if codigo != ""}
DOMINIOS_CON_ERROR_CONOCIDO = {
    "gmai.com": "gmail.com",
}
PARTICULAS_NOMBRE = {"de", "del", "la", "las", "los", "y"}


@dataclass(frozen=True)
class ErrorImportacionAlumno:
    mensaje: str
    fila: Optional[int] = None
    columna: str = ""
    valor: str = ""


@dataclass
class ResultadoValidacionAlumnos:
    filas_validas: list[dict[str, Any]] = field(default_factory=list)
    errores: list[ErrorImportacionAlumno] = field(default_factory=list)
    advertencias: list[ErrorImportacionAlumno] = field(default_factory=list)
    encabezados_previsualizacion: list[str] = field(default_factory=list)
    filas_previsualizacion: list[list[str]] = field(default_factory=list)

    @property
    def es_valido(self) -> bool:
        return not self.errores

    @property
    def total_filas(self) -> int:
        return len(self.filas_validas)


class ErrorImportacionAlumnos(Exception):
    """Indica que el lote no pudo importarse y fue revertido por completo."""


def _texto_limpio(valor: Any) -> str:
    """Convierte un valor de celda a texto sin representar vacíos como NaN."""
    if valor is None or pd.isna(valor):
        return ""
    return str(valor).strip()


def _clave_comparacion(valor: Any) -> str:
    """Normaliza espacios y mayúsculas únicamente para comparar catálogos."""
    return " ".join(_texto_limpio(valor).casefold().split())


def _identificador_limpio(valor: Any) -> str:
    """Evita el sufijo .0 que Excel agrega a enteros leídos como flotantes."""
    if valor is None or pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _palabras_nombre(valor: Any) -> set[str]:
    """Obtiene palabras comparables sin acentos, signos ni partículas."""
    texto = unicodedata.normalize("NFKD", _texto_limpio(valor).casefold())
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    palabras = re.findall(r"[a-z0-9]+", texto)
    return {palabra for palabra in palabras if palabra not in PARTICULAS_NOMBRE}


def _coincidencia_nombre(nombre_referencia: str, nombre_registrado: str) -> float:
    referencia = _palabras_nombre(nombre_referencia)
    if not referencia:
        return 1.0
    registradas = _palabras_nombre(nombre_registrado)
    return len(referencia & registradas) / len(referencia)


def _catalogo_normalizado(opciones) -> dict[str, tuple[Any, str]]:
    return {
        _clave_comparacion(etiqueta): (codigo, etiqueta)
        for codigo, etiqueta in opciones
        if codigo != ""
    }


CARRERAS_NORMALIZADAS = _catalogo_normalizado(CARRERAS)
SEXOS_NORMALIZADOS = _catalogo_normalizado(SEXOS)


def obtener_trimestre_ingreso(matricula: str) -> str:
    """Deriva ``AA-T`` de una matrícula válida de 9 o 10 dígitos.

    La validación completa de longitud y contenido corresponde a la fase 2.
    Si el valor todavía no permite derivar el trimestre, se devuelve una cadena
    vacía para que esa fase pueda reportar el error en la fila correspondiente.
    """
    if (
        len(matricula) not in {9, 10}
        or not matricula.isdigit()
        or matricula[3] not in TRIMESTRES_INGRESO
    ):
        return ""
    return f"{matricula[1:3]}-{TRIMESTRES_INGRESO[matricula[3]]}"


def normalizar_fila_alumno(fila: dict[str, Any], numero_fila: int) -> dict[str, Any]:
    """Transforma una fila externa a los nombres y códigos internos esperados."""
    carrera_original = _texto_limpio(fila.get("Plan de estudios"))
    sexo_original = _texto_limpio(fila.get("Sexo"))
    carrera = CARRERAS_NORMALIZADAS.get(_clave_comparacion(carrera_original))
    sexo = SEXOS_NORMALIZADOS.get(_clave_comparacion(sexo_original))

    matricula_original = fila.get("Matrícula")
    matricula = _identificador_limpio(matricula_original)

    return {
        "numero_fila": numero_fila,
        "matricula": matricula,
        "matricula_original_es_texto": isinstance(matricula_original, str),
        "matricula_original_es_entero": (
            isinstance(matricula_original, Integral)
            and not isinstance(matricula_original, bool)
        ),
        "email": _texto_limpio(fila.get("Correo institucional")).lower(),
        "correo_personal": _texto_limpio(fila.get("Correo alterno")).lower(),
        "last_name": _texto_limpio(fila.get("Apellido Paterno")),
        "second_last_name": _texto_limpio(fila.get("Apellido Materno")),
        "first_name": _texto_limpio(fila.get("Nombres")),
        "carrera": carrera[0] if carrera else None,
        "carrera_nombre": carrera[1] if carrera else carrera_original,
        "tutor_matricula": _identificador_limpio(
            fila.get("Núm. económico tutor"),
        ),
        "tutor_nombre_referencia": _texto_limpio(fila.get("Nombre del tutor")),
        "estado": _identificador_limpio(fila.get("Estado académico")),
        "sexo": sexo[0] if sexo else None,
        "sexo_nombre": sexo[1] if sexo else sexo_original,
        "trimestre_ingreso": obtener_trimestre_ingreso(matricula),
    }


def leer_archivo_alumnos(archivo) -> pd.DataFrame:
    """Lee un CSV o libro de Excel sin realizar escrituras ni validaciones."""
    extension = Path(archivo.name).suffix.casefold()
    if extension in {".xls", ".xlsx"}:
        return pd.read_excel(archivo, dtype=object)
    if extension == ".csv":
        return pd.read_csv(archivo, dtype=object, keep_default_na=False)
    raise ValueError("El archivo debe tener formato CSV, XLS o XLSX.")


def leer_y_normalizar_alumnos(archivo) -> list[dict[str, Any]]:
    """Lee el archivo y devuelve filas normalizadas sin consultar la base."""
    dataframe = leer_archivo_alumnos(archivo)
    dataframe.columns = [_texto_limpio(columna) for columna in dataframe.columns]
    return [
        normalizar_fila_alumno(fila.to_dict(), numero_fila=indice + 2)
        for indice, (_, fila) in enumerate(dataframe.iterrows())
    ]


def _agregar_error(resultado, fila, columna, mensaje, valor=""):
    resultado.errores.append(ErrorImportacionAlumno(
        fila=fila,
        columna=columna,
        valor=_texto_limpio(valor),
        mensaje=mensaje,
    ))


def _es_fila_vacia(fila: dict[str, Any]) -> bool:
    campos = (
        "matricula", "email", "correo_personal", "last_name",
        "second_last_name", "first_name", "carrera_nombre",
        "tutor_matricula", "estado", "sexo_nombre",
    )
    return not any(_texto_limpio(fila.get(campo)) for campo in campos)


def _validar_correo(resultado, fila, campo, columna, requerido, longitud_maxima):
    correo = fila[campo]
    if not correo:
        if requerido:
            _agregar_error(resultado, fila["numero_fila"], columna,
                           "Este campo es obligatorio.")
        return

    if len(correo) > longitud_maxima:
        _agregar_error(
            resultado, fila["numero_fila"], columna,
            f"No puede exceder {longitud_maxima} caracteres.", correo,
        )
        return

    try:
        validate_email(correo)
    except ValidationError:
        _agregar_error(resultado, fila["numero_fila"], columna,
                       "No tiene un formato de correo electrónico válido.", correo)
        return

    dominio = correo.rsplit("@", 1)[1].casefold()
    if dominio in DOMINIOS_CON_ERROR_CONOCIDO:
        sugerencia = DOMINIOS_CON_ERROR_CONOCIDO[dominio]
        _agregar_error(
            resultado, fila["numero_fila"], columna,
            f"El dominio parece estar mal escrito; revise si quiso usar {sugerencia}.",
            correo,
        )


def _errores_por_duplicados(resultado, filas, campo, columna):
    apariciones = defaultdict(list)
    for fila in filas:
        valor = fila.get(campo)
        if valor not in (None, ""):
            apariciones[str(valor).casefold()].append(fila["numero_fila"])

    for valor, numeros in apariciones.items():
        if len(numeros) < 2:
            continue
        listado = ", ".join(str(numero) for numero in numeros)
        for numero in numeros:
            _agregar_error(
                resultado, numero, columna,
                f"El valor está repetido en las filas {listado}.", valor,
            )


def validar_filas_alumnos(filas: list[dict[str, Any]]) -> ResultadoValidacionAlumnos:
    """Valida todas las filas normalizadas mediante consultas de solo lectura."""
    resultado = ResultadoValidacionAlumnos()
    filas_con_datos = []

    for fila_original in filas:
        fila = fila_original.copy()
        numero = fila["numero_fila"]
        if _es_fila_vacia(fila):
            resultado.advertencias.append(ErrorImportacionAlumno(
                fila=numero,
                mensaje="La fila está vacía y se omitió.",
            ))
            continue

        filas_con_datos.append(fila)
        matricula = fila["matricula"]
        if not matricula:
            _agregar_error(resultado, numero, "Matrícula", "Este campo es obligatorio.")
        else:
            if not (
                fila["matricula_original_es_texto"]
                or fila["matricula_original_es_entero"]
            ):
                _agregar_error(
                    resultado, numero, "Matrícula",
                    "Debe estar guardada como texto o como un número entero.", matricula,
                )
            if not matricula.isdigit() or len(matricula) not in {9, 10}:
                _agregar_error(
                    resultado, numero, "Matrícula",
                    "Debe contener exactamente 9 o 10 dígitos.", matricula,
                )
            elif not fila["trimestre_ingreso"]:
                _agregar_error(
                    resultado, numero, "Matrícula",
                    "El cuarto dígito debe ser 1, 2 o 3 para obtener el trimestre.", matricula,
                )

        _validar_correo(
            resultado, fila, "email", "Correo institucional", True, 254,
        )
        _validar_correo(
            resultado, fila, "correo_personal", "Correo alterno", False, 50,
        )

        for campo, columna in (
            ("last_name", "Apellido Paterno"),
            ("first_name", "Nombres"),
        ):
            if not fila[campo]:
                _agregar_error(resultado, numero, columna, "Este campo es obligatorio.")
            elif len(fila[campo]) > 150:
                _agregar_error(resultado, numero, columna,
                               "No puede exceder 150 caracteres.", fila[campo])
        if len(fila["second_last_name"]) > 150:
            _agregar_error(resultado, numero, "Apellido Materno",
                           "No puede exceder 150 caracteres.", fila["second_last_name"])

        if fila["carrera"] is None:
            _agregar_error(
                resultado, numero, "Plan de estudios",
                "No corresponde a uno de los planes de estudios permitidos.",
                fila["carrera_nombre"],
            )
        if fila["sexo"] is None:
            _agregar_error(
                resultado, numero, "Sexo",
                "No corresponde a una de las opciones permitidas.", fila["sexo_nombre"],
            )

        tutor = fila["tutor_matricula"]
        if not tutor:
            _agregar_error(resultado, numero, "Núm. económico tutor",
                           "Este campo es obligatorio.")
        elif not tutor.isdigit() or int(tutor) <= 0:
            _agregar_error(resultado, numero, "Núm. económico tutor",
                           "Debe ser un entero positivo.", tutor)

        estado_texto = fila["estado"]
        try:
            estado = int(estado_texto)
        except (TypeError, ValueError):
            estado = None
        if estado is None or str(estado) != estado_texto or estado not in ESTADOS_VALIDOS:
            _agregar_error(resultado, numero, "Estado académico",
                           "Debe ser uno de los estados permitidos (1 a 19).", estado_texto)
        else:
            fila["estado"] = estado

    _errores_por_duplicados(resultado, filas_con_datos, "matricula", "Matrícula")
    _errores_por_duplicados(resultado, filas_con_datos, "email", "Correo institucional")
    # Los vacíos se excluyen expresamente: el correo personal es opcional.
    _errores_por_duplicados(
        resultado, filas_con_datos, "correo_personal", "Correo alterno"
    )

    matriculas = {fila["matricula"] for fila in filas_con_datos if fila["matricula"]}
    correos = {fila["email"] for fila in filas_con_datos if fila["email"]}
    personales = {
        fila["correo_personal"] for fila in filas_con_datos
        if fila["correo_personal"]
    }
    tutores_solicitados = {
        fila["tutor_matricula"] for fila in filas_con_datos
        if fila["tutor_matricula"].isdigit()
    }

    matriculas_existentes = set(
        Usuario.objects.filter(matricula__in=matriculas)
        .values_list("matricula", flat=True)
    )
    correos_existentes = set(
        Usuario.objects.annotate(valor=Lower("email"))
        .filter(valor__in=correos).values_list("valor", flat=True)
    )
    personales_existentes = set(
        Usuario.objects.annotate(valor=Lower("correo_personal"))
        .filter(valor__in=personales).values_list("valor", flat=True)
    )
    tutores_por_matricula = {
        tutor.matricula: tutor
        for tutor in Tutor.objects.filter(matricula__in=tutores_solicitados)
    }

    for fila in filas_con_datos:
        numero = fila["numero_fila"]
        if fila["matricula"] in matriculas_existentes:
            _agregar_error(resultado, numero, "Matrícula",
                           "Ya pertenece a un usuario registrado.", fila["matricula"])
        if fila["email"] in correos_existentes:
            _agregar_error(resultado, numero, "Correo institucional",
                           "Ya pertenece a un usuario registrado.", fila["email"])
        if fila["correo_personal"] and fila["correo_personal"] in personales_existentes:
            _agregar_error(resultado, numero, "Correo alterno",
                           "Ya pertenece a un usuario registrado.", fila["correo_personal"])
        tutor = fila["tutor_matricula"]
        tutor_registrado = tutores_por_matricula.get(tutor)
        if tutor.isdigit() and tutor_registrado is None:
            _agregar_error(resultado, numero, "Núm. económico tutor",
                           "No corresponde a un tutor registrado.", tutor)
        elif tutor_registrado is not None and fila["tutor_nombre_referencia"]:
            nombre_registrado = tutor_registrado.nombre_completo
            coincidencia = _coincidencia_nombre(
                fila["tutor_nombre_referencia"], nombre_registrado,
            )
            if coincidencia < 0.60:
                resultado.advertencias.append(ErrorImportacionAlumno(
                    fila=numero,
                    columna="Nombre del tutor",
                    valor=fila["tutor_nombre_referencia"],
                    mensaje=(
                        f"El nombre «{fila['tutor_nombre_referencia']}» parece no "
                        f"corresponder al tutor con número "
                        f"económico {tutor}, registrado como "
                        f"«{nombre_registrado or 'Sin nombre registrado'}». "
                        "Verifique ambos datos."
                    ),
                ))

    resultado.filas_validas = filas_con_datos
    return resultado


def validar_archivo_alumnos(archivo) -> ResultadoValidacionAlumnos:
    """Lee y valida un archivo completo sin realizar ninguna escritura."""
    dataframe = leer_archivo_alumnos(archivo)
    dataframe.columns = [_texto_limpio(columna) for columna in dataframe.columns]
    resultado = ResultadoValidacionAlumnos(
        encabezados_previsualizacion=list(dataframe.columns),
        filas_previsualizacion=[
            [_texto_limpio(valor) for valor in fila]
            for fila in dataframe.itertuples(index=False, name=None)
        ],
    )

    faltantes = [
        encabezado for encabezado in ENCABEZADOS_IMPORTACION
        if encabezado not in dataframe.columns
    ]
    for encabezado in faltantes:
        _agregar_error(resultado, None, encabezado,
                       "Falta esta columna obligatoria en el encabezado.")
    if faltantes:
        return resultado

    adicionales = [
        columna for columna in dataframe.columns
        if columna not in ENCABEZADOS_IMPORTACION + ENCABEZADOS_OPCIONALES
    ]
    for columna in adicionales:
        resultado.advertencias.append(ErrorImportacionAlumno(
            columna=columna,
            mensaje="La columna no se utiliza y será ignorada.",
        ))

    filas = [
        normalizar_fila_alumno(fila.to_dict(), numero_fila=indice + 2)
        for indice, (_, fila) in enumerate(dataframe.iterrows())
    ]
    if not filas:
        _agregar_error(resultado, None, "", "El archivo no contiene filas de alumnos.")
        return resultado

    validacion = validar_filas_alumnos(filas)
    validacion.advertencias = resultado.advertencias + validacion.advertencias
    validacion.encabezados_previsualizacion = resultado.encabezados_previsualizacion
    validacion.filas_previsualizacion = resultado.filas_previsualizacion
    if not validacion.filas_validas:
        _agregar_error(
            validacion, None, "", "El archivo no contiene filas de alumnos con datos."
        )
    return validacion


@transaction.atomic
def importar_alumnos_validados(filas: list[dict[str, Any]]) -> int:
    """Crea un lote previamente validado o revierte todas sus filas.

    La matrícula se conserva como contraseña inicial, igual que en el
    importador anterior. ``create_user`` aplica el hash antes de guardarla.
    """
    tutores_solicitados = {fila["tutor_matricula"] for fila in filas}
    tutores_por_matricula = {
        tutor.matricula: tutor
        for tutor in Tutor.objects.select_for_update().filter(
            matricula__in=tutores_solicitados,
        )
    }
    tutores_faltantes = tutores_solicitados - set(tutores_por_matricula)
    if tutores_faltantes:
        faltantes = ", ".join(sorted(tutores_faltantes))
        raise ErrorImportacionAlumnos(
            f"Ya no se encontraron los tutores con número económico: {faltantes}."
        )

    for fila in filas:
        Alumno.objects.create_user(
            matricula=fila["matricula"],
            email=fila["email"],
            correo_personal=fila["correo_personal"] or None,
            first_name=fila["first_name"],
            last_name=fila["last_name"],
            second_last_name=fila["second_last_name"] or None,
            password=fila["matricula"],
            rol=[ALUMNO],
            sexo=fila["sexo"],
            carrera=fila["carrera"],
            estado=fila["estado"],
            tutor_asignado=tutores_por_matricula[fila["tutor_matricula"]],
            trimestre_ingreso=fila["trimestre_ingreso"],
            rfc=None,
        )

    return len(filas)
