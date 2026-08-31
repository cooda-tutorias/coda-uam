import os
import json
import logging
from uuid import UUID
from django.conf import settings  # ✅ Asegurar que está importado
from typing import Any, Dict
from django.shortcuts import get_object_or_404
from django.db.models.query import QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import render, HttpResponse
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView
from django.views.generic import TemplateView, DeleteView, UpdateView
from .models import Usuario, Tutor, Alumno, Coda, Cordinador
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.urls import reverse_lazy, reverse
from django.views.generic.edit import FormView
from .forms import FormVerAlumnos, ImportAlumnosForm
from django.shortcuts import get_object_or_404
from django.views.generic.list import ListView
from django.http import HttpResponseBadRequest
from django.views.generic import View
from django.http import HttpResponse
#from .models import Tutoria
from . import forms as userForms
from .mixins import BaseAccessMixin, CodaViewMixin, AlumnoViewMixin, CordinadorViewMixin, TutorViewMixin
from django.http import JsonResponse
from .forms import ImportAlumnosForm
from .models import Alumno, Usuario, Tutor
from .constants import CARRERAS, ESTADOS_ALUMNO, SEXOS, ALUMNO, CODA, COORDINADOR, TUTOR
from django.contrib import messages
from django.core.exceptions import PermissionDenied
import io
import pandas as pd
from .models import Documento
from .forms import DocumentoForm

# Bibliotecas para generar códigos QR
import qrcode
import base64
from io import BytesIO
from django.views import View
from django.http import Http404
from PIL import Image, ImageDraw, ImageFont

from .models import HorarioTutor, PushDevice
from .forms import HorarioTutorForm
from django.db import transaction
from .services.importacion_alumnos import (
    ErrorImportacionAlumnos,
    importar_alumnos_validados,
    validar_archivo_alumnos,
)
from .services.plantilla_importacion_alumnos import (
    generar_plantilla_importacion_alumnos,
)

from webpush.models import PushInformation, SubscriptionInfo

logger = logging.getLogger(__name__)

class SettingsTutorView(BaseAccessMixin, TemplateView):
    template_name = "Usuarios/configuraciones.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["usuario"] = self.request.user
        context["vapid_public_key"] = settings.WEBPUSH_SETTINGS["VAPID_PUBLIC_KEY"]
        context["push_enabled"] = self.request.user.notificaciones_habilitadas
        return context


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except (TypeError, ValueError):
        return None


def _serialize_push_device(device, current_device_id=None):
    return {
        "id": device.pk,
        "browser": device.browser or "Navegador",
        "operating_system": device.operating_system or "Sistema no identificado",
        "device_name": device.device_name or "Dispositivo",
        "status": device.status,
        "is_current": device.pk == current_device_id,
        "created_at": device.created_at.isoformat(),
        "last_seen_at": device.last_seen_at.isoformat(),
    }


