"""
Script de prueba para crear tutorías retroactivas en lote.

Uso recomendado:
1) Haz respaldo de la base de datos antes de ejecutarlo.
2) Ajusta la configuración en la sección CONFIG.
3) Ejecuta primero con DRY_RUN = True.
4) Si la salida se ve correcta, cambia DRY_RUN = False y vuelve a ejecutarlo.

Ejecución sugerida desde la raíz del proyecto:
    docker compose exec -T web python manage.py shell < coda-src/scripts/generar_tutorias_prueba.py

Este script:
- Crea tutorías con fechas pasadas para tutores específicos.
- Marca los registros con un texto identificable para borrarlos fácilmente después.
- Intenta reutilizar una tutoría existente del tutor como plantilla, si existe.
- Si no existe plantilla previa, genera valores seguros por defecto.
"""

from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from Usuarios.models import Tutor, Alumno
from Tutorias.models import Tutoria

try:
    from Tutorias.constants import ACEPTADO
except Exception:
    ACEPTADO = "ACE"


CONFIG = {
    # Ejecuta primero en True para ver qué haría sin guardar nada.
    "DRY_RUN": False,

    # Marca visible para identificar y borrar tutorías de prueba.
    "MARCADOR": "[PRUEBA_REPORTE_2026_MIKA]",

    # Fechas base retroactivas.
    "DIAS_ATRAS_INICIO": 180,
    "SALTO_DIAS": 2,

    # Cantidad de tutorías por tutor.
    # Cambia solo_activos a True cuando quieras probar el filtro del 5to commit.
    "TUTORES": [
        #{"matricula": "30419", "cantidad": 5, "solo_activos": False},   # Antonio
        #{"matricula": "41935", "cantidad": 20, "solo_activos": False},  # Arelí
        {"matricula": "30780", "cantidad": 30, "solo_activos": False},   # Mika
    ],
}


def field_names(model):
    names = []
    for f in model._meta.get_fields():
        if getattr(f, "concrete", False) and not getattr(f, "many_to_many", False):
            names.append(f.name)
    return set(names)


def get_choice_default(model, field_name, fallback=None):
    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return fallback

    choices = getattr(field, "choices", None)
    if choices:
        for value, _label in choices:
            if value not in ("", None):
                return value

    default = getattr(field, "default", None)
    if default not in (None, "", []):
        return default() if callable(default) else default

    return fallback


def get_base_tutoria(tutor):
    return Tutoria.objects.filter(tutor=tutor).order_by("-id").first()


def build_kwargs_from_base(base, tutor, alumno, fecha, marcador):
    data = {}

    if base is not None:
        for key in [
            "tema",
            "estado",
            "asistencia",
            "duracion",
            "firma_documentos_beca",
            "beca_otorgada",
            "asesoria_especializada",
            "observaciones",
            "impacto_tutoria",
            "resultados_tutoria",
        ]:
            if hasattr(base, key):
                data[key] = getattr(base, key)

    # Sobrescrituras seguras
    data["alumno"] = alumno
    data["tutor"] = tutor
    data["fecha"] = fecha
    data["descripcion"] = f"{marcador} Tutoria retroactiva de prueba"

    # Asegurar valores mínimos para que entre al reporte anual
    available = field_names(Tutoria)

    if "estado" in available:
        data["estado"] = ACEPTADO

    if "asistencia" in available:
        data["asistencia"] = True

    if "tema" in available and not data.get("tema"):
        tema_tutor = getattr(tutor, "tema_tutorias", None)
        if tema_tutor:
            data["tema"] = [tema_tutor]
        else:
            try:
                base_field = Tutoria._meta.get_field("tema").base_field
                first_choice = None
                for value, _label in getattr(base_field, "choices", []):
                    if value not in ("", None):
                        first_choice = value
                        break
                data["tema"] = [first_choice] if first_choice else []
            except Exception:
                data["tema"] = []

    if "duracion" in available and not data.get("duracion"):
        data["duracion"] = get_choice_default(Tutoria, "duracion", fallback=30)

    if "firma_documentos_beca" in available and data.get("firma_documentos_beca") is None:
        data["firma_documentos_beca"] = False

    if "beca_otorgada" in available and not data.get("beca_otorgada"):
        data["beca_otorgada"] = ""

    if "asesoria_especializada" in available and data.get("asesoria_especializada") is None:
        data["asesoria_especializada"] = False

    if "observaciones" in available and not data.get("observaciones"):
        data["observaciones"] = f"{marcador} Observaciones de prueba"

    if "impacto_tutoria" in available and not data.get("impacto_tutoria"):
        data["impacto_tutoria"] = 3

    if "resultados_tutoria" in available and not data.get("resultados_tutoria"):
        data["resultados_tutoria"] = f"{marcador} Resultado de prueba"

    return data


@transaction.atomic
def run():
    marcador = CONFIG["MARCADOR"]
    dry_run = CONFIG["DRY_RUN"]
    inicio = timezone.now() - timedelta(days=CONFIG["DIAS_ATRAS_INICIO"])
    salto = CONFIG["SALTO_DIAS"]

    total_creadas = 0

    print("=" * 80)
    print("INICIO SCRIPT TUTORIAS DE PRUEBA")
    print(f"DRY_RUN = {dry_run}")
    print(f"MARCADOR = {marcador}")
    print("=" * 80)

    for bloque_index, tutor_cfg in enumerate(CONFIG["TUTORES"]):
        tutor = Tutor.objects.get(matricula=tutor_cfg["matricula"])
        cantidad = int(tutor_cfg["cantidad"])
        solo_activos = bool(tutor_cfg["solo_activos"])

        alumnos_qs = Alumno.objects.filter(tutor_asignado=tutor).order_by("matricula")
        if solo_activos:
            alumnos_qs = alumnos_qs.filter(estado=1)

        alumnos = list(alumnos_qs)

        if not alumnos:
            print(f"[WARN] Tutor {tutor.matricula}: no hay alumnos disponibles.")
            continue

        base = get_base_tutoria(tutor)
        if base:
            print(f"[INFO] Tutor {tutor.matricula}: se usará tutoria base #{base.pk} como plantilla.")
        else:
            print(f"[INFO] Tutor {tutor.matricula}: no hay tutoria base; se usarán valores por defecto.")

        creadas_tutor = 0

        for i in range(cantidad):
            alumno = alumnos[i % len(alumnos)]
            fecha = inicio + timedelta(days=(bloque_index * 100) + i * salto)

            kwargs = build_kwargs_from_base(
                base=base,
                tutor=tutor,
                alumno=alumno,
                fecha=fecha,
                marcador=marcador,
            )

            if dry_run:
                print(
                    f"[DRY_RUN] Tutor {tutor.matricula} | Alumno {alumno.matricula} | "
                    f"Fecha {fecha:%Y-%m-%d %H:%M} | Estado {kwargs.get('estado')} | "
                    f"Asistencia {kwargs.get('asistencia')}"
                )
            else:
                Tutoria.objects.create(**kwargs)

            creadas_tutor += 1
            total_creadas += 1

        print(
            f"[OK] Tutor {tutor.matricula}: "
            f"{creadas_tutor} tutorías {'simuladas' if dry_run else 'creadas'} "
            f"(solo_activos={solo_activos})"
        )

    if dry_run:
        print("[ROLLBACK] No se guardó nada porque DRY_RUN=True")
        transaction.set_rollback(True)

    print("=" * 80)
    print(f"TOTAL {'SIMULADAS' if dry_run else 'CREADAS'}: {total_creadas}")
    print("=" * 80)


run()
