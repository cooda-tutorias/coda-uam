import os
import json
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
from django.contrib.auth.hashers import make_password
from django.contrib import messages
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

from .models import HorarioTutor
from .forms import HorarioTutorForm
from django.db import transaction

from webpush.models import PushInformation, SubscriptionInfo

class SettingsTutorView(BaseAccessMixin, TemplateView):
    template_name = "Usuarios/configuraciones.html"  

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pasamos el usuario al contexto para que funcione {{ usuario.first_name }}
        context['usuario'] = self.request.user 
        
             
        # Aquí se pasa la llave pública VAPID de WebPush
        context['vapid_public_key'] = settings.WEBPUSH_SETTINGS['VAPID_PUBLIC_KEY']

        # Verificamos si el usuario ya existe en la BD de Push
        # Esto devuelve True o False
        context['is_push_active'] = PushInformation.objects.filter(user=self.request.user).exists() 
               
        return context


@require_POST
@login_required
def save_information(request):
    try:
        data = json.loads(request.body)
        status_type = data.get('status_type')
        
        sub_data = data.get('subscription', {})
        endpoint = sub_data.get('endpoint')
        keys = sub_data.get('keys', {})
        auth_key = keys.get('auth')
        p256dh_key = keys.get('p256dh')
        browser = data.get('browser', 'Chrome')

        if not endpoint:
            return JsonResponse({'error': 'No endpoint provided'}, status=400)

        # CASO 1: DESUSCRIBIR
        if status_type == 'unsubscribe':
            count, _ = PushInformation.objects.filter(
                user=request.user,
                subscription__endpoint=endpoint
            ).delete()
            
            # Opcional: Limpiar huérfanos
            SubscriptionInfo.objects.filter(endpoint=endpoint).delete()
            
            print(f"✅ Suscripción eliminada para: {request.user}")
            return HttpResponse(status=200)

        # CASO 2: SUSCRIBIR
        elif status_type == 'subscribe':
            # Paso A: Guardamos los datos técnicos (Aquí SÍ va el browser)
            subscription_obj, created = SubscriptionInfo.objects.update_or_create(
                endpoint=endpoint,
                defaults={
                    'auth': auth_key,
                    'p256dh': p256dh_key,
                    'browser': browser 
                }
            )

            # Paso B: Vinculamos al usuario (Aquí NO va el browser)
            # PushInformation solo necesita User y Subscription
            PushInformation.objects.get_or_create(
                user=request.user,
                subscription=subscription_obj,
                defaults={
                    'group': None 
                }
            )
            
            print(f"✅ Suscripción guardada correctamente para: {request.user}")
            return HttpResponse(status=201)

        else:
            return JsonResponse({'error': 'Invalid status_type'}, status=400)

    except Exception as e:
        print(f"💥 Error en save_information: {str(e)}")
        import traceback
        traceback.print_exc()
        return HttpResponse(status=500)


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
        # Authenticate the user
        user = form.get_user()
        selected_role = self.request.POST.get("role")  # Get role from form input

        if user is not None:
            # Fetch user's roles from the database
            user_roles = user.get_roles()

            # Check if the selected role exists in the user's roles
            if selected_role == "coordinador" and COORDINADOR in user_roles:
                user = Cordinador.objects.get(pk=user.pk)
            elif selected_role == "tutor" and TUTOR in user_roles:
                # Ensure we log in as Tutor only if Coordinador is NOT the selected role
                if not (COORDINADOR in user_roles and selected_role == "tutor"):
                    user = Tutor.objects.get(pk=user.pk)
            elif selected_role == "alumno" and ALUMNO in user_roles:
                user = Alumno.objects.get(pk=user.pk)
            elif selected_role == "coda" and CODA in user_roles:
                user = Coda.objects.get(pk=user.pk)
            else:
                # If the selected role is invalid, show an error
                messages.error(self.request, "Rol no válido para este usuario.")
                return redirect("login")

            # Log in user with the correct role
            login(self.request, user)
            self.request.session["role"] = selected_role
            self.request.session.modified = True  # Ensure session updates

            # Revisa si una alumno escaneó el QR de su tutor y fue redirigido a login, 
            # para redirigirlo a la URL para registrar la tutoría in situ después de iniciar sesión.
            next_url = self.request.POST.get("next") or self.request.GET.get("next")
            if next_url:
                return redirect(next_url)

            # Redirect to the appropriate profile page
            return redirect(reverse_lazy(f"perfil-{selected_role}", kwargs={"pk": user.pk}))

        # If the user does not exist, show an error
        messages.error(self.request, "El usuario no existe. Verifique sus credenciales.")
        return redirect("login")


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

    def form_valid(self, form):
        uploaded_file = self.request.FILES.get('archivo')

        # Get default context (ensures user roles are included)
        context = self.get_context_data(form=form)

        if not uploaded_file:
            context["error"] = "No file uploaded."
            return render(self.request, self.template_name, context)

        warnings = []  # Stores students that couldn't be created
        success_count = 0  # Tracks successful imports

        try:
            file_extension = uploaded_file.name.split(".")[-1]
            if file_extension in ["xls", "xlsx"]:
                df = pd.read_excel(uploaded_file)
            elif file_extension == "csv":
                df = pd.read_csv(uploaded_file)
            else:
                context["error"] = "Invalid file format."
                return render(self.request, self.template_name, context)

            # Check for required columns
            required_columns = ["Plan de estudios", "Matrícula", "Correo institucional", "Correo", "Apellido 1", "Apellido 2", "Nombres", "No. Económico de Tutor", "Estado", "Sexo", "rfc", "Trimestre Ingreso"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                context["error"] = f"Missing columns: {', '.join(missing_columns)}"
                return render(self.request, self.template_name, context)

            # Process data row by row
            for _, row in df.iterrows():
                try:
                    matricula = str(row["Matrícula"]).strip()
                    email = row["Correo institucional"].strip()
                    correo_personal = row["Correo"].strip()
                    last_name = row["Apellido 1"].strip()
                    second_last_name = row["Apellido 2"].strip()
                    first_name = row["Nombres"].strip()
                    rfc = row["rfc"].strip()
                    # carrera = CARRERAS[row["Plan de estudios"].strip()]
                    carrera = next((key for key, value in CARRERAS if value == row["Plan de estudios"].strip()), None)
                    estado = row["Estado"]
                    # estado = next((key for key, value in ESTADOS_ALUMNO if value == row["Estado"]), None)
                    sexo = next((key for key, value in SEXOS if value == row["Sexo"].strip()), None)
                    tutor_id = row["No. Económico de Tutor"]
                    trimestre_ingreso = row["Trimestre Ingreso"].strip()

                    # Ensure required fields are valid
                    if not (matricula and email and first_name and last_name and carrera and estado and sexo and tutor_id):
                        print("matricula :",matricula)
                        print("email :",email)
                        print("correo_personal :",correo_personal)
                        print("last_name :",last_name)
                        print("second_last_name :",second_last_name)
                        print("first_name :",first_name)
                        print("rfc :",rfc)
                        print("carrera :",carrera)
                        print("estado :",estado)
                        print("sexo :",sexo)
                        print("tutor_id :",tutor_id)
                        print("trimestre_ingreso :",trimestre_ingreso)
                        warnings.append(f"Alumno {matricula}: Datos obligatorios faltantes. Asegúrese de que todos los campos obligatorios de información estén presentes.")
                        continue  # Skip to the next student

                    # Find assigned tutor
                    tutor_asignado = Tutor.objects.filter(matricula=tutor_id).first()
                    if not tutor_asignado:
                        warnings.append(f"Alumno {matricula}: Tutor con número económico {tutor_id} no encontrado. Aseegúrese de que el tutor esté registrado en el sistema.")
                        continue

                    # Generate password (increment each digit of matricula by 1)
                    password = matricula
                    hashed_password = make_password(password)

                    # Create Usuario
                    usuario, created = Usuario.objects.get_or_create(
                        matricula=matricula,
                        defaults={
                            "email": email,
                            "correo_personal": correo_personal,
                            "first_name": first_name,
                            "last_name": last_name,
                            "second_last_name": second_last_name,
                            "password": hashed_password,
                            "rol": [ALUMNO],
                            "sexo":sexo
                        },
                    )

                    # Check if already an Alumno
                    if not Alumno.objects.filter(id=usuario.id).exists():
                        alumno = Alumno(
                            id=usuario.id,
                            carrera=carrera,
                            estado=estado,
                            tutor_asignado=tutor_asignado,
                            trimestre_ingreso=trimestre_ingreso,
                            rfc=rfc
                        )
                        alumno.__dict__.update(usuario.__dict__)  # Copy fields
                        alumno.save()

                    success_count += 1  # Increment success counter

                except Exception as e:
                    warnings.append(f"Alumno {matricula}: {str(e)}")
                    continue  # Skip to next student

            # Update context
            context.update({
                "warnings": warnings if warnings else None,
                "success": f"{success_count} alumnos importados exitosamente." if success_count > 0 else None,
            })

            return render(self.request, self.template_name, context)

        except Exception as e:
            context.update({
                "error": str(e),
                "warnings": warnings if warnings else None,  # Ensure warnings are included
            })
            return render(self.request, self.template_name, context)

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
    
def eliminar_documento(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    archivo_path = os.path.join(settings.MEDIA_ROOT, str(documento.archivo))

    if os.path.exists(archivo_path):
        os.remove(archivo_path) 

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

class VerAlumnosCODDAAView(FormView):
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
