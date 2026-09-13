"""QR compartido por la pantalla individual y las tarjetas administrativas."""
import qrcode
from django.urls import reverse


def generar_qr_tutor(request, tutor):
    url = request.build_absolute_uri(
        reverse("tutoria_insitu", kwargs={"tutor_pk": tutor.pk})
    )
    qr = qrcode.QRCode(box_size=20, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    return url, qr.make_image(fill_color="black", back_color="white").convert("RGB")
