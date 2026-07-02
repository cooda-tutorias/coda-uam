"""
Genera datos sintéticos para pruebas de reportes masivos de tutorías T28.

Ejecución directa:

    docker compose exec -T web python manage.py shell < coda-src/scripts/generar_db_pruebas_reportes.py

Ejecución con fase específica:

    docker compose exec -T web env FASE_T28=DB_B DRY_RUN_T28=false BORRAR_T28=true \
        python manage.py shell < coda-src/scripts/generar_db_pruebas_reportes.py

Propósito:
- Crear datos sintéticos para probar la función coddaa_26I_28.
- Generar tutores, alumnos y tutorías en cantidades controladas.
- Distribuir los datos entre las cuatro licenciaturas usadas por el sistema.
- Permitir crear escenarios de prueba reproducibles: DB_0, DB_A, DB_B, DB_C y DB_D.
- Permitir exportar posteriormente cada escenario como dump PostgreSQL mediante generar_dumps_t28.sh.

Relación con archivos principales:
- coda-src/Usuarios/models.py
  - Tutor: modelo usado para crear tutores sintéticos.
  - Alumno: modelo usado para crear alumnos sintéticos asignados a tutores.
  - Cordinador: modelo disponible para escenarios donde se quiera crear coordinador-tutor.
- coda-src/Usuarios/constants.py
  - TUTOR, ALUMNO, COORDINADOR: constantes de rol usadas al crear usuarios.
- coda-src/Tutorias/models.py
  - Tutoria: modelo usado para crear tutorías sintéticas.
- coda-src/Tutorias/constants.py
  - ACEPTADO: estado usado para que las tutorías entren al reporte.
  - OTRO: tema genérico usado en tutorías sintéticas.
- coda-src/Tutorias/views.py
  - ReporteTutoriasBrindadasMasivoView.form_valid(): consume estos datos al generar reportes desde la interfaz.
- coda-src/scripts/benchmark_reportes_t28.py
  - Usa los datos generados por este script para medir la generación masiva.
"""

import os
import random
import unicodedata
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

# Modelos definidos en coda-src/Usuarios/models.py.
# Se usan para crear los usuarios sintéticos involucrados en la prueba.
from Usuarios.models import Tutor, Alumno, Cordinador

# Constantes de roles definidas en coda-src/Usuarios/constants.py.
# Permiten guardar usuarios con el rol correcto dentro del ArrayField rol.
from Usuarios.constants import TUTOR, ALUMNO, COORDINADOR

# Modelo de tutoría definido en coda-src/Tutorias/models.py.
from Tutorias.models import Tutoria

# Constantes definidas en coda-src/Tutorias/constants.py.
# ACEPTADO permite que la tutoría represente una tutoría válida para reporte.
# OTRO se usa como tema genérico de prueba.
from Tutorias.constants import ACEPTADO, OTRO


def env_bool(name, default):
    """
    Lee una variable de entorno y la interpreta como booleano.

    Ejemplos aceptados como True:
    - 1
    - true
    - yes
    - y
    - si
    - sí

    Se usa para controlar DRY_RUN_T28 y BORRAR_T28 desde generar_dumps_t28.sh
    sin tener que editar manualmente este archivo.
    """
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "y", "si", "sí")


