from django import forms
from .models import Tutoria
from Usuarios.models import Documento, Alumno, Tutor, HorarioTutor
from .constants import TEMAS, ESTADO, ACEPTADO, PENDIENTE, DURACION_ASESORIA, ROLES, CARRERAS
from Usuarios.constants import ESTADOS_ALUMNO


def str_to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == 'true'


class FormEditarTutoriaModal(forms.ModelForm):
    """
    Formulario para editar los temas y la descripción de la tutoría.
    """
    tema = forms.MultipleChoiceField(
        choices=TEMAS,
        widget=forms.CheckboxSelectMultiple,
        label="Temas de la tutoría",
        required=True,
    )

    descripcion = forms.CharField(
        label="Descripción",
        max_length=255,
        required=True,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
            }
        ),
    )

    class Meta:
        model = Tutoria
        fields = ["tema", "descripcion"]

#TODO: este formulario fue hecho principalmente para que el alumno solicite una cita con el tutor,
# pero encontré (Antonio LJ) que también se está usando para que el tutor pueda crear una cita 
# con el alumno, por lo que hay que revisar si esta función se requiere o no.
class FormTutorias(forms.ModelForm):
    """
    Formulario para solicitar una tutoría.
    El formulario se adapta según si el tutor definió disponibilidad de horarios no.
    Cuando hay horarios, el alumno debe seleccionar uno de ellos. En caso contrario, 
    el alumno puede sugerir una fecha para la tutoría.
    """

    horario_tutor = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Selecciona un horario disponible",
    )

    fecha_sugerida = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        label="Sugerir fecha para la cita"
    )

    class Meta:
        model = Tutoria
        fields = ["tema", "fecha", "descripcion", "fecha_sugerida", "horario_tutor"]

    def __init__(self, *args, **kwargs):
        # Extrae el usuario del contexto (no todos los formularios lo enviarán)
        self.user = kwargs.pop('user', None)
        self.skip_fecha_validacion = kwargs.pop("skip_fecha_validacion", False)
        super().__init__(*args, **kwargs)

        
        # Caso de ALUMNO solicitando tutoría
        if self.user and self.user.has_role("ALU"):
            tutor = self.user.alumno.tutor_asignado
            horarios = HorarioTutor.objects.filter(
                tutor=tutor, activo=True
            ).order_by('dia_semana','hora_inicio')
            self.fields["horario_tutor"].queryset = horarios

            if horarios.exists():
                # Hay horarios → ocultamos la fecha sugerida
                self.fields["fecha_sugerida"].widget = forms.HiddenInput()
                self.fields["fecha_sugerida"].required = False
            else:
                # Sin horarios → ocultamos el selector de horarios
                self.fields["horario_tutor"].widget = forms.HiddenInput()
                self.fields["horario_tutor"].required = False


        # Personaliza comportamiento según el rol
        if self.user:
            if self.user.has_role("ALU"):
                # Si es alumno, el campo tutor no se edita
                if "tutor" in self.fields:
                    self.fields["tutor"].widget = forms.HiddenInput()

            elif self.user.has_role("TUT"):
                # Si es tutor, el campo alumno no se edita
                if "alumno" in self.fields:
                    self.fields["alumno"].widget = forms.HiddenInput()

        # Añade estilos base a los widgets
        for field_name, field in self.fields.items():
            css_class = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css_class} form-control".strip()

    alumno = forms.CharField(disabled=True, required=False)
    tutor = forms.CharField(disabled=True, required=False)

    tema= forms.MultipleChoiceField(
        choices=TEMAS,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Temas de la tutoría",
        required=True
    )

    otro_tema = forms.CharField(required=False, label='Especificar tema')
    fecha = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}), required=False)
    descripcion = forms.CharField(widget=forms.Textarea, max_length=255, required=True)
    estado = forms.ChoiceField(choices=ESTADO, required=False)

    def clean(self):
        cleaned_data = super().clean()

        horario = cleaned_data.get("horario_tutor")
        fecha_sugerida = cleaned_data.get("fecha_sugerida")

        # Validación de selección
        if not getattr(self, "skip_fecha_validacion", False):
            if not horario and not fecha_sugerida:
                raise forms.ValidationError(
                    "Debes seleccionar un horario disponible o sugerir una fecha."
                )
                
        temas = cleaned_data.get('tema')
        otro_tema = cleaned_data.get('otro_tema')

        # Validar que haya seleccionado al menos un tema
        if not temas:
            self.add_error('tema', 'Debes seleccionar al menos un tema para la tutoría.')

        if temas and 'OTRO' in temas:
            if not otro_tema or not otro_tema.strip():
                self.add_error('otro_tema', 'Este campo es obligatorio si seleccionas "Otro".')

        return cleaned_data

    
