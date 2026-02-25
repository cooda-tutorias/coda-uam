from collections.abc import Iterable
from django.db import models, transaction
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from .constants import ROLES, CARRERAS
from Tutorias.constants import TEMAS, OTRO
from .constants import CODA, TUTOR, COORDINADOR, ALUMNO, SEXOS, ESTADOS_ALUMNO

class UserManager(BaseUserManager):
    """Define a model manager for User model with no username field."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular User with the given email and password."""
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('rol', ["USR"])  # Default role
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('rol', ["USR"])  # Ensure a role is set

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)

def usr_pfp_path(instance, filename):
    return f'Usuarios/fotos/usuario_{instance.matricula}/{filename}'

class Usuario(AbstractUser):
    username = None
    matricula = models.CharField(max_length=11, unique=True)
    foto = models.ImageField(null=True, blank=True, upload_to=usr_pfp_path)
    email = models.EmailField(unique=True)
    correo_personal = models.EmailField(max_length=50, blank=True, null=True)
    rol = ArrayField(models.CharField(max_length=8, choices=ROLES), default=list)
    sexo = models.CharField(max_length=30, choices=SEXOS, null=True)
    # first_name y last_name vienen por defecto en el modelo AbstractUser,
    # declaramos second_last_name para tener en cuenta el "apellido materno"
    # por lo tanto: last_name = apellido paterno,
    # second_last_name = apellido materno
    second_last_name = models.CharField(max_length=150, blank=True,null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ['matricula']

    objects = UserManager()

    def __str__(self) -> str:
        return str(self.matricula)
    
    def get_roles(self) -> list:
        return self.rol  # Returns a list of roles

    def has_role(self, role: str) -> bool:
        return role in self.rol  # Check if user has a specific role

class Tutor(Usuario):
    cubiculo = models.IntegerField()
    horario = models.FileField(null=True, blank=True)
    coordinacion = models.CharField(max_length=30, choices=CARRERAS)
    es_coordinador = models.BooleanField(default=False)
    es_tutor = models.BooleanField(default=True)
    tema_tutorias = models.CharField(max_length=4, choices=TEMAS, default=OTRO)

    class Meta:
        verbose_name = 'Tutor'
        verbose_name_plural = 'Tutores'

    def save(self, *args, **kwargs):
        if TUTOR not in self.rol:
            self.rol.append(TUTOR)
        super().save(*args, **kwargs)

class Coda(Usuario):
    cubiculo = models.IntegerField()
    horario = models.FileField(null=True, blank=True)
    es_coordinador = models.BooleanField(default=False)
    tema_tutorias = models.CharField(max_length=4, choices=TEMAS, default=OTRO)

    class Meta:
        verbose_name = 'CODA'
        verbose_name_plural = 'CODAA'

    def save(self, *args, **kwargs):
        if CODA not in self.rol:
            self.rol.append(CODA)
        super().save(*args, **kwargs)

class Cordinador(Usuario):
    cubiculo = models.IntegerField()
    horario = models.FileField(null=True, blank=True)
    coordinacion = models.CharField(max_length=30, choices=CARRERAS)
    es_coordinador = models.BooleanField(default=True)
    es_tutor = models.BooleanField(default=False)
    tutor_tutorias = models.BooleanField(default=True)

    tutor_relacion = models.OneToOneField(
        'Tutor',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='cordinador_relacion'
    )

    class Meta:
        verbose_name = 'Cordinador'
        verbose_name_plural = 'Cordinadores'

    def save(self, *args, **kwargs):
        if COORDINADOR not in self.rol:
            self.rol.append(COORDINADOR)

        with transaction.atomic():
            super().save(*args, **kwargs)

            if self.es_tutor:
                tutor, created = Tutor.objects.update_or_create(
                    id=self.id,
                    defaults={
                        "cubiculo": self.cubiculo,
                        "horario": self.horario,
                        "coordinacion": self.coordinacion,
                        "es_coordinador": True,
                        "es_tutor": True,
                        "email": self.email,
                        "matricula": self.matricula,
                        "first_name": self.first_name,
                        "last_name": self.last_name,
                        "second_last_name":self.second_last_name,
                        "sexo":self.sexo,
                        "rol": self.rol,
                        "password": self.password,
                    },
                )
                self.tutor_relacion = tutor
                super().save(update_fields=['tutor_relacion'])

def alumno_trayectoria_path(instance, filename):
    return f'Usuarios/trayectorias/alumno_{instance.matricula}/{filename}'

class Alumno(Usuario):
    carrera = models.CharField(max_length=30, choices=CARRERAS)
    trayectoria = models.FileField(null=True, blank=True, upload_to=alumno_trayectoria_path)
    tutor_asignado = models.ForeignKey(Tutor, on_delete=models.PROTECT)
    estado = models.IntegerField(choices=ESTADOS_ALUMNO, null=True)
    trimestre_ingreso = models.CharField(max_length=30, null=True)
    rfc = models.CharField(max_length=30, null=True)

    def save(self, *args, **kwargs):
        if ALUMNO not in self.rol:
            self.rol.append(ALUMNO)
        super().save(*args, **kwargs)
        
    def get_estado_display(self):
        dict_estado = dict(ESTADOS_ALUMNO)
        print(" dfansrfnakerfnakfnasdkfansdkfasdkfasmdf ------------------> ", dict_estado)
        return dict_estado.get(self.estado, "Desconocido")
    
    class Meta:
        verbose_name = 'Alumno'
        verbose_name_plural = 'Alumnos'

class Documento(models.Model):
    nombre = models.CharField(max_length=255, unique=True)  # Nombre del archivo
    archivo = models.FileField(upload_to='documentos/')  # Ruta del archivo en el servidor
    fecha_subida = models.DateTimeField(auto_now_add=True)  # Fecha de subida

    def __str__(self):
        return self.nombre
    
    @property
    def nombre_archivo(self):
        return self.archivo.name.split('/')[-1]  # Devuelve solo el nombre del archivo sin la ruta

    #@property
    #def get_tutor_fullname(self) -> str:
    #    return f'{self.tutor_asignado.first_name} {self.tutor_asignado.last_name}'

# class Coordinador(Usuario):
#     coordinacion = models.CharField(max_length=30, choices=CARRERAS)
#     class Meta:
#         verbose_name = 'Coordinador'
#         verbose_name_plural = 'Coordinadores'
   
