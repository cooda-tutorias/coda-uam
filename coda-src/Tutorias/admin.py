from django.contrib import admin
from.models import Tutoria
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import CharWidget

# Register your models here.

class TutoriaResource(resources.ModelResource):
    tema_display = fields.Field(column_name='tema', attribute='tema', widget=CharWidget())
    alumno_full_name = fields.Field(column_name='alumno_full_name')
    tutor_full_name = fields.Field(column_name='tutor_full_name')
    alumno_matricula = fields.Field(column_name='alumno_matricula')
    tutor_matricula = fields.Field(column_name='tutor_matricula')

    class Meta:
        model = Tutoria
        fields = ('id', 'tema_display', 'alumno_full_name', 'tutor_full_name', 'descripcion', 'fecha')

    def dehydrate_tema_display(self, tutoria):
        temas_display = [tema for tema in tutoria.get_tema_display()]
        return ', '.join(temas_display)

    def dehydrate_alumno_full_name(self, tutoria):
        return f"{tutoria.alumno.first_name} {tutoria.alumno.last_name}"

    def dehydrate_tutor_full_name(self, tutoria):
        return f"{tutoria.tutor.first_name} {tutoria.tutor.last_name}"
    
    def dehydrate_alumno_matricula(self, tutoria):
        return f"{tutoria.alumno.matricula}"
    
    def dehydrate_tutor_matricula(self, tutoria):
        return f"{tutoria.tutor.matricula}"

class TutoriasAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    """Define admin model for Tutoria objects"""

    resource_class = TutoriaResource
    
    list_display = ('tema_display', 'alumno', 'tutor', 'descripcion', 'fecha')

    def tema_display(self, obj):
        return ', '.join(obj.get_tema_display())
    
    tema_display.short_description = 'Temas'
    
    search_fields = ('tema', 'alumno', 'tutor', 'fecha')

class PlantillaResource(resources.ModelResource):
    titulo_display = fields.Field(column_name='titulo', attribute='titulo', widget=CharWidget())
    archivo = fields.Field(column_name='archivo')

    class Meta:
        model = Tutoria
        fields = ('id', 'titulo', 'nombre_de_archivo')

class PlantillasAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    """Define admin model for Plantilla objects"""

    resource_class = PlantillaResource
    
    list_display = ('titulo', 'archivo')

    search_fields = ('titulo', 'archivo')


admin.site.register(Tutoria, TutoriasAdmin)