# Formato para la tutorias in-situ
# forms.py
class FormTutoriasInSitu(forms.ModelForm):
    # class Meta:
    #     model = Tutoria
    #     fields = ["tema", "descripcion"]   # agrega otros si los necesitas
    #     widgets = {
    #         "tema": forms.Select(attrs={"class": "form-control"}),
    #         "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    #     }

    def __init__(self, *args, **kwargs):
        # Extrae el usuario del contexto (no todos los formularios lo enviarán)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Si existe instancia con fecha, formatea para HTML5
        if self.instance and self.instance.fecha:
            self.initial['fecha'] = self.instance.fecha.strftime('%Y-%m-%dT%H:%M')

        # Personaliza comportamiento según el rol
        if self.user:
            if self.user.has_role("ALU"):
                # Si es alumno, el campo tutor no se edita
                if "tutor" in self.fields:
                    self.fields["tutor"].widget = forms.HiddenInput()

            elif self.user.has_role("TUT"):
                # Si es tutor, el campo alumno no se edita
                if "alumno" in self.fields:
                    self.fields["alumno"].widget = forms.HiddenInput()

        # Añade estilos base a los widgets
        for field_name, field in self.fields.items():
            css_class = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css_class} form-control".strip()

    alumno = forms.CharField(disabled=True, required=False)
    tutor = forms.CharField(disabled=True, required=False)
    tema= forms.MultipleChoiceField(
        choices=TEMAS,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Temas de la tutoría",
        required=True
    )
    otro_tema = forms.CharField(required=False, label='Especificar tema')
    #fecha = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}), required=True)
    descripcion = forms.CharField(widget=forms.Textarea, max_length=255, required=True)
    estado = forms.ChoiceField(choices=ESTADO, required=False)

    class Meta:
        model = Tutoria
        fields = ['tema', 'descripcion']

    def clean(self):
        cleaned_data = super().clean()
        temas = cleaned_data.get('tema')
        otro_tema = cleaned_data.get('otro_tema')

        # Validar que haya seleccionado al menos un tema
        if not temas:
            self.add_error('tema', 'Debes seleccionar al menos un tema para la tutoría.')

        if temas and 'OTRO' in temas:
            if not otro_tema or not otro_tema.strip():
                self.add_error('otro_tema', 'Este campo es obligatorio si seleccionas "Otro".')


class FormEditarEstadoAlumnoHistorico(forms.Form):
    """Formulario para editar solo el estado histórico del alumno en una tutoría"""
    estado_alumno_historico = forms.TypedChoiceField(
        choices=ESTADOS_ALUMNO[1:],  # Excluir la opción vacía
        label="Estado del alumno al momento de la tutoría",
        required=True,
        coerce=int,
    )


class FormSeguimiento(forms.ModelForm):
    estado_alumno_actual = forms.TypedChoiceField(
        choices=ESTADOS_ALUMNO[1:],
        required=True,
        coerce=int,
        label="Estado actual del alumno",
    )
    asistencia = forms.TypedChoiceField(
        choices=((True, 'Sí'), (False, 'No')),
        required=True,
        initial=True,
        coerce=str_to_bool,
    )
    duracion = forms.ChoiceField(choices=DURACION_ASESORIA, required=True)
    firma_documentos_beca = forms.TypedChoiceField(
        choices=((True, 'Sí'), (False, 'No')),
        required=True,
        coerce=str_to_bool,
    )
    beca_otorgada = forms.CharField(max_length=255, required=False)
    asesoria_especializada = forms.TypedChoiceField(
        choices=((True, 'Sí'), (False, 'No')),
        required=True,
        coerce=str_to_bool,
    )
    observaciones = forms.CharField(widget=forms.Textarea, max_length=1000, required=False)
    impacto_tutoria = forms.IntegerField(
        required=True,
        error_messages={
            'required': 'Selecciona un nivel de impacto antes de guardar el reporte.',
        },
    )
    resultados_tutoria = forms.CharField(widget=forms.Textarea, max_length=1000, required=False)

    class Meta:
        model = Tutoria
        fields = ['asistencia', 'duracion', 'firma_documentos_beca', 'beca_otorgada', 'asesoria_especializada', 'observaciones', 'impacto_tutoria', 'resultados_tutoria']
        exclude = ['alumno', 'tutor', 'tema', 'fecha', 'descripcion', 'estado']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and self.instance.alumno_id:
            self.fields['estado_alumno_actual'].initial = self.instance.alumno.estado


