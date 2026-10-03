import mimetypes
from os.path import basename

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views import View

from .constants import CODA
from .models import Alumno, Documento, TrayectoriaVersion, Usuario
from .views_trayectoria import can_view_trayectoria


def _respuesta_archivo_privado(campo_archivo, descargar=False):
    nombre = campo_archivo.name
    response = FileResponse(
        campo_archivo.open('rb'),
        as_attachment=descargar,
        filename=basename(nombre),
        content_type=mimetypes.guess_type(nombre)[0] or 'application/octet-stream',
    )
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


class ArchivoPrivadoView(LoginRequiredMixin, View):
    def get(self, request, nombre):
        usuario = Usuario.objects.filter(foto=nombre).first()
        if usuario:
            return _respuesta_archivo_privado(usuario.foto)

        version = TrayectoriaVersion.objects.select_related(
            'alumno', 'alumno__tutor_asignado'
        ).filter(archivo=nombre).first()
        if version:
            if not can_view_trayectoria(request.user, version.alumno):
                raise PermissionDenied
            return _respuesta_archivo_privado(
                version.archivo,
                descargar=request.GET.get('download') == '1',
            )

        alumno = Alumno.objects.select_related('tutor_asignado').filter(
            trayectoria=nombre
        ).first()
        if alumno:
            if not can_view_trayectoria(request.user, alumno):
                raise PermissionDenied
            return _respuesta_archivo_privado(
                alumno.trayectoria,
                descargar=request.GET.get('download') == '1',
            )

        documento = Documento.objects.filter(archivo=nombre).first()
        if documento:
            if not request.user.has_role(CODA):
                raise PermissionDenied
            return _respuesta_archivo_privado(documento.archivo, descargar=True)

        raise Http404('El archivo solicitado no existe.')
