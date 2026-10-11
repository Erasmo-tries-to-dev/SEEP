# Documentación de Pruebas Automatizadas (Suite SEEP)

> ⚠️ **Alcance y Limitaciones Actuales (Disclaimer)**
> La intención principal de esta suite de pruebas fue validar empíricamente que los bugs críticos (B1 a B9) detectados en la auditoría inicial hayan sido parcheados con éxito. Si bien los tests se refactorizaron posteriormente para generalizarlos hacia una cobertura por dominios, **aún se requieren pruebas manuales exhaustivas**, preferentemente ejecutadas en las computadoras del entorno real de los laboratorios. Asimismo, se reconoce la necesidad de continuar expandiendo esta suite en futuras versiones para terminar de mitigar el _bus factor_ (o más bien, el _tabaco factor_) del proyecto a largo plazo.

---

Este documento detalla la arquitectura de pruebas implementada para garantizar la calidad, resiliencia y correctitud del Sistema de Entrega de Exámenes de Programación (SEEP).

## 🏛️ Estrategia Arquitectónica

La suite de pruebas fue diseñada abandonando un enfoque reactivo (testear bugs aislados) para adoptar un estándar proactivo basado en **Ingeniería de Software de Calidad**:

- **Particiones Equivalentes:** Para validar de forma exhaustiva matrices cruzadas de datos (ej. extensiones vs. módulos) sin escribir cientos de tests manuales.
- **Valores Límite (Boundary Values):** Para someter al servidor a condiciones extremas matemáticas (ej. archivos vacíos de 0 bytes o que superen el límite máximo permitido).
- **Caminos Tristes (Sad Paths):** Para garantizar que el sistema falle con gracia y comunique el error correctamente cuando el usuario omite campos, envía credenciales falsas o cuando ocurren errores de hardware.

## 🐛 Trazabilidad de Errores (Auditoría)

| \#  | Ubicación Original    | Problema Detectado                                         | Estado Actual   | Test que verifica su corrección |
| --- | --------------------- | ---------------------------------------------------------- | --------------- | ------------------------------- |
| B1  | `servidor_docente.py` | Sobrescritura de entregas en el mismo segundo              | ✅ **Resuelto** | `test_persistencia.py`          |
| B2  | `servidor_docente.py` | CSV bloqueado por Excel crashea el servidor                | ✅ **Resuelto** | `test_persistencia.py`          |
| B3  | `cliente_alumno.py`   | Error de red inesperado causa `NameError`                  | ✅ **Resuelto** | `test_cliente.py`               |
| B4  | `cliente_alumno.py`   | HTTP 500 HTML rompe el parseo JSON del cliente             | ✅ **Resuelto** | `test_cliente.py`               |
| B5  | `servidor_docente.py` | Inconsistencia en validación de extensiones (Mayús/Minús)  | ✅ **Resuelto** | `test_validaciones.py`          |
| B6  | `servidor_docente.py` | Excepciones del sistema operativo retornan HTML crudo      | ✅ **Resuelto** | `test_api_upload.py`            |
| B7  | `servidor_docente.py` | Desfasaje de tiempo por llamadas dobles a `datetime.now()` | ✅ **Resuelto** | `test_persistencia.py`          |
| B8  | `cliente_alumno.py`   | Texto invisible en modo claro de Windows                   | 🟡 Pendiente    | _(Prueba manual / UI)_          |
| B9  | `cliente_alumno.py`   | Violación de Thread-Safety en Tkinter                      | 🟡 Pendiente    | _(Prueba manual / UI)_          |

## 📂 Estructura de Dominios y Cobertura

### 1. Dominio Compartido (Reglas de Negocio Centrales)

#### `tests/compartido/test_validaciones.py`

- **Técnica Aplicada:** Particiones Equivalentes Parametrizadas.
- **Qué evalúa:** La matriz cruzada entre los módulos activos (`imperativo`, `objetos`, `concurrente`) y las extensiones de archivo provistas por el alumno (`.pas`, `.zip`, sin extensión).
- **Regresiones que detecta:**
  - **B5 (Inconsistencia de capitalización):** Garantiza que el servidor procese correctamente archivos como `EXAMEN.PAS` y los acepte con un código HTTP 200. Evita que envíos con extensiones cruzadas o archivos peligrosos (`.exe`, `.pdf`) sean aceptados (HTTP 400).

### 2. Dominio del Servidor (API y Persistencia)

#### `tests/servidor/test_api_ping.py`

