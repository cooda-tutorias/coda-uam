from django import forms
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

import qrcode
from django.contrib.auth.mixins import LoginRequiredMixin
# Importa tu mixin de roles
from Usuarios.mixins import ContextConRolesMixin
from django.views.generic import TemplateView

from collections import Counter
from typing import Any, Dict
from django.shortcuts import get_object_or_404, redirect
from django.db.models.query import QuerySet
from django.forms.models import BaseModelForm
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.views.generic.edit import CreateView, UpdateView
from django.views.generic import View, FormView
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail, EmailMessage
from django.contrib import messages
from datetime import datetime, timedelta
import pandas as pd
from urllib3 import request
from .constants import TEMAS

from .models import Tutoria, HistorialCambioTutoria, Asesoria
from .forms import (
    FormTutorias,
    FormEditarTutoriaModal,
    FormSeguimiento,
    FormReporte,
    FormCartasDeAsignacion,
    FormReporteDeTutorias,
    FormTutoriasInSitu,
    ComunicacionMasivaForm,
    FormVerTutorias,
    FormReporteTutoriasMasivo,
)

from Tutorias.signals.events import EventoTutoria
from Tutorias.signals.signals_definitions import tutoria_notification_requested

# from .forms import FormSeguimiento # de nuevo, no estoy seguro, FormReporte

# De esta manera se incluyen todas la constantes.
# TODO: Usar el estándar PEP8 para importar constantes:
# from . import constants
# Pero se tendría que cambiar el código que usa las constantes, por ejemplo:
# constants.TEMAS o constants.PENDIENTE, etc. Esto es más limpio y evita conflictos de nombres.
from .constants import *

from Usuarios.constants import TUTOR, ALUMNO, COORDINADOR, TEMPLATES, ESTADOS_ALUMNO
from Usuarios.views import BaseAccessMixin, CodaViewMixin, TutorViewMixin, AlumnoViewMixin, CordinadorViewMixin
from Usuarios.models import Tutor, Alumno, Cordinador, Coda, HorarioTutor
from Usuarios.models import Documento
from django.http import FileResponse
from django.utils import timezone
from django.utils.safestring import mark_safe
from reportlab.pdfgen import canvas
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from django.shortcuts import get_object_or_404, get_list_or_404

import re, docx, os
from zipfile import ZipFile
from .services.docx_reportes import generar_docx_reporte_tutorias_brindadas

from django.views.generic import TemplateView, FormView
from django.conf import settings
from django.http import (
    FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseForbidden,
    JsonResponse,
)


from icalendar import Calendar, Event

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

# Función para convertir una fecha en formato string a un objeto datetime con zona horaria.
def convertir_fecha_local(valor):
    fecha_sin_zona = datetime.strptime(
        valor,
        "%Y-%m-%dT%H:%M",
    )

    return timezone.make_aware(
        fecha_sin_zona,
        timezone.get_current_timezone(),
    )


def resolver_franja_tutor(slot, valor_franja):
    """Valida y convierte una franja de 30 minutos perteneciente a un horario."""
    try:
        fecha_sin_zona = datetime.fromisoformat(valor_franja)
    except (TypeError, ValueError):
        raise ValueError("La franja seleccionada no tiene un formato válido.")

    hora = fecha_sin_zona.time()
    inicio = datetime.combine(fecha_sin_zona.date(), slot.hora_inicio)
    final = datetime.combine(fecha_sin_zona.date(), slot.hora_fin)
    seleccion = datetime.combine(fecha_sin_zona.date(), hora)

    if (
        fecha_sin_zona.date().weekday() != slot.dia_semana
        or seleccion < inicio
        or seleccion + timedelta(minutes=30) > final
        or (seleccion - inicio).total_seconds() % (30 * 60) != 0
    ):
        raise ValueError("La franja seleccionada no pertenece al horario del tutor.")

    return timezone.make_aware(
        seleccion,
        timezone.get_current_timezone(),
    )

# Función para que el tutor pueda proponer fechas alternativas para la tutoría. 
# Se llama desde la vista de detalle de la tutoría.
@login_required
def proponer_fechas_tutoria(request, pk):
    tutoria = get_object_or_404(Tutoria, pk=pk)

    if tutoria.tutor_id != request.user.pk:
        raise PermissionDenied
    
    if request.method == 'POST':
        propuesta_1_raw = request.POST.get('propuesta_1')
        propuesta_2_raw = request.POST.get('propuesta_2')
        es_reagendacion = request.POST.get('es_reagendacion') == '1'

        if es_reagendacion and tutoria.estado_efectivo != ACEPTADO:
            messages.error(request, "Solo se pueden reagendar tutorías agendadas.")
            return redirect("Panel-tutorias-tutor")

        # Verificar que efectivamente haya al menos una propuesta de fecha.
        if propuesta_1_raw:
            try:
                propuesta_1 = convertir_fecha_local(propuesta_1_raw)
                propuesta_2 = convertir_fecha_local(propuesta_2_raw) if propuesta_2_raw else None
            except ValueError:
                messages.error(
                    request,
                    "Alguna de las fechas proporcionadas no es válida.",
                )
                return redirect("Panel-tutorias-tutor")
                                   
            # Si hay dos propuestas, se envían al alumno para que elija. Si solo hay una, se acepta directamente.
            if propuesta_2_raw:
                # CASO A: Dos fechas -> El alumno debe elegir en su vista
                tutoria.fecha_propuesta_1 = propuesta_1
                tutoria.fecha_propuesta_2 = propuesta_2
                tutoria.estado = PROPUESTA
                tutoria.reagendacion_pendiente = es_reagendacion
                if es_reagendacion:
                    messages.success(request, "Se enviaron al alumno las opciones para reagendar la tutoría.")
                    evento = EventoTutoria.TUT_REAGENDA_2_FECHAS

                else:
                    messages.success(request, "Se han enviado las alternativas de horario al alumno.")
                    evento = EventoTutoria.TUT_PROPONE_2_FECHAS
            else:
                # CASO B: Una sola fecha -> Se reasigna la fecha y se ACEPTA directamente
                tutoria.fecha = propuesta_1
                tutoria.fecha_propuesta_1 = None
                tutoria.fecha_propuesta_2 = None
                tutoria.estado = ACEPTADO
                tutoria.reagendacion_pendiente = False
                messages.success(request, "Se ha actualizado y aceptado la tutoría con la nueva fecha.")
                if es_reagendacion:
                    evento = EventoTutoria.TUT_REAGENDA_1_FECHA
                else:
                    evento = EventoTutoria.TUT_PROPONE_1_FECHA

            tutoria.save()

            # El tutor propuso 1 o 2 fechas para reagendar o aceptar solicitud, el alumno recibe la notificación.
            tutoria_notification_requested.send(
                sender=proponer_fechas_tutoria,
                event=evento,
                tutoria=tutoria,
                actor=request.user,
                recipient=tutoria.alumno,
            )            
        else:
            messages.error(request, "Debes ingresar al menos la Opción 1.")

    return redirect('Panel-tutorias-tutor')

# Función para que el alumno pueda seleccionar una de las fechas propuestas por el tutor.
@login_required
def seleccionar_propuesta_tutoria(request, pk):
    tutoria = get_object_or_404(Tutoria, pk=pk)
    
    if request.method == 'POST':
        opcion_elegida = request.POST.get('opcion_elegida') # '1' o '2'

        if opcion_elegida == '1' and tutoria.fecha_propuesta_1:
            tutoria.fecha = tutoria.fecha_propuesta_1
        elif opcion_elegida == '2' and tutoria.fecha_propuesta_2:
            tutoria.fecha = tutoria.fecha_propuesta_2
        else:
            messages.error(request, "Selección inválida.")
            return redirect('Tutorias-alumno')

        # Se confirma el horario y se resetean las propuestas
        tutoria.estado = ACEPTADO
        tutoria.fecha_propuesta_1 = None
        tutoria.fecha_propuesta_2 = None
        tutoria.reagendacion_pendiente = False
        tutoria.save()

        messages.success(request, "Tu solicitud ha sido agendada con éxito. No faltes a la cita en el día y horario que elegiste 📅.")

        # El alumno eligió una fecha propuesta, el tutor recibe la notifación.
        tutoria_notification_requested.send(
            sender=seleccionar_propuesta_tutoria,
            event=EventoTutoria.ALU_ELIGE_FECHA_PROPUESTA,
            tutoria=tutoria,
            actor=request.user,
            recipient=tutoria.tutor,
        )

    return redirect('Tutorias-alumno')

# Esta función se usa para crear el archivo .ics con información de la 
# fecha de la tutoria para que se pueda agregar el evento a 
# Calendarios de Apple o Outlook.
# Para Google Calendar se usa otro procedimiento.
def descargar_ics_tutoria(request, tutoria_id):
    # 1. Obtener la tutoria
    tutoria = get_object_or_404(Tutoria, pk=tutoria_id)
    
    # 2. Crear el objeto calendario
    cal = Calendar()
    cal.add('prodid', '-//UAM Cuajimalpa//Sistema Tutorias//MX')
    cal.add('version', '2.0')
    
    # 3. Crear el evento
    event = Event()
    event.add('summary', f"Tutoría con {tutoria.alumno.nombre_completo}")
    
    # Manejar los tiempos
    start_time = tutoria.fecha
    end_time = start_time + timedelta(hours=1)
    
    event.add('dtstart', start_time)
    event.add('dtend', end_time)
    
    # Descripción y ubicación (Opcional)
    # Como tu tema es una lista, usamos tu lógica de join si es necesario
    temas_str = ", ".join(tutoria.get_tema_display())
    event.add('description', f"Tema(s): {temas_str}")
    
    # 4. Agregar evento al calendario
    cal.add_component(event)
    
    # 5. Dejar listo el archivo para descarga
    response = HttpResponse(cal.to_ical(), content_type="text/calendar")
    response['Content-Disposition'] = f'attachment; filename="cita_{tutoria.id}.ics"'

    return response


#Funcion para descargar pdf
def carta_tutorados_pdf(request):
    print(request)
    print(request.user)
    tutor_id = int(request.GET.get('tutor-id'))
    print(type(tutor_id))
    print(tutor_id)
    tutor = get_object_or_404(Tutor, matricula=tutor_id)
    print(tutor.coordinacion)
    tutorados = Alumno.objects.filter(tutor_asignado=tutor.pk)
    print(tutorados)
    print(type(tutorados))

    # Crear un buffer de bytes para almacenar el PDF
    buffer = BytesIO()

    # Crear el objeto PDF usando el buffer
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Encabezado del PDF
    header_style = ParagraphStyle(name='HeaderStyle', fontSize=12)
    header_text = 'Asignación de tutorados'
    header_paragraph = Paragraph(header_text, header_style)
    elements.append(header_paragraph)

    # Agregar nombre del tutor
    tutor_name = f'Nombre Tutor: {tutor.first_name} {tutor.last_name}'
    tutor_name_paragraph = Paragraph(tutor_name, header_style)
    elements.append(tutor_name_paragraph)

    # Agregar un espacio en blanco para separar el nombre del tutor de la tabla
    elements.append(Spacer(1, 12))  # Ajusta el segundo valor para controlar la altura de la separación

    # Agregar párrafo
    parrafo = f"""Estimado doctor {tutor.last_name}, como parte del Sistema de Acompañamiento al 
    Alumnado que desarrolla la Universidad Autónoma Metropolitana Unidad Cuajimalpa y con la finalidad de
    propiciar el buen desempeño académico de nuestros alumnos y alumnas desde su ingreso a la Universidad y 
    hasta la conclusión de sus estudios, le comunico que tiene asignados los siguientes miembros del alumnado de 
    la licenciatura en Ingeniería en Computación para su Tutoría y Asesoría."""
    parr_paragraph = Paragraph(parrafo, header_style)
    elements.append(parr_paragraph)

    # Agregar un espacio en blanco para separar el nombre del tutor de la tabla
    elements.append(Spacer(1, 12))  # Ajusta el segundo valor para controlar la altura de la separación

    # Agregar datos como una tabla
    data = [["Trimestre de inicio","Matrícula", 'Apellido 1', 'Apellido 2', 'Nombre(s)']]

    for alumno in tutorados:
        data.append([
            None,
            alumno.matricula,
            alumno.last_name,
            None,
            alumno.first_name,
        ])
        print(f"Alumno completo: {alumno.matricula} {alumno.first_name} {alumno.last_name}")

    # Estilo de la tabla
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.orange),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white), 
        ('GRID', (0, 0), (-1, -1), 1, colors.black), 
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), 
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), 
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12), 
    ])

    # Crear la tabla
    tabla = Table(data)
    tabla.setStyle(style)
    elements.append(tabla)

    # Construir el PDF
    doc.build(elements)

    # Resetear el buffer de bytes al inicio
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'{tutor.last_name.upper()}_TUTORES_ATENDIDOS_21-24.pdf')

