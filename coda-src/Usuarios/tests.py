from django.test import TestCase
from django.db import models
from Usuarios.models import Tutor, Cordinador, Coda  
from django.contrib.auth import get_user_model

# Importar el modelo de Usuario
Usuario = get_user_model()

class CubiculoTestCase(TestCase):

    def test_campo_cubiculo_es_charfield(self):
        modelos = [Tutor, Cordinador, Coda]
        
        for modelo in modelos:
            campo = modelo._meta.get_field('cubiculo')
            # Verifica que el campo sea de tipo models.CharField
            self.assertIsInstance(campo, models.CharField)

            
    def test_tipo_interno_cubiculo(self):
            modelos = [Tutor, Cordinador, Coda]
            
            for modelo in modelos:
                tipo = modelo._meta.get_field('cubiculo').get_internal_type()
                # Compara la cadena de texto 'CharField'
                self.assertEqual(tipo, 'CharField')


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
