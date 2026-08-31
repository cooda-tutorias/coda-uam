from django.db import models
from django.utils.http import urlencode
from datetime import timedelta
from django.contrib.postgres.fields import ArrayField
from Usuarios.models import Alumno, Tutor, Usuario
from Usuarios.constants import ESTADOS_ALUMNO
from .constants import ( 
    TEMAS, SERVICIO, ESTADO, DURACION_ASESORIA, ORIGEN_CANCELACION, 
    DIAS_TOLERANCIA_TUTOR, MOTIVOS_CANCELACION, MOTIVOS_RECHAZO_TUTOR,
    MOTIVO_RECHAZO_OTRO,
)
from django.utils import timezone

# Incluir todos los estados de una tutoría.
from .constants import (
    PENDIENTE, PROPUESTA, VENCIDA, ACEPTADO,
    REALIZADA, REPORTADA, RECHAZADO, CANCELADO
)

# Create your models here.
class Tutoria(models.Model):

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    tutor = models.ForeignKey(Tutor, on_delete=models.CASCADE)
    # tema = models.CharField(SERVICIO, max_length=4, choices=TEMAS, default=SERVICIO)
    # Se cambia el campo para que sea una lista
    tema = ArrayField(models.CharField(SERVICIO, max_length=4, choices=TEMAS, default=SERVICIO))

    descripcion = models.CharField(max_length=255, blank=True, null=True)

    # Fecha sugerida o agendada para realizar la tutoría.
    fecha = models.DateTimeField()

    # Estados en los que puede transitar una tutoría en su periodo de vida.
    estado = models.CharField(PENDIENTE, max_length=4, choices=ESTADO, default=PENDIENTE)

    # Fecha en la que el alumno hizo la solicitud de la tutoría.
    fecha_solicitud = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de solicitud"
    )

    # Fecha en la que el tutor llena el reporte de seguimiento de la tutoría.
    fecha_reporte = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de llenado del reporte"
    )

    # Propuestas alternativas cuando el tutor acepta la tutoría, pero propone otras fechas.
    fecha_propuesta_1 = models.DateTimeField(null=True, blank=True)
    fecha_propuesta_2 = models.DateTimeField(null=True, blank=True)

    # Distingue una propuesta para mover una tutoría ya agendada de una
    # propuesta hecha al atender una solicitud nueva.
    reagendacion_pendiente = models.BooleanField(default=False)

    # Atributo para registrar el motivo de rechazo de la tutoría.
    motivo_rechazo = models.CharField(
        max_length=32,
        choices=MOTIVOS_RECHAZO_TUTOR,
        blank=True,
        null=True,
    )

    detalle_motivo_rechazo = models.CharField(
        max_length=500,
        blank=True,
        null=True,
    )

    # Datos del usuario que canceló la tutoría.
    cancelado_por = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='tutorias_canceladas'
    )

    # Origen de la cancelación de la tutoría: alumno, tutor, sistema.
    origen_cancelacion = models.CharField(
        max_length=15,
        choices= ORIGEN_CANCELACION,
        null=True,
        blank=True
    )

    # Motivo proporcionado por el tutor o alumno al cancelar una tutoría solicitada/agendada.
    motivo_cancelacion = models.CharField(
        max_length=10,
        choices=MOTIVOS_CANCELACION,
        null=True,
        blank=True
    )

    # Campo opcional únicamente si elige 'OTRO'
    detalle_motivo_cancelacion = models.CharField(
        max_length=144,
        null=True,
        blank=True
    )


    # motivo_cancelacion = models.CharField(
    #     max_length=500,
    #     blank=True,
    #     null=True,
    # )

    # campos para el seguimiento de tutoría
    asistencia = models.BooleanField(default=True, blank=True, null=True)
    duracion = models.IntegerField(DURACION_ASESORIA,default=0, blank=True, null=True)
    firma_documentos_beca = models.BooleanField(default=False, blank=True, null=True)
    beca_otorgada = models.CharField(max_length=255, blank=True, null=True)
    asesoria_especializada = models.BooleanField(default=False, blank=True, null=True)
    observaciones = models.CharField(max_length=1000, blank=True, null=True)
    impacto_tutoria = models.IntegerField(default=0, blank=True, null=True)
    resultados_tutoria = models.CharField(max_length=1000, blank=True, null=True)
    
    # Estado del alumno al momento de crear la tutoría (snapshot histórico)
    estado_alumno_historico = models.IntegerField(choices=ESTADOS_ALUMNO, blank=True, null=True)

    def __str__(self) -> str:
        string_tutoria = f'{self.alumno.first_name} {self.alumno.last_name}: tutoria {self.pk}'
        return  string_tutoria
    
    class Meta:
        ordering = ["-fecha"]

    @property
    def estado_efectivo(self):
        """ 
        Regresa el estado efectivo de la tutoría al momento de la consulta, 
        considerando la fecha y la asistencia.
        """
        ahora = timezone.now()
        
        # 1. Una propuesta sigue activa mientras al menos una alternativa
        # continúe vigente. Esto permite reactivar solicitudes cuya fecha
        # original ya venció proponiendo nuevos horarios.
        if self.estado == PROPUESTA:
            fechas_propuestas = [
                fecha for fecha in (
                    self.fecha_propuesta_1,
                    self.fecha_propuesta_2,
                ) if fecha is not None
            ]
            fecha_limite = max(fechas_propuestas, default=self.fecha)
            if fecha_limite < ahora:
                return VENCIDA

        # 2. Solicitud pendiente que venció sin ser atendida
        if self.estado == PENDIENTE and self.fecha < ahora:
            return VENCIDA

        # 3. Tutoría aceptada que ya pasó la fecha (REALIZADA o REPORTADA)
        if self.estado == ACEPTADO and self.fecha < ahora:
            if self.fecha_reporte is not None:
                return REPORTADA
            
            return REALIZADA    
                
        # 4. En cualquier otro caso, regresa el estado normal grabado en BD
        return self.estado


    def _get_FIELD_display(self, field):
        """
        Intercepta la generación automática de labels de Django 
        para soportar estados dinámicos sin romper la convención del framework.
        """
        if field.name == 'estado':
            # Si el estado efectivo está en nuestro diccionario global, devolvemos su texto
            return dict(ESTADO).get(self.estado_efectivo)
        
        return super()._get_FIELD_display(field)

    @property
    def fecha_cancelacion_automatica(self):
        """
        Esta función calcula la fecha en la que una solicitud no respondida por el tutor
        debe ser calcelada automáticamente. La fecha compensa según el margen con que se
        hizo la solicitud, entre más margen para la cita, menos días para cancelar automáticamente.

        NOTA: esta fecha no funcionaría si se quiere determinar cuando se cancelaría una solicitud que
        el alumno no respondió a una propuesta de fechas del tutor.
        Actualmente el sistema NO le da extesión al alumno, la tutoría se cancela automáticamente
        al terminar el día de la fecha propuesta por el tutor.
        """
        # Días de margen que tiene la fecha solicitada por el alumno para la cita.
        dias_holgura = (self.fecha.date() - self.fecha_solicitud.date()).days

        # Días restantes que tiene el tutor para responder compensando
        # con qué tan justa es la fecha para la cita.
        dias_restantes = DIAS_TOLERANCIA_TUTOR - dias_holgura

        # Solicitudes con mucha holgura tendrán solamente 1 días de extesión,
        # pero solicitudes muy apretadas tendrán más.
        dias_extension = max(1, dias_restantes)

        return self.fecha + timedelta(days=dias_extension)

    @property
    def debe_cancelarse_automaticamente(self):
        return (
            self.estado_efectivo == VENCIDA
            and timezone.now() >= self.fecha_cancelacion_automatica
        )

    @property
    def estado_badge_class(self):
        """Devuelve la clase CSS correspondiente al estado efectivo actual."""
        mapa_clases = {
            'PEN': 'bg-pendiente',
            'PRO': 'bg-propuesta',
            'ACE': 'bg-aceptada',
            'REJ': 'bg-rechazada',
            'CAN': 'bg-cancelada',
            'VEN': 'bg-vencida',
            'REP': 'bg-reportada',
            'REA': 'bg-realizada',
        }
        return mapa_clases.get(self.estado_efectivo, 'bg-secondary')

    #Sobreescribir método get_foo_display de django
    def get_tema_display(self):
        # values = self.tema
        choices = dict(TEMAS)
        # return choices
        return [choices.get(t, "Unknown") for t in self.tema]

    @property
    def motivo_rechazo_legible(self):
        """Devuelve la etiqueta del motivo o el detalle escrito por el tutor."""
        if self.motivo_rechazo == MOTIVO_RECHAZO_OTRO:
            return self.detalle_motivo_rechazo or "Otro motivo"
        return self.get_motivo_rechazo_display() if self.motivo_rechazo else ""

    @property
    def motivo_cancelacion_legible(self):
        """Devuelve la etiqueta del motivo o el detalle escrito al cancelar."""
        if self.motivo_cancelacion in {"ALU_OTRO", "TUT_OTRO"}:
            return self.detalle_motivo_cancelacion or "Otro motivo"
        return (
            self.get_motivo_cancelacion_display()
            if self.motivo_cancelacion
            else ""
        )
    
    def get_duracion_display(self):
        choices = dict(DURACION_ASESORIA)
        return choices.get(self.duracion, "Unknown")
    
    def get_estado_alumno_historico_display(self):
        """Retorna la etiqueta legible del estado histórico del alumno"""
        if self.estado_alumno_historico is None:
            return "Sin registro"
        choices_dict = dict(ESTADOS_ALUMNO)
        return choices_dict.get(self.estado_alumno_historico, "Sin registro")

    def calendar_summary_for(self, recipient_role):
        """Construye el título del evento desde la perspectiva del destinatario."""
        counterpart = self.tutor if recipient_role == "alumno" else self.alumno
        return f"Tutoría con {counterpart.nombre_completo}"

    def google_calendar_url_for(self, recipient_role):
        """Construye la URL de Google Calendar para el alumno o el tutor."""
        # 1. Configurar fechas
        start_time = timezone.localtime(self.fecha)
        end_time = start_time + timedelta(hours=1) # Asumimos 1 hora de duración

        # 2. Formato que pide Google: YYYYMMDDTHHMMSSZ (o sin Z para hora local)
        fmt = "%Y%m%dT%H%M%S"

        # 3. Construir parámetros
        temas_texto = ", ".join(self.get_tema_display())
        params = {
            'action': 'TEMPLATE',
            'text': self.calendar_summary_for(recipient_role),
            "details": (
                f"Temas: {temas_texto}\n"
                f"Descripción: {self.descripcion or 'sin descripción'}"
            ),
            'dates': f"{start_time.strftime(fmt)}/{end_time.strftime(fmt)}",
            'ctz': 'America/Mexico_City' # Fuerza la zona horaria de CDMX
        }   

        return f"https://calendar.google.com/calendar/render?{urlencode(params)}"

    @property
    def google_calendar_url_tutor(self):
        return self.google_calendar_url_for("tutor")

    @property
    def google_calendar_url_alumno(self):
        return self.google_calendar_url_for("alumno")


class HistorialCambioTutoria(models.Model):
    tutoria = models.ForeignKey(Tutoria, on_delete=models.CASCADE, related_name='historial_cambios')
    correo_editor = models.EmailField()
    cambios_realizados = models.TextField()
    fecha_cambio = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_cambio"]

    def __str__(self) -> str:
        return f'Historial tutoria {self.tutoria_id} - {self.correo_editor}'

    
class Asesoria(models.Model):

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    tutor = models.ForeignKey(Tutor, on_delete=models.CASCADE)
    tema = models.CharField(max_length=120)
    fecha = models.DateTimeField()
    descripcion = models.CharField(max_length=255)
