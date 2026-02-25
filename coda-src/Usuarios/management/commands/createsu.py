from django.core.management.base import BaseCommand
from Usuarios.models import Usuario as User
import os

class Command(BaseCommand):

    def handle(self, *args, **options):
        if not User.objects.filter(email="admin@admin.com").exists():
            User.objects.create_superuser("admin@admin.com", os.environ["DJANGO_ADMIN_PASSWORD"])