CONFIG = {
    # Fase de prueba. Puede recibirse desde variable de entorno FASE_T28.
    # Ejemplos: DB_0, DB_A, DB_B, DB_C, DB_D.
    "FASE": os.environ.get("FASE_T28", "DB_B"),

    # Si es True, el script muestra el plan pero no crea registros.
    "DRY_RUN": env_bool("DRY_RUN_T28", True),

    # Si es True, borra datos sintéticos T28 previos antes de crear nuevos.
    "BORRAR_DATOS_PREVIOS": env_bool("BORRAR_T28", False),

    # Marcador usado para identificar datos generados por este script.
    "MARCADOR": "[PRUEBA_T28]",

    # Contraseña temporal para usuarios sintéticos.
    "PASSWORD": "Temporal12345",

    # Rango de fechas usado para distribuir tutorías sintéticas.
    "FECHA_INICIO": "2025-05-26",
    "FECHA_FIN": "2026-06-30",

    # Se dejó desactivado para evitar complejidad de herencia múltitabla
    # entre Cordinador, Tutor y Usuario durante las pruebas masivas.
    "CREAR_COORDINADORES_TUTORES": False,

    # Escenarios de prueba.
    # Cada escenario genera datos en las cuatro licenciaturas.
    "ESCENARIOS": {
        "DB_0": {
            # Prueba mínima o smoke test.
            "tutores_por_lic": {"COM": 2, "MAT": 2, "IB": 2, "BM": 2},
            "alumnos_por_tutor": 2,
            "tutorias_por_alumno": 1,
        },
        "DB_A": {
            # Prueba funcional pequeña.
            "tutores_por_lic": {"COM": 5, "MAT": 5, "IB": 5, "BM": 5},
            "alumnos_por_tutor": 5,
            "tutorias_por_alumno": 2,
        },
        "DB_B": {
            # Carga media.
            "tutores_por_lic": {"COM": 15, "MAT": 15, "IB": 15, "BM": 15},
            "alumnos_por_tutor": 10,
            "tutorias_por_alumno": 2,
        },
        "DB_C": {
            # Carga media-alta.
            "tutores_por_lic": {"COM": 25, "MAT": 25, "IB": 25, "BM": 25},
            "alumnos_por_tutor": 10,
            "tutorias_por_alumno": 4,
        },
        "DB_D": {
            # Escenario cercano a carga real:
            # 150 tutores, 1500 alumnos y 6000 tutorías.
            "tutores_por_lic": {"COM": 38, "MAT": 37, "IB": 38, "BM": 37},
            "alumnos_por_tutor": 10,
            "tutorias_por_alumno": 4,
        },
    },
}


# Catálogo de licenciaturas usado por la función T28.
# Los códigos corresponden a los valores del campo coordinacion/carrera.
LICENCIATURAS = {
    "COM": "Ingeniería en Computación",
    "MAT": "Matemáticas Aplicadas",
    "IB": "Ingeniería Biológica",
    "BM": "Biología Molecular",
}


# Listas base para generar nombres sintéticos.
# No representan personas reales.
NOMBRES_M = [
    "Santiago", "Luis", "Carlos", "Fernando", "Miguel", "José", "Daniel",
    "Jorge", "Andrés", "Emiliano", "Raúl", "Victor", "Diego", "Leonardo",
    "Alan", "Rodrigo", "Manuel", "Iván", "Erick", "Francisco",
]

NOMBRES_F = [
    "María", "Ana", "Karla", "Diana", "Alejandra", "Valeria", "Camila",
    "Fernanda", "Sofía", "Paola", "Mónica", "Andrea", "Daniela",
    "Jimena", "Carolina", "Natalia", "Estefanía", "Nancy", "Romina",
    "Vanessa",
]

APELLIDOS = [
    "López", "García", "Hernández", "Martínez", "González", "Pérez",
    "Rodríguez", "Sánchez", "Ramírez", "Flores", "Torres", "Rivera",
    "Vázquez", "Reyes", "Cruz", "Morales", "Rangel", "Aguilar",
    "Jiménez", "Castillo", "Mendoza", "Cortés", "Nava", "Escobar",
]


def normalizar(texto):
    """
    Normaliza texto para formar correos electrónicos sintéticos.

    Ejemplo:
    - "José López" -> "jose.lopez"

    Quita acentos, pasa a minúsculas y conserva únicamente caracteres seguros.
    """
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower().replace("ñ", "n")
    return "".join(c for c in texto if c.isalnum() or c in [".", "_"])


def nombre_persona(i):
    """
    Genera una persona sintética.

    Usa el índice para alternar sexo de forma determinística:
    - índices pares: F
    - índices impares: M

    El nombre y apellidos se eligen desde listas internas.
    """
    sexo = "F" if i % 2 == 0 else "M"
    nombre = random.choice(NOMBRES_F if sexo == "F" else NOMBRES_M)
    return sexo, nombre, random.choice(APELLIDOS), random.choice(APELLIDOS)


