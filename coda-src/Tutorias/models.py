from django.db import models
from django.contrib.postgres.fields import ArrayField
from Usuarios.models import Alumno, Tutor
from Usuarios.constants import ESTADOS_ALUMNO
from .constants import TEMAS, SERVICIO, PENDIENTE, ESTADO, DURACION_ASESORIA

# Create your models here.
class Tutoria(models.Model):


    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    tutor = models.ForeignKey(Tutor, on_delete=models.CASCADE)
    # tema = models.CharField(SERVICIO, max_length=4, choices=TEMAS, default=SERVICIO)
    # Se cambia el campo para que sea una lista
    tema = ArrayField(models.CharField(SERVICIO, max_length=4, choices=TEMAS, default=SERVICIO))
    fecha = models.DateTimeField()
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    estado = models.CharField(PENDIENTE, max_length=4, choices=ESTADO, default=PENDIENTE)
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
