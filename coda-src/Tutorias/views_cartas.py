"""Preparación y descarga de cartas desde la lista de alumnos."""
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from Usuarios.views import CodaViewMixin
from .forms import FormLoteAsignacion
from .services.lotes_asignacion import seleccionar_alumnos, agrupar_alumnos, generar_lote


class LoteAsignacionView(CodaViewMixin, View):
    def post(self, request):
        seleccion = request.POST.get('seleccion', '')
        try:
            alumnos = seleccionar_alumnos(seleccion)
        except ValidationError as error:
            return render(request, 'Tutorias/lote_asignacion.html', {'error_seleccion': error.messages}, status=400)
        if request.POST.get('accion') == 'generar':
            form = FormLoteAsignacion(request.POST)
            if form.is_valid():
                try:
                    nombre, contenido = generar_lote(alumnos, form.cleaned_data)
                except ValidationError as error:
                    form.add_error(None, error)
                else:
                    response = HttpResponse(contenido, content_type='application/zip')
                    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
                    return response
        else:
            form = FormLoteAsignacion(initial={'seleccion': seleccion})
        grupos = agrupar_alumnos(alumnos)
        return render(request, 'Tutorias/lote_asignacion.html', {
            'form': form, 'grupos': grupos, 'total_alumnos': len(alumnos),
            'total_tutores': len({a.tutor_asignado_id for a in alumnos if a.tutor_asignado_id}),
            'total_cartas_tutor': sum(1 for g in grupos if g['tutor']),
            'trimestres': sorted({a.trimestre_ingreso or 'Sin trimestre' for a in alumnos}),
            'licenciaturas': sorted({a.get_carrera_display() for a in alumnos}),
            'sin_tutor': [a for a in alumnos if not a.tutor_asignado_id],
            'seleccion_con_tutor': ','.join(str(a.pk) for a in alumnos if a.tutor_asignado_id),
        })