def email_institucional(nombre, apellido, consecutivo):
    """
    Genera un correo institucional sintético.

    El fragmento '.t28' permite identificar y borrar posteriormente
    los usuarios creados por este script.
    """
    return f"{normalizar(nombre)}.{normalizar(apellido)}.t28{consecutivo}@cua.uam.mx"


def email_personal(nombre, apellido, consecutivo):
    """
    Genera un correo personal sintético.

    Se usa el dominio example.test para evitar usar direcciones reales.
    """
    return f"{normalizar(nombre)}.{normalizar(apellido)}.t28{consecutivo}@example.test"


def fecha_tutoria(fecha_inicio, fecha_fin, indice, total):
    """
    Genera una fecha de tutoría distribuida dentro del rango configurado.

    La distribución base es uniforme entre FECHA_INICIO y FECHA_FIN.
    Luego se agrega una pequeña variación aleatoria de días, hora y minuto
    para que las tutorías no queden idénticas.

    Devuelve una fecha timezone-aware porque el proyecto tiene soporte de zona horaria activo.
    """
    dias_totales = (fecha_fin - fecha_inicio).days
    paso = dias_totales / max(total - 1, 1)
    base = fecha_inicio + timedelta(days=int(indice * paso))

    fecha = base + timedelta(days=random.choice([0, 1, 2, 3]))
    fecha = fecha.replace(
        hour=random.choice([9, 10, 11, 12, 13, 15, 16, 17]),
        minute=random.choice([0, 15, 30, 45]),
        second=0,
        microsecond=0,
    )

    return timezone.make_aware(fecha) if timezone.is_naive(fecha) else fecha


def crear_tutor(matricula, coordinacion, index, es_coordinador=False):
    """
    Crea un Tutor sintético.

    Parámetros:
    - matricula: número económico sintético.
    - coordinacion: licenciatura del tutor.
    - index: consecutivo usado para generar nombre, correo y cubículo.
    - es_coordinador: opción para crear Cordinador con rol de tutor.

    Nota:
    Actualmente CREAR_COORDINADORES_TUTORES está en False porque la función T28
    no necesita probar coordinadores. Esto evita problemas de borrado por la
    herencia múltitabla Usuario -> Cordinador/Tutor.
    """
    sexo, nombre, apellido1, apellido2 = nombre_persona(index)

    datos_base = {
        "matricula": matricula,
        "email": email_institucional(nombre, apellido1, index),
        "correo_personal": email_personal(nombre, apellido1, index),
        "first_name": nombre,
        "last_name": apellido1,
        "second_last_name": apellido2,
        "sexo": sexo,
        "cubiculo": 100 + index,
        "coordinacion": coordinacion,
    }

    if es_coordinador:
        obj = Cordinador(
            **datos_base,
            rol=[COORDINADOR],
            es_coordinador=True,
            es_tutor=True,
        )
        obj.set_password(CONFIG["PASSWORD"])
        obj.save()
        return Tutor.objects.get(pk=obj.pk)

    obj = Tutor(
        **datos_base,
        rol=[TUTOR],
        es_coordinador=False,
        es_tutor=True,
        tema_tutorias=OTRO,
    )
    obj.set_password(CONFIG["PASSWORD"])
    obj.save()
    return obj


def crear_alumno(matricula, tutor, carrera, index):
    """
    Crea un Alumno sintético asignado a un tutor.

    El alumno queda:
    - asociado a la licenciatura indicada;
    - asignado al tutor recibido;
    - con estado=1, para que sea considerado activo;
    - con contraseña temporal;
    - marcado con '.t28' en el correo para facilitar limpieza.
    """
    sexo, nombre, apellido1, apellido2 = nombre_persona(index)

    obj = Alumno(
        matricula=matricula,
        email=email_institucional(nombre, apellido1, index),
        correo_personal=email_personal(nombre, apellido1, index),
        first_name=nombre,
        last_name=apellido1,
        second_last_name=apellido2,
        sexo=sexo,
        rol=[ALUMNO],
        carrera=carrera,
        tutor_asignado=tutor,
        estado=1,
        trimestre_ingreso=random.choice(["21-O", "22-O", "23-O", "24-O", "25-P", "25-O"]),
        rfc="Pendiente",
    )
    obj.set_password(CONFIG["PASSWORD"])
    obj.save()
    return obj


