TUTOR = "TUT"
COORDINADOR = "COR"
ALUMNO = "ALU"
CODA = "CODA"

ROLES = [
    ('', "Seleccione Rol"),
    (TUTOR, "Tutor"),
    (COORDINADOR, "Coordinador"),
    (ALUMNO, "Alumno"),
    (CODA, "CODDAA"),
]


MATEMATICAS = "MAT"
COMPUTACION = "COM"
IBIOLOGICA = "IB"
BMOLECULAR = "BM"

CARRERAS = [
        ('', "Seleccione una"),
        (MATEMATICAS, "Matemáticas Aplicadas"),
        (COMPUTACION, "Ingeniería en Computación"),
        (IBIOLOGICA, "Ingeniería Biológica"),
        (BMOLECULAR, "Biología Molecular")
    ]

TEMPLATES = {
    # ALUMNO: 'Usuarios/HeaderFooterAlumno.html',
    # TUTOR: 'Usuarios/HeaderFooterTutor.html',
    # COORDINADOR: 'Usuarios/HeaderFooterCoord.html',
    ALUMNO: 'Usuarios/navbar_alumno.html',
    TUTOR: 'Usuarios/navbar_tutor.html',
    COORDINADOR: 'Usuarios/navbar_coord.html',
    CODA: 'Usuarios/navbar_coda.html',
}

CORREO = 'tutorias.beta.uamc@gmail.com'

SEXOS = [
    ('', "Seleccione un sexo"),
    ('M',"Masculino"),
    ('F',"Femenino"),
]

ESTADOS_ALUMNO = [
    ('', 'Selecciona un estado'),
    (1,"Activo"),
    (2,"No reinscrito"),
    (10, "Inscrito sin carga académica")
]