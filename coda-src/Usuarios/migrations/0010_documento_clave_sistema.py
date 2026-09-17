from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('Usuarios', '0009_documento_tipo_activa')]
    operations = [migrations.AddField(model_name='documento', name='clave_sistema',
                  field=models.CharField(max_length=10, unique=True, null=True, blank=True, editable=False))]
