import hashlib

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from .constants import CODA, COORDINADOR, TUTOR
from .forms import TrayectoriaUploadForm
from .mixins import BaseAccessMixin
from .models import Alumno, TrayectoriaVersion


def can_view_trayectoria(usuario, alumno):
    if not usuario.is_authenticated:
        return False
    if usuario.pk == alumno.pk:
        return True
    if usuario.has_role(CODA) or usuario.has_role(COORDINADOR):
        return True
    return usuario.has_role(TUTOR) and alumno.tutor_asignado_id == usuario.pk


def can_manage_trayectoria(usuario, alumno):
    return usuario.is_authenticated and usuario.pk == alumno.pk


def _calcular_sha256(archivo):
    digest = hashlib.sha256()
    for bloque in archivo.chunks():
        digest.update(bloque)
    archivo.seek(0)
    return digest.hexdigest()


def _preservar_trayectoria_legada(alumno):
    archivo_legado = alumno.trayectoria
    if (
        not archivo_legado
        or alumno.trayectoria_versiones.exists()
        or not archivo_legado.storage.exists(archivo_legado.name)
    ):
        return

    with archivo_legado.open('rb') as archivo:
        sha256 = _calcular_sha256(archivo)

    TrayectoriaVersion.objects.create(
        alumno=alumno,
        archivo=archivo_legado.name,
        original_filename=archivo_legado.name.rsplit('/', 1)[-1][:255],
        size_bytes=archivo_legado.size,
        sha256=sha256,
        is_active=False,
    )


def _eliminar_version(alumno, version):
    era_activa = version.is_active
    almacenamiento = version.archivo.storage
    nombre_archivo = version.archivo.name

    version.delete()

    if era_activa:
        version_anterior = alumno.trayectoria_versiones.order_by('-created_at', '-pk').first()
        if version_anterior:
            version_anterior.is_active = True
            version_anterior.save(update_fields=['is_active'])
            alumno.trayectoria = version_anterior.archivo
        else:
            alumno.trayectoria = None
        alumno.save(update_fields=['trayectoria'])

    transaction.on_commit(lambda: almacenamiento.delete(nombre_archivo))


class TrayectoriaAccessMixin(BaseAccessMixin):
    def get_alumno(self):
        return get_object_or_404(
            Alumno.objects.select_related('tutor_asignado'),
            pk=self.kwargs['pk'],
        )

    def require_management_access(self, alumno):
        if not can_manage_trayectoria(self.request.user, alumno):
            raise PermissionDenied


class SubirTrayectoriaView(TrayectoriaAccessMixin, View):
    def post(self, request, pk):
        alumno = self.get_alumno()
        self.require_management_access(alumno)

        form = TrayectoriaUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            for error in form.errors.get('archivo', []):
                messages.error(request, error)
            return redirect('perfil-alumno', pk=alumno.pk)

        archivo = form.cleaned_data['archivo']
        version = form.save(commit=False)
        version.alumno = alumno
        version.original_filename = archivo.name[:255]
        version.size_bytes = archivo.size
        version.sha256 = _calcular_sha256(archivo)
        version.uploaded_by = request.user

        with transaction.atomic():
            alumno = Alumno.objects.select_for_update().get(pk=alumno.pk)
            _preservar_trayectoria_legada(alumno)
            alumno.trayectoria_versiones.filter(is_active=True).update(is_active=False)
            version.alumno = alumno
            version.save()
            alumno.trayectoria = version.archivo
            alumno.save(update_fields=['trayectoria'])

        messages.success(request, 'Se cargó una nueva versión de tu trayectoria académica.')
        return redirect('perfil-alumno', pk=alumno.pk)


class VerTrayectoriaView(TrayectoriaAccessMixin, View):
    def get(self, request, pk):
        alumno = self.get_alumno()
        if not can_view_trayectoria(request.user, alumno):
            raise PermissionDenied

        version_id = request.GET.get('version_id')
        if version_id:
            try:
                version_id = int(version_id)
            except (TypeError, ValueError):
                raise Http404('La versión solicitada no existe.')
            version = get_object_or_404(
                TrayectoriaVersion,
                pk=version_id,
                alumno=alumno,
            )
            archivo = version.archivo
            nombre = version.original_filename
        else:
            version = alumno.trayectoria_versiones.filter(is_active=True).first()
            if version:
                archivo = version.archivo
                nombre = version.original_filename
            elif alumno.trayectoria:
                archivo = alumno.trayectoria
                nombre = alumno.trayectoria.name.rsplit('/', 1)[-1]
            else:
                raise Http404('No existe trayectoria disponible.')

        response = FileResponse(
            archivo.open('rb'),
            as_attachment=request.GET.get('download') == '1',
            filename=nombre,
            content_type='application/pdf',
        )
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class EliminarTrayectoriaActivaView(TrayectoriaAccessMixin, View):
    def post(self, request, pk):
        alumno = self.get_alumno()
        self.require_management_access(alumno)

        with transaction.atomic():
            alumno = Alumno.objects.select_for_update().get(pk=alumno.pk)
            version = alumno.trayectoria_versiones.select_for_update().filter(is_active=True).first()
            if not version:
                messages.info(request, 'No hay una trayectoria activa para eliminar.')
                return redirect('perfil-alumno', pk=alumno.pk)
            _eliminar_version(alumno, version)

        messages.success(request, 'La trayectoria activa fue eliminada.')
        return redirect('perfil-alumno', pk=alumno.pk)


class EliminarVersionTrayectoriaView(TrayectoriaAccessMixin, View):
    def post(self, request, pk, version_id):
        alumno = self.get_alumno()
        self.require_management_access(alumno)

        with transaction.atomic():
            alumno = Alumno.objects.select_for_update().get(pk=alumno.pk)
            version = get_object_or_404(
                alumno.trayectoria_versiones.select_for_update(),
                pk=version_id,
            )
            _eliminar_version(alumno, version)

        messages.success(request, 'La versión fue eliminada.')
        return redirect('perfil-alumno', pk=alumno.pk)
