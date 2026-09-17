"""Formato institucional compartido por cartas, reportes y mediciones."""

def normalizar_numero_oficio(oficio_ingresado, fecha_documento) -> str:
    """Normaliza el número de oficio al formato institucional esperado."""
    if oficio_ingresado in (None, ""):
        return ""

    anio = fecha_documento.year
    return f"DCNI_CODDAA_{int(oficio_ingresado)}_{anio}"
