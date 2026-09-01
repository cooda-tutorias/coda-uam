from django.db import migrations, models


MOTIVOS_CONOCIDOS = {
    "SIN_DISPONIBILIDAD_FECHAS",
    "FUERA_AMBITO",
    "REQUIERE_CANALIZACION",
}
MOTIVO_OTRO = "TUT_RECH_OTRO"


def normalizar_motivos_rechazo(apps, schema_editor):
    Tutoria = apps.get_model("Tutorias", "Tutoria")
    for tutoria in Tutoria.objects.exclude(motivo_rechazo__isnull=True).exclude(
        motivo_rechazo=""
    ).iterator():
        motivo_anterior = tutoria.motivo_rechazo.strip()
        if motivo_anterior in MOTIVOS_CONOCIDOS:
            continue

        tutoria.motivo_rechazo = MOTIVO_OTRO
        tutoria.detalle_motivo_rechazo = (
            tutoria.detalle_motivo_rechazo or motivo_anterior
        )
        tutoria.save(update_fields=["motivo_rechazo", "detalle_motivo_rechazo"])


def revertir_motivos_rechazo(apps, schema_editor):
    Tutoria = apps.get_model("Tutorias", "Tutoria")
    for tutoria in Tutoria.objects.filter(motivo_rechazo=MOTIVO_OTRO).iterator():
        tutoria.motivo_rechazo = tutoria.detalle_motivo_rechazo or "Otro motivo"
        tutoria.save(update_fields=["motivo_rechazo"])


class Migration(migrations.Migration):

    dependencies = [
        ("Tutorias", "0015_alter_tutoria_asistencia"),
    ]

    operations = [
        migrations.AddField(
            model_name="tutoria",
            name="detalle_motivo_rechazo",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.RunPython(
            normalizar_motivos_rechazo,
            revertir_motivos_rechazo,
        ),
        migrations.AlterField(
            model_name="tutoria",
            name="motivo_rechazo",
            field=models.CharField(
                blank=True,
                choices=[
                    (
                        "SIN_DISPONIBILIDAD_FECHAS",
                        "No tengo disponibilidad y no puedo proponer otro horario.",
                    ),
                    (
                        "FUERA_AMBITO",
                        "El tema está fuera de mi ámbito de atención.",
                    ),
                    (
                        "REQUIERE_CANALIZACION",
                        "El tema requiere canalización especializada.",
                    ),
                    ("TUT_RECH_OTRO", "Otro motivo"),
                ],
                max_length=32,
                null=True,
            ),
        ),
    ]