#Funcion para descargar pdf
def generar_pdf(request):
    tutor_loggeado = get_object_or_404(Tutor, pk=request.user)

    # Obtener las fechas seleccionadas del formulario HTML
    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin') 
    # Obtención de los checkbox
    alumno = request.GET.get('alumno') 
    fecha = request.GET.get('fecha') 
    hora = request.GET.get('hora') 
    tema = request.GET.get('tema') 
    notas = request.GET.get('notas') 
    todo = request.GET.get('todo')

    # Convertir las fechas de cadena a objetos de fecha si se han proporcionado
    if fecha_inicio_str and fecha_fin_str:
        fecha_inicio = timezone.datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        fecha_fin = timezone.datetime.strptime(fecha_fin_str, '%Y-%m-%d') + timedelta(days=1)
        # Filtrar las tutorías por las fechas seleccionadas
        tutorias_tutor = Tutoria.objects.filter(tutor=tutor_loggeado, fecha__range=(fecha_inicio, fecha_fin))
    else:
        # Si no se han proporcionado fechas, obtener todas las tutorías del tutor
        tutorias_tutor = Tutoria.objects.filter(tutor=tutor_loggeado)

    # Crear un buffer de bytes para almacenar el PDF
    buffer = BytesIO()

    # Crear el objeto PDF usando el buffer
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Encabezado del PDF
    header_style = ParagraphStyle(name='HeaderStyle', fontSize=12)
    header_text = 'Historial tutorias'
    header_paragraph = Paragraph(header_text, header_style)
    elements.append(header_paragraph)

    # Agregar nombre del tutor
    tutor_name = f'Nombre Tutor: {tutor_loggeado.first_name} {tutor_loggeado.last_name} {tutor_loggeado.second_last_name}'
    tutor_name_paragraph = Paragraph(tutor_name, header_style)
    elements.append(tutor_name_paragraph)

    # Agregar un espacio en blanco para separar el nombre del tutor de la tabla
    elements.append(Spacer(1, 12))  # Ajusta el segundo valor para controlar la altura de la separación

    # Agregar datos como una tabla
    data = [["Alumno", 'Fecha', 'Hora', 'Tema', 'Notas']]

    for tutoria in tutorias_tutor:
        data.append([
            f"{tutoria.alumno.first_name} {tutoria.alumno.last_name} {tutoria.alumno.second_last_name}",
            tutoria.fecha.strftime('%Y-%m-%d'),
            tutoria.fecha.strftime('%I:%M %p'),
            # tutoria.get_tema_display(),
            # Agregar lista de temas al pdf
            Paragraph(', '.join(tutoria.get_tema_display())),
            tutoria.descripcion,
        ])

    # Eliminación de columnas
    if todo == None:
        if alumno == None:
            ind = data[0].index("Alumno")
            for i in range(len(data)):
                data[i].remove(data[i][ind])
        if fecha == None:
            ind = data[0].index("Fecha")
            for i in range(len(data)):
                data[i].remove(data[i][ind])
        if hora == None:
            ind = data[0].index("Hora")
            for i in range(len(data)):
                data[i].remove(data[i][ind])
        if tema == None:
            ind = data[0].index("Tema")
            for i in range(len(data)):
                data[i].remove(data[i][ind])
        if notas == None:
            ind = data[0].index("Notas")
            for i in range(len(data)):
                data[i].remove(data[i][ind]) 

    # Estilo de la tabla
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white), 
        ('GRID', (0, 0), (-1, -1), 1, colors.orange), 
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), 
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), 
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12), 
    ])

    # Crear la tabla
    tabla = Table(data)
    tabla.setStyle(style)
    elements.append(tabla)

    # Construir el PDF
    doc.build(elements)

    # Resetear el buffer de bytes al inicio
    buffer.seek(0)

    # Devolver el PDF como una respuesta de archivo
    return FileResponse(buffer, as_attachment=True, filename='tabla.pdf')

#Generar archivo txt de tutorias
def generar_archivo_txt(request,pk):

    # Genera el contenido del archivo de texto (aquí es solo un ejemplo)
    tutor = Tutor.objects.get(pk=pk)
    tutorias = Tutoria.objects.filter(tutor=tutor)

    # Obtener las fechas seleccionadas del formulario HTML
    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin') 

    # Convertir las fechas de cadena a objetos de fecha si se han proporcionado
    if fecha_inicio_str and fecha_fin_str:
        fecha_inicio = timezone.datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        fecha_fin = timezone.datetime.strptime(fecha_fin_str, '%Y-%m-%d') + timedelta(days=1)

        # Filtrar las tutorías por las fechas seleccionadas
        tutorias = Tutoria.objects.filter(tutor=tutor, fecha__range=(fecha_inicio, fecha_fin))
    else:
        # Si no se han proporcionado fechas, obtener todas las tutorías del tutor
        tutorias = Tutoria.objects.filter(tutor=tutor)
    
    contenido = "Tutorias \n"
    for tutoria in tutorias:
        contenido += f"Alumno: {tutoria.alumno.first_name} {tutoria.alumno.last_name} {tutoria.alumno.second_last_name}\n"
        contenido += f"Tutor: {tutoria.tutor.first_name} {tutoria.tutor.last_name} {tutoria.tutor.second_last_name}\n"
        contenido += f"Fecha: {tutoria.fecha}\n"
        contenido += f"Tema: {tutoria.get_tema_display()}\n"
        contenido += f"Notas: {tutoria.descripcion}\n\n"

    # Escribe el contenido en un archivo de texto
    with open("tutoria.txt", "w") as archivo:
        archivo.write(contenido)

    # Abre el archivo de texto y lo sirve como una respuesta HTTP para descargarlo
    with open("tutoria.txt", "rb") as archivo:
        response = HttpResponse(archivo.read(), content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename=archivo.txt'
        return response


# Create your views here.
def index(request):
    return HttpResponse("Tutorias app index placeholder")

def normalizar_numero_oficio(oficio_ingresado, fecha_documento) -> str:
    """Normaliza el número de oficio al formato institucional esperado."""
    if oficio_ingresado in (None, ""):
        return ""

    anio = fecha_documento.year
    return f"DCNI_CODDAA_{int(oficio_ingresado)}_{anio}"

class AceptarTutoriaView(View):
    def post(self, request, pk):
        tutoria = get_object_or_404(Tutoria, pk=pk)
        if not request.user.has_role("TUT") or tutoria.tutor_id != request.user.pk:
            raise PermissionDenied("No tienes permiso para modificar esta tutoría")

        if tutoria.estado == ACEPTADO:
            return redirect(
                f"{reverse('Panel-tutorias-tutor')}?tab=agendadas"
            )

        tutoria.estado = ACEPTADO
        tutoria.save(update_fields=["estado"])

        messages.success(request, f"Haz aceptado la solicitud de tutoría de {tutoria.alumno.nombre_completo}.")

        tutoria_notification_requested.send(
            sender=self.__class__,
            event= EventoTutoria.TUT_ACEPTA_SOLICITUD, #"aceptada",
            tutoria=tutoria,
            actor=request.user,
            recipient=tutoria.alumno
        )
        return redirect(
            f"{reverse('Panel-tutorias-tutor')}?tab=agendadas"
        )

  
class RechazarTutoriaView(View):
    def post(self, request, pk):
        tutoria = get_object_or_404(Tutoria, pk=pk)
        if not request.user.has_role("TUT") or tutoria.tutor_id != request.user.pk:
            raise PermissionDenied("No tienes permiso para modificar esta tutoría")

        if tutoria.estado == RECHAZADO:
            return redirect('Panel-tutorias-tutor')

        motivo = request.POST.get("motivo_rechazo", "").strip()
        if motivo == "otro":
            motivo = request.POST.get("motivo_rechazo_otro", "", ).strip()

        if not motivo:
            messages.error(
                request,
                "Debes seleccionar o escribir una razón para el rechazo.",
            )
            return redirect("Panel-tutorias-tutor")
        
        tutoria.estado = RECHAZADO
        tutoria.motivo_rechazo = motivo
        tutoria.save(update_fields=["estado", "motivo_rechazo"])

        tutoria_notification_requested.send(
            sender=self.__class__,
            event=EventoTutoria.TUT_RECHAZA_SOLICITUD, # "rechazada",
            tutoria=tutoria,
            actor=request.user,
            recipient=tutoria.alumno
        )

        messages.info(
            request,
            (
                "El rechazo se registró correctamente y el alumno será notificado. "
                "No es necesario realizar ninguna acción adicional."
            ),
        )

        return redirect('Panel-tutorias-tutor')

class CancelarTutoriaView(View):
    def post(self, request, pk):
        tutoria = get_object_or_404(Tutoria, pk=pk)

        es_tutor_propietario = (
            request.user.has_role("TUT")
            and tutoria.tutor_id == request.user.pk
        )
        es_alumno_propietario = (
            request.user.has_role("ALU")
            and tutoria.alumno_id == request.user.pk
        )

        if not es_tutor_propietario and not es_alumno_propietario:
            raise PermissionDenied("No tienes permiso para cancelar esta tutoría")

        #TODO: revisar si se debe quitar el estado VENCIDA porque el alumno no puede cancelar una tutoría vencida,
        # solamente lo puede hacer un tutor.
        if es_alumno_propietario:
            if tutoria.estado_efectivo not in [PENDIENTE, VENCIDA, ACEPTADO]:
                messages.error(
                    request,
                    "Esta tutoría ya no se encuentra disponible para cancelación.",
                )
                return redirect('Tutorias-alumno')

            motivo = request.POST.get("motivo_cancelacion", "").strip()
            motivos_validos = dict(MOTIVOS_CANCELACION_ALUMNO)
            detalle_motivo = request.POST.get(
                "detalle_motivo_cancelacion", ""
            ).strip()

            if motivo not in motivos_validos:
                messages.error(request, "Debes seleccionar un motivo de cancelación válido.")
                return redirect('Tutorias-alumno')

            if motivo == "ALU_OTRO" and not detalle_motivo:
                messages.error(request, "Debes escribir el detalle del motivo de cancelación.")
                return redirect('Tutorias-alumno')

            tutoria.estado = CANCELADO
            tutoria.motivo_cancelacion = motivo
            tutoria.detalle_motivo_cancelacion = (
                detalle_motivo if motivo == "ALU_OTRO" else None
            )
            tutoria.cancelado_por = request.user
            tutoria.origen_cancelacion = "ALUMNO"
            tutoria.fecha_propuesta_1 = None
            tutoria.fecha_propuesta_2 = None
            tutoria.reagendacion_pendiente = False
            tutoria.save(update_fields=[
                "estado",
                "motivo_cancelacion",
                "detalle_motivo_cancelacion",
                "cancelado_por",
                "origen_cancelacion",
                "fecha_propuesta_1",
                "fecha_propuesta_2",
                "reagendacion_pendiente",
            ])
            messages.success(request, "La tutoría se canceló correctamente.")

            if tutoria.estado_efectivo == PENDIENTE:
                evento = EventoTutoria.ALU_CANCELA_SOLICITUD
            else:
                evento = EventoTutoria.ALU_CANCELA_AGENDADA

            # El alumno cancela, y el tutor debe recibir notificación.
            tutoria_notification_requested.send(
                sender=self.__class__,
                event= evento, 
                tutoria=tutoria,
                actor=request.user,
                recipient=tutoria.tutor
            )

            return redirect('Tutorias-alumno')

        if tutoria.estado_efectivo != ACEPTADO:
            messages.error(
                request,
                "Esta tutoría ya no se encuentra disponible para cancelación.",
            )
            return redirect('Panel-tutorias-tutor')

        motivo = request.POST.get("motivo_cancelacion", "").strip()
        motivos_validos = dict(MOTIVOS_CANCELACION_TUTOR)
        detalle_motivo = request.POST.get(
            "detalle_motivo_cancelacion", ""
        ).strip()

        if motivo not in motivos_validos:
            messages.error(request, "Debes seleccionar un motivo de cancelación válido.")
            return redirect(
                f"{reverse('Panel-tutorias-tutor')}?tab=agendadas"
            )

        if motivo == "TUT_OTRO" and not detalle_motivo:
            messages.error(request, "Debes escribir el detalle del motivo de cancelación.")
            return redirect(
                f"{reverse('Panel-tutorias-tutor')}?tab=agendadas"
            )

        tutoria.estado = CANCELADO
        tutoria.motivo_cancelacion = motivo
        tutoria.detalle_motivo_cancelacion = (
            detalle_motivo if motivo == "TUT_OTRO" else None
        )
        tutoria.cancelado_por = request.user
        tutoria.origen_cancelacion = "TUTOR"
        tutoria.save(update_fields=[
            "estado",
            "motivo_cancelacion",
            "detalle_motivo_cancelacion",
            "cancelado_por",
            "origen_cancelacion",
        ])
        messages.success(request, "La tutoría agendada se canceló correctamente.")

        # El tutor cancela, y el alumno debe recibir la notificación.
        tutoria_notification_requested.send(
            sender=self.__class__,
            event= EventoTutoria.TUT_CANCELA_AGENDADA, 
            tutoria=tutoria,
            actor=request.user,
            recipient=tutoria.alumno
        )
        
        return redirect(
            f"{reverse('Panel-tutorias-tutor')}?tab=historial"
        )
   

class TutoriaUpdateView(BaseAccessMixin, UpdateView):
    model = Tutoria
    form_class = FormTutorias  # ← Usa tu formulario personalizado
    template_name = 'Tutorias/editarTutoria.html'

    def get_queryset(self) -> QuerySet[Any]:
        queryset = super().get_queryset()

        if self.request.user.has_role("TUT"):
            return queryset.filter(tutor=self.request.user)

        if self.request.user.has_role("ALU"):
            return queryset.filter(alumno=self.request.user)

        return queryset.none()

    def get_success_url(self):
        if self.request.user.has_role("ALU"):
            return reverse_lazy('Tutorias-alumno')
        return reverse_lazy('Tutorias-tutor')

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["historial_cambios"] = self.object.historial_cambios.all()[:20]
        return context

    def _build_change_summary(self, original: Tutoria, form: BaseModelForm, changed_fields: list[str]) -> str:
        """Resume los campos modificados de la tutoría para guardarlos en el historial."""
        field_labels = {
            "tema": "Tema(s)",
            "fecha": "Fecha y Hora",
            "descripcion": "Observaciones",
            "estado": "Estado de la tutoría",
        }
        tema_map = dict(TEMAS)
        estado_map = dict(ESTADO)
        changes = []

        for field in changed_fields:
            if field == "tema":
                old_value = ", ".join(original.get_tema_display())
                new_codes = form.cleaned_data.get("tema", [])
                new_value = ", ".join([tema_map.get(code, code) for code in new_codes])
            elif field == "fecha":
                old_value = original.fecha.strftime('%Y-%m-%d %H:%M')
                new_value = form.cleaned_data.get("fecha").strftime('%Y-%m-%d %H:%M')
            elif field == "descripcion":
                old_value = original.descripcion or ""
                new_value = form.cleaned_data.get("descripcion") or ""
            elif field == "estado":
                old_value = estado_map.get(original.estado, original.estado)
                new_state = form.cleaned_data.get("estado") or getattr(form.instance, "estado", None)
                new_value = estado_map.get(new_state, new_state)
            else:
                old_value = str(getattr(original, field, ""))
                new_value = str(form.cleaned_data.get(field, ""))

            label = field_labels.get(field, field)
            changes.append(f"{label}: '{old_value}' -> '{new_value}'")

        return " | ".join(changes)

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        original = self.get_object()
        changed_fields = list(form.changed_data)
        fecha_changed_by_tutor = self.request.user.has_role("TUT") and "fecha" in changed_fields
        estado_changed_by_tutor = False
        estado_notification_event = None

        if self.request.user.has_role("TUT"):
            nuevo_estado_tutoria = self.request.POST.get("estado_tutoria")
            allowed_states = {ACEPTADO, RECHAZADO}
            if nuevo_estado_tutoria in allowed_states and nuevo_estado_tutoria != original.estado:
                form.instance.estado = nuevo_estado_tutoria
                if "estado" not in changed_fields:
                    changed_fields.append("estado")
                estado_changed_by_tutor = True
                estado_notification_event = "aceptada" if nuevo_estado_tutoria == ACEPTADO else "rechazada"

        change_summary = self._build_change_summary(original, form, changed_fields) if changed_fields else "Sin cambios detectados"
        actor = self.request.user

        # Manejar cambio de estado histórico si viene en el POST y el usuario tiene permiso
        nuevo_estado_raw = self.request.POST.get('estado_alumno_historico')
        if nuevo_estado_raw and not self.request.user.has_role("ALU"):
            try:
                nuevo_estado = int(nuevo_estado_raw)
                if nuevo_estado != original.estado_alumno_historico:
                    from Usuarios.constants import ESTADOS_ALUMNO
                    estado_dict = dict(ESTADOS_ALUMNO)
                    etiqueta_anterior = estado_dict.get(original.estado_alumno_historico, "Sin registro")
                    etiqueta_nueva = estado_dict.get(nuevo_estado, "Desconocido")
                    form.instance.estado_alumno_historico = nuevo_estado
                    estado_change = f"Estado histórico del alumno: '{etiqueta_anterior}' -> '{etiqueta_nueva}'"
                    if change_summary == "Sin cambios detectados":
                        change_summary = estado_change
                    else:
                        change_summary += f" | {estado_change}"
            except (ValueError, TypeError):
                pass

        if self.request.user.has_role("TUT"):
            recipient = Alumno.objects.filter(pk=self.get_object().alumno_id)
        elif self.request.user.has_role("ALU"):
            recipient = Tutor.objects.filter(pk=self.get_object().tutor_id)
        else:
            recipient = Tutor.objects.none()

        # TODO: ajustar el manejador del canal de correo porque el evento ahora se llama diferente.
        tutoria_notification_requested.send(
            sender=self.__class__,
            event="tutoria_modificada",
            tutoria=self.object,
            actor=actor,
            recipient=recipient,
            verb="Tutoria Modificada",
        )
        response = super().form_valid(form)

        # TODO: esta llamada ya no es necesaria porque el tutor no puede cambiar la info de
        # la tutoría (temas y descripción).
        if fecha_changed_by_tutor:
            tutoria_notification_requested.send(
                sender=self.__class__,
                event="cita_programada",
                tutoria=self.object,
                actor=actor,
            )

        # TODO: esta llamada ya no es necesaria porque el tutor no puede cambiar la info de
        # la tutoría (temas y descripción).
        if estado_changed_by_tutor and estado_notification_event:
            tutoria_notification_requested.send(
                sender=self.__class__,
                event=estado_notification_event,
                tutoria=self.object,
                actor=actor,
            )

        HistorialCambioTutoria.objects.create(
            tutoria=self.object,
            correo_editor=actor.email,
            cambios_realizados=change_summary,
        )

        return response
    
    def editar_tutoria(request, pk):
        tutoria = get_object_or_404(Tutoria, pk=pk)

        if request.method == 'POST':
            form = FormTutorias(request.POST, instance=tutoria)
            if form.is_valid():
                form.save()
                return redirect('nombre-de-tu-vista-exitosa')  # Ajusta esto
        else:
            form = FormTutorias(instance=tutoria)

        return render(request, 'tutoria/editar_tutoria.html', {'form': form})
    

class TutoriaModalUpdateView(TutoriaUpdateView):
    """
    Vista para editar los temas y la descripción de una tutoría usando una ventana modal.
    """
    form_class = FormEditarTutoriaModal
    template_name = "Tutorias/includes/_modal_editar_tutoria.html"

    def form_valid(self, form):
        # Reutiliza guardado, historial y notificaciones de la vista original.
        super().form_valid(form)

        recipient = self.request.user.alumno.tutor_asignado

        # El alumno edita detalles, y el alumno debe recibir la notificación.
        tutoria_notification_requested.send(
            sender=self.__class__,
            event= EventoTutoria.ALU_EDITA_INFO_TUTORIA, 
            tutoria=self.object,
            actor=self.request.user, # Debería ser el alumno porque solamente puede editar desde UI.
            recipient=recipient
        )

        return JsonResponse({
            "ok": True,
            "message": "La tutoría se actualizó correctamente.",
        })

    def form_invalid(self, form):
        response = self.render_to_response(
            self.get_context_data(form=form)
        )
        response.status_code = 422
        return response

    
# Solicitud Tutorias
# API para devolver los slots de un tutor
@login_required
@require_GET
def api_slots_tutor(request, tutor_id):
    slots = HorarioTutor.objects.filter(tutor_id=tutor_id, activo=True)
    print(slots)  # en consola del servidor

    data = {
        "slots": [
            {
                "id": slot.id,
                "dia_semana_num": slot.dia_semana,  # Tiene los días así (0=Lunes..6=Domingo)
                "dia_semana": slot.get_dia_semana_display(),
                "hora_inicio": slot.hora_inicio.strftime("%H:%M:%S"),
                "hora_fin": slot.hora_fin.strftime("%H:%M:%S"),
                "nombre": f"{slot.get_dia_semana_display()} {slot.hora_inicio.strftime('%H:%M')}–{slot.hora_fin.strftime('%H:%M')}"
            }
            for slot in slots
        ]
    }
    return JsonResponse(data)



# API para devolver las fechas futuras disponibles de un slot
@login_required
@require_GET
def api_fechas_slot(request, slot_id):
    try:
        slot = HorarioTutor.objects.get(id=slot_id, activo=True)
    except HorarioTutor.DoesNotExist:
        return JsonResponse({"fechas": []})

    hoy = timezone.localdate()
    fechas = []

    dias_semana = [
        "Lunes", "Martes", "Miércoles", "Jueves", "Viernes",
        "Sábado", "Domingo"
    ]
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre",
        "diciembre"
    ]

    for i in range(28):
        dia = hoy + timedelta(days=i)

        if dia.weekday() == slot.dia_semana:
            fecha_legible = f"{dias_semana[dia.weekday()]}, {dia.day} de {meses[dia.month - 1]}"

            fechas.append({
                "fecha_iso": dia.isoformat(),
                "fecha_legible": fecha_legible
            })

    return JsonResponse({"fechas": fechas})



