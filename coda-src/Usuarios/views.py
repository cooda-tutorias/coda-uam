import os
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
    model = Usuario
    template_name = 'Usuarios/perfil_tutor.html'

    def get_queryset(self) -> QuerySet[Any]:
        return Usuario.objects.filter(rol__contains=["TUT"])  # Filter for Tutors


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


def comunicacion_masiva(request):
    return render(request, 'Tutorias/comunicacionMasiva.html')