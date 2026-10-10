# Changelog - SEEP (Versión LAN)

Todas las mejoras notables de este proyecto se documentarán en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

## [v0.2.0] - 2026-10-10

### ⚙️ Infraestructura y Mantenimiento
- **(Punto 15) Build Reproducible y Binarios en Git:** Se eliminó el seguimiento de la carpeta `dist/` y de los archivos `.exe` del repositorio mediante ajustes en el `.gitignore`. Se versionan correctamente `pyproject.toml`, `poetry.lock` y `*.spec`.
- **(Punto 15) Integración Continua (CI/CD):** Se implementó un flujo de GitHub Actions (`release.yml`) que compila automáticamente los ejecutables en un entorno limpio y genera sus respectivos hashes SHA-256 al crear un nuevo Tag, publicándolos como una Release oficial.
