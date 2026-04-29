from django.urls import path, re_path, include
from django.contrib.auth import views as auth_views
from django.contrib import admin
from . import views
import notifications.urls
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.UsuarioLoginView.as_view(), name='login'),
    path('logout/', auth_views.logout_then_login, name='logout'),
    #path('perfil-test/', views.perfil_view_test, name='perfil-test'),
    path('perfil-alumno/<int:pk>/', views.PerfilAlumnoView.as_view(), name='perfil-alumno'),
    path('perfil-tutor/<int:pk>/', views.PerfilTutorView.as_view(), name='perfil-tutor'),
    path('perfil-coordinador/<int:pk>/', views.PerfilCordinadorView.as_view(), name='perfil-coordinador'),
    path('perfil-coda/<int:pk>/', views.PerfilCodaView.as_view(), name='perfil-coda'),
    path('perfil/', views.redirect_perfil, name='perfil'),
    path('reset-password/', auth_views.PasswordResetView.as_view(), name='reset_password'),
    re_path(r'^inbox/notifications/', include(notifications.urls, namespace='notifications')),
    re_path(r'login_success/$', views.login_success, name='login_success'),

    # Password change URLs
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    path('password-change-done/', views.PasswordChangeDoneView.as_view(), name='password_change_done'),

    path('remove-notifications/', views.BorrarNotificaciones.as_view(), name='remove-notifications'),

    # URLs del Coda para creación de usuarios
    path('registrar-alumno/', views.CreateAlumnoView.as_view(), name='crear-alumno'),
    path('modificar-alumno/<int:pk>/', views.ChangeAlumnoView.as_view(), name="editar-alumno"),
    path('registrar-tutor/', views.CreateTutorView.as_view(), name='crear-tutor'),
    path('registrar-coordinador/', views.CreateCordinadorView.as_view(), name='crear-coordinador'),
    path("importar-alumnos/", views.ImportAlumnosView.as_view(), name="importar-alumnos"),
    path('ver-alumnos/', views.VerAlumnosCODDAAView.as_view(), name='ver-alumnos'),
    path('ajustes/', views.ajustes.as_view(), name='ajustes'),
    path('cargar_plantilla/', views.CargarPlantilla.as_view(), name='cargar_plantilla'),
    path('eliminar-documento/<int:pk>/', views.eliminar_documento, name='eliminar_documento'),
    path('ver_plantilla/<int:documento_id>/', views.VerPlantilla.as_view(), name='ver_plantilla')
    # ... (other existing URL patterns)
]