def obtener_franjas_disponibles_api(request, tutor_id):
    """
    Retorna las franjas disponibles de 30 minutos para una fecha dada (?fecha=YYYY-MM-DD).
    """
    fecha_str = request.GET.get('fecha')
    if not fecha_str:
        return JsonResponse({'error': 'Parámetro fecha requerido'}, status=400)
    
    fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    dia_semana_py = fecha_dt.weekday() # 0=Lunes, 1=Martes...

    # Mapeo según cómo tengas guardado el día de la semana en HorarioTutor
    horarios_tutor = HorarioTutor.objects.filter(
        tutor_id=tutor_id,
        dia_semana=dia_semana_py,
        activo=True
    )

    # Tutorías agendadas en ese día para evitar colisiones
    tutorias_existentes = Tutoria.objects.filter(
        tutor_id=tutor_id,
        fecha__date=fecha_dt,
        estado__in=[PENDIENTE, ACEPTADO],
    )
    horas_ocupadas = [t.fecha.strftime("%H:%M") for t in tutorias_existentes if t.fecha]

    franjas = []
    duracion = timedelta(minutes=30)

    for h in horarios_tutor:
        actual = datetime.combine(fecha_dt, h.hora_inicio)
        limite = datetime.combine(fecha_dt, h.hora_fin)

        while actual + duracion <= limite:
            hora_inicio_str = actual.strftime("%H:%M")
            if hora_inicio_str not in horas_ocupadas:
                franjas.append({
                    'slot_id': h.id,
                    'hora_inicio': hora_inicio_str,
                    'hora_fin': (actual + duracion).strftime("%H:%M"),
                    'datetime_iso': actual.isoformat()
                })
            actual += duracion

    return JsonResponse({'franjas': franjas})


@login_required
@require_POST
def solicitar_cambio_fecha_tutoria(request, pk):
    """Permite al alumno cambiar una solicitud o pedir reagendar una cita."""
    tutoria = get_object_or_404(Tutoria, pk=pk)

    if tutoria.alumno_id != request.user.pk or not request.user.has_role("ALU"):
        raise PermissionDenied("No tienes permiso para modificar esta tutoría")

    if tutoria.estado_efectivo not in (PENDIENTE, ACEPTADO):
        messages.error(request, "Esta tutoría ya no permite solicitar un cambio de fecha.")
        return redirect("Tutorias-alumno")

    horario_id = request.POST.get("horario_tutor", "").strip()
    franja_seleccionada = request.POST.get("franja_seleccionada", "").strip()
    fecha_sugerida = request.POST.get("fecha_sugerida", "").strip()

    try:
        if horario_id:
            slot = HorarioTutor.objects.get(pk=horario_id, tutor=tutoria.tutor, activo=True)
            nueva_fecha = resolver_franja_tutor(slot, franja_seleccionada)
            nuevo_estado = ACEPTADO
        else:
            nueva_fecha = convertir_fecha_local(fecha_sugerida)
            nuevo_estado = PENDIENTE
    except (HorarioTutor.DoesNotExist, TypeError, ValueError):
        messages.error(request, "La fecha u horario seleccionado no es válido.")
        return redirect("Tutorias-alumno")

    if nueva_fecha <= timezone.now():
        messages.error(request, "La nueva fecha debe ser posterior a la fecha actual.")
        return redirect("Tutorias-alumno")

    if horario_id and Tutoria.objects.filter(
        tutor=tutoria.tutor,
        fecha=nueva_fecha,
        estado__in=[PENDIENTE, ACEPTADO],
    ).exclude(pk=tutoria.pk).exists():
        messages.error(request, "Ese horario acaba de ocuparse. Selecciona otro.")
        return redirect("Tutorias-alumno")

    fecha_anterior = timezone.localtime(tutoria.fecha)
    tutoria.fecha = nueva_fecha
    tutoria.estado = nuevo_estado
    tutoria.fecha_propuesta_1 = None
    tutoria.fecha_propuesta_2 = None
    tutoria.reagendacion_pendiente = False
    tutoria.save(update_fields=[
        "fecha", "estado", "fecha_propuesta_1", "fecha_propuesta_2",
        "reagendacion_pendiente",
    ])

    HistorialCambioTutoria.objects.create(
        tutoria=tutoria,
        correo_editor=request.user.email,
        cambios_realizados=(
            f"Solicitud de cambio de fecha: '{fecha_anterior:%d/%m/%Y %H:%M}' "
            f"-> '{timezone.localtime(nueva_fecha):%d/%m/%Y %H:%M}'"
        ),
    )
    tutoria_notification_requested.send(
        sender=solicitar_cambio_fecha_tutoria,
        event="tutoria_modificada",
        tutoria=tutoria,
        actor=request.user,
        recipient=Tutor.objects.filter(pk=tutoria.tutor_id),
        verb="Solicitud de cambio de fecha",
    )

    if nuevo_estado == ACEPTADO:
        messages.success(request, "La tutoría se reagendó en un horario disponible del tutor.")
    else:
        messages.success(request, "La nueva fecha se envió al tutor para su confirmación.")
    return redirect("Tutorias-alumno")

    
# Vista para que el ALUMNO solicite tutorias, ya sea:
# a) eligiendo uno de los horarios predefinidos por su tutor, o si no ha definido,
# a) sugiriendo una fecha a su tutor para la cita que debe ser aceptado o rechazado.

# El método form_valid se encarga de notificar al tutor por estos medios:
# a) notificación del sistema web.
# b) correo con la información de la cita.
# c) notificación web push si la tiene habilitada en su navegador.