@require_POST
@login_required
def push_notification_state(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Solicitud JSON inválida."}, status=400)

    endpoint = data.get("endpoint")
    try:
        installation_id = UUID(str(data.get("installation_id")))
    except (TypeError, ValueError, AttributeError):
        installation_id = None
    devices = list(
        PushDevice.objects.filter(user=request.user).select_related("subscription")
    )
    current_by_endpoint = next(
        (device for device in devices if endpoint and device.subscription.endpoint == endpoint),
        None,
    )
    if current_by_endpoint and installation_id and not current_by_endpoint.installation_id:
        installation_owner = PushDevice.objects.filter(
            installation_id=installation_id,
        ).first()
        if installation_owner is None:
            current_by_endpoint.installation_id = installation_id
            current_by_endpoint.save(update_fields=["installation_id", "last_seen_at"])
    current = current_by_endpoint or next(
        (
            device for device in devices
            if installation_id and device.installation_id == installation_id
        ),
        None,
    )
    if current:
        current.save(update_fields=["last_seen_at"])
    return JsonResponse({
        "enabled": request.user.notificaciones_habilitadas,
        "current_device": _serialize_push_device(current, current.pk) if current else None,
        "current_endpoint_matches": bool(current_by_endpoint),
        "other_devices": [
            _serialize_push_device(device, current.pk if current else None)
            for device in devices
            if current is None or device.pk != current.pk
        ],
    })


@require_POST
@login_required
def set_push_preference(request):
    data = _json_body(request)
    if data is None or not isinstance(data.get("enabled"), bool):
        return JsonResponse({"error": "Indica una preferencia válida."}, status=400)

    request.user.notificaciones_habilitadas = data["enabled"]
    request.user.save(update_fields=["notificaciones_habilitadas"])
    return JsonResponse({"enabled": request.user.notificaciones_habilitadas})


def _register_push_device(request, data):
    sub_data = data.get("subscription") or {}
    keys = sub_data.get("keys") or {}
    endpoint = sub_data.get("endpoint")
    auth_key = keys.get("auth")
    p256dh_key = keys.get("p256dh")
    try:
        installation_id = UUID(str(data.get("installation_id")))
    except (TypeError, ValueError, AttributeError):
        installation_id = None
    if not all((endpoint, auth_key, p256dh_key, installation_id)):
        return None, JsonResponse(
            {"error": "La suscripción del navegador está incompleta."},
            status=400,
        )

    with transaction.atomic():
        installed_device = PushDevice.objects.select_for_update().filter(
            installation_id=installation_id,
        ).select_related("subscription").first()
        subscriptions = list(
            SubscriptionInfo.objects.select_for_update().filter(endpoint=endpoint).order_by("pk")
        )
        subscription = subscriptions[0] if subscriptions else SubscriptionInfo(endpoint=endpoint)
        subscription.auth = auth_key
        subscription.p256dh = p256dh_key
        subscription.browser = (data.get("browser") or "Navegador")[:100]
        subscription.user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        subscription.save()

        old_subscription = None
        if installed_device and installed_device.subscription_id != subscription.pk:
            old_subscription = installed_device.subscription

        # El endpoint identifica al navegador. Al activarlo desde otra cuenta se
        # transfiere a la cuenta actual para evitar entregas cruzadas.
        PushInformation.objects.filter(
            subscription__endpoint=endpoint,
        ).delete()
        if old_subscription:
            PushInformation.objects.filter(subscription=old_subscription).delete()
        for duplicate in subscriptions[1:]:
            duplicate.delete()

        PushInformation.objects.create(
            user=request.user,
            subscription=subscription,
            group=None,
        )
        device_defaults = {
            "user": request.user,
            "status": PushDevice.Status.ACTIVE,
            "browser": (data.get("browser") or "Navegador")[:100],
            "operating_system": (data.get("operating_system") or "")[:100],
            "device_name": (data.get("device_name") or "Dispositivo actual")[:150],
            "installation_id": installation_id,
        }
        if installed_device:
            preserve_custom_name = installed_device.user_id == request.user.pk
            PushDevice.objects.filter(subscription=subscription).exclude(
                pk=installed_device.pk,
            ).delete()
            installed_device.subscription = subscription
            for field, value in device_defaults.items():
                if field == "device_name" and preserve_custom_name and installed_device.device_name:
                    continue
                setattr(installed_device, field, value)
            installed_device.save()
            device = installed_device
        else:
            device, _ = PushDevice.objects.update_or_create(
                subscription=subscription,
                defaults=device_defaults,
            )

        if old_subscription:
            old_subscription.delete()
        if not request.user.notificaciones_habilitadas:
            request.user.notificaciones_habilitadas = True
            request.user.save(update_fields=["notificaciones_habilitadas"])

    return device, None


@require_POST
@login_required
def save_information(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Solicitud JSON inválida."}, status=400)

    if data.get("status_type") == "unsubscribe":
        endpoint = (data.get("subscription") or {}).get("endpoint")
        device = PushDevice.objects.filter(
            user=request.user,
            subscription__endpoint=endpoint,
        ).select_related("subscription").first()
        if device:
            device.subscription.delete()
        return JsonResponse({"deleted": bool(device)})

    if data.get("status_type") not in (None, "subscribe"):
        return JsonResponse({"error": "Operación no válida."}, status=400)

    device, error_response = _register_push_device(request, data)
    if error_response:
        return error_response
    return JsonResponse(
        {"device": _serialize_push_device(device, device.pk), "enabled": True},
        status=201,
    )


@require_POST
@login_required
def set_push_device_status(request, device_id):
    data = _json_body(request)
    status = data.get("status") if data else None
    if status not in PushDevice.Status.values:
        return JsonResponse({"error": "Estado de dispositivo no válido."}, status=400)

    device = get_object_or_404(PushDevice, pk=device_id, user=request.user)
    device.status = status
    device.save(update_fields=["status", "updated_at", "last_seen_at"])
    return JsonResponse({"device": _serialize_push_device(device, device.pk)})


@require_POST
@login_required
def rename_push_device(request, device_id):
    data = _json_body(request)
    name = data.get("device_name") if data else None
    if not isinstance(name, str) or not name.strip():
        return JsonResponse({"error": "Escribe un nombre para el dispositivo."}, status=400)

    name = name.strip()
    if len(name) > PushDevice._meta.get_field("device_name").max_length:
        return JsonResponse(
            {"error": "El nombre puede tener como máximo 150 caracteres."},
            status=400,
        )

    device = get_object_or_404(PushDevice, pk=device_id, user=request.user)
    device.device_name = name
    device.save(update_fields=["device_name", "updated_at", "last_seen_at"])
    return JsonResponse({"device": _serialize_push_device(device, device.pk)})


@require_POST
@login_required
def delete_push_device(request, device_id):
    device = get_object_or_404(
        PushDevice.objects.select_related("subscription"),
        pk=device_id,
        user=request.user,
    )
    device.subscription.delete()
    return JsonResponse({"deleted": True})


@require_POST
@login_required
def test_push_device(request, device_id):
    if not request.user.notificaciones_habilitadas:
        return JsonResponse(
            {"message": "Activa primero la preferencia general de notificaciones."},
            status=409,
        )
    device = get_object_or_404(
        PushDevice.objects.select_related("subscription"),
        pk=device_id,
        user=request.user,
        status=PushDevice.Status.ACTIVE,
    )
    data = _json_body(request)
    endpoint = data.get("endpoint") if data else None
    if not endpoint or endpoint != device.subscription.endpoint:
        return JsonResponse(
            {"message": "La prueba sólo puede enviarse al dispositivo actual."},
            status=400,
        )
    from Tutorias.signals.handle_push_notifications import send_test_push

    sent, message = send_test_push(device)
    return JsonResponse({"sent": sent, "message": message}, status=200 if sent else 502)


class HorariosTutorView(BaseAccessMixin, View):
    """Vista para manejar la creación y actualización de horarios de tutor."""

    def get(self, request):
        if not request.user.is_tutor:
            raise Http404()

        horarios = HorarioTutor.objects.filter(tutor=request.user)
        form = HorarioTutorForm()

        # Lista de hararios que se mostrarán
        horas = [
            f"{h:02d}:{m:02d}"
            for h in range(8, 17)      # Desde las 08:00 hasta las 16:30
            for m in (0, 30)           # Intervalos de 30 minutos
        ]

        return render(
            request,
            "Usuarios/horarios_tutor.html",
            {
                "form": form,
                "horarios": horarios,
                "horas": horas,
                "dias_semana": HorarioTutor.DiaSemana.choices,
                "header_footer": "Usuarios/navbar_tutor.html",
            }
        )

    def post(self, request):
        if not request.user.is_tutor:
            raise Http404()

        tutor = request.user

        # Transacción atómica: si algo falla a la mitad, revierte el borrado
        with transaction.atomic():

            # 1. Eliminar todos los horarios anteriores
            HorarioTutor.objects.filter(tutor=tutor).delete()

            # 2. Reconstruirlos iterando sobre las claves de DiaSemana (0, 1, 2, 3, 4)
            for dia_int, _ in HorarioTutor.DiaSemana.choices:
                inicios = request.POST.getlist(f"inicio_{dia_int}[]")
                fines = request.POST.getlist(f"fin_{dia_int}[]")

                for inicio, fin in zip(inicios, fines):
                    if inicio and fin:
                        HorarioTutor.objects.create(
                            tutor=tutor,
                            dia_semana=dia_int,
                            hora_inicio=inicio,
                            hora_fin=fin,
                        )

        messages.success(request, "Tus horarios fueron actualizados con éxito.")

        return redirect("tutor_horarios")


class EliminarHorarioTutorView(BaseAccessMixin, View):
    def post(self, request, pk):
        horario = get_object_or_404(HorarioTutor, pk=pk, tutor=request.user)
        horario.delete()
        return redirect("tutor_horarios")


class ListaHorariosTutorView(BaseAccessMixin, ListView):
    model = HorarioTutor
    template_name = "Usuarios/tutor_horarios.html"

    def get_queryset(self):
        return HorarioTutor.objects.filter(tutor=self.request.user)


# Esta es la vista que genera el código QR para los tutores, incluyendo 
# el diseño institucional y la información del tutor.
# El código QR sirve para solicitar tutorías in situ, y la 
# URL codificada en el QR redirige a la vista de tutorías in situ.
class VerQRView(BaseAccessMixin, View):

    def get(self, request):
        user = request.user

        if not user.is_tutor:
            raise Http404("Solo los tutores pueden ver su QR.")

        # URL destino del QR
        url_qr = request.build_absolute_uri(
            reverse("tutoria_insitu", kwargs={"tutor_pk": user.pk}) ##reverse("tutoria_insitu", args=[tutor_pk])
        )

        # Generar QR
        qr = qrcode.QRCode(box_size=20, border=4)
        qr.add_data(url_qr)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        qr_width, qr_height = qr_img.size

        #  DISEÑO INSTITUCIONAL 

        # Barra institucional
        banner_height = 120
        total_height = banner_height + qr_height + 50  # espacio extra abajo

        final_img = Image.new("RGB", (qr_width, total_height), "white")
        draw = ImageDraw.Draw(final_img)

        # Barra superior
        draw.rectangle([(0, 0), (qr_width, banner_height)], fill="#F08200")

        # Cargar fuente Montserrat
        font_path = os.path.join(
            settings.BASE_DIR,
            "Usuarios/static/fonts/Montserrat-Regular.ttf"
        )

        # ========================================
        # Calcular ancho necesario para texto
        # ========================================

        # ========================================
        # Texto en dos líneas
        # ========================================

        line1 = "Tutorías DCNI"
        line2 = f"{user.first_name} {user.last_name}"

        # Cargar fuente
        try:
            font = ImageFont.truetype(font_path, 52)
        except:
            font = ImageFont.load_default()

        # Medir líneas
        line1_w, line1_h = draw.textsize(line1, font=font)
        line2_w, line2_h = draw.textsize(line2, font=font)

        side_margin = 80

        # Nuevo ancho: lo suficiente para el texto más largo
        final_width = max(qr_width, line1_w + side_margin, line2_w + side_margin)

        # Alturas
        banner_height = line1_h + line2_h + 50
        spacing_between_lines = 10  # espacio vertical entre línea 1 y línea 2

        total_height = banner_height + qr_height + 50

        # Crear imagen final
        final_img = Image.new("RGB", (final_width, total_height), "white")
        draw = ImageDraw.Draw(final_img)

        # Barra superior
        draw.rectangle([(0, 0), (final_width, banner_height)], fill="#F08200")

        # Posiciones centradas
        line1_x = (final_width - line1_w) // 2
        line2_x = (final_width - line2_w) // 2

        # Punto vertical de inicio
        start_y = 20

        # Dibujar texto centrado
        draw.text((line1_x, start_y), line1, fill="white", font=font)
        draw.text((line2_x, start_y + line1_h + spacing_between_lines), line2, fill="white", font=font)

        # Centrar QR
        qr_x = (final_width - qr_width) // 2
        final_img.paste(qr_img, (qr_x, banner_height + 20))

        # Exportar imagen como base64
        buffer = BytesIO()
        final_img.save(buffer, format="PNG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        return render(
            request,
            "Usuarios/ver_qr.html",
            {
                "qr_base64": f"data:image/png;base64,{img_base64}",
                "url_qr": url_qr,
                "header_footer": "Usuarios/navbar_tutor.html",
            },
        )

    
# Test Views (Remove for production)
def login_view_test(request):
    return render(request, 'Usuarios/login.html')

def perfil_view_test(request):
    return render(request, 'Usuarios/perfil.html')

def recordarcontras_view_test(request):
    return render(request, 'Usuarios/recordarContrasenia.html')


### Profile Views Updated for `Usuario`
class PerfilAlumnoView(BaseAccessMixin, DetailView):
    model = Usuario
    template_name = 'Usuarios/perfil_alumno.html'

    def get_queryset(self) -> QuerySet[Any]:
        return Usuario.objects.filter(rol__contains=["ALU"])  # Filter for Alumnos


class PerfilTutorView(BaseAccessMixin, DetailView):
    """Muestra el perfil público o detallado de un tutor.

    Permite a los alumnos y coordinadores visualizar los datos del tutor.
    Agrega al contexto el flag `user_es_tutor` para mostrar u ocultar campos
    sensibles (como el número económico) en la plantilla.
    """
    
    model = Usuario
    template_name = 'Usuarios/perfil_tutor.html'

    def get_queryset(self) -> QuerySet[Any]:
        return Usuario.objects.filter(rol__contains=["TUT"])  # Filter for Tutors

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # 1. Verificar si el usuario que está VISUALIZANDO la página (request.user)
        #    tiene el rol de Tutor.
        user_es_tutor = self.request.user.has_role("TUT")

        # 2. Pasar el resultado booleano al contexto
        context['user_es_tutor'] = user_es_tutor

        return context

class PerfilCodaView(BaseAccessMixin, DetailView):
    model = Usuario
    template_name = 'Usuarios/perfil_cooda.html'

    def get_queryset(self) -> QuerySet[Any]:
        return Usuario.objects.filter(rol__contains=["CODA"])  # Filter for Coda


class PerfilCordinadorView(BaseAccessMixin, DetailView):
    model = Usuario
    template_name = 'Usuarios/perfil_coordinador.html'

    def get_queryset(self) -> QuerySet[Any]:
        return Usuario.objects.filter(rol__contains=["COR"])  # Filter for Coordinadores


# Antonio LJ
@login_required
def redirect_perfil_tutor(request):
    """
    Obtiene el tutor del alumno autenticado y lo redirige a la vista PerfilTutorView.
    """
    try:
        # 1. Obtener la instancia de Alumno asociada al usuario actual
        # Asumimos que Alumno hereda de Usuario o tiene un campo relacionado con request.user
        alumno = Alumno.objects.get(pk=request.user.pk)

        # 2. Obtener la instancia del Tutor asignado
        # Asumimos que el modelo Alumno tiene un campo llamado 'tutor_asignado'
        tutor_pk = alumno.tutor_asignado.pk # Asumiendo que Tutor está relacionado con User

        # Si el tutor está relacionado directamente con el modelo Tutor y este a su vez
        # con el modelo Usuario, se debe obtener la PK del Usuario del Tutor
        # Si el Tutor hereda de Usuario, simplemente usamos:
        # tutor_pk = alumno.tutor_asignado.pk

        tutor_pk = alumno.tutor_asignado.pk # Asumiendo que Tutor hereda de Usuario

    except Alumno.DoesNotExist:
        messages.error(request, "El usuario actual no es un alumno o no está registrado como tal.")
        return redirect('perfil-alumno') # Redireccionar a una página segura
    except AttributeError: # Si 'tutor_asignado' es None
        messages.warning(request, "Aún no tienes un tutor asignado.")
        return redirect('perfil-alumno') # Redireccionar a una página segura

    # 3. Redirigir a la vista del perfil del tutor, usando su PK
    return redirect('perfil-tutor', pk=tutor_pk)

### Role-Based Profile Redirection
@login_required
def redirect_perfil(request):
    user = request.user

    if user.has_role("TUT"):
        return redirect('perfil-tutor', pk=user.pk)

    if user.has_role("ALU"):
        return redirect('perfil-alumno', pk=user.pk)

    if user.has_role("CODA"):
        return redirect('perfil-coda', pk=user.pk)

    if user.has_role("COR"):
        return redirect('perfil-coordinador', pk=user.pk)

    return redirect('perfil-alumno', pk=user.pk)  # Default case


### Role-Based Login Success Redirection
@login_required
def login_success(request):
    user = request.user
    selected_role = request.session.get("role")  # Retrieve stored role from session

    if selected_role == "alumno" and user.has_role("ALU"):
        return redirect("Tutorias-alumno")

    if selected_role == "tutor" and user.has_role("TUT"):
        return redirect("Tutorias-tutor")

    if selected_role == "coordinador" and user.has_role("COR"):
        return redirect("Tutorias-Coordinacion")

    if selected_role == "coda" and user.has_role("CODA"):
        return redirect("Tutores-Coda")

    print("ERROR: Usuario no definido o rol incorrecto")
    return HttpResponseBadRequest("ERROR. Tipo de usuario o rol no definido")


class UsuarioLoginView(LoginView):
    redirect_authenticated_user = True
    template_name = "Usuarios/login.html"

    def form_valid(self, form):
        user = form.get_user()
        role_config = {
            ALUMNO: ("alumno", Alumno),
            TUTOR: ("tutor", Tutor),
            COORDINADOR: ("coordinador", Cordinador),
            CODA: ("coda", Coda),
        }
        user_roles = user.get_roles() or []

        # Cada cuenta representa un solo perfil. No elegimos silenciosamente
        # entre varios roles porque el segundo rol también concedería permisos.
        if len(user_roles) != 1 or user_roles[0] not in role_config:
            logger.warning(
                "Inicio de sesión rechazado por configuración de roles inválida: "
                "usuario_id=%s roles=%r",
                user.pk,
                user_roles,
            )
            messages.error(
                self.request,
                "Esta cuenta tiene una configuración de roles inválida. "
                "Contacta al administrador para corregirla.",
            )
            return redirect("login")

        selected_role, role_model = role_config[user_roles[0]]
        try:
            role_user = role_model.objects.get(pk=user.pk)
        except role_model.DoesNotExist:
            logger.warning(
                "Inicio de sesión rechazado porque falta el perfil asociado: "
                "usuario_id=%s rol=%s modelo=%s",
                user.pk,
                user_roles[0],
                role_model.__name__,
            )
            messages.error(
                self.request,
                "Esta cuenta no tiene un perfil válido. "
                "Contacta al administrador para corregirla.",
            )
            return redirect("login")

        login(self.request, role_user)
        # Se conserva para que ContextConRolesMixin seleccione el navbar.
        self.request.session["role"] = selected_role
        self.request.session.modified = True

        # Permite continuar hacia una tutoría in situ después del login.
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url:
            return redirect(next_url)

        tutoring_panels = {
            "alumno": "Tutorias-alumno",
            "tutor": "Panel-tutorias-tutor",
        }
        if selected_role in tutoring_panels:
            return redirect(tutoring_panels[selected_role])

        return redirect(
            reverse_lazy(f"perfil-{selected_role}", kwargs={"pk": role_user.pk})
        )


class ChangePasswordView(BaseAccessMixin, PasswordChangeView):
    template_name = 'Usuarios/change_password.html'  # Create a template for password change form
    success_url = reverse_lazy('password_change_done')  # Redirect to this URL after a successful password change

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        return super().get_context_data(**kwargs)


class PasswordChangeDoneView(TemplateView):
    template_name = 'Usuarios/password_change_done.html'


### Notification Handling
class BorrarNotificaciones(View):
    def post(self, request):
        usuario = Usuario.objects.get(pk=self.request.user.pk)
        notificaciones = usuario.notifications.unread()
        notificaciones.mark_all_as_read()
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))


