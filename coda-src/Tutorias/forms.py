from django import forms
from .models import Tutoria
from Usuarios.models import Documento, Tutor
from .constants import TEMAS, ESTADO, ACEPTADO, PENDIENTE, DURACION_ASESORIA
from Usuarios.constants import ESTADOS_ALUMNO

class FormTutorias(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Si existe instancia con fecha, ajustamos el formato para HTML5
        if self.instance and self.instance.fecha:
            self.initial['fecha'] = self.instance.fecha.strftime('%Y-%m-%dT%H:%M')

    alumno = forms.CharField(disabled=True, required=False)
    tutor = forms.CharField(disabled=True, required=False)
    tema= forms.MultipleChoiceField(
        choices=TEMAS,
        widget=forms.CheckboxSelectMultiple,
        label="Temas de la tutoría",
        required=True
    )
    otro_tema = forms.CharField(required=False, label='Especificar tema')
    fecha = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}), required=True)
    descripcion = forms.CharField(widget=forms.Textarea, max_length=255, required=True)
    estado = forms.ChoiceField(choices=ESTADO, required=False)

    class Meta:
        model = Tutoria
        fields = ['tema', 'fecha', 'descripcion']

    def clean(self):
        cleaned_data = super().clean()
        temas = cleaned_data.get('tema')
        otro_tema = cleaned_data.get('otro_tema')

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
    asistencia = forms.BooleanField(required=True)
    duracion = forms.ChoiceField(choices=DURACION_ASESORIA, required=True)
    firma_documentos_beca = forms.BooleanField(required=True)
    beca_otorgada = forms.CharField(max_length=255, required=False)
    asesoria_especializada = forms.BooleanField(required=True)
    observaciones = forms.CharField(widget=forms.Textarea, max_length=1000, required=False)
    impacto_tutoria = forms.IntegerField(required=True)
    resultados_tutoria = forms.CharField(widget=forms.Textarea, max_length=1000, required=False)

    class Meta:
        model = Tutoria
        fields = ['asistencia', 'duracion', 'firma_documentos_beca', 'beca_otorgada', 'asesoria_especializada', 'observaciones', 'impacto_tutoria', 'resultados_tutoria']
        exclude = ['alumno', 'tutor', 'tema', 'fecha', 'descripcion', 'estado']


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

        self.fields['carrera'].initial = carreras_dict.get(tutor_instance.coordinacion, "Carrera desconocida")

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

        self.fields['carrera'].initial = carreras_dict.get(tutor_instance.coordinacion, "Carrera desconocida")

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

    oficio_inicial = forms.IntegerField(required=True, min_value=1, label="Número de Oficio inicial")
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


class FormVerTutorias(forms.Form):
    estado = forms.TypedChoiceField(
        choices=[('', 'Todos los estados')] + ESTADOS_ALUMNO[1:],
        required=False,
        label="Estado del Alumno",
        coerce=int,
        empty_value='',
    )
