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
- Visualización de la descripción de la tutoría en la lista de tutorías del tutor

### Fixed
- Compatibilidad de ArrayField con SQLite mediante monkeypatch
- Dependencias corregidas (python-docx, pandas, whitenoise, coverage)

### Initial Release
- Estructura inicial del proyecto Django
- Apps: Tutorias, Usuarios, Metricas