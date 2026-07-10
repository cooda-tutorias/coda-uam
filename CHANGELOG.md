# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/)
y el proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added
- Se agregó la vista de generación masiva de reportes de tutorías.
- Se agregó la selección de tutores específicos para limitar la generación de reportes.
- Se implementó la descarga de reportes en formato ZIP.
- Los documentos generados se organizan por licenciatura dentro del archivo comprimido.
- Generación masiva de reportes de tutorías para múltiples tutores.
- Descarga de reportes agrupados en un archivo ZIP.
- Organización de reportes por licenciatura dentro del ZIP generado.
- Selección de tutores específicos por licenciatura desde la interfaz de generación masiva.
- Opción para generar reportes de todos los tutores de una licenciatura o únicamente de tutores seleccionados.
- Agrupación visual de tutores por licenciatura para facilitar la selección.
- Script `coda-src/scripts/medir_reportes_tutorias_masivos.py` para medir tiempos de generación y tamaños de archivos en reportes masivos.
- Script `coda-src/scripts/diagnosticar_peso_docx.py` para analizar el peso de plantillas y documentos DOCX generados.
- Se incorporó un indicador visual con spinner, contador de tiempo y barra animada durante la generación de reportes masivos.
- Se agregó descarga controlada mediante `fetch` y `Blob` para detectar cuándo el ZIP terminó de recibirse desde el servidor.

### Testing
- Se habilitó la Fase 0 de pruebas piloto para validar generación de reportes con subconjuntos de tutores.
- Se realizaron mediciones de tiempo de generación y tamaño de archivos para reportes masivos.
- Se verificó la organización de documentos por licenciatura dentro del ZIP generado.
- Se verificó la generación masiva seleccionando las cuatro licenciaturas.
- Se comprobó que el indicador de procesamiento se retire después de recibir el ZIP.
- Se validó que una descarga completada no muestre posteriormente un aviso incorrecto de tardanza.

### Fixed
- Corrección en la estructura de carpetas del ZIP para clasificar reportes por licenciatura.
- Rediseño del formulario de generación masiva para mejorar la experiencia de usuario.
- Filtrado visual de tutores por coordinación/licenciatura.
- Se corrigió la validación que impedía seleccionar las cuatro licenciaturas en la generación masiva.
- Se corrigió el aviso de tardanza que permanecía visible después de completarse correctamente la generación y descarga del ZIP.
- Se evitó el envío duplicado del formulario mientras una generación masiva se encuentra en proceso.
- Se agregó manejo visual de errores cuando el servidor no devuelve un archivo ZIP válido.


### Changed 
- Refactor de la generación de cartas a `Tutorias/services/docx_reportes.py` para separar la lógica de documentos de `views.py`. 
- Ocultamiento de observaciones de tutoría para usuarios CODDAA en vistas de tutorías
- Ocultamiento de observaciones de tutoría para usuarios coordinador en vistas de tutores > "tutor/a" 
- La generación masiva utiliza automáticamente la plantilla denominada `Reporte tutorías atendidas (carta anual)`.
- Se eliminó el selector editable de plantilla en el formulario de generación masiva para evitar seleccionar documentos incompatibles.
- La interfaz ahora informa que la plantilla debe administrarse desde Ajustes y conservar su nombre exacto.
- El flujo de descarga tradicional del formulario fue sustituido por una solicitud asíncrona que conserva al usuario en la misma página.

### Initial Release
- Estructura inicial del proyecto Django
- Apps: Tutorias, Usuarios, Metricas

