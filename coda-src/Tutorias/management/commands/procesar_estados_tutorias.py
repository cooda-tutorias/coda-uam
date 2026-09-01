from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from Tutorias.constants import (
    ACEPTADO,
    CANCELADO,
    PENDIENTE,
    PROPUESTA,
)
from Tutorias.models import Tutoria
from Tutorias.signals.events import EventoTutoria
from Tutorias.signals.signals_definitions import (
    tutoria_notification_requested,
)


class Command(BaseCommand):
    help = "Procesa los cambios automáticos de estado de las tutorías"

    def handle(self, *args, **options):
        ahora = timezone.now()

        realizadas = self.procesar_realizadas(ahora)
        vencidas = self.procesar_vencidas(ahora)
        propuestas_canceladas = self.procesar_propuestas_canceladas(ahora)
        vencidas_canceladas = self.procesar_vencidas_canceladas(ahora)

        self.stdout.write(
            self.style.SUCCESS(
                "Procesamiento terminado: "
                f"{realizadas} realizadas, "
                f"{vencidas} vencidas, "
                f"{propuestas_canceladas} propuestas canceladas y "
                f"{vencidas_canceladas} solicitudes vencidas canceladas."
            )
        )

    def enviar_notificacion(self, *, event, tutoria, recipient):
        """
        En los eventos automáticos no existe un usuario humano que haya
        realizado la acción. La propia tutoría se usa como actor del sistema.
        """
        tutoria_notification_requested.send(
            sender=self.__class__,
            event=event,
            tutoria=tutoria,
            actor=tutoria,
            recipient=recipient,
        )

    def procesar_realizadas(self, ahora):
        """
        Una tutoría ACE cuya fecha ya pasó se considera realizada.
        No modifica estado porque REALIZADA es un estado dinámico.
        """
        tutorias = Tutoria.objects.filter(
            estado=ACEPTADO,
            fecha__lt=ahora,
            fecha_reporte__isnull=True,
            notificada_realizada_at__isnull=True,
        ).select_related("alumno", "tutor")

        procesadas = 0

        for tutoria in tutorias:
            with transaction.atomic():
                tutoria = (
                    Tutoria.objects
                    .select_for_update()
                    .select_related("alumno", "tutor")
                    .get(pk=tutoria.pk)
                )

                if tutoria.notificada_realizada_at is not None:
                    continue

                if tutoria.estado != ACEPTADO or tutoria.fecha >= ahora:
                    continue

                tutoria.notificada_realizada_at = ahora
                tutoria.save(update_fields=["notificada_realizada_at"])

                self.enviar_notificacion(
                    event=EventoTutoria.TUTORIA_REALIZADA,
                    tutoria=tutoria,
                    recipient=tutoria.alumno,
                )

                procesadas += 1

        return procesadas

    def procesar_vencidas(self, ahora):
        """
        Una solicitud PEN vence cuando pasa la fecha sugerida sin que
        el tutor responda. VEN sigue siendo un estado dinámico.
        """
        tutorias = Tutoria.objects.filter(
            estado=PENDIENTE,
            fecha__lt=ahora,
            notificada_vencida_at__isnull=True,
        ).select_related("alumno", "tutor")

        procesadas = 0

        for tutoria in tutorias:
            with transaction.atomic():
                tutoria = (
                    Tutoria.objects
                    .select_for_update()
                    .select_related("alumno", "tutor")
                    .get(pk=tutoria.pk)
                )

                if tutoria.notificada_vencida_at is not None:
                    continue

                if tutoria.estado != PENDIENTE or tutoria.fecha >= ahora:
                    continue

                tutoria.notificada_vencida_at = ahora
                tutoria.save(update_fields=["notificada_vencida_at"])

                self.enviar_notificacion(
                    event=EventoTutoria.TUTORIA_VENCIDA,
                    tutoria=tutoria,
                    recipient=tutoria.alumno,
                )

                procesadas += 1

        return procesadas

    def procesar_propuestas_canceladas(self, ahora):
        """
        Cancela una propuesta PRO cuando todas las fechas propuestas
        por el tutor ya pasaron y el alumno no eligió ninguna.
        """
        tutorias = Tutoria.objects.filter(
            estado=PROPUESTA,
            notificada_propuesta_cancelada_at__isnull=True,
        ).select_related("alumno", "tutor")

        procesadas = 0

        for tutoria in tutorias:
            fechas = [
                fecha
                for fecha in (
                    tutoria.fecha_propuesta_1,
                    tutoria.fecha_propuesta_2,
                )
                if fecha is not None
            ]

            fecha_limite = max(fechas, default=tutoria.fecha)

            if fecha_limite >= ahora:
                continue

            with transaction.atomic():
                tutoria = (
                    Tutoria.objects
                    .select_for_update()
                    .select_related("alumno", "tutor")
                    .get(pk=tutoria.pk)
                )

                if tutoria.estado != PROPUESTA:
                    continue

                if tutoria.notificada_propuesta_cancelada_at is not None:
                    continue

                fechas = [
                    fecha
                    for fecha in (
                        tutoria.fecha_propuesta_1,
                        tutoria.fecha_propuesta_2,
                    )
                    if fecha is not None
                ]
                fecha_limite = max(fechas, default=tutoria.fecha)

                if fecha_limite >= ahora:
                    continue

                tutoria.estado = CANCELADO
                tutoria.origen_cancelacion = "SISTEMA"
                tutoria.fecha_propuesta_1 = None
                tutoria.fecha_propuesta_2 = None
                tutoria.reagendacion_pendiente = False
                tutoria.notificada_propuesta_cancelada_at = ahora

                tutoria.save(update_fields=[
                    "estado",
                    "origen_cancelacion",
                    "fecha_propuesta_1",
                    "fecha_propuesta_2",
                    "reagendacion_pendiente",
                    "notificada_propuesta_cancelada_at",
                ])

                self.enviar_notificacion(
                    event=EventoTutoria.PROPUESTA_FECHAS_CANCELADA,
                    tutoria=tutoria,
                    recipient=tutoria.alumno,
                )

                procesadas += 1

        return procesadas

    def procesar_vencidas_canceladas(self, ahora):
        """
        Cancela una solicitud PEN que ya venció y agotó el periodo
        adicional para que el tutor respondiera.
        """
        tutorias = Tutoria.objects.filter(
            estado=PENDIENTE,
            fecha__lt=ahora,
            notificada_vencida_cancelada_at__isnull=True,
        ).select_related("alumno", "tutor")

        procesadas = 0

        for tutoria in tutorias:
            if ahora < tutoria.fecha_cancelacion_automatica:
                continue

            with transaction.atomic():
                tutoria = (
                    Tutoria.objects
                    .select_for_update()
                    .select_related("alumno", "tutor")
                    .get(pk=tutoria.pk)
                )

                if tutoria.estado != PENDIENTE:
                    continue

                if tutoria.notificada_vencida_cancelada_at is not None:
                    continue

                if ahora < tutoria.fecha_cancelacion_automatica:
                    continue

                tutoria.estado = CANCELADO
                tutoria.origen_cancelacion = "SISTEMA"
                tutoria.notificada_vencida_cancelada_at = ahora

                tutoria.save(update_fields=[
                    "estado",
                    "origen_cancelacion",
                    "notificada_vencida_cancelada_at",
                ])

                self.enviar_notificacion(
                    event=EventoTutoria.TUTORIA_VENCIDA_CANCELADA,
                    tutoria=tutoria,
                    recipient=tutoria.alumno,
                )

                procesadas += 1

        return procesadas