- **Técnica Aplicada:** Particiones Equivalentes.
- **Qué evalúa:** Verifica que el endpoint `GET /ping` actúe como un _handshake_ inicial robusto. Asegura que las versiones obsoletas, futuras o nulas sean rechazadas con un HTTP 426 (Upgrade Required).
- **Regresiones que detecta:** Protege la integridad del examen asegurando que ningún alumno pueda rendir utilizando una versión del cliente con reglas de negocio desactualizadas o adulteradas.

#### `tests/servidor/test_api_upload.py`

- **Técnicas Aplicadas:** Caminos Tristes (Sad Paths) y Valores Límite.
- **Qué evalúa:** La robustez del endpoint principal `/upload` frente a peticiones malformadas, maliciosas o fallos del sistema operativo.
  - **Camino Triste (Incompletitud):** Verifica mediante parametrización que la omisión de _cualquier_ campo obligatorio resulte en HTTP 400.
  - **Camino Triste (Seguridad):** Garantiza el rechazo explícito con HTTP 403 (Forbidden) ante un PIN inválido.
  - **Valores Límite (Archivos):** Verifica el comportamiento en los límites matemáticos (0 bytes, 1 KB, 5 MB + 1 KB forzando HTTP 413 Payload Too Large).
  - **Excepciones Críticas (B6):** Simula un fallo grave del hardware utilizando `unittest.mock.patch` sobre el método `save()`.
- **Regresiones que detecta:**
  - **B6 (Cuelgue por HTML crudo):** Asegura que, sin importar la gravedad del error interno, el servidor atrape la excepción y devuelva siempre un JSON estructurado con un HTTP 500.

#### `tests/servidor/test_persistencia.py`

- **Técnicas Aplicadas:** Pruebas End-to-End (Camino Feliz) y Stress Testing (Concurrencia).
- **Qué evalúa:** Los efectos secundarios a nivel de sistema de archivos y auditoría.
  - **Camino Feliz Unificado:** Garantiza de forma simultánea que una entrega exitosa genere tres eventos inseparables: guardado del archivo físico, registro atómico en el archivo CSV (manejando correctamente delimitadores `;`) y traza de auditoría en el logger local.
  - **Concurrencia (Multi-threading):** Utiliza hilos (`threading.Thread`) para bombardear el servidor con múltiples entregas simultáneas y validar la generación de nombres únicos para evitar colisiones.
- **Regresiones que detecta:**
  - **B1 (Sobrescritura por concurrencia):** Garantiza que múltiples entregas en el mismo milisegundo generen archivos independientes en el disco, evitando la pérdida del trabajo previo.
  - **B2 (Bloqueo de CSV por Excel):** Evita la pérdida de exámenes si el docente mantiene el archivo de auditoría abierto. Fuerza un `PermissionError` de Windows sobre el CSV y verifica que el servidor lo atrape silenciosamente, devolviendo HTTP 200 y asegurando el archivo en disco.
  - **B7 (Desfasaje de tiempo):** Al centralizar el guardado en un único flujo, asegura la consistencia temporal entre el CSV y el FileSystem.

### 3. Dominio Cliente (`tests/cliente/`)

_Comportamiento de la Interfaz Gráfica, resiliencia de red y experiencia del usuario._

#### `tests/cliente/test_cliente.py`

- **Técnicas Aplicadas:** Mocks (`unittest.mock.patch`), Aserciones de Estado de UI (Tkinter) y Ejecución en Subprocesos (`subprocess`).
- **Qué evalúa:** La capacidad de la interfaz gráfica para sobrevivir a escenarios catastróficos, comunicando los errores de manera efectiva al alumno, así como la persistencia local de logs.
  - **Resiliencia de Red:** Simula una caída abrupta de conexión y verifica que el cliente atrape la excepción, actualizando el texto en pantalla (`lbl_estado`) en lugar de colapsar.
  - **Tolerancia a Respuestas Malformadas:** Simula un fallo grave del servidor (código 500 devolviendo HTML en lugar de JSON) y garantiza que el error de parseo es manejado limpiamente.
  - **Auditoría Física Local:** Ejecuta la aplicación de forma aislada para corroborar la creación del archivo `seep_cliente.log` en el equipo del estudiante con los registros de la actividad.
- **Regresiones que detecta:**
  - **B3 (Crash silencioso por NameError):** Garantiza que el manejo de excepciones asincrónico es seguro y notifica visualmente fallas de red.
  - **B4 (Cuelgue por JSON inválido):** Asegura que si el servidor falla y responde con una plantilla genérica, el cliente intercepta la situación y avisa al alumno que el servidor está caído.
