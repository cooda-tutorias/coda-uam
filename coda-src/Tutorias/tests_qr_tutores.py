from io import BytesIO
import base64
import re
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, RequestFactory, Client
from django.urls import reverse
from PIL import Image

from Usuarios.models import Tutor, Cordinador
from Usuarios.services.qr_tutor import generar_qr_tutor
from Tutorias.services.qr_tutores_pdf import generar_pdf_qr_tutores


class PermisosQRTutoresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coda = get_user_model().objects.create_user(email="coda-qr@example.com", matricula="coda-qr", rol=["CODA"])
        cls.coord = Cordinador.objects.create_user(email="coord-qr@example.com", matricula="coord-qr", coordinacion="COM")
        cls.uno = Tutor.objects.create_user(email="uno-qr@example.com", matricula="uno-qr", coordinacion="COM", first_name="Ana")
        cls.otro = Tutor.objects.create_user(email="otro-qr@example.com", matricula="otro-qr", coordinacion="MAT", first_name="Beatriz")
        cls.alumno = get_user_model().objects.create_user(email="alu-qr@example.com", matricula="alu-qr", rol=["ALU"])

    def setUp(self):
        self.url = reverse("imprimir-qr-tutores")

    def test_coda_seleccion_exacta_sin_duplicados(self):
        self.client.force_login(self.coda)
        with patch("Tutorias.services.qr_tutores_pdf.generar_pdf_qr_tutores", return_value=BytesIO(b"%PDF-test")) as generar:
            response = self.client.post(self.url, {"tutores": [self.otro.pk, self.otro.pk]}, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([t.pk for t in generar.call_args.args[1]], [self.otro.pk])
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(b"".join(response.streaming_content), b"%PDF-test")

    def test_coordinador_limita_lista_y_pdf(self):
        self.client.force_login(self.coord)
        response = self.client.get(reverse("Tutores-Cordinador"), secure=True)
        self.assertContains(response, f'data-tutor-id="{self.uno.pk}"')
        self.assertNotContains(response, f'data-tutor-id="{self.otro.pk}"')
        with patch("Tutorias.services.qr_tutores_pdf.generar_pdf_qr_tutores", return_value=BytesIO(b"%PDF-test")) as generar:
            response = self.client.post(self.url, {"tutores": [self.uno.pk]}, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"%PDF-test")
            generar.reset_mock()
            response = self.client.post(self.url, {"tutores": [self.uno.pk, self.otro.pk]}, secure=True)
            self.assertEqual(response.status_code, 403)
            generar.assert_not_called()

    def test_ids_invalidos_no_generan_pdf(self):
        self.client.force_login(self.coda)
        for ids in ([], ["abc"], ["-1"], ["1.5"], ["9" * 19], ["9" * 30], [str(self.otro.pk + 9999)]):
            with self.subTest(ids=ids), patch("Tutorias.services.qr_tutores_pdf.generar_pdf_qr_tutores") as generar:
                response = self.client.post(self.url, {"tutores": ids}, secure=True)
                self.assertIn(response.status_code, (400, 403))
                generar.assert_not_called()

    def test_roles_metodo_y_csrf(self):
        self.assertEqual(self.client.post(self.url, secure=True).status_code, 302)
        for user in (self.uno, self.alumno):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url, {"tutores": [self.uno.pk]}, secure=True).status_code, 403)
        self.client.force_login(self.coda)
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.coda)
        self.assertEqual(client.post(self.url, {"tutores": [self.uno.pk]}, secure=True).status_code, 403)

    def test_lista_coda_conserva_reportes_y_agrega_acciones(self):
        self.client.force_login(self.coda)
        response = self.client.get(reverse("Tutores-Coda"), secure=True)
        self.assertContains(response, reverse("Reporte-tutorias-masivo"))
        self.assertContains(response, "Generar reportes masivos")
        self.assertContains(response, "Acciones (0)")
        self.assertContains(response, "Imprimir QR")

    def test_filtro_licenciatura_limita_filas_seleccionables(self):
        self.client.force_login(self.coda)
        for codigo, incluido, excluido in [('COM', self.uno, self.otro), ('MAT', self.otro, self.uno)]:
            response = self.client.get(reverse('Tutores-Coda'), {'licenciatura': codigo}, secure=True)
            self.assertContains(response, f'data-tutor-id="{incluido.pk}"')
            self.assertNotContains(response, f'data-tutor-id="{excluido.pk}"')
            self.assertEqual(response.context['licenciatura_seleccionada'], codigo)
        response = self.client.get(reverse('Tutores-Coda'), secure=True)
        for tutor in [self.uno, self.otro]:
            self.assertContains(response, f'data-tutor-id="{tutor.pk}"')
        response = self.client.get(reverse('Tutores-Coda'), {'licenciatura': 'invalida'}, secure=True)
        self.assertFalse(response.context['object_list'].exists())

    def test_qr_individual_usa_servicio_compartido(self):
        self.client.force_login(self.uno)
        with patch("Usuarios.services.qr_tutor.generar_qr_tutor", wraps=generar_qr_tutor) as generar:
            response = self.client.get(reverse("ver_qr_tutor"), secure=True)
            self.assertEqual(response.status_code, 200)
            generar.assert_called_once()
            self.assertEqual(response.context["url_qr"], f"https://testserver/tutorias/in-situ/{self.uno.pk}/")
            self.assertContains(response, 'download="qr_tutor.png"')
            png = base64.b64decode(response.context["qr_base64"].split(",", 1)[1])
            with Image.open(BytesIO(png)) as tarjeta:
                self.assertEqual(tarjeta.format, "PNG")
                self.assertEqual(tarjeta.size, (750, 1000))
                self.assertEqual(tarjeta.getpixel((15, 15)), (240, 130, 0))
                self.assertEqual(tarjeta.getpixel((15, 950)), (240, 130, 0))
                self.assertAlmostEqual(tarjeta.info["dpi"][0], 300, places=1)



class DocumentoQRTutoresTests(SimpleTestCase):
    def test_url_y_qr_conservan_flujo_individual(self):
        request = RequestFactory().get("/", secure=True)
        tutor = SimpleNamespace(pk=123)
        with patch("Usuarios.services.qr_tutor.qrcode.QRCode") as factory:
            url, _ = generar_qr_tutor(request, tutor)
            self.assertEqual(url, "https://testserver/tutorias/in-situ/123/")
            factory.assert_called_once_with(box_size=20, border=4)
            factory.return_value.add_data.assert_called_once_with(url)

    def test_pdf_carta_nueve_tarjetas_por_pagina(self):
        request = RequestFactory().get("/", secure=True)
        for cantidad, paginas in ((1, 1), (9, 1), (10, 2), (90, 10)):
            with self.subTest(cantidad=cantidad):
                tutores = [SimpleNamespace(pk=n, nombre_completo="María José Álvarez Pérez", matricula=str(n),
                           get_coordinacion_display=lambda: "Ingeniería en Computación") for n in range(cantidad)]
                with patch("Tutorias.services.qr_tutores_pdf.generar_qr_tutor", return_value=("url", Image.new("RGB", (32, 32), "white"))) as generar:
                    data = generar_pdf_qr_tutores(request, tutores).getvalue()
                self.assertTrue(data.startswith(b"%PDF-"))
                self.assertEqual(len(re.findall(rb"/Type /Page\b", data)), paginas)
                self.assertEqual(generar.call_count, cantidad)
                self.assertIn(b"/MediaBox [ 0 0 612 792 ]", data)