### Create User Views (Updated for `Usuario`)
class CreateAlumnoView(CodaViewMixin, CreateView):
    model = Alumno
    template_name = 'Usuarios/agregar_alumno.html'
    success_url = reverse_lazy('login_success')
    form_class = userForms.FormAlumno
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Convierte CARRERAS en diccionario {'MAT': 'Matemáticas Aplicadas', ...}
        context['coordinacion_dict'] = {clave: nombre for clave, nombre in CARRERAS if clave}
        
        return context


class ChangeAlumnoView(CodaViewMixin, UpdateView):
    model = Alumno
    template_name = 'Usuarios/modificar_alumno.html'
    success_url = reverse_lazy('Tutores-Coda')
    form_class = userForms.FormAlumnoUpdate
    
    def get_object(self, queryset=None):
        pk = self.kwargs.get('pk')
        return get_object_or_404(Alumno, pk=pk)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Convierte CARRERAS en diccionario {'MAT': 'Matemáticas Aplicadas', ...}
        context['coordinacion_dict'] = {clave: nombre for clave, nombre in CARRERAS if clave}
        
        return context

#PermissionRequiredMixin
class CreateCordinadorView(CodaViewMixin, CreateView):
    template_name = 'Usuarios/agregar_cordinador.html'
    success_url = reverse_lazy('Tutores-Coda')
    form_class = userForms.FormCordinador


