from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from unittest.mock import patch

import docx
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from Usuarios.models import Coda, Tutor, Alumno, Documento
from .services.cartas_asignacion import parrafos


class LotesAsignacionTests(TestCase):
    def setUp(self):
        temporal = TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        configuracion = override_settings(MEDIA_ROOT=temporal.name)
        configuracion.enable()
        self.addCleanup(configuracion.disable)
        self.coda = Coda.objects.create_user(email='coda.lote@example.com', matricula='900', password='test')
        self.tutor = Tutor.objects.create_user(email='tutor.lote@example.com', matricula='901', password='test',
                                              first_name='Ana', last_name='Tutor', sexo='F', coordinacion='COM')
        self.otro = Tutor.objects.create_user(email='otro.lote@example.com', matricula='902', password='test',
                                             first_name='Otro', last_name='Tutor', sexo='M', coordinacion='MAT')
        self.alumnos = []
        for indice in range(12):
            self.alumnos.append(Alumno.objects.create_user(
                email=f'alumno{indice}@example.com', matricula=str(1000 + indice), password='test',
                first_name=f'Alumno{indice}', last_name='Nuevo', carrera='COM' if indice < 10 else 'MAT',
                trimestre_ingreso='26-O', tutor_asignado=self.tutor if indice != 9 else self.otro))
        self.anterior = Alumno.objects.create_user(email='anterior@example.com', matricula='2000', password='test',
                                                   first_name='Anterior', last_name='No incluir', carrera='COM',
                                                   trimestre_ingreso='25-O', tutor_asignado=self.tutor)
        ejemplos = Path(__file__).resolve().parent.parent / 'plantillas_ejemplo'
        self.plantillas = {}
        for tipo in ('alumno', 'tutor'):
            self.plantillas[tipo] = Documento.objects.create(nombre=f'Plantilla {tipo}', tipo=tipo,
                archivo=ContentFile((ejemplos / f'carta_asignacion_{tipo}_plantilla.docx').read_bytes(), name=f'{tipo}.docx'))
        self.client.force_login(self.coda)
        self.url = reverse('cartas-asignacion-lote')

    def datos(self, alumnos=None, **cambios):
        datos = {'accion': 'generar', 'seleccion': ','.join(str(a.pk) for a in (alumnos or self.alumnos)),
                 'destinatarios': 'ambas', 'plantilla_alumno': self.plantillas['alumno'].pk,
                 'plantilla_tutor': self.plantillas['tutor'].pk, 'oficio_alumno': 63, 'oficio_tutor': 100,
                 'fecha': '2026-09-15'}
        datos.update(cambios)
        return datos

    def texto(self, contenido):
        return '\n'.join(p.text for p in parrafos(docx.Document(BytesIO(contenido))))

    def test_filtros_y_columna_tutor(self):
        response = self.client.get(reverse('ver-alumnos'), {'carrera': 'MAT', 'trimestre_ingreso': '26-O'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['alumnos']), 2)
        self.assertContains(response, 'Tutor asignado')
        self.assertContains(response, 'id="seleccionar-alumnos"')
        self.assertNotContains(response, 'No incluir')

    def test_resumen_varios_tutores_y_paginas(self):
        response = self.client.post(self.url, self.datos(accion='preparar'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_alumnos'], 12)
        self.assertEqual(response.context['total_tutores'], 2)
        self.assertEqual(response.context['total_cartas_tutor'], 3)
        self.assertEqual(response.context['form']['destinatarios'].value(), 'ambas')
        self.assertContains(response, 'Generar cartas y descargar ZIP')

    def test_zip_separado_por_licenciatura_y_solo_seleccionados(self):
        response = self.client.post(self.url, self.datos())
        self.assertEqual(response['Content-Type'], 'application/zip')
        with ZipFile(BytesIO(response.content)) as externo:
            self.assertEqual(len(externo.namelist()), 2)
            documentos = []
            for nombre in externo.namelist():
                with ZipFile(BytesIO(externo.read(nombre))) as interno:
                    for ruta in interno.namelist():
                        texto = self.texto(interno.read(ruta))
                        consecutivo_archivo = ruta.rsplit('/', 1)[-1].split('_', 1)[0]
                        self.assertIn(f'DCNI_CODDAA_{consecutivo_archivo}_2026', texto)
                        self.assertNotIn('{', texto)
                        self.assertNotIn('No incluir', texto)
                        documentos.append((nombre, ruta, texto))
                        if 'tutores/' in ruta and 'mat.zip' in nombre:
                            self.assertIn('Matemáticas Aplicadas', texto)
                            self.assertNotIn('Ingeniería en Computación', texto)
            self.assertEqual(len(documentos), 15)
            self.assertEqual(sum('Cartas_para_alumnos/' in ruta for _, ruta, _ in documentos), 12)
            self.assertEqual(sum('Cartas_para_tutores/' in ruta for _, ruta, _ in documentos), 3)
            for consecutivo in range(63, 75):
                self.assertTrue(any(f'DCNI_CODDAA_{consecutivo}_2026' in texto for _, _, texto in documentos))

    def test_un_alumno_genera_ambas_cartas_en_zip_directo(self):
        response = self.client.post(self.url, self.datos([self.alumnos[0]]))
        with ZipFile(BytesIO(response.content)) as archivo:
            self.assertEqual(len(archivo.namelist()), 2)
            self.assertTrue(all(nombre.endswith('.docx') for nombre in archivo.namelist()))

    def test_solo_alumnos_no_requiere_plantilla_tutor(self):
        response = self.client.post(self.url, self.datos([self.alumnos[0]], destinatarios='alumno', plantilla_tutor='', oficio_tutor=''))
        with ZipFile(BytesIO(response.content)) as archivo:
            self.assertEqual(len(archivo.namelist()), 1)
            self.assertTrue(archivo.namelist()[0].startswith('Cartas_para_alumnos/'))

    def test_solo_tutores(self):
        response = self.client.post(self.url, self.datos(self.alumnos[:10], destinatarios='tutor', plantilla_alumno='', oficio_alumno=''))
        with ZipFile(BytesIO(response.content)) as archivo:
            self.assertEqual(len(archivo.namelist()), 2)
            self.assertTrue(all(nombre.startswith('Cartas_para_tutores/') for nombre in archivo.namelist()))

    def test_colision_oficios_no_descarga_zip(self):
        response = self.client.post(self.url, self.datos(oficio_tutor=64))
        self.assertContains(response, 'se superponen')
        self.assertNotEqual(response['Content-Type'], 'application/zip')

    def test_error_plantilla_conserva_seleccion(self):
        response = self.client.post(self.url, self.datos(plantilla_alumno=self.plantillas['tutor'].pk))
        self.assertIn('plantilla_alumno', response.context['form'].errors)
        self.assertEqual(response.context['total_alumnos'], 12)
        self.assertEqual(response.context['form']['oficio_alumno'].value(), '63')

    def test_ids_invalidos_y_eliminados(self):
        for seleccion in ('', 'x', '99999999'):
            response = self.client.post(self.url, self.datos(seleccion=seleccion))
            self.assertEqual(response.status_code, 400)

    def test_sin_tutor_no_se_omite_silenciosamente(self):
        alumno = self.alumnos[0]
        alumno.tutor_asignado_id = None
        with patch('Tutorias.views_cartas.seleccionar_alumnos', return_value=[alumno]):
            response = self.client.post(self.url, self.datos())
            self.assertContains(response, 'Hay alumnos sin tutor')
            self.assertNotEqual(response['Content-Type'], 'application/zip')

    def test_acceso_restringido(self):
        self.client.force_login(self.tutor)
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.datos()).status_code, 302)