class TutoriaCreateView(AlumnoViewMixin, CreateView):
    model = Tutoria
    form_class = FormTutorias
    template_name = 'Tutorias/solicitudTutoria.html'
    success_url = reverse_lazy('Tutorias-alumno')


    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        alumno = getattr(self.request.user, "alumno", None)
        tutor = getattr(alumno, "tutor_asignado", None)

        context["tutor"] = tutor

        # Validar si el tutor tiene horarios de atención activos registrados
        tiene_horarios = False
        if tutor:
            tiene_horarios = HorarioTutor.objects.filter(tutor=tutor, activo=True).exists()

        if tiene_horarios:
            titulo = "Agendar tutoría"
            texto_boton = "Agendar tutoría"
            alerta_texto = "Estás por agendar una tutoría dentro de los horarios definidos por tu tutor."
            alerta_tipo = "success"
            subtitulo_modal = "Tu tutor(a) definió horarios de atención. Selecciona un día y un horario disponible."
        else:
            titulo = "Solicitar tutoría"
            texto_boton = "Solicitar tutoría"
            alerta_texto = "Estás por solicitar una tutoría. Debes sugerir una fecha y hora."
            alerta_tipo = "warning"
            subtitulo_modal = "Tu tutor(a) aún no registra horarios de atención para tutorías. Pero puedes sugerirle una fecha para visitarlo."

        info_adicional = "Información adicional sobre la tutoría."

        # Colocar todas las variantes de clave que usamos en plantillas anteriores
        context["tiene_horarios"] = tiene_horarios
        context["titulo_formulario"] = titulo
        context["titulo_form"] = titulo              # compatibilidad
        context["texto_boton"] = texto_boton
        context["boton_texto"] = texto_boton         # compatibilidad
        context["info_adicional"] = info_adicional
        context["alerta_texto"] = alerta_texto
        context["alerta_tipo"] = alerta_tipo
        context["subtitulo_modal"] = subtitulo_modal

        # Si ya se eligió fecha mediante el modal
        fecha_cita = self.request.session.get("fecha_cita", None)
        context["fecha_cita"] = fecha_cita

        return context

    
    def form_valid(self, form: FormTutorias) -> HttpResponse:
        alumno = get_object_or_404(Alumno, pk=self.request.user)
        tutor = alumno.tutor_asignado

        # ====================================================
        # 1) Validar que el alumno tenga un tutor asignado y asignar los objetos a la tutoría
        # ====================================================
        if not tutor:
            form.add_error(None, "No tienes un tutor asignado.")
            return self.form_invalid(form)

        form.instance.alumno = alumno
        form.instance.tutor = tutor

        # Snapshot del estado del alumno al momento de crear la tutoría
        if not form.instance.estado_alumno_historico:
            form.instance.estado_alumno_historico = alumno.estado


        # ====================================================
        # 2) Leer valores ocultos enviados por el modal
        # ====================================================
        request = self.request
        horario_id = request.POST.get("horario_tutor")
        franja_seleccionada = request.POST.get("franja_seleccionada")
        fecha_final = request.POST.get("fecha_sugerida")

        if not horario_id and not fecha_final:
            form.add_error(None, "Debes elegir un horario o sugerir una fecha.")
            return self.form_invalid(form)

        # ====================================================
        # 3) Guardar temas correctamente (el modelo requiere lista)
        # ====================================================
        form.instance.tema = form.cleaned_data["tema"]  # es lista, y es válido para ArrayField


        # ====================================================
        # 4) Asignación de fecha
        # ====================================================

        # Caso donde el alumno elige un horario de los disponibles del tutor (Agenda cita).
        if horario_id:
            alumno_sugirio = False

            slot = HorarioTutor.objects.filter(pk=horario_id, tutor=tutor).first()
            if not slot:
                form.add_error(None, "El horario seleccionado ya no está disponible.")
                return self.form_invalid(form)

            if not franja_seleccionada:
                form.add_error(None, "Debes elegir una franja para el horario.")
                return self.form_invalid(form)

            try:
                fecha_final_dt = resolver_franja_tutor(slot, franja_seleccionada)
            except ValueError as error:
                form.add_error(None, str(error))
                return self.form_invalid(form)

            if Tutoria.objects.filter(
                tutor=tutor,
                fecha=fecha_final_dt,
                estado__in=[PENDIENTE, ACEPTADO],
            ).exists():
                form.add_error(None, "Ese horario acaba de ocuparse. Selecciona otro.")
                return self.form_invalid(form)

            form.instance.fecha = fecha_final_dt

            # Como eligió un horarios disponible del tutor, se considera ya ACEPTADA la cita.
            form.instance.estado = "ACE"
            messages.success(request, "Tu solicitud ha sido agendada con éxito. No faltes a la cita en el día y horario que elegiste 📅.")
        else:
            # Caso donde el tutor no tenía horarios registrados y
            # el alumno sugirió una fecha para la cita (Solicita cita).
            alumno_sugirio = True

            # fecha_final ya tiene el formato '2025-11-24T10:00'
            try:
                form.instance.fecha = datetime.fromisoformat(fecha_final)

                # Como el alumno sugirió una fecha, queda PENDIENTE hasta que el
                # tutor acepte la tutoría en esa fecha.
                form.instance.estado = "PEN"
                messages.warning(request, "Tu solicitud de tutoría ha sido enviada. Espera la respuesta de tu tutor ⏳.")
            except(ValueError, TypeError):
                form.add_error(None, "No enviaste una fecha válida.")
                return self.form_invalid(form)

        # Mensaje corto para saber si es tutoría agendada o solicitada.
        resumen_notificacion="Nueva solicitud de tutoría"
        evento = EventoTutoria.ALU_SOLICITA_TUTORIA

        if not alumno_sugirio:
            resumen_notificacion="Nueva tutoría agendada"
            evento = EventoTutoria.ALU_AGENDA_TUTORIA

        # Eliminar corchetes de la lista
        # El alumno solicita o agenda una tutoría, y el tutor debe recibir la notificación.
        tutoria_notification_requested.send(
            sender=self.__class__,
            event=evento,
            tutoria=form.instance,
            actor=alumno,
            recipient=tutor,
            description=f'{", ".join(form.instance.get_tema_display())}',
        )
        
        # TODO utilizar una rutina para mandar los correos
        #send_mail(
         #   subject='Nueva solicitud de tutoria',
          #  message=f'Solicitud de tutoria creada por {alumno.get_full_name()} con tema: {form.instance.get_tema_display()}',
           # from_email=CORREO,
            #recipient_list=[recipient.email],
            #fail_silently=False
    
        return super().form_valid(form)
    

    def get_initial(self) -> dict[str, Any]:
        return super().get_initial()
    
# Carta de notificación de tutorados (para el tutor)
class ReporteCreateView(CodaViewMixin, CreateView):
    model = Coda
    form_class = FormReporte
    template_name = 'Tutorias/generartutorados.html'
    success_url = reverse_lazy('Tutorados-Coda')  # Cambia esto a la URL adecuada

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        tutor_pk = self.kwargs.get('pk')
        tutor_instance = Tutor.objects.get(pk=tutor_pk)
        kwargs['tutor_instance'] = tutor_instance
        return kwargs

    def form_valid(self, form):
        # Obtén el nombre del alumno desde la URL
        tutor_pk = self.kwargs.get('pk_tutor')

        # Busca el alumno por nombre
        tutor = get_object_or_404(Tutor, pk=tutor_pk)

        # Completa el formulario con los datos del alumno
        form.instance.tutor = tutor

        return super().form_valid(form)
    
    def paragraph_replace_text(self,paragraph, regex, replace_str):
        while True:
            text = paragraph.text
            match = regex.search(text)
            if not match:
                break

            # --- when there's a match, we need to modify run.text for each run that
            # --- contains any part of the match-string.
            runs = iter(paragraph.runs)
            start, end = match.start(), match.end()

            # --- Skip over any leading runs that do not contain the match ---
            for run in runs:
                run_len = len(run.text)
                if start < run_len:
                    break
                start, end = start - run_len, end - run_len

            # --- Match starts somewhere in the current run. Replace match-str prefix
            # --- occurring in this run with entire replacement str.
            run_text = run.text
            run_len = len(run_text)
            run.text = "%s%s%s" % (run_text[:start], replace_str, run_text[end:])
            end -= run_len  # --- note this is run-len before replacement ---

            # --- Remove any suffix of match word that occurs in following runs. Note that
            # --- such a suffix will always begin at the first character of the run. Also
            # --- note a suffix can span one or more entire following runs.
            for run in runs:  # --- next and remaining runs, uses same iterator ---
                if end <= 0:
                    break
                run_text = run.text
                run_len = len(run_text)
                run.text = run_text[end:]
                end -= run_len

        # --- optionally get rid of any "spanned" runs that are now empty. This
        # --- could potentially delete things like inline pictures, so use your judgement.
        # for run in paragraph.runs:
        #     if run.text == "":
        #         r = run._r
        #         r.getparent().remove(r)

        return paragraph

    def post(self, request,pk):
        form = request.POST
        oficio_form = form.get('oficio')
        plantilla_nombre = form.get('plantilla')
        fecha_form = form.get('fecha')
        fecha_form = datetime.strptime(fecha_form,'%Y-%m-%dT%H:%M').date()
        oficio_form = normalizar_numero_oficio(oficio_form, fecha_form)
        tutor_pk = self.kwargs.get('pk')
        
        plantilla = get_object_or_404(Documento, nombre=plantilla_nombre)
        tutor = get_object_or_404(Tutor, pk=tutor_pk)
        open_plantilla = docx.Document(plantilla.archivo)   

        # Verifica si el archivo tiene tablas
        if not open_plantilla.tables:
            messages.error(request, "Este archivo no es compatible con el tipo de carta que deseas generar")
            return redirect('Reporte-create', pk=pk)

        #Creación de las expresiones regulares que se buscaran en el doc
        reg_placeh = re.compile(r'\{.*?\}') #Placeholder "{}"
        reg_ofi = re.compile(r'\{no_oficio\}') #Número de oficio
        reg_fech =re.compile( r'\{fecha\}') #Fecha
        reg_tut = re.compile(r'\{nombre_mayus_tutor\}') #Nombre de tutor en mayusculas
        reg_est = re.compile(r'\{estimado\}') # indentificamos el articulo en minusculas
        reg_tut_min = re.compile(r'\{nombre_tutor\}')
        reg_lic = re.compile(r'\{licenciatura\}')

        tut_alums = Alumno.objects.filter(tutor_asignado=tutor_pk)
        
        ## EDICIÓN DE LA TABLA
        # Find the table you want to replace (assuming it's the first table)
        old_table = open_plantilla.tables[0]
        
        # Extract headers from the first row
        headers = [cell.text for cell in old_table.rows[0].cells]
        
        # Extract table style
        table_style = old_table.style

        # Find the parent element of the table (usually a paragraph)
        parent = old_table._element.getparent()

        # Insert a placeholder before removing the old table
        placeholder = open_plantilla.add_paragraph()
        parent.insert(parent.index(old_table._element), placeholder._element)

        # Remove the old table
        parent.remove(old_table._element)

        # Insert the new table at the placeholder position
        new_table = open_plantilla.add_table(rows=1, cols=len(headers))
        new_table.style = table_style
        placeholder._element.addnext(new_table._element)
        
        # Extract column widths
        column_widths = [cell.width for cell in old_table.rows[0].cells]

        # Apply column widths
        for i, width in enumerate(column_widths):
            new_table.columns[i].width = width

        # Populate headers
        header_cells = new_table.rows[0].cells
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i]._element.get_or_add_tcPr().append(
                docx.oxml.parse_xml(r'<w:shd {} w:fill="BFBFBF"/>'.format(docx.oxml.ns.nsdecls('w')))
            )

        # Copy paragraph styles and cell formatting from old headers
        for i, old_cell in enumerate(old_table.rows[0].cells):
            new_cell = new_table.rows[0].cells[i]
            new_cell.paragraphs[0].style = old_cell.paragraphs[0].style
            new_cell._element.get_or_add_tcPr().extend(old_cell._element.get_or_add_tcPr())

        # Populate the new table with filtered data
        for obj in tut_alums:
            # apellidos = re.findall(r'[A-Z][a-z]*', obj.last_name)
            # apellidos = re.findall(r'[A-Z][a-z]*', obj.last_name)
            # apellidos = re.findall(r'[A-Z][a-z]*', obj.last_name) + [''] * (2 - len(re.findall(r'[A-Z][a-z]*', obj.last_name)))
            row_cells = new_table.add_row().cells
            row_cells[0].text = str(obj.trimestre_ingreso)  # Replace with actual fields
            row_cells[1].text = str(obj.matricula)  # Replace with actual fields
            # row_cells[2].text = str(obj.last_name)
            row_cells[2].text = str(obj.last_name) #Si el modelo tiene un campo para segundo apellido, agregar
            row_cells[3].text = str(obj.second_last_name) #Si el modelo tiene un campo para segundo apellido, agregar
            row_cells[4].text = str(obj.first_name)  # Replace with actual fields
        
        # Ensure data rows inherit cell formatting from old table
        for row_index, row in enumerate(new_table.rows[1:]):
            old_row = old_table.rows[min(row_index + 1, len(old_table.rows) - 1)]  # Avoid index out of bounds
            for cell_index, cell in enumerate(row.cells):
                old_cell = old_row.cells[cell_index]
                cell.paragraphs[0].style = old_cell.paragraphs[0].style
                cell._element.get_or_add_tcPr().extend(old_cell._element.get_or_add_tcPr())

        # Antes del ciclo for p in open_plantilla.paragraphs:
        self.est = ""
        self.dr = ""
        self.name = ""
        self.name = f"{tutor.first_name} {tutor.last_name}"
        self.nombre_licenciatura = ""
        if tutor.sexo == "M":
            # print(f'Masculino')
            self.est = "Estimado"
            self.dr = "Dr."
        if tutor.sexo == "F":
            self.est = "Estimada"
            self.dr = "Dra."
        if tutor.second_last_name:
            self.name = self.name + f" {tutor.second_last_name}"

        carreras_dict = {
            "MAT": "Matemáticas Aplicadas",
            "COM": "Ingeniería en Computación",
            "IB": "Ingeniería Biológica",
            "BM": "Biología Molecular"
        }
        self.nombre_licenciatura = carreras_dict.get(tutor.coordinacion, "Licenciatura desconocida")

        ##EDICIÓN DE LOS PLACEHOLDERS
        c=0
        for p in open_plantilla.paragraphs:
            c = c+1
            # print(c)
            line = p.text
            result = []
            line_matches = [] if (result := re.findall(reg_placeh,line)) is None else result
            # print(f'Before cycle: {(line_matches)}') if line_matches else None 

            for match in line_matches:
                print(f'Esta linea: {match} hizo match')
                if re.search(reg_ofi,match):
                    self.paragraph_replace_text(p, reg_ofi, f"{oficio_form}").text
                if re.match(reg_fech,match):
                    self.paragraph_replace_text(p, reg_fech, f"{fecha_form}").text
                if re.match(reg_tut,match):
                    print(f'IF de tutor')
                    print(f'Sexo: {tutor.sexo}')
                    self.paragraph_replace_text(p, reg_tut,(self.dr+" "+self.name).upper()).text
                if re.match(reg_est,match):
                    self.paragraph_replace_text(p, reg_est, self.est)
                if re.match(reg_tut_min,match):
                    self.paragraph_replace_text(p, reg_tut_min, self.dr+" "+self.name)
                if re.match(reg_lic, match):
                    self.paragraph_replace_text(p,reg_lic, self.nombre_licenciatura)

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'attachment; filename={tutor.last_name}_TUTORES_ATENDIDOS.docx'
        
        open_plantilla.save(response)
        
        return response
        # return FileResponse(buffer, as_attachment=True, filename=f'{tutor.last_name.upper()}_TUTORES_ATENDIDOS_21-24.pdf')
        # return super().post(request)

