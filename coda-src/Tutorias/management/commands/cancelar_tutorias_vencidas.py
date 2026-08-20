from django.core.management.base import BaseCommand
from django.utils import timezone
from Tutorias.models import Tutoria

class Command(BaseCommand):
    help = "Cancela tutorías VENCIDAS que rebasaron su fecha de cancelación automática"

    def handle(self, *args, **options):
        ahora = timezone.now()
        # Filtra las tutorías en estado VENCIDA
        vencidas = Tutoria.objects.filter(estado='VENCIDA')
        canceladas_count = 0

        for tutoria in vencidas:
            # Invoca tu método para validar si ya debe cancelarse
            if ahora >= tutoria.fecha_cancelacion_automatica():
                tutoria.estado = 'CANCELADA'
                tutoria.origen_cancelacion = 'SISTEMA'
                tutoria.motivo_cancelacion = 'Expiración por falta de respuesta del tutor'
                tutoria.save()
                canceladas_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'{canceladas_count} tutorías canceladas automáticamente.')
        )