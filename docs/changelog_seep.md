# Changelog - SEEP (Versión LAN)

Todas las mejoras notables de este proyecto se documentarán en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

## [v0.2.0] - 2026-10-10

### ⚙️ Infraestructura y Mantenimiento

- **(Punto 15) Build Reproducible y Binarios en Git:** Se eliminó el seguimiento de la carpeta `dist/` y de los archivos `.exe` del repositorio mediante ajustes en el `.gitignore`. Se versionan correctamente `pyproject.toml`, `poetry.lock` y `*.spec`.
- **(Punto 15) Integración Continua (CI/CD):** Se implementó un flujo de GitHub Actions (`release.yml`) que compila automáticamente los ejecutables en un entorno limpio y genera sus respectivos hashes SHA-256 al crear un nuevo Tag, publicándolos como una Release oficial.

### 🔧 Mantenibilidad y Portabilidad

- **Versionado de Protocolo:** Se agregó un control de versión (`VERSION_SEEP`). El servidor ahora responde con error HTTP 426 si un cliente desactualizado intenta conectarse.
- **Rutas Absolutas seguras:** El servidor ahora genera los registros CSV y las carpetas de exámenes de forma relativa a la ruta física del ejecutable (`sys.executable`), evitando la pérdida de archivos si el docente lanza el programa desde un acceso directo.
- **Escalado de Interfaz:** Se redujo la altura predeterminada del cliente y se habilitó el redimensionado vertical para garantizar la accesibilidad en monitores de laboratorio con baja resolución o alto porcentaje de escalado de Windows.

### 🧪 Pruebas Automatizadas (Testing)

- **(Punto 16) Suite de Pruebas del Servidor:** Se integró la librería `pytest` y se configuró un entorno de pruebas (`conftest.py`) utilizando el cliente de pruebas nativo de Flask con un directorio temporal, aislando las pruebas del sistema de archivos real.
- **(B1) Test de Estrés de Concurrencia:** Se implementó el archivo `test_concurrencia.py` para simular entregas simultáneas mediante múltiples hilos, garantizando mecánicamente que el Bug B1 está resuelto y protegiendo el código contra futuras regresiones.
- **(B2) Test de Tolerancia a Fallos CSV:** Se implementó `test_csv.py` para simular el bloqueo del archivo de registro a nivel de sistema operativo, garantizando que una entrega no se pierda si el docente tiene el archivo abierto.
- **(B3, B4) Pruebas de Interfaz Gráfica (Cliente):** Se implementó la suite `test_cliente.py` utilizando `unittest.mock` para simular fallos de red y errores HTTP 500. Se realizan aserciones visuales sobre los componentes de Tkinter para garantizar que la interfaz notifique al alumno correctamente sin colgarse.
- **(B5) Validación de Extensiones:** Se añadió `tests/test_extensiones.py` para garantizar mediante peticiones simuladas que el servidor acepte extensiones válidas independientemente de su capitalización (ej. `.PAS` vs `.pas`).
- **(B6) Test de Excepciones del Servidor:** Se agregó `tests/test_excepciones.py`, utilizando `unittest.mock.patch` para simular un fallo crítico del sistema operativo (como un disco lleno mediante `OSError`), garantizando que la API siempre responda con un JSON estructurado en lugar de colapsar devolviendo un HTML.

### 🐛 Errores Solucionados (Fixed)