# Carta de asignación tutor para alumno (para el alumno)
class Reporte2CreateView(CodaViewMixin, CreateView):
    model = Coda
    form_class = FormCartasDeAsignacion
    template_name = 'Tutorias/generarnotiftutor.html'
    success_url = reverse_lazy('Tutorados-Coda')  # Cambia esto a la URL adecuada

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        tutor_pk = self.kwargs.get('pk')
        tutor_instance = Tutor.objects.get(pk=tutor_pk)
        kwargs['tutor_instance'] = tutor_instance
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get selected students from URL parameters
        selected_ids = self.request.GET.getlist('selected_alumnos')
        if not selected_ids:
                selected_ids = self.request.session.get('selected_alumnos', [])
        print(selected_ids)
        
        # Fetch student objects from the database
        alumnos = get_list_or_404(Alumno, pk__in=selected_ids)

        # Pass single or multiple students to template
        context['alumnos'] = alumnos
        context['is_multiple'] = len(alumnos) > 1  # True if multiple students
        context['len_alumnos'] = len(alumnos) # Lenght of students selected

        self.request.session.pop('selected_alumnos', None)

        return context

    def form_valid(self, form):
        # Obtén el nombre del alumno desde la URL
        tutor_pk = self.kwargs.get('pk_tutor')

        # Busca el alumno por nombre
        tutor = get_object_or_404(Tutor, pk=tutor_pk)

        # Completa el formulario con los datos del alumno
        form.instance.tutor = tutor

        return super().form_valid(form)
    
    def paragraph_replace_text(self,paragraph, regex, replace_str):
        while True:
            text = paragraph.text
            match = regex.search(text)
            if not match:
                break

            # --- when there's a match, we need to modify run.text for each run that
            # --- contains any part of the match-string.
            runs = iter(paragraph.runs)
            start, end = match.start(), match.end()

            # --- Skip over any leading runs that do not contain the match ---
            for run in runs:
                run_len = len(run.text)
                if start < run_len:
                    break
                start, end = start - run_len, end - run_len

            # --- Match starts somewhere in the current run. Replace match-str prefix
            # --- occurring in this run with entire replacement str.
            run_text = run.text
            run_len = len(run_text)
            run.text = "%s%s%s" % (run_text[:start], replace_str, run_text[end:])
            end -= run_len  # --- note this is run-len before replacement ---

            # --- Remove any suffix of match word that occurs in following runs. Note that
            # --- such a suffix will always begin at the first character of the run. Also
            # --- note a suffix can span one or more entire following runs.
            for run in runs:  # --- next and remaining runs, uses same iterator ---
                if end <= 0:
                    break
                run_text = run.text
                run_len = len(run_text)
                run.text = run_text[end:]
                end -= run_len

        # --- optionally get rid of any "spanned" runs that are now empty. This
        # --- could potentially delete things like inline pictures, so use your judgement.
        # for run in paragraph.runs:
        #     if run.text == "":
        #         r = run._r
        #         r.getparent().remove(r)

        return paragraph

    def post (self, request, pk):
        selected_ids = self.request.GET.getlist('selected_alumnos')

        form = request.POST
        oficio_form = form.get('oficio')
        plantilla_nombre = form.get('plantilla')
        fecha_form = form.get('fecha')
        no_inicio_form = form.get('no_inicio')
        fecha_form = datetime.strptime(fecha_form,'%Y-%m-%dT%H:%M').date()
        
        tutor_pk = self.kwargs.get('pk')
        alumnos = get_list_or_404(Alumno, pk__in=selected_ids)
        plantilla = get_object_or_404(Documento, nombre=plantilla_nombre)
        tutor = get_object_or_404(Tutor, pk=tutor_pk)
        
        open_plantilla = docx.Document(plantilla.archivo)   
        if open_plantilla.tables:
            messages.error(request, "Este archivo no es compatible con el tipo de carta que deseas generar")

            # Obtener la URL base con el PK del tutor
            url_base = f"/crear-reporte-2/{tutor_pk}"

            # Agregar los parámetros GET con los alumnos seleccionados
            selected_param = "&".join([f"selected_alumnos={id}" for id in selected_ids])
            redirect_url = f"{url_base}?{selected_param}"

            return redirect(redirect_url)

        #Creación de las expresiones regulares que se buscaran en el doc
        reg_placeh = re.compile(r'\{.*?\}') #Placeholder "{}"
        reg_gen = re.compile(r'\{(a|o|e)\}') #Género
        reg_palab_tutor = re.compile(r'\{tutor*\}')
        reg_tut = re.compile(r'\{dr\}') #Tutor ex. Dr/doctor Algo
        reg_fech =re.compile( r'\{fecha\}') #Fecha
        reg_ofi = re.compile(r'\{no_oficio\}') #Número de oficio
        reg_nombre_alumno = re.compile(r'\{nombre_alumno\}') # nombre del alumno
        reg_licenciatura = re.compile(r'\{licenciatura\}') # licenciatura
        reg_det = re.compile(r'\{(la|el|él)\}')
        reg_academico = re.compile(r'\{academico\}')
        reg_nombre_tutor = re.compile(r'\{nombre_tutor\}')
        reg_asignacion = re.compile(r'\{asignado\}')
        reg_reasignacion = re.compile(r'\{reasignado\}')

        # Esta validacion es para generar una sola carta de asignación y no generar el zip de forma innecesaria.
        if len(alumnos) == 1:
            alumno = alumnos[0]
            open_plantilla = docx.Document(plantilla.archivo)
            c=0
            for p in open_plantilla.paragraphs:
                c = c+1
                # print(c)
                line = p.text
                result = []
                line_matches = [] if (result := re.findall(reg_placeh,line)) is None else result
                for match in line_matches:
                    if re.search(reg_ofi,match):
                        self.paragraph_replace_text(p, reg_ofi, f"{oficio_form}").text
                    if re.match(reg_fech,match):
                        self.paragraph_replace_text(p, reg_fech, f"{fecha_form}").text
                    # if re.match(reg_tut,match):
                    #     print(f"Tutor IF")
                    #     self.paragraph_replace_text(p, reg_tut, f"Doctor {tutor.last_name}").text
                    if re.match(reg_palab_tutor,match):
                        if tutor.sexo == "M":
                            self.paragraph_replace_text(p, reg_palab_tutor, f"tutor".capitalize()).text
                        if tutor.sexo == "F":
                            self.paragraph_replace_text(p, reg_palab_tutor, f"tutora".capitalize()).text
                    if re.match(reg_tut,match):
                        if tutor.sexo == "M":
                            self.paragraph_replace_text(p, reg_tut, f"Dr.").text
                        if tutor.sexo == "F":
                            self.paragraph_replace_text(p, reg_tut, f"Dra.").text
                    if re.match(reg_nombre_tutor, match):
                        name = f"{tutor.first_name.capitalize()} {tutor.last_name.capitalize()}"
                        if tutor.second_last_name:
                            name += f" {tutor.second_last_name.capitalize()}"
                        self.paragraph_replace_text(p, reg_nombre_tutor, name.title())
                    if re.match(reg_nombre_alumno,match):
                        nombre_alumno = f"{alumno.first_name} {alumno.last_name}"
                        if alumno.second_last_name:
                            nombre_alumno += f" {alumno.second_last_name}"
                        nombre_alumno = nombre_alumno.upper()
                        self.paragraph_replace_text(p, reg_nombre_alumno, nombre_alumno).text
                    if re.match(reg_academico, match):
                        academico = ""
                        if tutor.sexo:
                            if tutor.sexo == "M":
                                academico = "Académico"
                            if tutor.sexo == "F":
                                academico = "Académica"
                        self.paragraph_replace_text(p, reg_academico, academico)
                    if re.match(reg_licenciatura,match):
                        licenciatura = alumno.get_carrera_display()
                        self.paragraph_replace_text(p, reg_licenciatura, f"{licenciatura}".upper()).text
                    if re.match(reg_det,match):
                        if tutor.sexo == "M":
                            self.paragraph_replace_text(p, reg_det, f"el").text
                        if tutor.sexo == "F":
                            self.paragraph_replace_text(p, reg_det, f"la").text
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            response['Content-Disposition'] = f'attachment; filename={alumno.first_name}_{alumno.last_name}_TUTOR.docx'
            open_plantilla.save(response)

        else :    
            ##EDICIÓN DE LOS PLACEHOLDERS
            zip_buffer = BytesIO()
            oficio_regex = re.search(r'\_[xX]+\_', oficio_form)
            if no_inicio_form:
                contador_documentos:int = int(no_inicio_form)
            else:
                contador_documentos = 1
            with ZipFile(zip_buffer, 'w') as zip_file:
                for alumno in alumnos:
                    open_plantilla = docx.Document(plantilla.archivo)
                    c=0
                    for p in open_plantilla.paragraphs:
                        c = c+1
                        # print(c)
                        line = p.text
                        result = []
                        line_matches = [] if (result := re.findall(reg_placeh,line)) is None else result
                        for match in line_matches:
                            if re.search(reg_ofi,match):
                                if oficio_regex:
                                    oficio_nuevo = re.sub(r'\_[xX]+\_', f"_{contador_documentos}_",oficio_form )
                                    print("Oficio nuevo: ", oficio_nuevo)
                                    self.paragraph_replace_text(p, reg_ofi, f"{oficio_nuevo}").text
                                else:
                                    self.paragraph_replace_text(p, reg_ofi, f"{oficio_form} {contador_documentos}").text
                            if re.match(reg_fech,match):
                                self.paragraph_replace_text(p, reg_fech, f"{fecha_form}").text
                            # if re.match(reg_tut,match):
                            #     print(f"Tutor IF")
                            #     self.paragraph_replace_text(p, reg_tut, f"Doctor {tutor.last_name}").text
                            if re.match(reg_palab_tutor,match):
                                if tutor.sexo == "M":
                                    self.paragraph_replace_text(p, reg_palab_tutor, f"tutor".capitalize()).text
                                if tutor.sexo == "F":
                                    self.paragraph_replace_text(p, reg_palab_tutor, f"tutora".capitalize()).text
                            if re.match(reg_tut,match):
                                if tutor.sexo == "M":
                                    self.paragraph_replace_text(p, reg_tut, f"Dr.").text
                                if tutor.sexo == "F":
                                    self.paragraph_replace_text(p, reg_tut, f"Dra.").text
                            if re.match(reg_nombre_tutor, match):
                                name = f"{tutor.first_name.capitalize()} {tutor.last_name.capitalize()}"
                                if tutor.second_last_name:
                                    name += f" {tutor.second_last_name.capitalize()}"
                                self.paragraph_replace_text(p, reg_nombre_tutor, name.title())
                            if re.match(reg_nombre_alumno,match):
                                nombre_alumno = f"{alumno.first_name} {alumno.last_name}"
                                if alumno.second_last_name:
                                    nombre_alumno += f" {alumno.second_last_name}"
                                nombre_alumno = nombre_alumno.upper()
                                self.paragraph_replace_text(p, reg_nombre_alumno, nombre_alumno).text
                            if re.match(reg_academico, match):
                                academico = ""
                                if tutor.sexo:
                                    if tutor.sexo == "M":
                                        academico = "Académico"
                                    if tutor.sexo == "F":
                                        academico = "Académica"
                                self.paragraph_replace_text(p, reg_academico, academico)
                            if re.match(reg_licenciatura,match):
                                licenciatura = alumno.get_carrera_display()
                                self.paragraph_replace_text(p, reg_licenciatura, f"{licenciatura}".upper()).text
                            if re.match(reg_det,match):
                                if tutor.sexo == "M":
                                    self.paragraph_replace_text(p, reg_det, f"el").text
                                if tutor.sexo == "F":
                                    self.paragraph_replace_text(p, reg_det, f"la").text
                            if re.match(reg_asignacion, match):
                                if tutor.sexo == "F":
                                    self.paragraph_replace_text(p, reg_asignacion, f"asignada")
                                elif tutor.sexo == "M":
                                    self.paragraph_replace_text(p, reg_asignacion, f"asignado")
                            if re.match(reg_reasignacion, match):
                                if tutor.sexo == "F":
                                    self.paragraph_replace_text(p, reg_reasignacion, f"reasignada")
                                elif tutor.sexo == "M":
                                    self.paragraph_replace_text(p, reg_reasignacion, f"reasignado")

                    # Save each document to ZIP
                    temp_buffer = BytesIO()
                    open_plantilla.save(temp_buffer)
                    temp_buffer.seek(0)
                    zip_file.writestr(f"{alumno.first_name}_{alumno.last_name}_TUTOR.docx", temp_buffer.getvalue())
                    contador_documentos = contador_documentos+1

            # Return ZIP file
            zip_buffer.seek(0)
            response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = 'attachment; filename="Documentos_Alumnos.zip"'

        return response


