from django.db import migrations, models


def convertir_motivos_existentes(apps, schema_editor):
    Tutoria = apps.get_model('Tutorias', 'Tutoria')
    codigos_validos = {
        'ALU_RESOL', 'ALU_HORAR', 'ALU_PERSO', 'ALU_OTRO',
        'TUT_HORAR', 'TUT_ACADE', 'TUT_PERSO', 'TUT_OTRO',
    }
    equivalencias = {
        'Ya resolví mi duda o problema': 'ALU_RESOL',
        'Ya resolví la duda o tema por mi cuenta': 'ALU_RESOL',
        'Tuve un contratiempo personal': 'ALU_PERSO',
        'Compromisos personales': 'TUT_PERSO',
        'Imprevisto de salud': 'TUT_PERSO',
    }

    for tutoria in Tutoria.objects.exclude(motivo_cancelacion__isnull=True):
        motivo_anterior = tutoria.motivo_cancelacion.strip()
        if not motivo_anterior or motivo_anterior in codigos_validos:
            continue

        codigo = equivalencias.get(motivo_anterior)
        if codigo is None:
            codigo = (
                'ALU_OTRO'
                if tutoria.origen_cancelacion == 'ALUMNO'
                else 'TUT_OTRO'
            )
            tutoria.detalle_motivo_cancelacion = motivo_anterior[:144]

        tutoria.motivo_cancelacion = codigo
        tutoria.save(update_fields=[
            'motivo_cancelacion',
            'detalle_motivo_cancelacion',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('Tutorias', '0012_tutoria_reagendacion_pendiente'),
    ]

    operations = [
        migrations.AddField(
            model_name='tutoria',
            name='detalle_motivo_cancelacion',
            field=models.CharField(blank=True, max_length=144, null=True),
        ),
        migrations.RunPython(
            convertir_motivos_existentes,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='tutoria',
            name='motivo_cancelacion',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ALU_RESOL', 'Ya resolví la duda o tema por mi cuenta'),
                    ('ALU_HORAR', 'Incompatibilidad de horario o fecha'),
                    ('ALU_PERSO', 'Imprevisto personal o de salud'),
                    ('ALU_OTRO', 'Otro motivo'),
                    ('TUT_HORAR', 'Conflicto de horario o empalme de actividades'),
                    ('TUT_ACADE', 'Compromiso académico o laboral urgente'),
                    ('TUT_PERSO', 'Imprevisto personal o de salud'),
                    ('TUT_OTRO', 'Otro motivo'),
                ],
                max_length=10,
                null=True,
            ),
        ),
    ]