class FormReporte(forms.ModelForm):
    oficio = forms.IntegerField(required=True, min_value=1)
    fecha = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    plantilla = forms.ModelChoiceField(queryset=Documento.objects.all(), to_field_name='nombre', label="Selecciona una plantilla")
    tutor = forms.CharField(widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    carrera = forms.CharField(widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = Documento
        fields = ['oficio', 'plantilla', 'fecha']

    def __init__(self, *args, tutor_instance=None, **kwargs):
        super().__init__(*args, **kwargs)

        if tutor_instance:
            full_name = ""
            # Llenamos el nombre del tutor.
            if tutor_instance.sexo:
                if tutor_instance.sexo == "F":
                    full_name = "Dra."
                else:
                    full_name = "Dr."
                pass
            full_name += f" {tutor_instance.first_name} {tutor_instance.last_name}"
            if tutor_instance.second_last_name:
                full_name += f" {tutor_instance.second_last_name}"
            self.fields['tutor'].initial = full_name

        carreras_dict = dict([
            ("MAT", "Matemáticas Aplicadas"),
            ("COM", "Ingeniería en Computación"),
            ("IB", "Ingeniería Biológica"),
            ("BM", "Biología Molecular"),
        ])

        self.fields['carrera'].initial = carreras_dict.get(tutor_instance.coordinacion, "Licenciatura desconocida")

class FormCartasDeAsignacion(forms.ModelForm):
    no_inicio = forms.IntegerField(min_value=0)
    no_cartas = forms.IntegerField(widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    oficio = forms.CharField(required=False)
    fecha = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    plantilla = forms.ModelChoiceField(queryset=Documento.objects.all(), to_field_name='nombre', label="Selecciona una plantilla")
    tutor = forms.CharField(widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    carrera = forms.CharField(widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = Documento
        fields = ['oficio', 'plantilla', 'fecha', 'no_inicio']

    def __init__(self, *args, tutor_instance=None, **kwargs):
        super().__init__(*args, **kwargs)

        if tutor_instance:
            full_name = ""
            if tutor_instance.sexo:
                if tutor_instance.sexo == "F":
                    full_name = "Dra."
                else:
                    full_name = "Dr."
                pass
            full_name += f" {tutor_instance.first_name} {tutor_instance.last_name}"
            if tutor_instance.second_last_name:
                full_name += f" {tutor_instance.second_last_name}"
            self.fields['tutor'].initial = full_name

        carreras_dict = dict([
            ("MAT", "Matemáticas Aplicadas"),
            ("COM", "Ingeniería en Computación"),
            ("IB", "Ingeniería Biológica"),
            ("BM", "Biología Molecular"),
        ])

        self.fields['carrera'].initial = carreras_dict.get(tutor_instance.coordinacion, "Licenciatura desconocida")

class FormReporteDeTutorias(forms.ModelForm):

    oficio = forms.IntegerField(required=True, min_value=1)
    fecha_inicio = forms.DateField(required=True)
    fecha_fin = forms.DateField(required=True)
    fecha = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}), required=True)
    plantilla = forms.ModelChoiceField(queryset=Documento.objects.all(), to_field_name='nombre', label="Selecciona una plantilla", required=True)
    tutor = forms.CharField(widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = Documento
        fields = ['oficio', 'plantilla', 'fecha', 'fecha_inicio', 'fecha_fin']

    def __init__(self, *args, tutor_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tutor_instance:
                full_name = ""
                if tutor_instance.sexo:
                    if tutor_instance.sexo == "F":
                        full_name = "Dra."
                    else:
                        full_name = "Dr."
                    pass
                full_name += f" {tutor_instance.first_name} {tutor_instance.last_name}"
                if tutor_instance.second_last_name:
                    full_name += f" {tutor_instance.second_last_name}"
                self.fields['tutor'].initial = full_name

class FormReporteTutoriasMasivo(forms.Form):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["tutores"].label_from_instance = self.label_tutor

    def label_tutor(self, tutor):
        return f"{tutor.matricula} - {tutor.first_name} {tutor.last_name}"

    COORDINACION_CHOICES = [
        ("MAT", "Matemáticas Aplicadas"),
        ("COM", "Ingeniería en Computación"),
        ("IB", "Ingeniería Biológica"),
        ("BM", "Biología Molecular"),
    ]

    coordinaciones = forms.MultipleChoiceField(
        choices=COORDINACION_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Licenciaturas"
    )

    incluir_todas = forms.BooleanField(
        required=False,
        label="Incluir todas las licenciaturas"
    )

    tutores = forms.ModelMultipleChoiceField(
        queryset=Tutor.objects.all().order_by('coordinacion', 'last_name', 'first_name'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Tutores específicos"
    )

    oficio_inicial = forms.IntegerField(required=True, min_value=1, label="Número de oficio inicial")
    fecha_inicio = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    fecha_fin = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    fecha = forms.DateTimeField(
        required=True,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        label="Fecha de emisión"
    )

    PLANTILLA_REPORTE_TUTORIAS_MASIVO = "Reporte tutorías atendidas (carta anual)"

    col_alumno = forms.BooleanField(required=False, initial=True, label="Alumno")
    col_fecha = forms.BooleanField(required=False, initial=True, label="Fecha")
    col_hora = forms.BooleanField(required=False, label="Hora")
    col_tema = forms.BooleanField(required=False, label="Tema")
    col_notas = forms.BooleanField(required=False, label="Notas")

    def clean(self):
        cleaned_data = super().clean()
        incluir_todas = cleaned_data.get("incluir_todas")
        coordinaciones = cleaned_data.get("coordinaciones") or []
        tutores = cleaned_data.get("tutores") or Tutor.objects.none()

        if not any([
            cleaned_data.get("col_alumno"),
            cleaned_data.get("col_fecha"),
            cleaned_data.get("col_hora"),
            cleaned_data.get("col_tema"),
            cleaned_data.get("col_notas"),
        ]):
            raise forms.ValidationError("Selecciona al menos una columna para el reporte.")

        if not incluir_todas and not coordinaciones and not tutores.exists():
            raise forms.ValidationError(
                "Selecciona al menos una licenciatura, tutores específicos o marca 'Incluir todas las licenciaturas'."
            )

        return cleaned_data


class AlumnoChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        nombres = f"{obj.first_name} {obj.last_name}"
        if obj.second_last_name:
            nombres += f" {obj.second_last_name}"
        
        return f"{nombres} ({obj.email})"

class ComunicacionMasivaForm(forms.Form):

    OPCIONES_CARRERA = [('', '--- Todas las carreras ---')] + list(CARRERAS)
    
    filtro_carrera = forms.ChoiceField(
        choices=OPCIONES_CARRERA,
        required=False,
        label="Filtrar por licenciatura",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_filtro_carrera'})
    )

    OPCIONES_ASUNTO = [
        ('', '--- Todos los asuntos ---'),
        ('academico', 'Seguimiento Académico'),
        ('administrativo', 'Trámites Administrativos'),
        ('personal', 'Apoyo Personal'),
        ('becas', 'Becas y Apoyos'),
        ('otro', 'Otro'),
    ]
    
    filtro_asunto_tutoria = forms.ChoiceField(
        choices=OPCIONES_ASUNTO,
        required=False,
        label="Asunto de tutoría (categoría)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    tutorados = AlumnoChoiceField( 
        queryset=Alumno.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Seleccionar tutorados",
        required=True
    )

    asunto = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Asunto del correo'})
    )

    mensaje = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Escribe tu mensaje aquí...'})
    )

    archivos = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        label="Adjuntar archivos"
    )

    def __init__(self, *args, **kwargs):
        tutor_actual = kwargs.pop('tutor', None)
        super(ComunicacionMasivaForm, self).__init__(*args, **kwargs)

        self.fields['archivos'].widget.attrs.update({'multiple': True})

        if tutor_actual:

            self.fields['tutorados'].queryset = Alumno.objects.filter(tutor_asignado=tutor_actual)
            print(f"Alumnos encontrados para {tutor_actual}: {self.fields['tutorados'].queryset.count()}")

class FormVerTutorias(forms.Form):
    estado = forms.TypedChoiceField(
        choices=[('', 'Todos los estados')] + ESTADOS_ALUMNO[1:],
        required=False,
        label="Estado del alumno",
        coerce=int,
        empty_value='',
    )