def crear_tutoria(alumno, fecha, marcador, index):
    """
    Crea una tutoría sintética válida para reportes.

    La tutoría queda:
    - asociada al alumno;
    - asociada al tutor asignado del alumno;
    - con estado ACEPTADO;
    - con asistencia=True;
    - con estado_alumno_historico=1;
    - marcada en descripcion con [PRUEBA_T28]_<FASE>.

    El marcador permite que benchmark_reportes_t28.py mida sólo las tutorías
    pertenecientes a la fase restaurada.
    """
    return Tutoria.objects.create(
        alumno=alumno,
        tutor=alumno.tutor_asignado,
        tema=[OTRO],
        fecha=fecha,
        descripcion=f"{marcador} Tutoría sintética #{index}",
        estado=ACEPTADO,
        asistencia=True,
        duracion=30,
        firma_documentos_beca=False,
        beca_otorgada="",
        asesoria_especializada=False,
        observaciones=f"{marcador} Observaciones sintéticas",
        impacto_tutoria=3,
        resultados_tutoria=f"{marcador} Resultado sintético",
        estado_alumno_historico=1,
    )


def borrar_datos_previos():
    """
    Borra datos sintéticos T28 creados por ejecuciones anteriores.

    Orden de borrado:
    1. Tutorías.
    2. Alumnos.
    3. Tutores.
    4. Coordinadores.

    Se identifican los datos por:
    - descripcion con [PRUEBA_T28] en tutorías;
    - email que contiene '.t28' en usuarios sintéticos.
    """
    print("[INFO] Borrando datos sintéticos T28 previos...")

    tutorias = Tutoria.objects.filter(descripcion__contains=CONFIG["MARCADOR"])
    total_tutorias = tutorias.count()
    tutorias.delete()

    alumnos = Alumno.objects.filter(email__contains=".t28")
    total_alumnos = alumnos.count()
    alumnos.delete()

    tutores = Tutor.objects.filter(email__contains=".t28")
    total_tutores = tutores.count()
    tutores.delete()

    coordinadores = Cordinador.objects.filter(email__contains=".t28")
    total_coord = coordinadores.count()
    coordinadores.delete()

    print(f"[OK] Tutorías borradas: {total_tutorias}")
    print(f"[OK] Alumnos borrados: {total_alumnos}")
    print(f"[OK] Tutores borrados: {total_tutores}")
    print(f"[OK] Coordinadores borrados: {total_coord}")


