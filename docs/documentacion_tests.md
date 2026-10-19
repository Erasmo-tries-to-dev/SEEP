# Documentación de Pruebas Automatizadas y Arquitectura (Suite SEEP v0.7.0)

> ⚠️ **Alcance y Limitaciones Actuales (Disclaimer)**
> La intención principal de esta suite de pruebas fue validar que algunos de los bugs críticos (B1 a B9) detectados en la auditoría inicial hayan sido parcheados con éxito y facilitar tareas de refactoring. Si bien posteriormente se busco generalizarlos hacia una cobertura por dominios, aún se requieren pruebas manuales exhaustivas, preferentemente ejecutadas en las computadoras del entorno real de los laboratorios. Se reconoce la necesidad de continuar expandiendo esta suite en futuras versiones para terminar de mitigar el _bus factor_ del proyecto a largo plazo.

---

Este documento detalla las pruebas implementadas para garantizar la calidad, resiliencia y correctitud del Sistema de Entrega de Exámenes de Programación (SEEP), actualizada tras la refactorización profunda a la versión 0.7.0.

## 🐛 Trazabilidad de Errores (Auditoría Histórica)

La siguiente tabla refleja el estado de los fallos críticos de arquitectura originalmente detectados y cómo la versión 0.7.0 busco mitigarlos.

| \#     | Problema Original Detectado                                | Mitigación Arquitectónica (v0.7.0)                                                                                                                    | Módulo de Prueba Actual  |
| :----- | :--------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------- |
| **B1** | Sobrescritura de entregas en el mismo segundo              | ✅ **Resuelto.** Base de datos transaccional (SQLite) y adición de sufijos UUID/Microsegundos en disco. Controlado por `cerrojo_entregas`.            | `test_servidor.py`       |
| **B2** | CSV bloqueado por Excel crashea el servidor                | ✅ **Resuelto.** El CSV ya no es la fuente de verdad. Se utiliza un patrón Repositorio (SQLite). El CSV es ahora una exportación manual bajo demanda. | `test_servidor.py`       |
| **B3** | Error de red inesperado causa `NameError`                  | ✅ **Resuelto.** El módulo `cliente_red.py` intercepta genéricamente excepciones `requests.exceptions` y devuelve DTOs seguros.                       | `test_cliente_red.py`    |
| **B4** | HTTP 500 HTML rompe el parseo JSON del cliente             | ✅ **Resuelto.** `_obtener_texto_error()` incluye bloque `try/except ValueError` como mecanismo de _fallback_.                                        | `test_cliente_red.py`    |
| **B5** | Inconsistencia en validación de extensiones (Mayús/Minús)  | ✅ **Resuelto.** Validación estandarizada en minúsculas delegada a `seep_config.py`.                                                                  | _Unit Testing implícito_ |
| **B6** | Excepciones del sistema operativo retornan HTML crudo      | ✅ **Resuelto.** El servidor envuelve la capa IO (`_guardar_archivo_atomico`) y devuelve JSON `HTTP 500`.                                             | `test_servidor.py`       |
| **B7** | Desfasaje de tiempo por llamadas dobles a `datetime.now()` | ✅ **Resuelto.** Marca de tiempo calculada una única vez durante la fase de validación y propagada.                                                   | `test_servidor.py`       |
| **B8** | Texto invisible en modo claro de Windows                   | ✅ **Resuelto.** Uso estricto de forzado de tuplas de color en componentes CustomTkinter (`COLOR_TEXTO_HABILITADO`).                                  | _Diseño de UI_           |
| **B9** | Violación de Thread-Safety en Tkinter                      | ✅ **Resuelto.** Implementación del patrón `queue.Queue` y ciclo de sondeo `procesar_cola()` en el hilo principal.                                    | _Diseño de Arquitectura_ |

## 📂 Estructura de Dominios y Cobertura

### 1. Dominio Cliente (Aislamiento de Red)

**Archivo:** `tests/test_cliente_red.py`
Evalúa la correcta transformación de la capa de transporte HTTP a los Objetos de Transferencia de Datos (DTOs) que consume la interfaz gráfica.

- **Conectividad Temprana (Ping):** Asegura que los tiempos de espera agotados (Timeouts) y las incompatibilidades de versión (HTTP 426) se informen explícitamente sin colgar la UI.
- **Resiliencia a Fallas (Sad Paths):** Comprueba que si el servidor devuelve respuestas no tipificadas, errores internos (HTTP 500) o denegaciones de política (HTTP 403), el cliente extraiga el texto de error sin romper el contrato del DTO `ResultadoEntrega`.

### 2. Dominio Servidor (API, Seguridad y Persistencia)

**Archivo:** `tests/test_servidor.py`
Instancia la Application Factory de Flask junto a una base de datos SQLite efímera para testear end-to-end el flujo de entregas.

- **Filtros de Seguridad:** Verifica que la API impida accesos no autorizados mediante inyección de PINs inválidos (HTTP 403) o clientes desactualizados (HTTP 426).
- **Motor de Reglas de Negocio (Idempotencia y Reentregas):**
  - Comprueba que un alumno enviando su archivo por primera vez reciba su comprobante y su registro se asiente.
  - Valida la política restrictiva: Si el alumno intenta enviar de nuevo, el sistema debe bloquearlo con HTTP 403.
  - Asegura el estado mutacional: Si el docente habilita la reentrega por base de datos, el alumno puede sobreescribir su examen. El sistema debe consumir el permiso (volviendo a 0) y desactivar los exámenes previos (`es_activa = 0`), manteniendo intacta la pista de auditoría.
