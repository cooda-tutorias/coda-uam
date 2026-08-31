from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Usuarios", "0006_push_notification_preferences"),
    ]

    operations = [
        migrations.AddField(
            model_name="pushdevice",
            name="installation_id",
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
    ]
