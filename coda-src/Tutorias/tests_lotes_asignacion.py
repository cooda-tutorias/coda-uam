from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from unittest.mock import patch
import shutil
import os
import time
import smtplib

import docx
from django.core.files.base import ContentFile
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from Usuarios.models import Coda, Tutor, Alumno, Documento
from Usuarios.services.vista_previa_plantillas import ErrorVistaPrevia
from .services.cartas_asignacion import parrafos
from .forms import FormMensajesAsignacion
from .services.envios_asignacion import raiz_lotes, cargar_lote, limpiar_lotes_caducados
from .services.correos_asignacion import (correos_del_lote, iniciar_envio, estado_envio,
                                        guardar_estado, bloqueo)


class HiloInmediato:
    def __init__(self, target, args, daemon):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class LotesAsignacionTests(TestCase):
    def setUp(self):
        temporal = TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        configuracion = override_settings(MEDIA_ROOT=temporal.name,
                                          CARTAS_ENVIO_ROOT=str(Path(temporal.name) / 'privados'))
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
        self.assertEqual(response.context['form']['formato'].value(), 'docx')
        self.assertContains(response, 'Word (.docx)')
        self.assertContains(response, 'PDF (.pdf)')
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

    def test_pdf_varias_licenciaturas_convierte_cartas_personalizadas(self):
        textos = []

        def convertir(contenido):
            textos.append(self.texto(contenido))
            return b'%PDF-1.7 carta'

        with patch('Tutorias.services.lotes_asignacion.convertir_pdf', side_effect=convertir) as conversor:
            response = self.client.post(self.url, self.datos(formato='pdf'))
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertEqual(conversor.call_count, 15)
        self.assertTrue(all('{' not in texto and 'DCNI_CODDAA_' in texto for texto in textos))
        with ZipFile(BytesIO(response.content)) as externo:
            self.assertEqual(len(externo.namelist()), 2)
            for nombre in externo.namelist():
                with ZipFile(BytesIO(externo.read(nombre))) as interno:
                    for ruta in interno.namelist():
                        self.assertTrue(ruta.endswith('.pdf'))
                        self.assertEqual(interno.read(ruta), b'%PDF-1.7 carta')

    def test_error_pdf_no_descarga_lote_parcial_y_conserva_formulario(self):
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf',
                   side_effect=[b'%PDF-1.7 carta', ErrorVistaPrevia('tardó demasiado')]), \
             self.assertLogs('Tutorias.services.lotes_asignacion', level='ERROR'):
            response = self.client.post(self.url, self.datos([self.alumnos[0]], formato='pdf'))
        self.assertContains(response, 'No se pudo generar el lote en PDF')
        self.assertNotEqual(response['Content-Type'], 'application/zip')
        self.assertEqual(response.context['form']['formato'].value(), 'pdf')
        self.assertEqual(response.context['form']['seleccion'].value(), str(self.alumnos[0].pk))
        self.assertEqual(response.context['form']['oficio_alumno'].value(), '63')

    def test_formato_invalido_no_genera(self):
        response = self.client.post(self.url, self.datos(formato='otro'))
        self.assertIn('formato', response.context['form'].errors)

    def test_pdf_real_para_alumno_y_tutor(self):
        if not (shutil.which('libreoffice') or shutil.which('soffice')):
            self.skipTest('LibreOffice no está instalado.')
        response = self.client.post(self.url, self.datos([self.alumnos[0]], formato='pdf'))
        self.assertEqual(response['Content-Type'], 'application/zip')
        with ZipFile(BytesIO(response.content)) as archivo:
            self.assertEqual(len(archivo.namelist()), 2)
            for nombre in archivo.namelist():
                self.assertTrue(nombre.endswith('.pdf'))
                self.assertTrue(archivo.read(nombre).startswith(b'%PDF-'))
                self.assertGreater(len(archivo.read(nombre)), 1000)

    def test_word_explicito_no_invoca_conversor(self):
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf') as conversor:
            response = self.client.post(self.url, self.datos([self.alumnos[0]], formato='docx'))
        conversor.assert_not_called()
        self.assertEqual(response['Content-Type'], 'application/zip')

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

    def test_editor_correo_desde_seleccion(self):
        response = self.client.post(reverse('cartas-asignacion-correo'), self.datos())
        self.assertContains(response, 'Correo para alumnos')
        self.assertContains(response, 'Correo para tutores')
        self.assertContains(response, '{nombre_alumno}')
        self.assertEqual(response.context['total_alumnos'], 12)
        self.assertEqual(response.context['total_tutores'], 2)
        listado = self.client.get(reverse('ver-alumnos'))
        self.assertContains(listado, 'Enviar cartas de asignación por correo')
        self.assertContains(listado, 'formaction="' + reverse('cartas-asignacion-correo') + '"')

    def test_borrador_correo_se_recupera_solo_para_misma_seleccion(self):
        url = reverse('cartas-asignacion-correo')
        datos = self.datos(accion='guardar', destinatarios='alumno',
                           asunto_alumno='Asignación personalizada', cuerpo_alumno='Hola, {nombre_alumno}.')
        with patch('Tutorias.views_cartas.generar_lote') as generar:
            response = self.client.post(url, datos)
        generar.assert_not_called()
        self.assertTrue(response.context['guardado'])
        response = self.client.post(url, self.datos())
        self.assertEqual(response.context['form']['asunto_alumno'].value(), 'Asignación personalizada')
        response = self.client.post(url, self.datos([self.alumnos[0]]))
        self.assertNotEqual(response.context['form']['asunto_alumno'].value(), 'Asignación personalizada')

    def test_editor_correo_valida_mensajes_activos_y_seleccion(self):
        url = reverse('cartas-asignacion-correo')
        response = self.client.post(url, self.datos(accion='guardar', destinatarios='ambas'))
        self.assertIn('asunto_alumno', response.context['form'].errors)
        self.assertIn('cuerpo_tutor', response.context['form'].errors)
        self.assertNotIn('mensajes_asignacion', self.client.session)
        self.assertEqual(self.client.post(url, {'seleccion': 'x'}).status_code, 400)

    def test_editor_correo_restringido_a_coda(self):
        url = reverse('cartas-asignacion-correo')
        self.client.force_login(self.tutor)
        self.assertEqual(self.client.post(url, self.datos()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url, self.datos()).status_code, 302)

    def abrir_preparacion(self, alumnos=None, destinatarios='ambas'):
        return self.client.post(reverse('cartas-asignacion-correo'), self.datos(
            alumnos, accion='preparar', destinatarios=destinatarios,
            asunto_alumno='Asignación', cuerpo_alumno='Hola, {nombre_alumno}',
            asunto_tutor='Tutorados', cuerpo_tutor='Hola, {nombre_tutor}'))

    def test_preparar_abre_formulario_pdf_y_guarda_mensajes(self):
        response = self.abrir_preparacion()
        self.assertContains(response, 'Generar PDF para revisión')
        self.assertContains(response, 'Volver a editar mensajes')
        self.assertNotContains(response, 'Word (.docx)')
        self.assertEqual(response.context['form']['destinatarios'].value(), 'ambas')
        self.assertEqual(response.context['form']['formato'].value(), 'pdf')
        self.assertNotIn('lote_asignacion', self.client.session)
        self.assertEqual(self.client.session['mensajes_asignacion']['datos']['asunto_alumno'], 'Asignación')

    def test_preparar_lote_pdf_privado_con_snapshot_y_reemplazo(self):
        self.abrir_preparacion([self.alumnos[0]])
        url = reverse('cartas-asignacion-preparar')
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf', return_value=b'%PDF-1.7 carta'):
            response = self.client.post(url, self.datos([self.alumnos[0]], formato='docx'),
                                        HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.json()['url'], reverse('cartas-asignacion-preparadas'))
        lote = self.client.session['lote_asignacion']
        carpeta, cartas = cargar_lote(lote)
        self.assertEqual(len(cartas), 2)
        self.assertEqual(cartas[0]['correo'], self.alumnos[0].email)
        self.assertEqual(lote['mensajes']['asunto_alumno'], 'Asignación')
        pdf_url = reverse('carta-asignacion-preparada-pdf', args=[lote['token'], 0])
        response = self.client.get(pdf_url)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.7 carta')
        self.assertContains(self.client.get(reverse('cartas-asignacion-preparadas')), 'No se han enviado correos')
        otro_coda = Coda.objects.create_user(email='otro.coda@example.com', matricula='950', password='test')
        otro_cliente = Client()
        otro_cliente.force_login(otro_coda)
        self.assertEqual(otro_cliente.get(pdf_url).status_code, 404)
        self.abrir_preparacion([self.alumnos[0]])
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf', return_value=b'%PDF-1.7 nuevo'):
            self.client.post(url, self.datos([self.alumnos[0]], formato='pdf'))
        self.assertFalse(carpeta.exists())
        self.assertEqual(self.client.get(pdf_url).status_code, 404)

    def test_fallo_preparacion_elimina_pdf_parcial(self):
        self.abrir_preparacion([self.alumnos[0]])
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf',
                   side_effect=[b'%PDF-1.7 carta', ErrorVistaPrevia('Fallo')]), \
             self.assertLogs('Tutorias.services.lotes_asignacion', level='ERROR'):
            response = self.client.post(reverse('cartas-asignacion-preparar'),
                                        self.datos([self.alumnos[0]], formato='pdf'))
        self.assertContains(response, 'No se pudo generar el lote en PDF')
        self.assertNotIn('lote_asignacion', self.client.session)
        self.assertEqual(list(raiz_lotes().iterdir()), [])

    def test_preparacion_requiere_borrador_y_respeta_destinatarios(self):
        url = reverse('cartas-asignacion-preparar')
        self.assertEqual(self.client.post(url, self.datos()).status_code, 400)
        self.abrir_preparacion([self.alumnos[0]], destinatarios='alumno')
        response = self.client.post(url, self.datos([self.alumnos[0]], destinatarios='ambas'))
        self.assertIn('destinatarios', response.context['form'].errors)
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf', return_value=b'%PDF-1.7 carta'):
            response = self.client.post(url, self.datos([self.alumnos[0]], destinatarios='alumno'))
        self.assertEqual(response.status_code, 302)
        _, cartas = cargar_lote(self.client.session['lote_asignacion'])
        self.assertEqual(len(cartas), 1)
        self.assertEqual(cartas[0]['tipo'], 'alumno')

    def test_limpieza_lotes_caducados(self):
        self.abrir_preparacion([self.alumnos[0]])
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf', return_value=b'%PDF-1.7 carta'):
            self.client.post(reverse('cartas-asignacion-preparar'), self.datos([self.alumnos[0]]))
        carpeta, _ = cargar_lote(self.client.session['lote_asignacion'])
        self.assertEqual(limpiar_lotes_caducados(), 0)
        os.utime(carpeta / 'cartas.json', (time.time() - 86401, time.time() - 86401))
        self.assertEqual(limpiar_lotes_caducados(), 1)
        self.assertFalse(carpeta.exists())
        self.assertEqual(self.client.get(reverse('cartas-asignacion-preparadas')).status_code, 410)

    def test_preparacion_y_pdf_restringidos(self):
        self.client.force_login(self.tutor)
        self.assertEqual(self.client.post(reverse('cartas-asignacion-preparar'), self.datos()).status_code, 403)
        self.assertEqual(self.client.get(reverse('cartas-asignacion-preparadas')).status_code, 403)
        self.assertEqual(self.client.get(reverse('carta-asignacion-preparada-pdf', args=['a' * 32, 0])).status_code, 403)

    def preparar_para_envio(self, alumnos=None, destinatarios='ambas'):
        self.abrir_preparacion(alumnos, destinatarios)
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf', return_value=b'%PDF-1.7 exacto'):
            self.client.post(reverse('cartas-asignacion-preparar'), self.datos(alumnos, destinatarios=destinatarios))
        return self.client.session['lote_asignacion']

    def test_revision_personaliza_y_agrupa_adjuntos_de_tutor(self):
        lote = self.preparar_para_envio()
        correos = correos_del_lote(lote)
        self.assertEqual(len(correos), 14)
        alumno = next(c for c in correos if c['tipo'] == 'alumno')
        self.assertEqual(alumno['cuerpo'], 'Hola, ' + alumno['nombre'])
        tutor = next(c for c in correos if c['tipo'] == 'tutor' and len(c['adjuntos']) == 2)
        self.assertEqual(tutor['correo'], self.tutor.email)
        self.assertEqual(len(tutor['adjuntos']), 2)
        response = self.client.get(reverse('cartas-asignacion-preparadas'))
        self.assertContains(response, 'Alumnos (12)')
        self.assertContains(response, 'Tutores (2)')
        self.assertContains(response, 'data-pdf')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_envio_usa_pdf_exacto_y_no_repite_enviados(self):
        lote = self.preparar_para_envio()
        with patch('Tutorias.services.correos_asignacion.Thread', HiloInmediato):
            iniciar_envio(lote)
        self.assertEqual(len(mail.outbox), 14)
        mensaje = next(m for m in mail.outbox if m.to == [self.tutor.email])
        self.assertEqual(len(mensaje.attachments), 2)
        self.assertTrue(all(a[1] == b'%PDF-1.7 exacto' and a[2] == 'application/pdf' for m in mail.outbox for a in m.attachments))
        self.assertTrue(all(m.body == 'Hola, ' + c['nombre'] for m, c in zip(mail.outbox, correos_del_lote(lote))))
        with self.assertRaises(ValidationError):
            iniciar_envio(lote)
        self.assertEqual(len(mail.outbox), 14)
        self.assertTrue(all(r['estado'] == 'enviado' for r in estado_envio(lote)['correos'].values()))

    def test_reintento_solo_fallidos(self):
        lote = self.preparar_para_envio([self.alumnos[0]])
        with patch('Tutorias.services.correos_asignacion.Thread', HiloInmediato), \
             patch('Tutorias.services.correos_asignacion.EmailMessage.send', side_effect=[1, smtplib.SMTPDataError(550, b'Rechazado')]), \
             self.assertLogs('Tutorias.services.correos_asignacion', level='ERROR'):
            iniciar_envio(lote)
        resultados = estado_envio(lote)['correos']
        self.assertEqual([r['estado'] for r in resultados.values()], ['enviado', 'fallido'])
        with patch('Tutorias.services.correos_asignacion.Thread', HiloInmediato), \
             patch('Tutorias.services.correos_asignacion.EmailMessage.send', return_value=1) as enviar:
            iniciar_envio(lote)
        enviar.assert_called_once()

    def test_resultado_incierto_no_se_reenvia_automaticamente(self):
        lote = self.preparar_para_envio([self.alumnos[0]], destinatarios='alumno')
        with patch('Tutorias.services.correos_asignacion.Thread', HiloInmediato), \
             patch('Tutorias.services.correos_asignacion.EmailMessage.send', side_effect=TimeoutError()), \
             self.assertLogs('Tutorias.services.correos_asignacion', level='ERROR'):
            iniciar_envio(lote)
        self.assertEqual(next(iter(estado_envio(lote)['correos'].values()))['estado'], 'incierto')
        with self.assertRaises(ValidationError):
            iniciar_envio(lote)

    def test_envio_excluye_correo_invalido(self):
        self.alumnos[0].email = ''
        self.alumnos[0].save()
        lote = self.preparar_para_envio([self.alumnos[0]])
        self.assertEqual(self.client.get(reverse('cartas-asignacion-preparadas')).context['total_excluidos'], 1)
        with patch('Tutorias.services.correos_asignacion.Thread', HiloInmediato), \
             patch('Tutorias.services.correos_asignacion.EmailMessage.send', return_value=1) as enviar:
            iniciar_envio(lote)
        enviar.assert_called_once()

    def test_envio_exige_confirmacion_revision_y_token(self):
        lote = self.preparar_para_envio([self.alumnos[0]])
        url = reverse('cartas-asignacion-preparadas')
        datos = {'token': lote['token'], 'confirmar': 'si'}
        with patch('Tutorias.views_cartas.iniciar_envio') as iniciar:
            self.assertEqual(self.client.post(url, datos).status_code, 400)
            response = self.client.get(reverse('carta-asignacion-preparada-pdf', args=[lote['token'], 0]))
            response.close()
            self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
            self.assertEqual(self.client.post(url, {'token': lote['token']}).status_code, 400)
            self.assertEqual(self.client.post(url, {**datos, 'token': 'otro'}).status_code, 400)
            self.assertEqual(self.client.post(url, datos).status_code, 200)
            iniciar.assert_called_once()

    def test_envio_simultaneo_y_reemplazo_bloqueados(self):
        lote = self.preparar_para_envio([self.alumnos[0]])
        with patch('Tutorias.services.correos_asignacion.Thread'):
            iniciar_envio(lote)
        with self.assertRaises(ValidationError):
            iniciar_envio(lote)
        response = self.client.post(reverse('cartas-asignacion-preparar'), self.datos([self.alumnos[0]]))
        self.assertContains(response, 'Espera a que termine')
        self.assertEqual(self.client.session['lote_asignacion']['token'], lote['token'])

    def test_envio_interrumpido_no_repite_correo_en_curso(self):
        lote = self.preparar_para_envio([self.alumnos[0]], destinatarios='alumno')
        carpeta, _ = cargar_lote(lote)
        correo = correos_del_lote(lote)[0]
        guardar_estado(carpeta, {'fase': 'enviando', 'actualizado': time.time() - 60,
                                'correos': {correo['id']: {'estado': 'enviando', 'detalle': ''}}})
        self.assertEqual(estado_envio(lote)['fase'], 'interrumpido')
        self.assertEqual(estado_envio(lote)['correos'][correo['id']]['estado'], 'incierto')
        with self.assertRaises(ValidationError):
            iniciar_envio(lote)

    def test_limpiar_lote_no_elimina_envio_en_curso(self):
        lote = self.preparar_para_envio([self.alumnos[0]])
        carpeta, _ = cargar_lote(lote)
        os.utime(carpeta / 'cartas.json', (time.time() - 86401, time.time() - 86401))
        with bloqueo(carpeta):
            self.assertEqual(limpiar_lotes_caducados(), 0)
            self.assertTrue(carpeta.exists())

    def test_mensajes_rechazan_marcadores_no_admitidos(self):
        response = self.client.post(reverse('cartas-asignacion-correo'), self.datos(
            accion='preparar', asunto_alumno='Hola {inventado}', cuerpo_alumno='Mensaje',
            asunto_tutor='Tutor', cuerpo_tutor='Mensaje'))
        self.assertIn('asunto_alumno', response.context['form'].errors)

    @override_settings(TUTORIAS_SITE_URL='https://tutorias.example.edu')
    def test_plantillas_formales_personalizan_sexo_y_url_del_lote(self):
        inicial = FormMensajesAsignacion()
        mensajes = {campo: inicial[campo].value() for campo in (
            'asunto_alumno', 'cuerpo_alumno', 'asunto_tutor', 'cuerpo_tutor')}
        response = self.client.post(reverse('cartas-asignacion-correo'), self.datos(accion='preparar', **mensajes))
        self.assertFalse(response.context['form'].errors)
        with patch('Tutorias.services.lotes_asignacion.convertir_pdf', return_value=b'%PDF-1.7 prueba'):
            self.client.post(reverse('cartas-asignacion-preparar'), self.datos())
        lote = self.client.session['lote_asignacion']
        # El mensaje usa los datos del lote aunque cambien la cuenta y la configuración.
        self.tutor.sexo = 'M'
        self.tutor.save()
        with override_settings(TUTORIAS_SITE_URL='https://otro.example.edu'):
            correos = correos_del_lote(lote)
        for correo in correos:
            self.assertNotIn('{', correo['cuerpo'])
            self.assertIn('https://tutorias.example.edu', correo['cuerpo'])
            if correo['tipo'] == 'alumno':
                self.assertTrue(correo['cuerpo'].startswith('Estimado(a) '))
                referencia = 'del profesor Dr.' if correo['adjuntos'][0]['nombre_tutor'] == self.otro.nombre_completo else 'de la profesora Dra.'
                self.assertIn(referencia, correo['cuerpo'])
            else:
                saludo = 'Estimado Dr.' if correo['correo'] == self.otro.email else 'Estimada Dra.'
                self.assertTrue(correo['cuerpo'].startswith(saludo))
