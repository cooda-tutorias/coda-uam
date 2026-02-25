from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
#from django.utils.translation import ugettext_lazy
#from django.contrib.auth.models import User
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Usuario, Tutor, Alumno, Coda, Cordinador, Documento

#admin.site.register(Usuario, BaseUserAdmin)
admin.site.register(Documento)

class TutorResource(resources.ModelResource):

    class Meta:
        model = Tutor
        fields = ('id', 'password', 'email', 'coordinacion', 'carrera', 'first_name', 'last_name', 'second_last_name')

class CodaResource(resources.ModelResource):

    class Meta:
        model = Coda
        fields = ('id', 'password', 'email', 'carrera', 'first_name', 'last_name', 'second_last_name')

class CordinadorResource(resources.ModelResource):

    class Meta:
        model = Cordinador
        fields = ('id', 'password', 'email', 'coordinacion', 'carrera', 'first_name', 'last_name', 'second_last_name')

class AlumnoResource(resources.ModelResource):

    def before_save_instance(self, instance, using_transactions, dry_run):
        tmp_password = instance.password
        instance.set_password(tmp_password)

    class Meta:
        model = Alumno
        fields = ('id','password', 'email', 'matricula', 'carrera', 'first_name', 'last_name', 'tutor_asignado', 'second_last_name')


@admin.action(description="Actualiza el rol de los usuarios")
def actualizar_usuarios(modeladmin, request, queryset):
    for obj in queryset:
        obj.save()

@admin.register(Usuario)
class UserAdmin(BaseUserAdmin):
    """Define admin model for custom User model with no email field."""

    fieldsets = (
        (None, {'fields': ('email', 'password', 'matricula')}),
        (('Información Personal'), {'fields': ('first_name', 'last_name','sexo', 'foto')}),
        (('Permisos'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (('Fechas importantes'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email','matricula', 'password1', 'password2', 'sexo'),
        }),
    )
    list_display = ('pk', 'email', 'matricula', 'first_name', 'last_name', 'is_staff', 'sexo')
    search_fields = ('pk', 'email', 'matricula', 'first_name', 'last_name')
    ordering = ('pk',)

    

    
@admin.register(Tutor)
class TutorAdmin(ImportExportModelAdmin, UserAdmin):
    """Define admin model for custom User model with no email field."""

    fieldsets = (
        (None, {'fields': ('email', 'password', 'matricula')}),
        (('Información Personal'), {'fields': ('first_name', 'last_name', 'second_last_name', 'sexo','cubiculo', 'coordinacion', 'foto',)}),
        (('Permisos'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (('Fechas importantes'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name','second_last_name', 'email','matricula', 'coordinacion', 'cubiculo', 'password1', 'password2', 'es_coordinador'),
        }),
    )
    list_display = ('pk', 'email', 'matricula', 'coordinacion', 'first_name', 'last_name', 'second_last_name', 'sexo','is_staff', 'es_coordinador', 'es_tutor')
    search_fields = ('pk', 'email', 'matricula', 'coordinacion', 'first_name', 'last_name')
    ordering = ('pk','coordinacion')

    actions = [actualizar_usuarios]


@admin.register(Coda)
class CodaAdmin(ImportExportModelAdmin, UserAdmin):
    """Define admin model for Coda sin el campo 'coordinacion'."""

    fieldsets = (
        (None, {'fields': ('email', 'password', 'matricula')}),
        (('Información Personal'), {'fields': ('first_name', 'last_name', 'second_last_name', 'cubiculo', 'foto')}),
        (('Permisos'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                   'groups', 'user_permissions')}),
        (('Fechas importantes'), {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'second_last_name', 'email', 'matricula', 'cubiculo', 'password1', 'password2'),
        }),
    )

    list_display = ('pk', 'email', 'matricula', 'first_name', 'last_name', 'second_last_name', 'is_staff', 'es_coordinador')
    search_fields = ('pk', 'email', 'matricula', 'first_name', 'last_name')
    ordering = ('pk',)

    actions = [actualizar_usuarios]


@admin.register(Cordinador)
class CordinadorAdmin(ImportExportModelAdmin, UserAdmin):
    """Define admin model for custom User model with no email field."""

    fieldsets = (
        (None, {'fields': ('email', 'password', 'matricula')}),
        (('Información Personal'), {'fields': ('first_name', 'last_name', 'second_last_name', 'cubiculo', 'coordinacion', 'foto',)}),
        (('Permisos'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (('Fechas importantes'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name','second_last_name', 'email','matricula', 'coordinacion', 'cubiculo', 'password1', 'password2', 'es_tutor'),
        }),
    )
    list_display = ('pk', 'email', 'matricula', 'coordinacion', 'first_name', 'last_name', 'second_last_name', 'is_staff', 'es_coordinador', 'es_tutor')
    search_fields = ('pk', 'email', 'matricula', 'coordinacion', 'first_name', 'last_name')
    ordering = ('pk','coordinacion')

    actions = [actualizar_usuarios]

@admin.register(Alumno)
class AlumnoAdmin(ImportExportModelAdmin, UserAdmin):
    """Define admin model for custom User model with no email field."""

    resource_class = AlumnoResource

    fieldsets = (
        (None, {'fields': ('email', 'password', 'matricula', 'tutor_asignado',)}),
        (('Información Personal'), {'fields': ('first_name', 'last_name', 'second_last_name', 'sexo', 'estado','foto', 'carrera', 'trimestre_ingreso')}),
        (('Permisos'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (('Fechas importantes'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'second_last_name', 'email', 'carrera', 'correo_personal','matricula','tutor_asignado', 'password1', 'password2', 'sexo', 'estado', 'trimestre_ingreso'),
        }),
    )
    list_display = ('pk', 'email', 'matricula', 'carrera', 'first_name', 'last_name', 'second_last_name','sexo', 'estado', 'trimestre_ingreso', 'is_staff')
    search_fields = ('pk', 'email', 'matricula', 'carrera', 'first_name', 'last_name')
    ordering = ('pk','carrera')

    actions = [actualizar_usuarios]