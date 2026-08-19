from django.db import models
from django.utils.http import urlencode
from datetime import timedelta
from django.contrib.postgres.fields import ArrayField
from Usuarios.models import Alumno, Tutor
from Usuarios.constants import ESTADOS_ALUMNO
from .constants import TEMAS, SERVICIO, ESTADO, DURACION_ASESORIA
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
    fecha = models.DateTimeField()

    # Propuestas alternativas cuando el tutor acepta la tutoría, pero propone otras fechas.
    fecha_propuesta_1 = models.DateTimeField(null=True, blank=True)
    fecha_propuesta_2 = models.DateTimeField(null=True, blank=True)

    descripcion = models.CharField(max_length=255, blank=True, null=True)
    estado = models.CharField(PENDIENTE, max_length=4, choices=ESTADO, default=PENDIENTE)

    # Campo para registrar el motivo de rechazo de la tutoría.
    motivo_rechazo = models.CharField(
        max_length=500,
        blank=True,
        null=True,
    )

    # campos para el seguimiento de tutoría
    asistencia = models.BooleanField(default=False, blank=True, null=True)
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
        
        # 1. Solicitud o propuesta que venció sin ser aceptada
        if self.estado in [PENDIENTE, PROPUESTA] and self.fecha < ahora:
            return VENCIDA

        # 2. Tutoría aceptada que ya pasó la fecha
        if self.estado == ACEPTADO and self.fecha < ahora:
            if self.asistencia is not None:
                return REPORTADA
            return REALIZADA    
                
        # 3. En cualquier otro caso, regresa el estado normal grabado en BD
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
    
    def get_duracion_display(self):
        choices = dict(DURACION_ASESORIA)
        return choices.get(self.duracion, "Unknown")
    
    def get_estado_alumno_historico_display(self):
        """Retorna la etiqueta legible del estado histórico del alumno"""
        if self.estado_alumno_historico is None:
            return "Sin registro"
        choices_dict = dict(ESTADOS_ALUMNO)
        return choices_dict.get(self.estado_alumno_historico, "Sin registro")

    @property
    def google_calendar_url(self):
        # 1. Configurar fechas
        start_time = self.fecha
        end_time = start_time + timedelta(hours=1) # Asumimos 1 hora de duración

        # 2. Formato que pide Google: YYYYMMDDTHHMMSSZ (o sin Z para hora local)
        fmt = "%Y%m%dT%H%M%S"

        # 3. Construir parámetros
        temas_texto = ",".join(self.get_tema_display())
        params = {
            'action': 'TEMPLATE',
            'text': f"Tutoría con {self.alumno.nombre_completo}",
            'details': f"Temas: {temas_texto}.",
            'dates': f"{start_time.strftime(fmt)}/{end_time.strftime(fmt)}",
            'ctz': 'America/Mexico_City' # Fuerza la zona horaria de CDMX
        }   

        return f"https://calendar.google.com/calendar/render?{urlencode(params)}"

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