class CreateTutorView(CodaViewMixin, CreateView):
    template_name = 'Usuarios/agregar_tutor.html'
    success_url = reverse_lazy('Tutores-Coda')
    form_class = userForms.FormTutor


class ImportAlumnosView(CodaViewMixin, FormView):
    template_name = "Usuarios/importar_alumnos.html"
    form_class = userForms.ImportAlumnosForm
    success_url = reverse_lazy('Tutores-Coda')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "catalogo_carreras": CARRERAS,
            "catalogo_estados": ESTADOS_ALUMNO,
            "catalogo_sexos": SEXOS,
        })
        return context

    def form_valid(self, form):
        uploaded_file = form.cleaned_data['archivo']
        context = self.get_context_data(form=form)
        try:
            resultado = validar_archivo_alumnos(uploaded_file)
        except (ValueError, OSError, pd.errors.ParserError) as error:
            context["error"] = f"No se pudo leer el archivo: {error}"
        else:
            context.update({
                "errores_validacion": resultado.errores,
                "advertencias_validacion": resultado.advertencias,
                "total_filas": resultado.total_filas,
                "encabezados_previsualizacion": resultado.encabezados_previsualizacion,
                "filas_previsualizacion": resultado.filas_previsualizacion,
            })
            if resultado.es_valido:
                try:
                    total_importados = importar_alumnos_validados(
                        resultado.filas_validas,
                    )
                except ErrorImportacionAlumnos as error:
                    context["error"] = (
                        f"No se importó ningún alumno: {error}"
                    )
                except Exception:
                    logger.exception("Falló la importación transaccional de alumnos")
                    context["error"] = (
                        "Ocurrió un error al crear los alumnos. "
                        "La operación fue revertida y no se guardó ningún alumno."
                    )
                else:
                    context["importacion_exitosa"] = True
                    context["total_importados"] = total_importados
        return render(self.request, self.template_name, context)


