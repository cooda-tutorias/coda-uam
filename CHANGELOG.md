# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/)
y el proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added
- PR Template con checklists estructurados para pull requests
- Unit Tests para FormSeguimiento
- Unit Tests para CartaTutoradosPdf
- Test Settings Configuration con soporte para SQLite testing
- Script `coda-src/scripts/generar_tutorias_prueba.py` para generar tutorías de prueba en base de datos.
- Visualización de la descripción de la tutoría en la lista de tutorías del tutor

### Fixed
- Compatibilidad de ArrayField con SQLite mediante monkeypatch
- Dependencias corregidas (python-docx, pandas, whitenoise, coverage)
- Renombrado de "Seguimiento" a "Reporte" en el módulo de tutorías para mejorar claridad en la interfaz
- Corrección de campo de texto de oficio en generación de reporte anual (placeholder y subtítulo)
- Paginación de tablas en cartas de reporte de tutorados para limitar filas por página y mantener bordes visibles.
- Ajuste dinámico de filas por página según la cantidad de columnas seleccionadas en la carta: 
    - 2 columnas: 15 filas por página - 3 o más columnas: 10 filas por página
- Filtrado de reportes de tutorías para incluir únicamente alumnos con estado activo (`estado = 1`).


### Changed 
- Refactor de la generación de cartas a `Tutorias/services/docx_reportes.py` para separar la lógica de documentos de `views.py`. 
- Ocultamiento de observaciones de tutoría para usuarios CODDAA en vistas de tutorías
- Ocultamiento de observaciones de tutoría para usuarios coordinador en vistas de tutores > "tutor/a" 

### Initial Release
- Estructura inicial del proyecto Django
- Apps: Tutorias, Usuarios, Metricas

