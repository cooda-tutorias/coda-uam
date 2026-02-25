# Implementación de seguimiento de tutorías


## Funcionamiento general
Esta función es accesible desde la vista "Historial de tutorías" que puede ver el tutor. 

En la tabla que muestra el historial, se agregan distinas columnas para crear y visualizar el seguimiento. Se agregan las columnas que muestran la información del seguimiento, así como una columna que
contiene un botón.

Al presionar este botón, se lleva formulario de seguimiento. El formulario de seguimiento muestra la información de la tutoría seleccionada, junto con el formulario a responder por el tutor.

Al envíar el formulario, se actualiza la fila en la tabla de tutorías y se muestra la información actualizada del seguimiento en sus columnas correspondientes.

## Información que requiere el formulario

1. ¿El alumno asistió a la tutoría? (Si/No)

--- Las siguientes preguntas se activan sólo si se respondió "Sí" a la pregunta anterior ---

2. Duración de la tutoría (menos 30 min/30 min/1 hora/2 horas/más de 2 horas)
3. ¿Se firmó algún formato de solicitud de beca? (Sí/No)

--- La pregunta 4 solo se activa si se responde "Sí" a la pregunta anterior---

4. Nombre de la beca que se otorgó al alumno (respuesta libre)
5. ¿El alumno requirió asesoría especializada? (Sí/No)
6. Aspectos tratados en la tutoría, acuerdos o acciones establecidos, canalizaciones (respuesta libre)
7. ¿Nivel de impacto de tutoría en desempeño académico de alumno/a? (Selección del 1 al 5)
8. Resultados de tutoría (Respuesta libre)


## Componentes del código
Se añadieron los siguientes campos a `models.py`

```
    asistencia = models.BooleanField(default=False, blank=True, null=True)
    duracion = models.IntegerField(DURACION_ASESORIA,default=0, blank=True, null=True)
    firma_documentos_beca = models.BooleanField(default=False, blank=True, null=True)
    beca_otorgada = models.CharField(max_length=255, blank=True, null=True)
    asesoria_especializada = models.BooleanField(default=False, blank=True, null=True)
    observaciones = models.CharField(max_length=1000, blank=True, null=True)
    impacto_tutoria = models.IntegerField(default=0, blank=True, null=True)
    resultados_tutoria = models.CharField(max_length=1000, blank=True, null=True)
```
además, se añade un método para poder desplegar la duración de la tutoría correctamente usando las constantes que se enlistan en el siguiente punto
```
    def get_duracion_display(self):
        choices = dict(DURACION_ASESORIA)
        return choices.get(self.duracion, "Unknown")
```
En `constants.py`, se añaden las constantes para determinar la duración de la tutoría
```
DURACION_ASESORIA = [
    (0, 'Menos de 30 minutos'),
    (1, '30 minutos'),
    (2, '1 hora'),
    (3, '2 horas'),
    (4, 'Más de dos horas')
]
```

En `forms.py`, se añade la clase `FormSeguimiento`. Con esta clase, Django puede generar el formulario que se despliega al añadir el seguimiento a una tutoría y todas las funciones asociadas a esta aspecto

```
class FormSeguimiento(forms.ModelForm):
    asistencia = forms.BooleanField(required=False)
    duracion = forms.ChoiceField(choices=DURACION_ASESORIA, required=False)
    firma_documentos_beca = forms.BooleanField(required=False)
    beca_otorgada = forms.CharField(max_length=255, required=False)
    asesoria_especializada = forms.BooleanField(required=False)
    observaciones = forms.CharField(widget=forms.Textarea, max_length=1000, required=False)
    impacto_tutoria = forms.IntegerField(required=False)
    resultados_tutoria = forms.CharField(widget=forms.Textarea, max_length=1000, required=False)

    class Meta:
        model = Tutoria
        fields = ['asistencia', 'duracion', 'firma_documentos_beca', 'beca_otorgada', 'asesoria_especializada', 'observaciones', 'impacto_tutoria', 'resultados_tutoria']
        exclude = ['alumno', 'tutor', 'tema', 'fecha', 'descripcion', 'estado']
```

En `urls.py`, establecemos la ruta del template a usar para nuestra vista

```
#int:pk es la primary key de la tutoría que estamos editando. 'save_seguimiento' es el nombre que usamos para llamar a la vista desde los templates
path('tutoria/seguimiento/<int:pk>/', views.RealizarSeguimientoView.as_view(), name='save_seguimiento'),
```

Para crear la vista, hacemos lo siguiente en `views.py`:
1. Importamos la clase del formulario de seguimiento, así como las constantes de duración
```
from .forms import FormTutorias, FormSeguimiento
from .constants import PENDIENTE, ACEPTADO, RECHAZADO, DURACION_ASESORIA # de nuevo, no estoy seguro
```
2. La clase para la vista se contruye de la siguiente manera:
    * Se importa la clase `TutorViewMixin` ya que es la que nos va a permitir obtener los permisos del usuario "Tutor" sobre la base de datos
    * Se importa la clase `UpdateView`, la cual utiliza la clase `FormSeguimiento` que definimos en `forms.py` para generar el formulario de manera automática. En este caso, estamos usando UpdateView porque, al crear una tutoría, se crean también los campos del seguimiento, pero vacíos. Para llenarlos, solo tenemos que actualizar esos campos en la base de datos
    * En `model` se indica el modelo a usar que importamos de `model.py`
    * En `form_class` indicamos la clase en `forms.py` a usar para generar el formulario
    * En `template_name` indicamos la ruta del archivo html a usar como template. Se pone el nombre exacto del archivo html
    * `success_url` nos permite redirigir cuando la info. de seguimiento se actualice correctamente. `reverse_lazy` permite establecer la página de redirección a partir de cómo está identificada en `url.py`.
```
class RealizarSeguimientoView(TutorViewMixin, UpdateView):
    model = Tutoria
    form_class = FormSeguimiento
    template_name = 'Tutorias/seguimientoTutoria.html'
    success_url =  reverse_lazy('Tutorias-historial')

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        # pk = primary key. Estamos obteniendo la información del tutor a través de la primary key que se manda desde el template
        tutor = Tutor.objects.get(pk=self.request.user)
        recipient = Alumno.objects.filter(pk=self.get_object().alumno)

        notify.send(tutor, recipient=recipient, verb='Seguimiento de tutoria realizado')
        return super().form_valid(form)
```

Se hacen las modificaciones necesarias en `historialtutoria.html` para mostrar las nuevas columnas asociadas al seguimiento.

En `seguimientoTutoria.html` creamos el template para añadir la información de la tutoría. Desplegamos la información de la tutoría a modificar y se muestra el template. La clase UpdateView se encarga de hacer las modificaciones pertinentes en la base de datos.

## Flujo de ejecución
1. Tutor abre historial de tutorías
2. Tutor hace click en botón "Realizar seguimiento" asociado a una tutoría
3. Se genera formulario para llenar info de seguimiento
4. Tutor llena formulario de seguimiento
5. Al enviar el formulario, se actualiza la información en la base de datos, y se muestran los campos del seguimiento actualizados en el historial de tutorías