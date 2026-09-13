"""Tarjetas en cuadrícula fija para impresión en carta al 100 %."""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from Usuarios.services.qr_tutor import generar_qr_tutor
from Usuarios.services.tarjeta_qr import generar_tarjeta_qr

MARGIN = 12.7 * mm
WIDTH, HEIGHT = letter
CARD_WIDTH = (WIDTH - 2 * MARGIN) / 3
CARD_HEIGHT = (HEIGHT - 2 * MARGIN) / 3


def dibujar_cortes(pdf):
    pdf.setStrokeColor(colors.HexColor("#bbbbbb"))
    pdf.setLineWidth(.3)
    for n in range(4):
        x = MARGIN + n * CARD_WIDTH
        y = MARGIN + n * CARD_HEIGHT
        pdf.line(x, MARGIN, x, HEIGHT - MARGIN)
        pdf.line(MARGIN, y, WIDTH - MARGIN, y)


def generar_pdf_qr_tutores(request, tutores):
    buffer = BytesIO()
    pdf = Canvas(buffer, pagesize=letter)
    pdf.setTitle("Códigos QR de tutores — imprimir al 100 %")
    for index, tutor in enumerate(tutores):
        position = index % 9
        if position == 0:
            if index:
                dibujar_cortes(pdf)
                pdf.showPage()
            pdf.setFont("Helvetica", 6)
            pdf.setFillColor(colors.HexColor("#555555"))
            pdf.drawCentredString(WIDTH / 2, 6 * mm, "Carta · Imprimir a tamaño real (100 %)")
        col, row = position % 3, position // 3
        left = MARGIN + col * CARD_WIDTH
        top = HEIGHT - MARGIN - row * CARD_HEIGHT
        _, qr = generar_qr_tutor(request, tutor)
        tarjeta = generar_tarjeta_qr(tutor, qr)
        pdf.drawImage(ImageReader(tarjeta), left, top - CARD_HEIGHT,
                      CARD_WIDTH, CARD_HEIGHT)
    dibujar_cortes(pdf)
    pdf.save()
    buffer.seek(0)
    return buffer
