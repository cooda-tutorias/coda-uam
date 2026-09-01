from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_subscriptions(apps, schema_editor):
    Usuario = apps.get_model("Usuarios", "Usuario")
    PushDevice = apps.get_model("Usuarios", "PushDevice")
    PushInformation = apps.get_model("webpush", "PushInformation")

    users_with_push = set()
    for push_info in PushInformation.objects.select_related("subscription").order_by("id"):
        if not push_info.user_id:
            continue
        subscription = push_info.subscription
        PushDevice.objects.update_or_create(
            subscription_id=subscription.pk,
            defaults={
                "user_id": push_info.user_id,
                "status": "ACTIVE",
                "browser": subscription.browser or "",
                "device_name": subscription.browser or "Dispositivo registrado",
            },
        )
        users_with_push.add(push_info.user_id)

    if users_with_push:
        Usuario.objects.filter(pk__in=users_with_push).update(
            notificaciones_habilitadas=True,
        )

    # Un endpoint representa un navegador concreto y no debe pertenecer a
    # varias cuentas al mismo tiempo. En registros duplicados prevalece la
    # asociación más reciente procesada arriba.
    for device in PushDevice.objects.all():
        PushInformation.objects.filter(
            subscription_id=device.subscription_id,
        ).exclude(user_id=device.user_id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("Usuarios", "0005_horariotutor"),
        ("webpush", "0005_auto_20230614_1529"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="notificaciones_habilitadas",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="PushDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("ACTIVE", "Activo"), ("PAUSED", "Pausado")], default="ACTIVE", max_length=10)),
                ("browser", models.CharField(blank=True, max_length=100)),
                ("operating_system", models.CharField(blank=True, max_length=100)),
                ("device_name", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("subscription", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="device", to="webpush.subscriptioninfo")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_devices", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-last_seen_at",)},
        ),
        migrations.RunPython(
            migrate_existing_subscriptions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
