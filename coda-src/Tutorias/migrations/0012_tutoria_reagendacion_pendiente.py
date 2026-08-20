from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Tutorias', '0011_tutoria_cancelado_por_tutoria_origen_cancelacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='tutoria',
            name='reagendacion_pendiente',
            field=models.BooleanField(default=False),
        ),
    ]
