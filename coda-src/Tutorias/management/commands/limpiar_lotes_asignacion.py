from django.core.management.base import BaseCommand
from Tutorias.services.envios_asignacion import limpiar_lotes_caducados


class Command(BaseCommand):
    help = 'Elimina lotes PDF de asignación preparados hace más de 24 horas.'

    def handle(self, *args, **options):
        total = limpiar_lotes_caducados()
        self.stdout.write(f'Lotes eliminados: {total}')
