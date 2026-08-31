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

# Departamentos de la DCNI
DMAS = "Matemáticas Aplicadas y Sistemas"
DCN = "Ciencias Naturales"
DPT = "Procesos y Tecnologías"

# MAPEO: COORDINACIÓN -> DEPARTAMENTO 
COORDINACION_A_DEPARTAMENTO = {
    MATEMATICAS: DMAS,
    COMPUTACION: DMAS,
    BMOLECULAR: DCN,
    IBIOLOGICA: DPT,
}

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
    (1, "Activo"),
    (2, "No activo"),
    (3, "Suspendido"),
    (4, "Baja definitiva"),
    (5, "Titulado"),
    (6, "Egresado con trámite de certificado"),
    (7, "Baja reglamentaria"),
    (8, "Egresado potencial"),
    (9, "Baja por dictamen de órgano colegiado"),
    (10, "Inscrito sin carga académica"),
    (11, "Aceptado nuevo ingreso"),
    (12, "Egresado sin trámite de certificado"),
    (13, "Alumno de nuevo ingreso no presentado"),
    (14, "Abandono de más de seis trimestres"),
    (15, "Alumno con diploma"),
    (16, "Alumno con grado"),
    (17, "Admitido en lista complementaria"),
    (18, "Estancia terminada (movilidad)"),
    (19, "Cancelación del trámite de registro o de ingreso"),
]
