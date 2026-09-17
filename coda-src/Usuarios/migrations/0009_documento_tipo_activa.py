from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('Usuarios', '0008_alter_alumno_estado')]
    operations = [
        migrations.AddField(model_name='documento', name='tipo', field=models.CharField(blank=True, choices=[('alumno', 'Carta para alumno'), ('tutor', 'Carta para tutor'), ('reporte', 'Reporte de tutorías')], default='', max_length=10)),
        migrations.AddField(model_name='documento', name='activa', field=models.BooleanField(default=False)),
        migrations.AddConstraint(model_name='documento', constraint=models.UniqueConstraint(fields=('tipo',), condition=models.Q(activa=True), name='una_plantilla_activa_por_tipo')),
    ]
