from django.test import TestCase
from django.contrib.auth import get_user_model

# Importar el modelo de Usuario
Usuario = get_user_model()

# Clase para probar que el nombre completo de los usuarios se muestra correctamente
# aún cuando no tienen apellido materno
class UsuarioNombreCompletoTest(TestCase):
    def test_nombre_completo_con_apellido_materno(self):
        # Crear un usuario con apellido materno
        usuario = Usuario(
            first_name="Antonio",
            last_name="López",
            second_last_name="Jaimes"
        )
        self.assertEqual(usuario.nombre_completo, "Antonio López Jaimes")

    def test_nombre_completo_sin_apellido_materno(self):
        # Crear un usuario sin apellido materno
        usuario = Usuario(
            first_name="Mika",
            last_name="Olsen",
            second_last_name=None  # No tiene apellido materno
        )

        #1. Comprobamos que el nombre completo se genera correctamente sin el apellido materno.
        self.assertEqual(usuario.nombre_completo, "Mika Olsen")

        #2. Reforzamos que el apellido materno es None para este usuario.
        self.assertNotIn("None", usuario.nombre_completo)