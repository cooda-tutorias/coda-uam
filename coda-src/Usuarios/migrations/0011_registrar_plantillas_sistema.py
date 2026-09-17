from django.db import migrations


def registrar(apps, schema_editor):
    Documento = apps.get_model('Usuarios', 'Documento')
    documentos = Documento.objects.using(schema_editor.connection.alias)
    for tipo, titulo in [('alumno', 'Carta para alumno'), ('tutor', 'Carta para tutor'), ('reporte', 'Reporte de tutorías')]:
        if documentos.filter(clave_sistema=tipo).exists():
            continue
        nombre = f'Ejemplo institucional — {titulo}'
        base, numero = nombre, 1
        while documentos.filter(nombre=nombre).exists():
            nombre = f'{base} ({numero})'
            numero += 1
        documentos.create(clave_sistema=tipo, tipo=tipo, nombre=nombre, archivo='',
                          activa=not documentos.filter(tipo=tipo, activa=True).exists())


def retirar(apps, schema_editor):
    apps.get_model('Usuarios', 'Documento').objects.using(schema_editor.connection.alias).filter(
        clave_sistema__in=['alumno', 'tutor', 'reporte']).delete()


class Migration(migrations.Migration):
    dependencies = [('Usuarios', '0010_documento_clave_sistema')]
    operations = [migrations.RunPython(registrar, retirar)]
