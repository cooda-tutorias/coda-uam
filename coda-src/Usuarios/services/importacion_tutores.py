"""Normalización y validación previa para importar tutores desde el admin."""

from collections import Counter
from dataclasses import dataclass, field
from numbers import Integral, Real
import re
from typing import Any, Optional

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models.functions import Lower

from Usuarios.constants import CARRERAS, SEXOS
from Usuarios.models import Tutor, Usuario


ENCABEZADOS_IMPORTACION_TUTORES = (
    "matricula",
    "first_name",
    "last_name",
    "second_last_name",
    "email",
    "sexo",
    "coordinacion",
    "cubiculo",
    "password",
)

PATRON_CUBICULO = re.compile(r"^\d{3}[A-Z]?$")


@dataclass(frozen=True)
class ErrorImportacionTutor:
    mensaje: str
    fila: Optional[int] = None
    campo: str = ""
    valor: str = ""


@dataclass
class ResultadoValidacionTutores:
    filas_normalizadas: list[dict[str, Any]] = field(default_factory=list)
    errores: list[ErrorImportacionTutor] = field(default_factory=list)

    @property
    def es_valido(self):
        return not self.errores


def _texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _clave_catalogo(valor):
    return " ".join(_texto(valor).casefold().split())


def _catalogo(opciones):
    catalogo = {}
    for codigo, nombre in opciones:
        if codigo == "":
            continue
        catalogo[_clave_catalogo(codigo)] = codigo
        catalogo[_clave_catalogo(nombre)] = codigo
    return catalogo


SEXOS_NORMALIZADOS = _catalogo(SEXOS)
COORDINACIONES_NORMALIZADAS = _catalogo(CARRERAS)


def _numero_economico(valor):
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, Integral):
        return str(valor)
    if isinstance(valor, Real) and float(valor).is_integer():
        return str(int(valor))
    return _texto(valor)


def normalizar_fila_tutor(fila, numero_fila):
    """Devuelve los valores canónicos sin consultar ni escribir en la base."""
    numero_economico = _numero_economico(fila.get("matricula"))
    sexo_original = _texto(fila.get("sexo"))
    coordinacion_original = _texto(fila.get("coordinacion"))
    password = fila.get("password")
    if password is None:
        password = ""
    elif not isinstance(password, str):
        password = str(password)

    return {
        "numero_fila": numero_fila,
        "matricula": numero_economico,
        "first_name": _texto(fila.get("first_name")),
        "last_name": _texto(fila.get("last_name")),
        "second_last_name": _texto(fila.get("second_last_name")),
        "email": _texto(fila.get("email")).lower(),
        "sexo": SEXOS_NORMALIZADOS.get(_clave_catalogo(sexo_original)),
        "sexo_original": sexo_original,
        "coordinacion": COORDINACIONES_NORMALIZADAS.get(
            _clave_catalogo(coordinacion_original)
        ),
        "coordinacion_original": coordinacion_original,
        "cubiculo": _texto(fila.get("cubiculo")).upper(),
        "password": password,
    }


def _agregar_error(resultado, fila, campo, mensaje, valor=""):
    resultado.errores.append(ErrorImportacionTutor(
        fila=fila,
        campo=campo,
        mensaje=mensaje,
        valor=_texto(valor),
    ))


def _validar_duplicados(resultado, filas, campo):
    valores = [
        str(fila[campo]).casefold()
        for fila in filas
        if fila.get(campo) not in (None, "")
    ]
    repetidos = {valor for valor, cantidad in Counter(valores).items() if cantidad > 1}
    for fila in filas:
        valor = str(fila.get(campo) or "").casefold()
        if valor in repetidos:
            _agregar_error(
                resultado,
                fila["numero_fila"],
                campo,
                "El valor está repetido dentro del archivo.",
                fila.get(campo),
            )