- **(B1, R8b) Sobrescritura de entregas simultáneas:** Se agregaron microsegundos (`%f`) al timestamp de los nombres de archivo. Dos entregas que llegan en el mismo segundo exacto ya no colisionan en disco.
- **(B7) Desfasaje de tiempo:** Se unificó la llamada a `datetime.now()` para que la hora registrada en el CSV y la del nombre del archivo sean idénticas.
- **(B2) Bloqueo de Excel (PermissionError):** Se implementó un bloque `try-except PermissionError` en la escritura del CSV. Si el docente tiene el Excel abierto, el archivo del alumno se guarda igual en disco y se emite una advertencia por consola, evitando el error 500 y la pérdida de la entrega.
- **(B3) Error silencioso en interfaz gráfica:** Se resolvió un `NameError` asincrónico capturando el texto de la excepción e inyectándolo directamente en el _scope_ de las funciones `lambda` de Tkinter.
- **(B4) Caída por error HTTP 500:** Se implementó un bloque `try-except ValueError` al decodificar las respuestas del servidor. Si el servidor falla y devuelve un HTML de error genérico en lugar de un JSON, el cliente ahora lo maneja de forma segura y notifica al alumno.
- **(B5) Inconsistencia en extensiones (Mayúsculas/Minúsculas):** Se corrigió la validación en el servidor aplicando `.lower()` al nombre del archivo antes de evaluarlo. Esto alinea el comportamiento del servidor con el del cliente y permite a los alumnos entregar archivos guardados como `EXAMEN.PAS` o `tp.ZIP` sin ser rechazados.
- **(B6) Manejo de errores internos del servidor:** Se envolvió la lógica crítica de la ruta `/upload` en un bloque `try-except Exception`. Cualquier error interno del servidor (disco lleno, permisos, etc.) ahora es capturado y reportado al cliente mediante un JSON limpio con un código HTTP 500, en lugar de retornar la plantilla HTML de error por defecto de Flask.
- **(B8) Texto invisible en modo claro:** Se eliminó el parámetro rígido `text_color="white"` del label de archivo seleccionado, permitiendo que CustomTkinter aplique el color contrastante correcto según el tema del sistema operativo.
- **(B9) Actualización insegura de GUI entre hilos:** Se rediseñó la comunicación entre el hilo de red y la interfaz gráfica implementando `queue.Queue`. Ahora el hilo secundario encola las tareas y el hilo principal las dibuja, previniendo posibles crashes (`TclError`) por violaciones de Thread-Safety en Tkinter.

### ♻️ Refactorización (Refactor)

- **Estado Global y Application Factory:** Se eliminó el estado global (`PIN_ACTUAL` y configuración de módulo en `__main__`) en `servidor_docente.py`. Se implementó el patrón _Application Factory_ (`crear_app()`) de Flask, encapsulando la configuración y permitiendo importar y testear el servidor de forma aislada y profesional sin efectos secundarios. Se actualizaron todos los tests y el fixture `cliente_pruebas` para soportar esta nueva arquitectura.
- **Módulo Compartido (Single Source of Truth):** Se creó el archivo `seep_config.py` para centralizar la configuración compartida entre el cliente y el servidor aplicando el principio DRY (Don't Repeat Yourself).
  - Se unificó la lógica de `validar_extension()`, resolviendo divergencias futuras.
  - Se extrajeron las constantes de red (`PUERTO_API`, `TIMEOUT_PING`, `TIMEOUT_UPLOAD`).
  - Se centralizó el límite de tamaño de archivo (`MAX_TAMANO_MB`), y ahora el servidor también lo hace cumplir estrictamente utilizando `app.config["MAX_CONTENT_LENGTH"]`, previniendo ataques de saturación de disco.
- **Interfaz Gráfica Dinámica (DRY):** Se refactorizó la creación del formulario en `cliente_alumno.py`. Se reemplazaron más de 30 líneas de código repetitivo de `CustomTkinter` por una estructura de datos (lista de diccionarios) y un bucle `for` que genera los campos dinámicamente. Esto facilita el mantenimiento y la escalabilidad de la UI si en el futuro se requieren nuevos campos.

### ✨ Añadido

- **Auditoría y Logging:** Se reemplazaron los prints efímeros por la librería estándar `logging`. El servidor ahora registra intentos fallidos y errores graves con niveles apropiados (INFO, WARNING, ERROR). El cliente genera un archivo persistente (`seep_cliente.log`) en la PC del alumno para facilitar el diagnóstico post-examen en caso de fallos de red o de sistema. Se agregaron tests automatizados para validar este comportamiento.
