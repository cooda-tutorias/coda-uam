"""Preparación y descarga de cartas desde la lista de alumnos."""
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View

from Usuarios.views import CodaViewMixin
from .forms import FormLoteAsignacion, FormMensajesAsignacion, FormPrepararAsignacion
from .services.envios_asignacion import preparar_lote, cargar_lote, eliminar_lote
from .services.correos_asignacion import correos_del_lote, estado_envio, iniciar_envio
from .services.lotes_asignacion import seleccionar_alumnos, agrupar_alumnos, generar_lote


class MensajesAsignacionView(CodaViewMixin, View):
    def post(self, request):
        seleccion = request.POST.get('seleccion', '')
        try:
            alumnos = seleccionar_alumnos(seleccion)
        except ValidationError as error:
            return render(request, 'Tutorias/mensajes_asignacion.html',
                          {'error_seleccion': error.messages}, status=400)
        ids = sorted(a.pk for a in alumnos)
        borrador = request.session.get('mensajes_asignacion', {})
        inicial = borrador.get('datos', {}) if borrador.get('alumnos') == ids else {}
        form = FormMensajesAsignacion(initial={**inicial, 'seleccion': seleccion})
        guardado = False
        if request.POST.get('accion') in ('guardar', 'preparar'):
            form = FormMensajesAsignacion(request.POST)
            if form.is_valid():
                request.session['mensajes_asignacion'] = {'alumnos': ids, 'datos': form.cleaned_data}
                guardado = True
                if request.POST.get('accion') == 'preparar':
                    return PrepararAsignacionView.as_view()(request)
        return render(request, 'Tutorias/mensajes_asignacion.html', {
            'form': form, 'guardado': guardado, 'total_alumnos': len(alumnos),
            'total_tutores': len({a.tutor_asignado_id for a in alumnos if a.tutor_asignado_id}),
            'sin_tutor': sum(not a.tutor_asignado_id for a in alumnos),
        })


class LoteAsignacionView(CodaViewMixin, View):
    preparar_envio = False

    def post(self, request):
        seleccion = request.POST.get('seleccion', '')
        try:
            alumnos = seleccionar_alumnos(seleccion)
        except ValidationError as error:
            return render(request, 'Tutorias/lote_asignacion.html', {'error_seleccion': error.messages}, status=400)
        if request.POST.get('accion') == 'generar':
            form = self.crear_form(request.POST)
            if form.is_valid():
                try:
                    if self.preparar_envio:
                        anterior = request.session.get('lote_asignacion', {})
                        if anterior:
                            try:
                                en_proceso = estado_envio(anterior)['fase'] in ('en_cola', 'enviando')
                            except ValidationError:
                                en_proceso = False
                            if en_proceso:
                                raise ValidationError('Espera a que termine el envío del lote anterior antes de preparar otro.')
                        lote = preparar_lote(alumnos, form.cleaned_data)
                        request.session['lote_asignacion'] = {
                            **lote, 'mensajes': self.mensajes, 'alumnos': sorted(a.pk for a in alumnos),
                            'fecha': form.cleaned_data['fecha'].isoformat(),
                        }
                        eliminar_lote(anterior)
                        url = reverse('cartas-asignacion-preparadas')
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({'url': url})
                        return redirect(url)
                    nombre, contenido = generar_lote(alumnos, form.cleaned_data)
                except ValidationError as error:
                    form.add_error(None, error)
                else:
                    response = HttpResponse(contenido, content_type='application/zip')
                    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
                    return response
        else:
            form = self.crear_form(initial={'seleccion': seleccion})
        grupos = agrupar_alumnos(alumnos)
        return render(request, 'Tutorias/lote_asignacion.html', {
            'form': form, 'grupos': grupos, 'total_alumnos': len(alumnos),
            'preparar_envio': self.preparar_envio,
            'total_tutores': len({a.tutor_asignado_id for a in alumnos if a.tutor_asignado_id}),
            'total_cartas_tutor': sum(1 for g in grupos if g['tutor']),
            'trimestres': sorted({a.trimestre_ingreso or 'Sin trimestre' for a in alumnos}),
            'licenciaturas': sorted({a.get_carrera_display() for a in alumnos}),
            'sin_tutor': [a for a in alumnos if not a.tutor_asignado_id],
            'seleccion_con_tutor': ','.join(str(a.pk) for a in alumnos if a.tutor_asignado_id),
        })

    def crear_form(self, datos=None, **kwargs):
        if self.preparar_envio:
            inicial = {'destinatarios': self.mensajes['destinatarios'], 'formato': 'pdf'}
            inicial.update(kwargs.pop('initial', {}))
            return FormPrepararAsignacion(datos, initial=inicial,
                                          destinatarios=self.mensajes['destinatarios'], **kwargs)
        return FormLoteAsignacion(datos, **kwargs)



