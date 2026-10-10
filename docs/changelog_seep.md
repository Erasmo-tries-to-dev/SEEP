# Changelog - SEEP (Versión LAN)

Todas las mejoras notables de este proyecto se documentarán en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

## [v0.2.0] - 2026-10-10

### ⚙️ Infraestructura y Mantenimiento

- **(Punto 15) Build Reproducible y Binarios en Git:** Se eliminó el seguimiento de la carpeta `dist/` y de los archivos `.exe` del repositorio mediante ajustes en el `.gitignore`. Se versionan correctamente `pyproject.toml`, `poetry.lock` y `*.spec`.
- **(Punto 15) Integración Continua (CI/CD):** Se implementó un flujo de GitHub Actions (`release.yml`) que compila automáticamente los ejecutables en un entorno limpio y genera sus respectivos hashes SHA-256 al crear un nuevo Tag, publicándolos como una Release oficial.

### 🧪 Pruebas Automatizadas (Testing)

- **(Punto 16) Suite de Pruebas del Servidor:** Se integró la librería `pytest` y se configuró un entorno de pruebas (`conftest.py`) utilizando el cliente de pruebas nativo de Flask con un directorio temporal, aislando las pruebas del sistema de archivos real.
- **(B1) Test de Estrés de Concurrencia:** Se implementó el archivo `test_concurrencia.py` para simular entregas simultáneas mediante múltiples hilos, garantizando mecánicamente que el Bug B1 está resuelto y protegiendo el código contra futuras regresiones.
- **(B2) Test de Tolerancia a Fallos CSV:** Se implementó `test_csv.py` para simular el bloqueo del archivo de registro a nivel de sistema operativo, garantizando que una entrega no se pierda si el docente tiene el archivo abierto.
- **(B3, B4) Pruebas de Interfaz Gráfica (Cliente):** Se implementó la suite `test_cliente.py` utilizando `unittest.mock` para simular fallos de red y errores HTTP 500. Se realizan aserciones visuales sobre los componentes de Tkinter para garantizar que la interfaz notifique al alumno correctamente sin colgarse.

### 🐛 Errores Solucionados (Fixed)

- **(B1, R8b) Sobrescritura de entregas simultáneas:** Se agregaron microsegundos (`%f`) al timestamp de los nombres de archivo. Dos entregas que llegan en el mismo segundo exacto ya no colisionan en disco.
- **(B7) Desfasaje de tiempo:** Se unificó la llamada a `datetime.now()` para que la hora registrada en el CSV y la del nombre del archivo sean idénticas.
- **(B2) Bloqueo de Excel (PermissionError):** Se implementó un bloque `try-except PermissionError` en la escritura del CSV. Si el docente tiene el Excel abierto, el archivo del alumno se guarda igual en disco y se emite una advertencia por consola, evitando el error 500 y la pérdida de la entrega.
- **(B3) Error silencioso en interfaz gráfica:** Se resolvió un `NameError` asincrónico capturando el texto de la excepción e inyectándolo directamente en el _scope_ de las funciones `lambda` de Tkinter.
- **(B4) Caída por error HTTP 500:** Se implementó un bloque `try-except ValueError` al decodificar las respuestas del servidor. Si el servidor falla y devuelve un HTML de error genérico en lugar de un JSON, el cliente ahora lo maneja de forma segura y notifica al alumno.
