from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Tutorias', '0002_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistorialCambioTutoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('correo_editor', models.EmailField(max_length=254)),
                ('cambios_realizados', models.TextField()),
                ('fecha_cambio', models.DateTimeField(auto_now_add=True)),
                ('tutoria', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historial_cambios', to='Tutorias.tutoria')),
            ],
            options={
                'ordering': ['-fecha_cambio'],
            },
        ),
    ]