class PrepararAsignacionView(LoteAsignacionView):
    preparar_envio = True

    def post(self, request):
        try:
            alumnos = seleccionar_alumnos(request.POST.get('seleccion', ''))
        except ValidationError as error:
            return render(request, 'Tutorias/mensajes_asignacion.html',
                          {'error_seleccion': error.messages}, status=400)
        borrador = request.session.get('mensajes_asignacion', {})
        if borrador.get('alumnos') != sorted(a.pk for a in alumnos):
            return render(request, 'Tutorias/mensajes_asignacion.html', {
                'error_seleccion': ['Vuelve al editor y guarda los mensajes para esta selección.'],
            }, status=400)
        self.mensajes = borrador['datos']
        return super().post(request)


class LotePreparadoView(CodaViewMixin, View):
    def get(self, request):
        try:
            lote = request.session.get('lote_asignacion', {})
            _, cartas = cargar_lote(lote)
            correos = correos_del_lote(lote)
            estado = estado_envio(lote)
        except ValidationError as error:
            return render(request, 'Tutorias/lote_preparado.html', {'errores': error.messages}, status=410)
        for correo in correos:
            correo['resultado'] = estado['correos'].get(correo['id'], {
                'estado': 'pendiente' if correo['valido'] else 'excluido',
                'detalle': '' if correo['valido'] else 'Correo no válido o no registrado.',
            })
        return render(request, 'Tutorias/lote_preparado.html', {
            'cartas': cartas, 'token': lote['token'], 'correos': correos,
            'grupos': [{'tipo': tipo, 'correos': [c for c in correos if c['tipo'] == tipo]}
                       for tipo in ('alumno', 'tutor') if any(c['tipo'] == tipo for c in correos)],
            'total_validos': sum(c['valido'] for c in correos),
            'total_excluidos': sum(not c['valido'] for c in correos),
            'sin_enviar': estado['fase'] == 'sin_enviar',
        })

    def post(self, request):
        lote = request.session.get('lote_asignacion', {})
        try:
            if request.POST.get('token') != lote.get('token'):
                raise ValidationError('El lote cambió. Recarga la página antes de enviar.')
            if request.POST.get('confirmar') != 'si':
                raise ValidationError('Confirma el envío a los destinatarios del lote.')
            if not lote.get('pdf_revisado'):
                raise ValidationError('Abre al menos una carta PDF antes de enviar.')
            iniciar_envio(lote)
        except (ValidationError, OSError) as error:
            errores = error.messages if isinstance(error, ValidationError) else ['No se pudo iniciar el envío. Intenta nuevamente.']
            return JsonResponse({'errores': errores}, status=400)
        return JsonResponse({'iniciado': True})


class EstadoEnvioAsignacionView(CodaViewMixin, View):
    def get(self, request, token):
        lote = request.session.get('lote_asignacion', {})
        if token != lote.get('token'):
            raise Http404('El lote no está disponible.')
        try:
            return JsonResponse({**estado_envio(lote), 'pdf_revisado': bool(lote.get('pdf_revisado'))})
        except ValidationError as error:
            return JsonResponse({'errores': error.messages}, status=410)


class CartaPreparadaPDFView(CodaViewMixin, View):
    def get(self, request, token, indice):
        if token != request.session.get('lote_asignacion', {}).get('token'):
            raise Http404('La carta preparada no está disponible.')
        try:
            carpeta, cartas = cargar_lote(request.session.get('lote_asignacion', {}))
            carta = cartas[indice]
            archivo = (carpeta / carta['archivo']).open('rb')
        except (ValidationError, IndexError, OSError) as error:
            raise Http404('La carta preparada no está disponible.') from error
        respuesta = FileResponse(archivo, content_type='application/pdf',
                                 filename=carta['ruta'].rsplit('/', 1)[-1])
        respuesta['Cache-Control'] = 'private, no-store'
        respuesta['X-Frame-Options'] = 'SAMEORIGIN'
        lote = request.session['lote_asignacion']
        if not lote.get('pdf_revisado'):
            request.session['lote_asignacion'] = {**lote, 'pdf_revisado': True}
        return respuesta