class ReporteTutoriasBrindadasView(CodaViewMixin, CreateView):
    model = Coda
    form_class = FormReporteDeTutorias
    template_name = 'Tutorias/generarhistorialtutoria.html'
    success_url = reverse_lazy('Tutorados-Coda')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        tutor_pk = self.kwargs.get('pk')
        tutor_instance = Tutor.objects.filter(pk=tutor_pk).first()
        kwargs['tutor_instance'] = tutor_instance
        return kwargs

    def post(self, request, *args, **kwargs):
        form = request.POST
        tutor_pk = self.kwargs.get('pk')

        oficio = form.get('oficio')
        fecha_emision = form.get('fecha')
        plantilla_nombre = form.get('plantilla')
        fecha_inicio = form.get('fecha_inicio')
        fecha_fin = form.get('fecha_fin')
        fecha_emision_date = datetime.strptime(fecha_emision, '%Y-%m-%dT%H:%M').date()
        oficio = normalizar_numero_oficio(oficio, fecha_emision_date)

        tutor = get_object_or_404(Tutor, pk=tutor_pk)
        tema_dict = dict(TEMAS)

        if fecha_inicio and fecha_fin:
            fecha_inicio = timezone.datetime.strptime(fecha_inicio, '%Y-%m-%d')
            fecha_fin = timezone.datetime.strptime(fecha_fin, '%Y-%m-%d') + timedelta(days=1)
            tutorias = Tutoria.objects.filter(tutor=tutor, fecha__range=(fecha_inicio, fecha_fin))
        else:
            tutorias = Tutoria.objects.filter(tutor=tutor)

        mostrar_col_alumno = 'col_alumno' in form
        mostrar_col_fecha = 'col_fecha' in form
        mostrar_col_hora = 'col_hora' in form
        mostrar_col_tema = 'col_tema' in form
        mostrar_col_notas = 'col_notas' in form

        columnas_activas = []
        if mostrar_col_alumno:
            columnas_activas.append('Alumno')
        if mostrar_col_fecha:
            columnas_activas.append('Fecha')
        if mostrar_col_hora:
            columnas_activas.append('Hora')
        if mostrar_col_tema:
            columnas_activas.append('Tema')
        if mostrar_col_notas:
            columnas_activas.append('Notas')

        plantilla = get_object_or_404(Documento, nombre=plantilla_nombre)

        return generar_docx_reporte_tutorias_brindadas(
            tutor=tutor,
            tutorias=tutorias,
            plantilla=plantilla,
            oficio=oficio,
            fecha_emision=fecha_emision,
            columnas_activas=columnas_activas,
            mostrar_col_alumno=mostrar_col_alumno,
            mostrar_col_fecha=mostrar_col_fecha,
            mostrar_col_hora=mostrar_col_hora,
            mostrar_col_tema=mostrar_col_tema,
            mostrar_col_notas=mostrar_col_notas,
            tema_dict=tema_dict,
        )


class ReporteTutoriasBrindadasMasivoView(CodaViewMixin, FormView):
    template_name = 'Tutorias/generarhistorialtutorias_masivo.html'
    form_class = FormReporteTutoriasMasivo
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        coordinaciones = [
            ("MAT", "Matemáticas Aplicadas"),
            ("COM", "Ingeniería en Computación"),
            ("IB", "Ingeniería Biológica"),
            ("BM", "Biología Molecular"),
        ]

        tutores_por_coordinacion = []

        for codigo, nombre in coordinaciones:
            tutores = Tutor.objects.filter(
                coordinacion=codigo
            ).order_by("last_name", "first_name")

            tutores_por_coordinacion.append({
                "codigo": codigo,
                "nombre": nombre,
                "tutores": tutores,
            })

        context["tutores_por_coordinacion"] = tutores_por_coordinacion
        context["plantilla_masiva_nombre"] = FormReporteTutoriasMasivo.PLANTILLA_REPORTE_TUTORIAS_MASIVO
        return context

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def form_valid(self, form):
        coordinaciones = form.cleaned_data.get('coordinaciones') or []
        incluir_todas = form.cleaned_data.get('incluir_todas')
        oficio_inicial = form.cleaned_data.get('oficio_inicial')
        fecha_inicio = form.cleaned_data.get('fecha_inicio')
        fecha_fin = form.cleaned_data.get('fecha_fin')
        fecha_emision = form.cleaned_data.get('fecha')
        fecha_emision_str = fecha_emision.strftime('%Y-%m-%dT%H:%M')
        plantilla_nombre = FormReporteTutoriasMasivo.PLANTILLA_REPORTE_TUTORIAS_MASIVO
        #Con lo siguiente se busca que si esté la plantilla como parte de las plantillas agregadas
        #solo se acepta con el nombre exacto
        try:
            plantilla = Documento.objects.get(nombre=plantilla_nombre)
        except Documento.DoesNotExist:
            form.add_error(
                None,
                f'No se encontró la plantilla "{plantilla_nombre}". '
                'Debe cargarse desde Ajustes con ese nombre exacto.'
            )
            return self.form_invalid(form)
        tutores_seleccionados = form.cleaned_data.get('tutores')
        mostrar_col_alumno = form.cleaned_data.get('col_alumno')
        mostrar_col_fecha = form.cleaned_data.get('col_fecha')
        mostrar_col_hora = form.cleaned_data.get('col_hora')
        mostrar_col_tema = form.cleaned_data.get('col_tema')
        mostrar_col_notas = form.cleaned_data.get('col_notas')

        columnas_activas = []
        if mostrar_col_alumno:
            columnas_activas.append('Alumno')
        if mostrar_col_fecha:
            columnas_activas.append('Fecha')
        if mostrar_col_hora:
            columnas_activas.append('Hora')
        if mostrar_col_tema:
            columnas_activas.append('Tema')
        if mostrar_col_notas:
            columnas_activas.append('Notas')

        if incluir_todas:
            tutores = Tutor.objects.all()
        elif coordinaciones:
            tutores = Tutor.objects.filter(coordinacion__in=coordinaciones)
        else:
            tutores = Tutor.objects.all()

        if tutores_seleccionados.exists():
            tutores = tutores.filter(pk__in=tutores_seleccionados.values_list('pk', flat=True))

        tutores = tutores.order_by('coordinacion', 'last_name', 'first_name').distinct()

        fecha_inicio_dt = timezone.datetime.combine(fecha_inicio, datetime.min.time())
        fecha_fin_dt = timezone.datetime.combine(fecha_fin, datetime.min.time()) + timedelta(days=1)

        tema_dict = dict(TEMAS)
        zip_buffer = BytesIO()

        with ZipFile(zip_buffer, 'w') as zip_file:
            consecutivo = oficio_inicial

            for tutor in tutores:
                tutorias = Tutoria.objects.filter(
                    tutor=tutor,
                    fecha__range=(fecha_inicio_dt, fecha_fin_dt)
                )

                oficio = normalizar_numero_oficio(consecutivo, fecha_emision.date())

                response = generar_docx_reporte_tutorias_brindadas(
                    tutor=tutor,
                    tutorias=tutorias,
                    plantilla=plantilla,
                    oficio=oficio,
                    fecha_emision=fecha_emision_str,
                    columnas_activas=columnas_activas,
                    mostrar_col_alumno=mostrar_col_alumno,
                    mostrar_col_fecha=mostrar_col_fecha,
                    mostrar_col_hora=mostrar_col_hora,
                    mostrar_col_tema=mostrar_col_tema,
                    mostrar_col_notas=mostrar_col_notas,
                    tema_dict=tema_dict,
                )

                carpetas_licenciatura = {
                    "COM": "Ingenieria_en_Computacion",
                    "MAT": "Matematicas_Aplicadas",
                    "IB": "Ingenieria_Biologica",
                    "BM": "Biologia_Molecular",
                }

                nombre_carpeta = carpetas_licenciatura.get(tutor.coordinacion, "Sin_licenciatura")
                nombre_archivo = f"{tutor.matricula}_{tutor.last_name}_{tutor.first_name}_TUTORIAS_BRINDADAS.docx"
                ruta_zip = f"{nombre_carpeta}/{nombre_archivo}"

                zip_file.writestr(ruta_zip, response.content)

                consecutivo += 1

        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="reportes_tutorias_masivos.zip"'
        return response


# Ver Tutorias
# TODO Añadir verificación de permisos de acceso a la tutoria
class TutoriasDetailView(BaseAccessMixin, DetailView):
     
    model = Tutoria

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        return super().get_context_data(**kwargs)

    template_name='Tutorias/verTutorias_tutor.html'

    def get_queryset(self) -> QuerySet[Any]:
        
        if Tutor.objects.filter(pk=self.request.user.pk).exists():
            # Tutorias correspondientes al tutor
            queryset = super().get_queryset().filter(tutor=self.request.user)
        else: 
            # Tutorias correspondientes al alumno
            queryset = super().get_queryset().filter(alumno=self.request.user)
        
        if self.request.user.is_superuser == 1: 
            # Muestra todas las tutorias para el primer usuario creado (generalmente el primer superuser)
            queryset = super().get_queryset().all()
        
        return queryset
    
class HistorialTutoriasListView(BaseAccessMixin, ListView):
    """
    Vista para mostrar el historial de tutorías de un usuario, ya sea para un tutor o un alumno. 
    La vista filtra las tutorías según el rol del usuario y la fecha de realización.
    """ 
    model = Tutoria
    template_name='Tutorias/historialtutoria.html'
    context_object_name = "tutorias"

    def get_queryset(self) -> QuerySet[Any]:
        ahora = timezone.now()
        user = self.request.user

        # Tutor: solamente tutorías ya realizadas
        if user.has_role("TUT"):
            return Tutoria.objects.filter(
                tutor=user,
                fecha__lt=ahora
            ).order_by("-fecha")


        # Alumno: sus tutorías
        if user.has_role("ALU"):
            return Tutoria.objects.filter(
                alumno=user
            ).order_by("-fecha")

        # Cualquier otro rol: no mostrar tutorías
        return Tutoria.objects.none()
 

class HistorialTutoriasGenerateView(BaseAccessMixin, ListView):
    model = Tutoria
    template_name = 'Tutorias/generarhistorialtutoria.html'

class VerTutoriasCoordinadorListView(CordinadorViewMixin, FormView):
    model = Tutoria
    template_name='Tutorias/verTutorias_cordinador.html'
    form_class = FormVerTutorias

    def form_valid(self, form):
        estado = form.cleaned_data.get("estado")

        coord = get_object_or_404(Cordinador, pk=self.request.user.pk)
        tutores = Tutor.objects.all().filter(coordinacion=coord.coordinacion)
        tutorias = Tutoria.objects.filter(tutor__in=tutores)

        if estado:
            tutorias = tutorias.filter(alumno__estado=estado)

        context = self.get_context_data(form=form, object_list=tutorias)
        return self.render_to_response(context)

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        coord = get_object_or_404(Cordinador, pk=request.user.pk)
        tutores = Tutor.objects.all().filter(coordinacion=coord.coordinacion)
        tutorias = Tutoria.objects.filter(tutor__in=tutores)
        return self.render_to_response(self.get_context_data(form=form, object_list=tutorias))
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)

        coord = get_object_or_404(Cordinador, pk=self.request.user.pk)
        tutores = Tutor.objects.all().filter(coordinacion=coord.coordinacion)
        context["tutores"] = tutores

        return context
    
class VerTutoriasCoordinadorPorTutorListView(CordinadorViewMixin, FormView):
     
    model = Tutoria
    template_name='Tutorias/verTutorias_cordinador_portutor.html'
    form_class = FormVerTutorias

    def form_valid(self, form):
        estado = form.cleaned_data.get("estado")

        tutorias = Tutoria.objects.filter(tutor=self.kwargs.get('pk'))

        if estado:
            tutorias = tutorias.filter(alumno__estado=estado)

        context = self.get_context_data(form=form, object_list=tutorias)
        return self.render_to_response(context)

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        tutorias = Tutoria.objects.filter(tutor=self.kwargs.get('pk'))
        return self.render_to_response(self.get_context_data(form=form, object_list=tutorias))
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        tutor = Tutor.objects.get(pk=self.kwargs.get('pk'))
        context["tutor"] = tutor
        return context


class VerTutoriasCodaListView(CodaViewMixin, ListView):    
    model = Tutoria
    template_name='Tutorias/verTutorias_cooda.html'
    
    def get_queryset(self) -> QuerySet[Any]:
        
        queryset = super().get_queryset().filter(tutor=self.kwargs.get('pk'))   
        
        return queryset 
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        tutor = Tutor.objects.get(pk=self.kwargs.get('pk'))
        context["tutor"] = tutor
        return context

class VerTutoresListView(CodaViewMixin, ListView):
    model = Tutor
    template_name = 'Tutorias/verTutores_coda.html'

class VerAlumnosListView(CodaViewMixin, ListView):
    model = Alumno
    template_name = 'Tutorias/verAlumnos_coda.html'

class VerTutoresCoordListView(CordinadorViewMixin, ListView):
    model = Tutor
    template_name = 'Tutorias/verTutores_cordinador.html'

    def get_queryset(self) -> QuerySet[Any]:
        coord = get_object_or_404(Cordinador, pk=self.request.user.pk)

        queryset = super().get_queryset().filter(coordinacion=coord.coordinacion)
        return queryset
    
class VerTutoradosCodaListView(CodaViewMixin, ListView):
    model = Alumno
    template_name = 'Tutorias/verTutorados_coda.html'
    
    def get_queryset(self) -> QuerySet[Any]:
        
        queryset = super().get_queryset().filter(tutor_asignado=self.kwargs.get('pk'))   
        
        return queryset 

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        tutor = Tutor.objects.get(pk=self.kwargs.get('pk'))
        context["tutor"] = tutor
        print(context)
        return context
    
class VerTutoradosCoordinadorListView(CordinadorViewMixin, ListView):
    model = Alumno
    template_name = 'Tutorias/verTutorados_cordinador.html'
    
    def get_queryset(self) -> QuerySet[Any]:
        
        queryset = super().get_queryset().filter(tutor_asignado=self.kwargs.get('pk'))   
        
        return queryset 

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        tutor = Tutor.objects.get(pk=self.kwargs.get('pk'))
        context["tutor"] = tutor
        return context