def validar_filas_tutores(filas):
    """Valida todas las filas y consulta conflictos existentes sin guardar."""
    resultado = ResultadoValidacionTutores(filas_normalizadas=filas)

    for fila in filas:
        numero = fila["numero_fila"]
        matricula = fila["matricula"]
        if not matricula:
            _agregar_error(resultado, numero, "matricula", "Es obligatoria.")
        elif not matricula.isdigit() or int(matricula) <= 0:
            _agregar_error(
                resultado, numero, "matricula",
                "Debe ser un número económico entero positivo.", matricula,
            )
        elif len(matricula) > 11:
            _agregar_error(
                resultado, numero, "matricula",
                "No puede exceder 11 dígitos.", matricula,
            )

        for campo in ("first_name", "last_name"):
            if not fila[campo]:
                _agregar_error(resultado, numero, campo, "Es obligatorio.")
            elif len(fila[campo]) > 150:
                _agregar_error(
                    resultado, numero, campo,
                    "No puede exceder 150 caracteres.", fila[campo],
                )
        if len(fila["second_last_name"]) > 150:
            _agregar_error(
                resultado, numero, "second_last_name",
                "No puede exceder 150 caracteres.", fila["second_last_name"],
            )

        if not fila["email"]:
            _agregar_error(resultado, numero, "email", "Es obligatorio.")
        else:
            try:
                validate_email(fila["email"])
            except ValidationError:
                _agregar_error(
                    resultado, numero, "email",
                    "No tiene un formato de correo electrónico válido.", fila["email"],
                )
            if len(fila["email"]) > 254:
                _agregar_error(
                    resultado, numero, "email",
                    "No puede exceder 254 caracteres.", fila["email"],
                )

        if fila["sexo"] is None:
            _agregar_error(
                resultado, numero, "sexo",
                "No corresponde a una opción permitida.", fila["sexo_original"],
            )
        if fila["coordinacion"] is None:
            _agregar_error(
                resultado, numero, "coordinacion",
                "No corresponde a una coordinación permitida.",
                fila["coordinacion_original"],
            )

        if not fila["cubiculo"]:
            _agregar_error(resultado, numero, "cubiculo", "Es obligatorio.")
        elif not PATRON_CUBICULO.fullmatch(fila["cubiculo"]):
            _agregar_error(
                resultado, numero, "cubiculo",
                "Debe tener tres dígitos y, opcionalmente, una letra final.",
                fila["cubiculo"],
            )

        if not fila["password"]:
            _agregar_error(resultado, numero, "password", "Es obligatoria.")
        else:
            usuario_temporal = Tutor(
                matricula=matricula,
                email=fila["email"],
                first_name=fila["first_name"],
                last_name=fila["last_name"],
            )
            try:
                validate_password(fila["password"], user=usuario_temporal)
            except ValidationError as error:
                for mensaje in error.messages:
                    _agregar_error(resultado, numero, "password", mensaje)

    _validar_duplicados(resultado, filas, "matricula")
    _validar_duplicados(resultado, filas, "email")

    matriculas = {fila["matricula"] for fila in filas if fila["matricula"]}
    correos = {fila["email"] for fila in filas if fila["email"]}
    matriculas_existentes = set(
        Usuario.objects.filter(matricula__in=matriculas)
        .values_list("matricula", flat=True)
    )
    correos_existentes = set(
        Usuario.objects.annotate(valor=Lower("email"))
        .filter(valor__in=correos)
        .values_list("valor", flat=True)
    )
    for fila in filas:
        if fila["matricula"] in matriculas_existentes:
            _agregar_error(
                resultado, fila["numero_fila"], "matricula",
                "Ya pertenece a un usuario registrado; esta importación sólo crea tutores.",
                fila["matricula"],
            )
        if fila["email"] in correos_existentes:
            _agregar_error(
                resultado, fila["numero_fila"], "email",
                "Ya pertenece a un usuario registrado.", fila["email"],
            )
    return resultado


def validar_y_normalizar_dataset_tutores(dataset):
    """Valida un Dataset de django-import-export y devuelve todas sus filas."""
    resultado = ResultadoValidacionTutores()
    encabezados = list(dataset.headers or [])
    faltantes = [
        encabezado for encabezado in ENCABEZADOS_IMPORTACION_TUTORES
        if encabezado not in encabezados
    ]
    adicionales = [
        encabezado for encabezado in encabezados
        if encabezado not in ENCABEZADOS_IMPORTACION_TUTORES
    ]
    for encabezado in faltantes:
        _agregar_error(
            resultado, None, encabezado,
            "Falta esta columna obligatoria en el encabezado.",
        )
    for encabezado in adicionales:
        _agregar_error(
            resultado, None, encabezado,
            "La columna no forma parte del formato de importación de tutores.",
        )
    if resultado.errores:
        return resultado

    filas = []
    for indice, fila in enumerate(dataset.dict, start=2):
        normalizada = normalizar_fila_tutor(fila, indice)
        if not any(
            normalizada[campo]
            for campo in ENCABEZADOS_IMPORTACION_TUTORES
        ):
            continue
        filas.append(normalizada)

    if not filas:
        _agregar_error(resultado, None, "", "El archivo no contiene tutores.")
        return resultado
    return validar_filas_tutores(filas)


def aplicar_filas_normalizadas_al_dataset(dataset, filas):
    """Sustituye las celdas por valores canónicos antes de importar."""
    posiciones = {nombre: indice for indice, nombre in enumerate(dataset.headers)}
    for fila in filas:
        indice_fila = fila["numero_fila"] - 2
        valores = list(dataset[indice_fila])
        for campo in ENCABEZADOS_IMPORTACION_TUTORES:
            valores[posiciones[campo]] = fila[campo]
        dataset[indice_fila] = valores


def mensajes_errores_tutores(errores):
    mensajes = []
    for error in errores:
        ubicacion = f"Fila {error.fila}" if error.fila else "Encabezado"
        campo = f", columna {error.campo}" if error.campo else ""
        valor = f" (valor: {error.valor})" if error.valor else ""
        mensajes.append(f"{ubicacion}{campo}: {error.mensaje}{valor}")
    return mensajes
