"""Diseño único de la tarjeta para el PNG individual y las hojas PDF."""
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

ANCHO_MM = 63.5
ALTO_MM = 254 / 3
DPI = 300
ESCALA = DPI / 25.4


def generar_tarjeta_qr(tutor, qr):
    def px(mm):
        return round(mm * ESCALA)

    image = Image.new("RGB", (px(ANCHO_MM), px(ALTO_MM)), "white")
    draw = ImageDraw.Draw(image)
    fonts = Path(settings.BASE_DIR) / "static/Alumnos/fonts/montserrat"

    def texto(value, top, height, size, bold=False, color="black"):
        path = fonts / ("Montserrat-Bold.ttf" if bold else "Montserrat-Regular.ttf")
        width = px(ANCHO_MM - 6)
        # Ajustar palabras y nombres largos al espacio reservado, sin truncarlos.
        while True:
            font = ImageFont.truetype(str(path), max(1, round(size * DPI / 72)))
            lines = []
            line = ""
            for word in str(value).split():
                candidate = f"{line} {word}".strip()
                if line and draw.textlength(candidate, font=font) > width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            if line:
                lines.append(line)
            leading = size * DPI / 72 * 1.12
            if (len(lines) * leading <= px(height)
                    and all(draw.textlength(line, font=font) <= width for line in lines)) or size <= 3:
                break
            size -= .25
        for n, line in enumerate(lines):
            draw.text((image.width / 2, px(top) + n * leading), line,
                      font=font, fill=color, anchor="mt")

    # NEAREST mantiene los módulos negros/blancos nítidos y el margen del QR.
    # Pegar la imagen QR
    qr_size = px(50)
    image.paste(qr.resize((qr_size, qr_size), Image.Resampling.NEAREST),
                ((image.width - qr_size) // 2, px(12)))

    # Encabezado de la tarjeta
    inset = px(.15)
    draw.rectangle((inset, inset, image.width - inset - 1, px(14) - 1), fill="#F08200")
    draw.rectangle((inset, px(77), image.width - inset - 1, image.height - inset - 1), fill="#F08200")
    texto("Sistema de tutorías DCNI", 2.5, 4, 9, color="white")
    texto(tutor.nombre_completo, 7, 7, 10, True, "white")

    # Base de la tarjeta
    texto("¿Tutoría sin cita previa?", 60, 4, 9.5, True)
    texto("REGÍSTRALA AQUÍ", 64, 4.5, 11, True)
    texto("Si tu tutoría ya está agendada, no escanees el QR", 71, 3, 7.5)
    texto(tutor.get_coordinacion_display(), 79, 6, 9, True, "white")
    return image