class VerTutoriasTutorListView(TutorViewMixin, FormView):
    """
    Vista para mostrar solamente las tutorías pendientes de aprobación para un tutor.
    Permite filtrar las tutorías por estado del alumno.
    Adicionalmente, verifica si el tutor tiene horarios de atención definidos para
    motivar al tutor a configurarlos si no los tiene, mostrando un mensaje de advertencia.
    """
     
    model = Tutoria
    template_name='Tutorias/verTutorias_tutor.html'
    form_class = FormVerTutorias

    def form_valid(self, form):
        estado = form.cleaned_data.get("estado")

        # Obtiene las tutorías del tutor actual que requieren aprobación o están pendientes
        tutorias = Tutoria.objects.filter(
            tutor=self.request.user,
            estado__in=[PENDIENTE, PROPUESTA],
        ).order_by("fecha")

        if estado:
            tutorias = tutorias.filter(alumno__estado=estado)

        context = self.get_context_data(form=form, object_list=tutorias)
        return self.render_to_response(context)

    def get(self, request, *args, **kwargs):
        form = self.get_form()

        tutorias = Tutoria.objects.filter(
            tutor=request.user,
            estado__in=[PENDIENTE, PROPUESTA],
        ).order_by("fecha")

        return self.render_to_response(
            self.get_context_data(
                form=form, 
                object_list=tutorias
            )
        )
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        tutorados = Alumno.objects.filter(tutor_asignado=self.request.user)
        context["tutorados"] = tutorados

        context.update({
            "estado_propuesta": PROPUESTA,
            "estado_pendiente": PENDIENTE,
            "estado_aceptado": ACEPTADO,
            "estado_rechazado": RECHAZADO,
            "estado_cancelado": CANCELADO,
        })

        return context 

class TutorProximasListView(TutorViewMixin, ListView):
    """
    Vista para mostrar las tutorías próximas de un tutor.
    Filtra las tutorías que están aceptadas, cuya fecha es mayor o igual a la fecha actual.
    """
    model = Tutoria
    template_name = "Tutorias/tutorias_proximas.html"
    context_object_name = "tutorias_proximas"

    def get_queryset(self):
        user = self.request.user

        # Obtener el tutor real (objeto Tutor)
        try:
            tutor = user.tutor
        except Tutor.DoesNotExist:
            return Tutoria.objects.none()

        hoy = timezone.localdate()

        # Tutorías próximas:
        # estado = ACE (Aceptadas)
        # fecha >= hoy
        return (
            Tutoria.objects.filter(
                tutor=tutor,
                estado="ACE",
                fecha__date__gte=hoy
            ).order_by("fecha")
        )

class VerTutoriasTutorTabView(TutorViewMixin, ListView):
    """
        Organiza las tutorías del tutor por su estado efectivo para
        presentar 3 listas:
        1. Tutorías solicitadas.
        2. Tutorías agendadas.
        3. Historial de tutorías.
    """

    model = Tutoria
    template_name = 'Tutorias/panel_tutorias_tutor.html'
    context_object_name = 'tutorias'

    def get_queryset(self) -> QuerySet[Any]:
        return (
            super()
            .get_queryset()
            .filter(tutor_id=self.request.user.pk)
            .select_related('alumno')
        )

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['motivos_cancelacion'] = MOTIVOS_CANCELACION_TUTOR
        tutorias = list(context['tutorias'])

        # 1. Solicitadas: ordenadas por fecha de solicitud (las más recientes primero)
        solicitadas = [t for t in tutorias if t.estado_efectivo in [PENDIENTE, PROPUESTA, VENCIDA]]
        context['tutorias_solicitadas'] = sorted(
            solicitadas, key=lambda t: t.fecha_solicitud, reverse=True
        )

        # 2. Agendadas: ordenadas por fecha de la cita (las más próximas primero)
        agendadas = [t for t in tutorias if t.estado_efectivo == ACEPTADO]       
        context['tutorias_agendadas'] = sorted(
            agendadas, key=lambda t: t.fecha
        )

        # 3. Historial: ordenadas por fecha de la cita (las más recientes primero)
        historial = [t for t in tutorias if t.estado_efectivo in [REALIZADA, REPORTADA, RECHAZADO, CANCELADO]]
        context['tutorias_historial'] = sorted(
            historial, key=lambda t: t.fecha, reverse=True
        )

        return context

class VerTutoriasAlumnoListView(LoginRequiredMixin, ListView):
    """
        Organiza las tutorías del alumno por su estado efectivo para
        presentar 3 listas:
        1. Tutorías solicitadas.
        2. Tutorías agendadas.
        3. Historial de tutorías.
    """

    model = Tutoria
    template_name = 'Tutorias/panel_tutorias_alumno.html'
    context_object_name = 'tutorias'

    def get_queryset(self) -> QuerySet[Any]:
        return (
            super()
            .get_queryset()
            .filter(alumno_id=self.request.user.pk)
            .select_related('tutor')
        )

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['motivos_cancelacion'] = MOTIVOS_CANCELACION_ALUMNO
        tutorias = list(context['tutorias'])

        # HeaderAndFooterFachada.html extiende esta plantilla dinámicamente.
        # Esta vista usa LoginRequiredMixin directamente, por lo que debe
        # proporcionar el valor que antes agregaba AlumnoViewMixin.
        context['header_footer'] = TEMPLATES[ALUMNO]

       # 1. Solicitadas: ordenadas por fecha de solicitud (las más recientes primero)
        solicitadas = [t for t in tutorias if t.estado_efectivo in [PENDIENTE, PROPUESTA, VENCIDA]]
        context['tutorias_solicitadas'] = sorted(
            solicitadas, key=lambda t: t.fecha_solicitud, reverse=True
        )

        # 2. Agendadas: ordenadas por fecha de la cita (las más próximas primero)
        agendadas = [t for t in tutorias if t.estado_efectivo == ACEPTADO]       
        context['tutorias_agendadas'] = sorted(
            agendadas, key=lambda t: t.fecha
        )

        # 3. Historial: ordenadas por fecha de la cita (las más recientes primero)
        historial = [t for t in tutorias if t.estado_efectivo in [REALIZADA, REPORTADA, RECHAZADO, CANCELADO]]
        context['tutorias_historial'] = sorted(
            historial, key=lambda t: t.fecha, reverse=True
        )
        
        return context


# TODO Eliminar para prod
# class DebugTutoriasView(LoginRequiredMixin, ListView):

#     model = Tutoria
#     template_name='Tutorias/verTutorias_coordinador.html'

#     def get_queryset(self) -> QuerySet[Any]:
#         return super().get_queryset()
    
    
class QuickCreateTutoriaView(AlumnoViewMixin, CreateView):
    model = Tutoria
    template_name = 'Tutorias/registrar-tutoria.html'
    success_url = reverse_lazy('login_success')

    form_class = FormTutorias

    def form_valid(self, form: FormTutorias) -> HttpResponse:
        alumno = get_object_or_404(Alumno, pk=self.request.user)
        form.instance.alumno = alumno
        form.instance.tutor = alumno.tutor_asignado
        form.instance.estado = ACEPTADO
        
        # Snapshot del estado del alumno al momento de crear la tutoría con QR
        if not form.instance.estado_alumno_historico:
            form.instance.estado_alumno_historico = alumno.estado
        
        # rol = self.request.user.get_rol()
        if self.request.user.has_role("ALU"):
            recipient = alumno.tutor_asignado   # No sé que hace este bloque, pero no lo voy a quitar para que no se rompa. -Alfredo
        else:
            recipient = Alumno.objects.filter(pk=self.get_object().alumno)
        
        tutoria_notification_requested.send(
            sender=self.__class__,
            event="qr_generada",
            tutoria=form.instance,
            actor=alumno,
            recipient=recipient,
            verb='Tutoria registrada con QR',
        )

        return super().form_valid(form)

    def form_invalid(self, form: BaseModelForm) -> HttpResponse:
        print("Tutoria invalida")
        print(f'Form: {form.instance}')
        return super().form_invalid(form)

    def get_initial(self) -> dict[str, Any]:
        super().get_initial()
        try:
            alumno = Alumno.objects.get(pk=self.request.user.pk)
        except Alumno.DoesNotExist:
            raise PermissionDenied("Sólo los alumnos pueden registrar tutorias con QR")
        self.initial["alumno"] = alumno
        self.initial["tutor"] = alumno.tutor_asignado
        self.initial["tema"] = alumno.tutor_asignado.tema_tutorias
        print(f'Fecha: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        self.initial["fecha"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.initial["descripcion"] = "Tutoria registrada con QR"
        return self.initial 
      
    
class VerTutoradosTutorListView(TutorViewMixin, ListView):
     
    model = Alumno
    template_name='Tutorias/list_tutorados.html'

    def get_queryset(self) -> QuerySet[Any]:
        
        # Tutorias correspondientes al tutor
        queryset = super().get_queryset().filter(tutor_asignado=self.request.user)
    
        return queryset

# Este es para asesorias, aun no se va a usar
class QRCodeView(View):
    def get(self, request):
        # Obtengo el usuario
        user_id = request.user.id

        # Creo qr
        qr_content = f"User ID: {user_id}"

        # Crea el qr
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)


        img = qr.make_image(fill_color="black", back_color="white")

        # Mando htttppp
        response = HttpResponse(content_type="image/png")
        img.save(response, "PNG")

        return response


# ALJ: Esta vista es para solicitar tutorías In Situ, es decir,
# cuando el alumno escanea un QR directamente en la oficina del tutor.
# Para ver cómo se genera el QR, revisar VerQRView de Usuarios/views.py
# El QR está personalizado para cada tutor, de manera que solamente sus tutorados
# pueden solicitarle tutorías In Situ.
# TODO: agregar a los alumnos un campo de "tutor_sustituto" que normalmente será
# el coordinador para que también esa persona pueda atenderlo.

class TutoriaInSituCreateView(LoginRequiredMixin, ContextConRolesMixin, TemplateView):

    template_name = "Tutorias/tutoria_insitu_form.html"

    def get(self, request, tutor_pk):

        usuario = request.user

        # 1) Validar que sea alumno
        if not usuario.is_alumno:
            return HttpResponseForbidden("Solo los alumnos pueden registrar tutorías in-situ.")

        alumno = Alumno.objects.get(pk=request.user.pk)

        # 2) Validar tutor
        tutor = get_object_or_404(Tutor, pk=tutor_pk)

        # 3) Validar que el alumno pertenece a ese tutor
        if alumno.tutor_asignado.pk != tutor.pk:   # Ajusta nombre del campo
            return HttpResponseForbidden(f"{tutor.nombre_completo} no es tu tutor asignado.")

        # 4) Mostrar formulario
        form = FormTutoriasInSitu()

        # Construir contexto con roles
        context = self.get_context_data(
            form=form,
            tutor=tutor,
        )

        return render(request, self.template_name, context)

    def post(self, request, tutor_pk):

        usuario = request.user

        if not usuario.is_alumno:
            return HttpResponseForbidden("Solo los alumnos pueden registrar tutorías in-situ.")

        alumno = Alumno.objects.get(pk=request.user.pk)

        tutor = get_object_or_404(Tutor, pk=tutor_pk)

        if alumno.tutor_asignado.pk != tutor.pk:  # Ajusta si tu campo se llama diferente
            return HttpResponseForbidden(f"{tutor.nombre_completo} no es tu tutor asignado.")

        form = FormTutoriasInSitu(request.POST)

        if form.is_valid():
            nueva = form.save(commit=False)
            nueva.alumno = alumno
            nueva.tutor = tutor
            #nueva.modalidad = "INS"
            nueva.estado = "ACE"  # aceptada directamente, para el tutor pasa directamente a historial tutorías.
            nueva.fecha = timezone.now()
            nueva.save()

            # Agregar mensaje de confirmación
            messages.success(request, "Tutoría In Situ registrada con éxito.")

            # El alumno registra tutoría por QR, el tutor debe recibir notificación.
            tutoria_notification_requested.send(
                sender=self.__class__,
                event= EventoTutoria.ALU_AGENDA_POR_QR, 
                tutoria=nueva,
                actor=alumno,
                recipient=alumno.tutor_asignado
            )

            return redirect("Tutorias-alumno")

        # Si el formulario es inválido, regenerar el contexto completo
        context = self.get_context_data(
            form=form,
            tutor=tutor,
        )

        return render(request, self.template_name, context)


class CrearTutoriaPorAlumnoView(TutorViewMixin, CreateView):
    model = Tutoria
    form_class = FormTutorias
    template_name = 'Tutorias/solicitudTutoria.html'
    success_url = reverse_lazy('login_success')  # Cambia esto a la URL adecuada

    def form_valid(self, form):
        # Obtén el nombre del alumno desde la URL
        alumno_pk = self.kwargs.get('pk_alumno')

        # Busca el alumno por nombre
        alumno = get_object_or_404(Alumno, pk=alumno_pk)

        # Completa el formulario con los datos del alumno
        form.instance.alumno = alumno
        form.instance.tutor = alumno.tutor_asignado

        # Snapshot del estado del alumno al momento de crear la tutoría por tutor
        if not form.instance.estado_alumno_historico:
            form.instance.estado_alumno_historico = alumno.estado

        # Genera un slug único para la tutoría (puedes ajustar esto según tus necesidades)
        slug = slugify(form.instance.tema)
        form.instance.slug = slug

        return super().form_valid(form)


