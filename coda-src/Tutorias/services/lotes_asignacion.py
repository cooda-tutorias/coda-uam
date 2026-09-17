"""Selección, agrupación y empaquetado de cartas para varias licenciaturas."""
from collections import OrderedDict
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from django.core.exceptions import ValidationError
from django.utils.text import slugify
from Usuarios.models import Alumno
from .cartas_asignacion import cargar_plantilla, generar_carta


def seleccionar_alumnos(valor):
    valores = valor.split(',') if valor else []
    if not valores or any(not v.isdigit() for v in valores):
        raise ValidationError('Selecciona al menos un alumno en Alumnos registrados.')
    ids = set(int(v) for v in valores)
    alumnos = list(Alumno.objects.filter(pk__in=ids).select_related('tutor_asignado').order_by(
        'carrera', 'tutor_asignado__last_name', 'tutor_asignado__first_name', 'tutor_asignado_id',
        'last_name', 'second_last_name', 'first_name', 'pk'))
    if len(alumnos) != len(ids):
        raise ValidationError('Algunos alumnos seleccionados ya no existen. Actualiza la selección.')
    return alumnos


def agrupar_alumnos(alumnos):
    grupos = OrderedDict()
    for alumno in alumnos:
        clave = (alumno.carrera, alumno.tutor_asignado_id)
        if clave not in grupos:
            grupos[clave] = {'carrera': alumno.get_carrera_display(), 'codigo': alumno.carrera,
                             'tutor': alumno.tutor_asignado if alumno.tutor_asignado_id else None, 'alumnos': []}
        grupos[clave]['alumnos'].append(alumno)
    return list(grupos.values())


def generar_lote(alumnos, datos):
    if any(not alumno.tutor_asignado_id for alumno in alumnos):
        raise ValidationError('Hay alumnos sin tutor asignado. Corrige su asignación o exclúyelos antes de generar.')
    grupos = agrupar_alumnos(alumnos)
    tipos = ('alumno', 'tutor') if datos['destinatarios'] == 'ambas' else (datos['destinatarios'],)
    # Validar todas las plantillas antes de producir cualquier carta.
    plantillas = {tipo: cargar_plantilla(datos['plantilla_' + tipo].archivo_fuente, tipo) for tipo in tipos}
    consecutivos = {tipo: datos['oficio_' + tipo] for tipo in tipos}
    if len(tipos) == 2:
        a, t = consecutivos['alumno'], consecutivos['tutor']
        if max(a, t) < min(a + len(alumnos), t + len(grupos)):
            raise ValidationError('Los intervalos de oficios para alumnos y tutores se superponen. Cambia uno de los números iniciales.')
    paquetes = OrderedDict()
    for grupo in grupos:
        codigo = grupo['codigo']
        if codigo not in paquetes:
            paquetes[codigo] = BytesIO()
        with ZipFile(paquetes[codigo], 'a', ZIP_DEFLATED) as archivo:
            for tipo in tipos:
                destinatarios = [[alumno] for alumno in grupo['alumnos']] if tipo == 'alumno' else [grupo['alumnos']]
                for seleccion in destinatarios:
                    # La carta del tutor debe mencionar la licenciatura de estos alumnos,
                    # que puede diferir de la coordinación del profesor.
                    contenido = generar_carta(plantillas[tipo], grupo['tutor'], seleccion,
                                              consecutivos[tipo], datos['fecha'], tipo,
                                              licenciatura=grupo['carrera'])
                    persona = seleccion[0] if tipo == 'alumno' else grupo['tutor']
                    nombre = slugify(f'{persona.matricula}_{persona.first_name}_{persona.last_name}')
                    archivo.writestr(f'Cartas_para_{"alumnos" if tipo == "alumno" else "tutores"}/{consecutivos[tipo]}_{nombre}.docx', contenido)
                    consecutivos[tipo] += 1
    if len(paquetes) == 1:
        codigo, contenido = next(iter(paquetes.items()))
        return f'Cartas_asignacion_{slugify(codigo)}.zip', contenido.getvalue()
    salida = BytesIO()
    with ZipFile(salida, 'w', ZIP_DEFLATED) as archivo:
        for codigo, contenido in paquetes.items():
            archivo.writestr(f'Cartas_asignacion_{slugify(codigo)}.zip', contenido.getvalue())
    return 'Cartas_asignacion_licenciaturas.zip', salida.getvalue()