class DescargarPlantillaAlumnosView(CodaViewMixin, View):
    def get(self, request):
        contenido = generar_plantilla_importacion_alumnos()
        response = HttpResponse(
            contenido,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            'attachment; filename="plantilla_importacion_alumnos.xlsx"'
        )
        return response

#PermissionRequiredMixin
class ajustes(CodaViewMixin, TemplateView):
    template_name = 'Usuarios/ajustes.html'
    success_url = reverse_lazy('Tutores-Coda')

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        documentos = Documento.objects.all()
        context['documentos'] = documentos

        return context

#PermissionRequiredMixin
class CargarPlantilla(CodaViewMixin, CreateView):
    template_name = 'Usuarios/cargar_plantilla.html'
    success_url = reverse_lazy('ajustes')
    form_class = DocumentoForm  

    def form_valid(self, form):
        return super().form_valid(form)
    
@login_required
@require_POST
def eliminar_documento(request, pk):
    if not request.user.has_role(CODA):
        raise PermissionDenied("Solo el personal CODDAA puede eliminar documentos.")

    documento = get_object_or_404(Documento, pk=pk)
    documento.archivo.delete(save=False)
    documento.delete()
    return redirect('ajustes')

#PermissionRequiredMixin
class VerPlantilla(CodaViewMixin, UpdateView):
    model = Documento
    form_class = DocumentoForm
    template_name = 'Usuarios/ver_plantilla.html'
    success_url = reverse_lazy('ajustes')

    def get_object(self, queryset=None):
        documento_id = self.kwargs.get('documento_id')
        return get_object_or_404(Documento, id=documento_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['nombre_fuente'] = self.object.nombre
        context['archivo_url'] = self.object.archivo.url if self.object.archivo else None
        return context

class VerAlumnosCODDAAView(CodaViewMixin, FormView):
    template_name = "Usuarios/ver_alumnos_coda.html"
    form_class = FormVerAlumnos

    def form_valid(self, form):
        carrera = form.cleaned_data.get("carrera")
        estado = form.cleaned_data.get("estado")

        alumnos = Alumno.objects.all()

        if carrera:
            alumnos = alumnos.filter(carrera=carrera)
        if estado:
            alumnos = alumnos.filter(estado=estado)

        context = self.get_context_data(form=form, alumnos=alumnos)
        return self.render_to_response(context)

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        alumnos = Alumno.objects.all()  # por defecto muestra todos
        return self.render_to_response(self.get_context_data(form=form, alumnos=alumnos));
