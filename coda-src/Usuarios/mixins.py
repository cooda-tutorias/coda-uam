from typing import Any, Dict
from .constants import TUTOR, ALUMNO, COORDINADOR, CODA, TEMPLATES
from .models import Usuario
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

class ContextConRolesMixin:
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        selected_role = self.request.session.get("role")

        if self.request.user.has_role(COORDINADOR):
            context["header_footer"] = TEMPLATES[COORDINADOR]
        elif self.request.user.has_role(TUTOR):
            context["header_footer"] = TEMPLATES[TUTOR]
        elif self.request.user.has_role(ALUMNO):
            context["header_footer"] = TEMPLATES[ALUMNO]
        elif self.request.user.has_role(CODA):
            context["header_footer"] = TEMPLATES[CODA]
        elif selected_role == "alumno":
            context["header_footer"] = TEMPLATES[ALUMNO]
        elif selected_role == "tutor":
            context["header_footer"] = TEMPLATES[TUTOR]
        elif selected_role == "coordinador":
            context["header_footer"] = TEMPLATES[COORDINADOR]
        elif selected_role == "coda":
            context["header_footer"] = TEMPLATES[CODA]
        else:
            context["header_footer"] = TEMPLATES[COORDINADOR]

        return context

class ContextNotificationsMixin:

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = Usuario.objects.get(pk=self.request.user.pk)
        notifications_raw = user.notifications.unread()
        unread_notifications = []

        for notification in notifications_raw:
            notificacion_temp = {
                "header": "Notificacion" if not notification.description else f"{notification.description}",
                "text": f'{notification.verb} por {Usuario.objects.get(matricula=notification.actor).get_full_name()}',
                "time": notification.timestamp
            }
            unread_notifications.append(notificacion_temp)

        context["notificaciones_list"] = unread_notifications
        return context
    
class BaseAccessMixin(LoginRequiredMixin, ContextConRolesMixin, ContextNotificationsMixin):

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        return super().get_context_data(**kwargs)

class CodaViewMixin(BaseAccessMixin, UserPassesTestMixin):

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        return super().get_context_data(**kwargs)

    def test_func(self) -> bool:
        return self.request.user.has_role(CODA)

class TutorViewMixin(BaseAccessMixin, UserPassesTestMixin):

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        return super().get_context_data(**kwargs)

    def test_func(self) -> bool:
        return self.request.user.has_role(TUTOR)

class AlumnoViewMixin(BaseAccessMixin, UserPassesTestMixin):

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        return super().get_context_data(**kwargs)

    def test_func(self) -> bool:
        return self.request.user.has_role(ALUMNO)

class CordinadorViewMixin(BaseAccessMixin, UserPassesTestMixin):

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        return super().get_context_data(**kwargs)

    def test_func(self) -> bool:
        return self.request.user.has_role(COORDINADOR)