class RealizarSeguimientoView(TutorViewMixin, UpdateView):
    model = Tutoria
    form_class = FormSeguimiento
    template_name = 'Tutorias/seguimientoTutoria.html'
    success_url =  reverse_lazy('Tutorias-historial')

    seguimiento_fields = [
        'asistencia',
        'duracion',
        'firma_documentos_beca',
        'beca_otorgada',
        'asesoria_especializada',
        'observaciones',
        'impacto_tutoria',
        'resultados_tutoria',
    ]

    def _is_modal_request(self) -> bool:
        return self.request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def get_queryset(self):
        # Un tutor solamente puede consultar o modificar sus propias tutorías.
        return (
            super()
            .get_queryset()
            .filter(tutor_id=self.request.user.pk)
            .select_related('alumno', 'tutor', 'alumno__tutor_asignado')
            .prefetch_related('historial_cambios')
        )

    def get_template_names(self):
        if self._is_modal_request():
            return ['Tutorias/includes/partials/modal_seguimiento_tutoria.html']
        return [self.template_name]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self._is_modal_request() and self.request.method == 'POST':
            # El modal muestra únicamente los siete campos solicitados. Este
            # campo pertenece al formulario completo y debe conservarse para
            # no borrar información previa al editar desde el panel.
            data = kwargs['data'].copy()
            data['beca_otorgada'] = self.get_object().beca_otorgada or ''
            kwargs['data'] = data
        return kwargs

    def _has_existing_report(self, tutoria: Tutoria) -> bool:
        return tutoria.fecha_reporte is not None

    def _format_bool(self, value: Any) -> str:
        if value is True:
            return 'Sí'
        if value is False:
            return 'No'
        return 'Sin registro'

    def _build_seguimiento_change_summary(
        self,
        original: Tutoria,
        form: BaseModelForm,
        estado_anterior: Any,
        estado_nuevo: Any,
    ) -> str:
        field_labels = {
            'asistencia': 'Asistencia',
            'duracion': 'Duración de la tutoría',
            'firma_documentos_beca': 'Firma de documentos de beca',
            'beca_otorgada': 'Beca otorgada',
            'asesoria_especializada': 'Asesoría especializada',
            'observaciones': 'Observaciones',
            'impacto_tutoria': 'Impacto de la tutoría',
            'resultados_tutoria': 'Resultados de la tutoría',
            'estado_alumno_actual': 'Estado actual del alumno',
        }

        duracion_map = dict(DURACION_ASESORIA)
        estados_map = dict(ESTADOS_ALUMNO)
        changes = []

        for field in form.changed_data:
            if field not in field_labels:
                continue

            if field == 'duracion':
                old_value = duracion_map.get(original.duracion, 'Sin registro')
                new_duracion = form.cleaned_data.get(field)
                try:
                    new_duracion = int(new_duracion)
                except (TypeError, ValueError):
                    pass
                new_value = duracion_map.get(new_duracion, 'Sin registro')
            elif field in {'asistencia', 'firma_documentos_beca', 'asesoria_especializada'}:
                old_value = self._format_bool(getattr(original, field, None))
                new_value = self._format_bool(form.cleaned_data.get(field))
            elif field == 'estado_alumno_actual':
                old_value = estados_map.get(estado_anterior, 'Sin registro')
                new_value = estados_map.get(estado_nuevo, 'Sin registro')
            else:
                old_value = getattr(original, field, '') or ''
                new_value = form.cleaned_data.get(field, '') or ''

            if str(old_value) != str(new_value):
                label = field_labels[field]
                changes.append(f"{label}: '{old_value}' -> '{new_value}'")

        return ' | '.join(changes) if changes else 'Se editó el reporte sin cambios detectables.'

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)

        tutoria_actual = self.object
        alumno = tutoria_actual.alumno

        tutorias_alumno_qs = (
            Tutoria.objects.filter(alumno=alumno)
            .select_related('tutor')
            .order_by('-fecha')
        )

        tutorias_recientes = list(tutorias_alumno_qs[:10])
        historial_cambios_actual = list(tutoria_actual.historial_cambios.all()[:10])
        asesorias_recientes = list(
            Asesoria.objects.filter(alumno=alumno)
            .select_related('tutor')
            .order_by('-fecha')[:10]
        )

        # Contador por tema para mostrar un resumen util al tutor.
        tema_counter = Counter()
        for temas in tutorias_alumno_qs.values_list('tema', flat=True):
            for codigo_tema in temas or []:
                tema_counter[codigo_tema] += 1

        tema_labels = dict(TEMAS)
        resumen_temas = [
            {
                'codigo': codigo,
                'etiqueta': tema_labels.get(codigo, codigo),
                'total': total,
            }
            for codigo, total in tema_counter.most_common()
        ]

        impactos_ultimas_5 = [
            t.impacto_tutoria
            for t in tutorias_recientes
            if t.impacto_tutoria not in (None, 0)
        ][:5]
        promedio_impacto = None
        if impactos_ultimas_5:
            promedio_impacto = round(sum(impactos_ultimas_5) / len(impactos_ultimas_5), 1)

        total_tutorias = tutorias_alumno_qs.count()
        total_asistidas = tutorias_alumno_qs.filter(asistencia=True).count()

        becas_registradas = [
            t for t in tutorias_recientes if t.firma_documentos_beca and t.beca_otorgada
        ]

        context.update({
            'tutorias_recientes': tutorias_recientes,
            'resumen_temas': resumen_temas,
            'historial_cambios_actual': historial_cambios_actual,
            'asesorias_recientes': asesorias_recientes,
            'becas_registradas': becas_registradas,
            'promedio_impacto': promedio_impacto,
            'total_tutorias_alumno': total_tutorias,
            'total_tutorias_asistidas': total_asistidas,
            'seguimiento_completado': self._has_existing_report(tutoria_actual),
        })

        return context

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        tutor = Tutor.objects.get(pk=self.request.user)
        original_tutoria = self.get_object()
        seguimiento_completado = self._has_existing_report(original_tutoria)
        edit_confirmed = self.request.POST.get('edit_confirmed') == 'true'

        alumno = form.instance.alumno
        estado_actual_anterior = alumno.estado
        estado_actual_nuevo = form.cleaned_data.get('estado_alumno_actual')
        estado_actual_cambio = estado_actual_nuevo != estado_actual_anterior

        has_edit_changes = bool(form.changed_data) or estado_actual_cambio
        if seguimiento_completado and has_edit_changes and not edit_confirmed:
            messages.error(
                self.request,
                'Confirma la edición del reporte para guardar cambios y enviar la notificación al alumno.',
            )
            return self.form_invalid(form)

        if estado_actual_cambio:
            alumno.estado = estado_actual_nuevo
            alumno.save(update_fields=['estado'])

        # Registrar la fecha del primer llenado del reporte.
        if form.instance.fecha_reporte is None:
            form.instance.fecha_reporte = timezone.now()

        response = super().form_valid(form)

        if has_edit_changes:
            change_summary = self._build_seguimiento_change_summary(
                original_tutoria,
                form,
                estado_actual_anterior,
                estado_actual_nuevo,
            )
            HistorialCambioTutoria.objects.create(
                tutoria=self.object,
                correo_editor=self.request.user.email,
                cambios_realizados=change_summary,
            )

        #TODO: ajustar el manejador de notificaciones por correo porque el nombre del evento
        # ya cambió.
        tutoria_notification_requested.send(
            sender=self.__class__,
            event= EventoTutoria.TUTORIA_INFORME_REGISTRADO, #"seguimiento_registrado",
            tutoria=self.object,
            actor=tutor,
        )
        if self._is_modal_request():
            return JsonResponse({'ok': True})
        return response

    def form_invalid(self, form: BaseModelForm) -> HttpResponse:
        if self._is_modal_request():
            return self.render_to_response(
                self.get_context_data(form=form),
                status=422,
            )
        return super().form_invalid(form)


class EditarEstadoAlumnoHistoricoView(BaseAccessMixin, View):
    """
    Vista para editar el estado histórico del alumno en una tutoría.
    Solo TUT/COORDINADOR/CODA pueden editar; ALU no puede.
    """
    def post(self, request, pk):
        tutoria = get_object_or_404(Tutoria, pk=pk)
        
        # Validar permisos
        if request.user.has_role("TUT"):
            # TUT solo puede editar si es el tutor asignado
            if tutoria.tutor_id != request.user.pk:
                raise PermissionDenied("No tienes permiso para editar esta tutoría")
        elif request.user.has_role("COORDINADOR"):
            # COORDINADOR solo puede editar si el tutor está en su coordinación
            coord = get_object_or_404(Cordinador, pk=request.user.pk)
            if tutoria.tutor.coordinacion != coord.coordinacion:
                raise PermissionDenied("No tienes permiso para editar esta tutoría")
        elif request.user.has_role("CODA"):
            # CODA puede editar cualquier tutoría
            pass
        else:
            raise PermissionDenied("No tienes permiso para realizar esta acción")
        
        # Importar el formulario
        from .forms import FormEditarEstadoAlumnoHistorico
        form = FormEditarEstadoAlumnoHistorico(request.POST)
        
        if form.is_valid():
            nuevo_estado = form.cleaned_data['estado_alumno_historico']
            estado_anterior = tutoria.estado_alumno_historico
            
            # Obtener etiquetas del diccionario ESTADOS_ALUMNO
            from Usuarios.constants import ESTADOS_ALUMNO
            estado_dict = {key: value for key, value in ESTADOS_ALUMNO}
            
            etiqueta_anterior = estado_dict.get(estado_anterior, "Sin estado registrado")
            etiqueta_nueva = estado_dict.get(nuevo_estado, "Desconocido")
            
            # Actualizar el estado
            tutoria.estado_alumno_historico = nuevo_estado
            tutoria.save()
            
            # Registrar el cambio en HistorialCambioTutoria
            cambio_mensaje = f"Estado histórico del alumno: '{etiqueta_anterior}' -> '{etiqueta_nueva}'"
            HistorialCambioTutoria.objects.create(
                tutoria=tutoria,
                correo_editor=request.user.email,
                cambios_realizados=cambio_mensaje,
            )
            
            # Enviar notificación
            tutor = Tutor.objects.filter(pk=tutoria.tutor_id)
            alumno = Alumno.objects.filter(pk=tutoria.alumno_id)
            
            if request.user.has_role("TUT"):
                tutoria_notification_requested.send(
                    sender=self.__class__,
                    event="estado_historico_actualizado",
                    tutoria=tutoria,
                    actor=request.user,
                    recipient=alumno,
                    verb='Estado histórico de tutoría actualizado',
                )
            else:
                tutoria_notification_requested.send(
                    sender=self.__class__,
                    event="estado_historico_actualizado",
                    tutoria=tutoria,
                    actor=request.user,
                    recipient=tutor,
                    verb='Estado histórico de tutoría actualizado por administración',
                )
            
            # Mostrar mensaje de éxito
            messages.success(request, f"Estado histórico actualizado: {etiqueta_anterior} → {etiqueta_nueva}")
            
            # Redirigir a la vista de edición de la tutoría
            return redirect('Tutorias-update', pk=pk)
        else:
            # Si el formulario no es válido, redirigir de vuelta
            messages.error(request, "Error al actualizar el estado. Por favor, intenta de nuevo.")
            return redirect('Tutorias-update', pk=pk)
    
class TutoriasAceptadasListView(CodaViewMixin, ListView):
    model = Tutoria
    template_name = 'Tutorias/ver_tutorias_aceptadas_coda.html'
    context_object_name = 'tutorias'

    def get_queryset(self):
        return Tutoria.objects.filter(estado='ACE').order_by('-fecha')

class ExportarTutoriasAceptadasExcelView(CodaViewMixin, View):

    def get(self, request, *args, **kwargs):
        tema_dict = dict(TEMAS) 
        tutorias = Tutoria.objects.filter(estado='ACE').select_related('alumno', 'tutor')

        data = []
        for tutoria in tutorias:
            temas = ", ".join([tema_dict.get(t, t) for t in tutoria.tema])
            nombre_alumno = str(tutoria.alumno.first_name)
            nombre_alumno = nombre_alumno + " " + str(tutoria.alumno.last_name)
            if tutoria.alumno.second_last_name:
                nombre_alumno = nombre_alumno + " " + str(tutoria.alumno.second_last_name)
            nombre_tutor = str(tutoria.tutor.first_name)
            nombre_tutor = nombre_tutor + " " + str(tutoria.tutor.last_name)
            if tutoria.tutor.second_last_name:
                nombre_tutor = nombre_tutor + " " + str(tutoria.tutor.second_last_name)

            asistencia = "No"
            if tutoria.asistencia:
                asistencia = "Sí"
            
            data.append({
                "Id":tutoria.pk,
                "Matricula": tutoria.alumno.matricula,
                "Alumno:":nombre_alumno,
                "Correo Alumno": tutoria.alumno.email,
                "Tutor": nombre_tutor,
                "Numero Economico Tutor": tutoria.tutor.matricula,
                "Fecha": tutoria.fecha.strftime("%d/%m/%Y"),
                "Hora": tutoria.fecha.strftime("%H:%M"),
                "Tema(s)": temas,
                "Descripción": tutoria.descripcion,
                "Asistencia":asistencia
            })

        df = pd.DataFrame(data)

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="tutorias_aceptadas.xlsx"'

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Tutorías Aceptadas', index=False)

        return response


class ComunicacionMasivaTutoriasView(FormView):

    print("Inicializando vista de comunicación masiva")

    template_name = 'Tutorias/comunicacionMasiva.html'
    form_class = ComunicacionMasivaForm
    success_url = reverse_lazy('tutorias-comunicacion-masiva')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['header_footer'] = "Usuarios/base.html"
        print("Contexto:", ctx)
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        usuario_actual = self.request.user

        tutor_instance = None
        if hasattr(usuario_actual, 'tutor'):
            tutor_instance = usuario_actual.tutor
        else:
            try:
                tutor_instance = Tutor.objects.get(pk=usuario_actual.pk)
            except Tutor.DoesNotExist:
                print("El usuario logueado no es un Tutor válido")

        kwargs['tutor'] = tutor_instance
        return kwargs

    def form_valid(self, form):
        asunto = form.cleaned_data['asunto']
        mensaje = form.cleaned_data['mensaje']
        tutorados = form.cleaned_data['tutorados']

        lista_correos = [alumno.email for alumno in tutorados if alumno.email]
        if lista_correos:
            try:
                print(f"Preparando correo con asunto: {asunto}")
                email = EmailMessage(
                    subject=asunto,
                    body=mensaje,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[self.request.user.email],
                    bcc=lista_correos
                )

                print(f"Enviando correo a: {lista_correos}")

                archivos = self.request.FILES.getlist('archivos')
                for f in archivos:
                    email.attach(f.name, f.read(), f.content_type)

                email.send(fail_silently=False)

                cantidad = len(lista_correos)
                destinatario_texto = "tutorado" if cantidad == 1 else "tutorados"
                messages.success(self.request, f'Correo enviado a {cantidad} {destinatario_texto}.')

            except Exception as e:
                messages.error(self.request, f'Ocurrió un error al enviar el correo: {str(e)}')
                return super().form_invalid(form)
        else:
            messages.warning(self.request, 'No alumnos con correo válido.')

        return super().form_valid(form)
