# Plantillas de cartas de asignación

Estas copias adaptan los Word proporcionados al generador actual. Se registran
automáticamente como plantillas del sistema mediante la migración 0011 y pueden
usarse directamente. Los originales externos al repositorio no se modificaron.

En ambos Word el encabezado es `Oficio No. {no_oficio}`. El sistema inserta
`DCNI_CODDAA_63_2026`, tomando el año de la fecha de emisión. No se admite `{anio}`
ni debe agregarse el prefijo institucional alrededor de `{no_oficio}`.

## Carta dirigida al alumno

Obligatorios: `{no_oficio}`, `{fecha}`, `{nombre_alumno}`, `{matricula}`,
`{nombre_tutor}`. No debe contener tablas.

Opcionales: `{licenciatura}`, `{tutor}`, `{academico}`, `{dr}`, `{el}`, `{la}`,
`{él}`, `{asignado}`, `{reasignado}`, `{a}`, `{o}`, `{e}`. Los marcadores de
concordancia se refieren al tutor, no al alumno. `{nombre_tutor}` no incluye
tratamiento: usar `{dr} {nombre_tutor}` si se desea.

## Carta dirigida al tutor

Obligatorios: `{no_oficio}`, `{fecha}`, `{nombre_mayus_tutor}`, `{licenciatura}`.
Opcionales: `{nombre_tutor}`, `{estimado}`. Los nombres del tutor incluyen Dr./Dra.

Debe contener una primera tabla de cinco columnas, en este orden: trimestre de
ingreso, matrícula, primer apellido, segundo apellido y nombres. Se conserva la
fila de encabezados y se sustituyen las filas restantes por los alumnos elegidos.
La copia de ejemplo no conserva los alumnos que venían en el archivo original.

## Operación

Las cartas se generan exclusivamente desde Alumnos registrados mediante el flujo
de lotes descrito abajo. Permite ambas clases de cartas o solo una.

El nombre y firma institucional del texto fijo se conservaron; revisarlos antes de
usar los ejemplos. La validación ocurre al generar, no al subir desde Ajustes.

Los reportes de tutorías conservan su generador, plantilla y formato actuales.
La normalización del oficio ahora se importa desde `Tutorias.services.oficios`.

## Lotes desde Alumnos registrados

En Alumnos registrados se puede filtrar por licenciatura (opcional), trimestre de
 ingreso y estado. «Seleccionar todos los resultados» incluye todas las páginas
de la búsqueda de la tabla. Es posible desmarcar alumnos individualmente. Aplicar
nuevos filtros de licenciatura, trimestre o estado reinicia la selección.

«Generar cartas de asignación» abre el resumen de los alumnos, agrupados por
licenciatura y tutor. Se eligen ambas clases de cartas (opción inicial), solamente
alumnos o solamente tutores. Cada clase utiliza su propia plantilla y número de
oficio inicial; los intervalos no pueden superponerse dentro del lote.

Se genera una carta por alumno y una por cada pareja licenciatura/tutor, incluyendo
únicamente a los alumnos seleccionados. La licenciatura del texto de la carta del
tutor corresponde a esos alumnos, incluso si el profesor pertenece a otra
coordinación. Los números continúan entre licenciaturas, sin reiniciarse.

Una licenciatura produce un ZIP con carpetas para alumnos y tutores. Varias
licenciaturas producen un ZIP contenedor con un ZIP por licenciatura. No se envían
correos ni se registran números de oficio globalmente. La descarga usa las
asignaciones actuales al momento de generar.

## Ajustes: clasificación y plantilla predeterminada

Cada Documento tiene un tipo: alumno, tutor o reporte. Se permiten múltiples
alternativas por tipo y una sola predeterminada (restricción en base de datos).
El tipo es obligatorio al registrar una plantilla desde Ajustes. No se infiere
por el nombre. La migración 0009 conservó los registros anteriores sin clasificar;
la sección temporal de clasificación ya fue retirada de la interfaz.

Los formularios filtran por tipo y preseleccionan la predeterminada. Elegir una
alternativa en un lote no modifica la predeterminada. Los reportes masivos ya no
exigen un nombre exacto: el selector permite cualquiera del tipo reporte.

Se valida el contenido al cargar, sustituir, clasificar y activar una plantilla.
Para eliminar o reclasificar la predeterminada primero se debe activar otra del
mismo tipo. Los ejemplos se descargan desde su renglón en Ajustes y pueden predeterminarse.

El ejemplo `reporte_tutorias_plantilla.docx` requiere una tabla y los marcadores
`{no_oficio}`, `{fecha}`, `{nombre_mayus_tutor}`, `{nombre_tutor}`; admite además
`{estimado}`. Se eliminaron sus filas de ejemplo, conservando los encabezados.
La previsualización y generación de documentos de prueba quedan para otra fase.


## Ejemplos protegidos e interfaz de selección

La migración 0010 agrega `clave_sistema` y la 0011 registra los tres ejemplos.
Solo se predetermina un ejemplo si todavía no existe una activa de su tipo.
Los archivos de los ejemplos permanecen en este directorio, separado de MEDIA_ROOT.
`Documento.archivo_fuente` proporciona una fuente uniforme para ejemplos y archivos
subidos. Los ejemplos no admiten edición o eliminación desde vistas, formularios,
modelo, operaciones habituales de QuerySet ni administración de Django. Cambiar
su condición de predeterminada sí está permitido. SQL directo y mantenimiento de
migraciones corresponden a administradores del sistema.

En Ajustes, seleccionar una fila con el mouse o su radio con el teclado habilita
las acciones laterales. Nueva preselecciona el tipo de la fila. Para personalizar
un ejemplo, descargarlo y registrar la copia editada como una nueva plantilla.

## Vista previa de edición

Editar muestra el PDF del Word guardado, convertido localmente con LibreOffice
Writer en modo headless. Se requiere reconstruir la imagen web cuando cambie el
Dockerfile: `docker compose build web` y `docker compose up -d --no-deps web`.
La imagen incluye fuentes Liberation y DejaVu. Fuentes diferentes pueden producir
variaciones de diseño respecto a Word.

El PDF se sirve solo a CODDAA, sin publicarlo en media ni enviarlo a Google. La
conversión usa un perfil y directorio temporal exclusivos y un límite de 45 segundos.
Los temporales se eliminan al terminar. La caché de Django conserva durante 15 minutos
el PDF por hash del contenido, por lo que sustituir el Word invalida la vista previa.
La caché se pierde normalmente al reiniciar si se usa el backend de memoria.

La selección de un archivo nuevo no modifica la vista previa hasta guardarlo. Si
la validación falla, el archivo anterior se conserva. La interfaz informa si el
conversor no está disponible o falla y mantiene la descarga del Word como alternativa.
