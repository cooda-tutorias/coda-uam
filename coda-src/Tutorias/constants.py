
BECAS = "BEC"
INSCRIPCION = "INS"
INGLES = "ING"
COLEGIADO = "ORG"
REGLAMENTOS = "REG"
SERVICIO = "SS"
MOVILIDAD = "MOV"
PROYECTO = "PT"
ESTANCIA = "EV" 
TRAYECTORIA = "TC"
GRUPO = "EG" 
TITULACION = "TIT"
EGRESO = "EGRE"
PERSONALES = "PER"
SEGUIMIENTO = "SR"
LOCKER = "LKR"
RECUPERACION = "REC"
OTRO = "OTRO"

TEMAS = [
    (BECAS, "Becas"),
    (INSCRIPCION, "Inscripción"),
    (INGLES, "Inglés"),
    (COLEGIADO, "Órgano colegiado"),
    (REGLAMENTOS, "Reglamentos"),
    (SERVICIO, "Servicio social"),
    (MOVILIDAD, "Movilidad"),
    (PROYECTO, "Proyecto terminal"),
    (ESTANCIA, "Estancia de verano"),
    (TRAYECTORIA, "Trayectoria curricular"),
    (GRUPO, "Elección de grupo"),
    (TITULACION, "Titulación"),
    (EGRESO, "Egreso"),
    (PERSONALES, "Personales"),
    (SEGUIMIENTO, "Seguimiento de reunión"),
    (RECUPERACION, "Recuperación especial"),
    (LOCKER, "Solicitud de locker"),
    (OTRO, "Otro")
]

# Estados que sí se guardan en la base de datos
ACEPTADO = 'ACE'
RECHAZADO = 'REJ'
PENDIENTE = 'PEN'
CANCELADO = 'CAN'
PROPUESTA = 'PRO'

# Nuevos estados dinámicos (determinados en tiempo de ejecución)
VENCIDA = 'VEN'
REPORTADA = 'REP'
REALIZADA = 'REA'

ESTADO = [
    (ACEPTADO, 'Aceptada'),
    (RECHAZADO, 'Rechazada'),
    (PENDIENTE, 'Pendiente'),
    (CANCELADO, 'Cancelada'),
    (PROPUESTA, 'Propuesta'),
    # Estados determinados dinámicamente
    (VENCIDA, 'Vencida'),
    (REPORTADA, 'Registrada'),
    (REALIZADA, 'Realizada'),    
]

# Días de tolerancia para que el tutor responda a una solicitud antes de Cancelarla automáticamente.
DIAS_TOLERANCIA_TUTOR = 4

# Denotan el origen de la cancelación de una tutoría.
ORIGEN_CANCELACION = [
    ('ALUMNO', 'Alumno'),
    ('TUTOR', 'Tutor'),
    ('SISTEMA', 'Sistema / Vencimiento')
]

# Motivos para cancelar una tutoría que puede tener un alumno
MOTIVOS_CANCELACION_ALUMNO = [
    ('ALU_RESOL', 'Ya resolví la duda o tema por mi cuenta'),
    ('ALU_HORAR', 'Incompatibilidad de horario o fecha'),
    ('ALU_PERSO', 'Imprevisto personal o de salud'),
    ('ALU_OTRO',  'Otro motivo'),]

# Motivos para cancelar una tutoría que puede tener un tutor
MOTIVOS_CANCELACION_TUTOR = [
    ('TUT_HORAR', 'Conflicto de horario o empalme de actividades'),
    ('TUT_ACADE', 'Compromiso académico o laboral urgente'),
    ('TUT_PERSO', 'Imprevisto personal o de salud'),
    ('TUT_OTRO',  'Otro motivo'),]

# Unión para el campo choices del modelo Tutoria
MOTIVOS_CANCELACION = MOTIVOS_CANCELACION_ALUMNO + MOTIVOS_CANCELACION_TUTOR

DURACION_ASESORIA = [
    (0, 'Menos de 30 minutos'),
    (1, '30 minutos'),
    (2, '1 hora'),
    (3, '2 horas'),
    (4, 'Más de dos horas')
]

TUTOR = "TUT"
COORDINADOR = "COR"
ALUMNO = "ALU"
CODA = "CODA"

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

ROLES = [
    ('', "Seleccione Rol"),
    (TUTOR, "Tutor"),
    (COORDINADOR, "Coordinador"),
    (ALUMNO, "Alumno"),
    (CODA, "CODDAA"),
]