@transaction.atomic
def run():
    """
    Ejecuta la generación de datos para la fase configurada.

    Flujo:
    1. Valida la fase.
    2. Calcula totales planeados.
    3. Si DRY_RUN=True, sólo imprime el plan.
    4. Si BORRAR_DATOS_PREVIOS=True, limpia datos sintéticos anteriores.
    5. Crea tutores por licenciatura.
    6. Crea alumnos asignados equitativamente a cada tutor.
    7. Crea tutorías distribuidas dentro del rango de fechas configurado.
    8. Imprime resumen final.

    El decorador @transaction.atomic permite que la ejecución se trate como
    una transacción atómica: si ocurre un error no se guardan datos parciales.
    """
    fase = CONFIG["FASE"]

    if fase not in CONFIG["ESCENARIOS"]:
        raise SystemExit(f"[ERROR] Fase inválida: {fase}")

    # Hace que la generación aleatoria sea reproducible por fase.
    # DB_A siempre generará el mismo conjunto de nombres/fechas mientras no cambie el código.
    random.seed(fase)

    dry_run = CONFIG["DRY_RUN"]
    escenario = CONFIG["ESCENARIOS"][fase]
    marcador = f'{CONFIG["MARCADOR"]}_{fase}'

    fecha_inicio = datetime.strptime(CONFIG["FECHA_INICIO"], "%Y-%m-%d")
    fecha_fin = datetime.strptime(CONFIG["FECHA_FIN"], "%Y-%m-%d")

    total_tutores_plan = sum(escenario["tutores_por_lic"].values())
    total_alumnos_plan = total_tutores_plan * escenario["alumnos_por_tutor"]
    total_tutorias_plan = total_alumnos_plan * escenario["tutorias_por_alumno"]

    print("=" * 90)
    print("GENERADOR DE BASE DE PRUEBAS PARA REPORTES MASIVOS T28")
    print("=" * 90)
    print(f"FASE: {fase}")
    print(f"DRY_RUN: {dry_run}")
    print(f"BORRAR_DATOS_PREVIOS: {CONFIG['BORRAR_DATOS_PREVIOS']}")
    print(f"MARCADOR: {marcador}")
    print(f"Tutores planeados: {total_tutores_plan}")
    print(f"Alumnos planeados: {total_alumnos_plan}")
    print(f"Tutorías planeadas: {total_tutorias_plan}")
    print("=" * 90)

    if dry_run:
        print("[DRY_RUN] No se crearán registros.")
        print("=" * 90)
        return

    if CONFIG["BORRAR_DATOS_PREVIOS"]:
        borrar_datos_previos()

    tutores_creados = []
    alumnos_creados = []
    tutorias_creadas = 0

    tutor_index = 1
    alumno_index = 1
    tutoria_index = 1

    # Recorre las licenciaturas de la fase actual.
    for coordinacion, cantidad_tutores in escenario["tutores_por_lic"].items():
        print(f"[INFO] {coordinacion} - {LICENCIATURAS[coordinacion]}")

        # 1. Crear tutores de la licenciatura.
        tutores_lic = []
        for i in range(cantidad_tutores):
            tutor = crear_tutor(
                matricula=str(90000 + tutor_index),
                coordinacion=coordinacion,
                index=tutor_index,
                es_coordinador=CONFIG["CREAR_COORDINADORES_TUTORES"] and i == 0,
            )
            tutores_lic.append(tutor)
            tutores_creados.append(tutor)
            tutor_index += 1

        print(f"[OK] Tutores creados {coordinacion}: {len(tutores_lic)}")

        # 2. Crear alumnos y asignarlos equitativamente a los tutores.
        alumnos_lic = []
        for tutor in tutores_lic:
            for _ in range(escenario["alumnos_por_tutor"]):
                alumno = crear_alumno(
                    matricula=str(8000000000 + alumno_index),
                    tutor=tutor,
                    carrera=coordinacion,
                    index=alumno_index,
                )
                alumnos_lic.append(alumno)
                alumnos_creados.append(alumno)
                alumno_index += 1

        print(f"[OK] Alumnos creados {coordinacion}: {len(alumnos_lic)}")

        # 3. Crear tutorías para cada alumno.
        total_tutorias_lic = len(alumnos_lic) * escenario["tutorias_por_alumno"]

        for alumno in alumnos_lic:
            for j in range(escenario["tutorias_por_alumno"]):
                fecha = fecha_tutoria(
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    indice=j,
                    total=escenario["tutorias_por_alumno"],
                )

                crear_tutoria(
                    alumno=alumno,
                    fecha=fecha,
                    marcador=marcador,
                    index=tutoria_index,
                )

                tutorias_creadas += 1
                tutoria_index += 1

                # Progreso periódico para saber que el script sigue trabajando.
                if tutorias_creadas % 500 == 0:
                    print(f"[PROGRESO] Tutorías creadas: {tutorias_creadas}/{total_tutorias_plan}")

        print(f"[OK] Tutorías creadas {coordinacion}: {total_tutorias_lic}")

    print("=" * 90)
    print("RESUMEN FINAL")
    print("=" * 90)
    print(f"Tutores creados: {len(tutores_creados)}")
    print(f"Alumnos creados: {len(alumnos_creados)}")
    print(f"Tutorías creadas: {tutorias_creadas}")
    print("=" * 90)


run()