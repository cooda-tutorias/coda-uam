from django.test import TestCase
from django.db import models
from Usuarios.models import Tutor, Cordinador, Coda  

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