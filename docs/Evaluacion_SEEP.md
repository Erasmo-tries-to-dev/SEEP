# Evaluación técnica de SEEP

> **Objeto evaluado:** repositorio `SEEP` (commit `502ab20`): `cliente_alumno.py` (316 líneas), `servidor_docente.py` (259 líneas) y los ejecutables de `dist/`.
> **Referencia:** requisitos y reglas definidos en [`Metodologia.md`](Metodologia.md).
> **Fecha:** 2026-10-04

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Cómo se evaluó](#2-cómo-se-evaluó)
3. [Cumplimiento de requisitos](#3-cumplimiento-de-requisitos)
4. [Diferencias con la metodología](#4-diferencias-con-la-metodología)
5. [Análisis crítico](#5-análisis-crítico)
   - [5.1 Calidad del código](#51-calidad-del-código)
   - [5.2 Mantenibilidad y portabilidad](#52-mantenibilidad-y-portabilidad)
   - [5.3 Seguridad](#53-seguridad)
6. [Recomendaciones priorizadas](#6-recomendaciones-priorizadas)

---

## 1. Resumen ejecutivo

SEEP es un **prototipo bien encaminado**. La arquitectura es adecuada para el problema: un cliente liviano en cada PC y un receptor HTTP en la PC del docente, todo en red local y sin internet. El código es chico, claro y está comentado. Además, el autor anticipó varios problemas reales: el aislamiento de red, la integridad con hash, la concurrencia al escribir el CSV y la compatibilidad del CSV con Excel.

Sin embargo, **todavía no está listo para usarse en un examen real**. Le falta cumplir con buena parte de lo que pide la metodología:

| | Cantidad |
|---|---|
| ✅ Cumple | 4 requisitos |
| ⚠️ Cumple parcialmente | 8 requisitos |
| ❌ No cumple | 3 requisitos |

**Problemas más importantes:**

1. ❌ **No hay control de reentregas ni panel para el docente.** El servidor acepta entregas ilimitadas de cualquier alumno, y el docente solo ve líneas impresas en la consola.
2. ❌ **Suplantación trivial.** Cualquiera que tenga el PIN puede entregar a nombre de otro alumno. Esa entrega queda como la más reciente, que según la metodología es la que se evalúa.
3. 🐞 **Pérdida silenciosa de entregas.** Dos envíos con los mismos datos dentro del mismo segundo se **sobrescriben** en disco, mientras el CSV registra los dos (verificado).
4. 🐞 **Si el CSV está abierto en Excel, Windows bloquea el archivo y todas las entregas siguientes fallan.** El archivo del alumno se guarda, pero se le informa un error, así que el alumno reintenta y se generan duplicados.
5. 🔓 **Todo viaja por HTTP sin cifrar**, incluidos el PIN y el examen. En una red WiFi compartida, otro equipo puede capturarlos.

---

## 2. Cómo se evaluó

- **Lectura completa** del código fuente, el README y el historial de git.
- **Pruebas del servidor** con el cliente de pruebas de Flask, en Linux con Python 3.12. Se probaron los casos normales y los casos límite que figuran en la [sección 5.3](#53-seguridad).
- **Reproducción aislada** del error del cliente descrito en la [sección 5.1](#51-calidad-del-código).

**Lo que no se evaluó:**

- Ejecución en Windows ni en la red real de la facultad.
- Comportamiento del firewall de Windows.
- Carga real de 60 entregas simultáneas.
- Los `.exe` de `dist/`: no se analizaron, y no hay forma de verificar que se hayan generado a partir de este código (ver [5.2](#52-mantenibilidad-y-portabilidad)).

Los ítems marcados como *(verificado)* se reprodujeron en las pruebas. El resto surge del análisis del código.

---

## 3. Cumplimiento de requisitos

### 3.1 Requisitos (sección 5 de la metodología)

| # | Requisito | Estado | Evidencia |
|---|---|:-:|---|
| R1 | Envío directo alumno → docente | ✅ | HTTP en la red local, sin internet (`servidor_docente.py:259`). Las alternativas para una red con aislamiento (hotspot, puente en la nube) están solo descritas en el README, **no implementadas**. |
| R2 | Confidencialidad | ⚠️ | El servidor no expone ningún endpoint para descargar entregas, lo cual está bien. Pero el tráfico es **HTTP sin cifrar**: el examen y el PIN se pueden capturar en la red. |
| R3 | Identificación del alumno | ✅ | Se piden apellidos, nombres y legajo/DNI. El CSV guarda los datos **tal cual** se ingresaron, con acentos y ñ (`servidor_docente.py:213-223`) *(verificado)*. |
| R4 | Mitigar la suplantación | ❌ | El único control es el PIN, que es el mismo para todo el aula. El `hostname` lo informa el propio cliente y es falsificable (`servidor_docente.py:175`). No hay nada que ayude al docente a detectar una suplantación *(verificado)*. |
| R5 | Integridad | ⚠️ | Se calcula el SHA-256 **en el servidor** (`servidor_docente.py:208`), pero el cliente no envía su propio hash, así que **no hay verificación de punta a punta**. Además, si hay una colisión de nombre, el hash del CSV deja de corresponder con el archivo en disco *(verificado)*. |
| R6 | Detección e informe de errores | ⚠️ | El OK solo se muestra con una respuesta 200, después de guardar el archivo y escribir el CSV, lo cual está bien. Pero hay tres problemas: (a) los errores 500 llegan como HTML y el cliente falla al leerlos como JSON; (b) por un error del cliente, los errores inesperados **nunca se muestran** ([5.1](#51-calidad-del-código)); (c) si el CSV falla, el archivo ya quedó guardado pero el alumno ve un error. |
| R7 | Nombre correcto | ✅ | El servidor arma el nombre final (`Apellidos_Nombres_ID_timestamp.ext`) sin depender de cómo el alumno nombró su archivo (`servidor_docente.py:203-205`). |
| R8 | Reentrega solo con habilitación | ❌ | No existe. El servidor acepta **entregas ilimitadas** del mismo alumno *(verificado)*. El cliente solo deshabilita el botón dentro de la misma sesión: si el alumno cierra y vuelve a abrir la aplicación, puede reenviar (`cliente_alumno.py:269`). |
| R8b | Historial de entregas | ⚠️ | Las entregas anteriores se conservan porque el nombre incluye el timestamp, pero **no se marca cuál es la final**. Si dos entregas caen en el mismo segundo, una se **sobrescribe** *(verificado)*. |
| R9 | Registro del momento de entrega | ⚠️ | El CSV guarda solo la **hora** (`HH:MM:SS`), **sin fecha** (`servidor_docente.py:198`). Como el CSV es uno por módulo y se sigue agregando en cada ejecución, las entregas de distintos turnos y días quedan mezcladas y sin forma de distinguirlas. |
| R10 | Panel del docente | ❌ | Solo hay líneas impresas en la consola (`servidor_docente.py:227`). No se puede buscar a un alumno, ver si su entrega llegó bien, habilitar una reentrega ni ver quién falta. El README reconoce que la interfaz gráfica está pausada. |
| R11 | Evidencia ante reclamos | ⚠️ | El CSV con hora, IP y hash es una buena base. Pero falta la fecha, el alumno no recibe un comprobante (código o hash), el CSV es editable y se puede alterar con datos maliciosos ([5.3](#53-seguridad)). |
| R12 | Soportar el pico de entregas | ⚠️ | Waitress con 4 hilos y archivos de hasta 1 MB debería alcanzar para unas 60 entregas en 10 minutos. Pero el timeout del cliente es de 10 segundos (`cliente_alumno.py:262`): con el WiFi saturado, una entrega que llega igual puede mostrarse como error y provocar un reintento duplicado. **No se probó con carga real.** |
| R13 | Instalación coordinada, uso sin permisos de administrador | ⚠️ | Los `.exe` son portables y no requieren instalación, lo cual está bien. Pero el servidor escucha en `0.0.0.0:5000`: en Windows, el firewall bloquea esas conexiones entrantes y habilitarlas requiere permisos de administrador. Hay que coordinarlo con los responsables de los equipos. |
| R14 | Un receptor por aula | ✅ | Cada servidor tiene su propia IP y su propio PIN, así que el alumno entrega al receptor de su aula. |

### 3.2 Reglas de la entrega (sección 4 de la metodología)

| Regla | Estado | Comentario |
|---|:-:|---|
| Datos: nombre, apellido, legajo o DNI | ✅ | Un solo campo "Legajo o DNI". No queda registrado cuál de los dos se usó. |
| Datos tal cual, sin corregir | ⚠️ | El CSV los guarda sin cambios. El **nombre de archivo** reemplaza espacios por `_` y `/` por `-`, y elimina otros caracteres. Es razonable, pero no permite separar con seguridad apellidos de nombres (`De_La_Fuente_Juan_...`). |
| Entrega autónoma | ✅ | |
| Retiro controlado por el docente | ❌ | Sin un panel, el docente no tiene cómo verificar rápido la entrega de un alumno concreto. Hoy tendría que buscarlo en la consola o en el CSV. |
| Entrega en blanco con archivo | ✅ | Se acepta un archivo vacío *(verificado)*. No hay un botón específico para entregar en blanco. |
| Sin reentregas salvo habilitación | ❌ | Ver R8. |
| Registro de la hora, sin controlar el tiempo | ⚠️ | Se registra la hora, pero no la fecha (ver R9). |
| Mensaje de OK | ✅ | El cliente muestra "✅ Entrega exitosa." (`cliente_alumno.py:267`). |
| Organización en Drive por turno y aula | ❌ | Las carpetas son fijas por módulo (`entregas_imperativo/`, etc.) y se reutilizan en cada turno. No hay concepto de turno ni de aula. |
| Plan B (pendrive) | — | Está fuera del sistema. Lo único relevante es que, si el servidor se cae, las entregas ya recibidas quedan en disco. |

---

## 4. Diferencias con la metodología

Estas diferencias no son errores del código, pero **cambian el procedimiento del examen** y hay que decidir si se aceptan:

| Tema | Metodología | SEEP | Impacto |
|---|---|---|---|
| **Objetos** | Se entrega el directorio del proyecto NetBeans | Exige un **`.zip`** (`cliente_alumno.py:147`, `servidor_docente.py:137`) | Agrega un paso nuevo para el alumno: comprimir el proyecto. Además, hay que enseñárselo. Un proyecto con `.jar` o `dist/` puede superar el límite de 1 MB. |
| **Concurrente** | Archivo sin extensión fija, **podría ser `.rinfo` o `.crmi`** | Rechaza **cualquier** archivo con un punto en el nombre (`cliente_alumno.py:174`, `servidor_docente.py:143`) | Un archivo `APELLIDO_NOMBRE.rinfo` **no se puede entregar**. |
| **Imperativo** | `.pas` | El cliente acepta `.PAS` en mayúsculas, pero el servidor lo **rechaza** (`cliente_alumno.py:163` usa `.lower()`, `servidor_docente.py:132` no) *(verificado)* | El alumno ve el error "Solo se permiten archivos .pas" sobre un archivo `.PAS`, y no entiende por qué. |
| **Módulo** | Lo define el examen | El docente lo elige en el servidor y el alumno lo elige **de nuevo** en el cliente | Si no coinciden, el error recién aparece en el servidor. El cliente podría preguntarle el módulo al servidor. |
| **Turno y aula** | Organización por turno y por aula | No existen | Las entregas de distintos turnos quedan mezcladas en la misma carpeta y el mismo CSV. |

---

## 5. Análisis crítico

### 5.1 Calidad del código

#### Fortalezas

- **Simple y legible.** Son unas 575 líneas en total, con funciones cortas y nombres claros en castellano.
- **Bien documentado.** Hay docstrings en todas las funciones y comentarios que explican las decisiones, no solo lo que hace el código. Por ejemplo, por qué se eligió Waitress o de dónde sale el límite de 1 MB.
- **Buenas decisiones puntuales:**
  - Lock para escribir el CSV.
  - CSV en `utf-8-sig` con separador `;`, para que Excel lo abra bien en español.
  - Hash calculado en bloques.
  - Hilo separado en el cliente para que la interfaz no se congele.
  - Botón deshabilitado después del OK.
  - Servidor de producción (Waitress) en lugar del servidor de desarrollo de Flask.
- **El servidor no confía en el cliente.** Repite las validaciones y arma el nombre del archivo por su cuenta.

#### Errores encontrados

| # | Gravedad | Ubicación | Problema |
|---|:-:|---|---|
| B1 | 🔴 Alta | `servidor_docente.py:197-210` | **Sobrescritura de entregas.** El nombre usa un timestamp con resolución de segundos. Dos envíos con los mismos datos en el mismo segundo (doble clic, reintento rápido o suplantación) **pisan** el archivo anterior, y el CSV queda con dos filas que apuntan al mismo archivo, con hashes distintos *(verificado: 4 envíos, 1 solo archivo en disco)*. |
| B2 | 🔴 Alta | `servidor_docente.py:79` | **CSV bloqueado por Excel.** En Windows, Excel bloquea el CSV mientras está abierto. `open(..., "a")` lanza `PermissionError`, la respuesta es un error 500 y **todas** las entregas siguientes fallan, aunque el archivo se guarda antes. Es muy probable que pase: el docente abre el CSV para controlar durante el examen. |
| B3 | 🟠 Media | `cliente_alumno.py:297-304` | **El error inesperado nunca se muestra.** La `lambda` usa la variable `e` cuando el bloque `except` ya terminó, y en ese momento Python ya la eliminó, así que se produce un `NameError` *(verificado)*. El alumno se queda viendo "Conectando con la PC del docente…" con el botón "Reintentar Entrega". |
| B4 | 🟠 Media | `cliente_alumno.py:272` | Si el servidor responde con HTML (por ejemplo, un error 500), `respuesta.json()` lanza una excepción, que cae en B3. Juntos hacen que **cualquier error del servidor sea invisible** para el alumno. |
| B5 | 🟠 Media | `servidor_docente.py:132` vs `cliente_alumno.py:163` | El cliente y el servidor validan la extensión de forma inconsistente (mayúsculas y minúsculas). |
| B6 | 🟡 Baja | `servidor_docente.py:181-224` | No hay manejo de errores en `/upload`. Cualquier excepción (disco lleno, nombre inválido o demasiado largo, carácter nulo) devuelve un error 500 en HTML *(verificado)*. |
| B7 | 🟡 Baja | `servidor_docente.py:197-198` | Se llama dos veces a `datetime.now()`. La hora del CSV y la del nombre del archivo pueden diferir en un segundo. |
| B8 | 🟡 Baja | `cliente_alumno.py:187` | El nombre del archivo seleccionado se muestra en blanco (`text_color="white"`). Con el tema claro de Windows, queda invisible. |
| B9 | 🟡 Baja | `cliente_alumno.py:266-304` | La interfaz se actualiza con `self.after()` desde el hilo secundario. Suele funcionar, pero Tkinter no garantiza que eso sea seguro entre hilos. Lo correcto es usar una cola que el hilo principal consulte. |

#### Otros problemas de diseño

- **Validaciones duplicadas** entre el cliente y el servidor, en dos implementaciones distintas que ya divergen (B5). Deberían vivir en un módulo compartido.
- **Constantes repetidas:** el puerto `5000` está escrito en tres lugares de dos archivos. Lo mismo pasa con los timeouts y el límite de 1 MB, que se controla solo en el cliente.
- **Estado global:** `PIN_ACTUAL` es una variable global y `app.config["MODULO"]` se asigna solo dentro de `__main__`. Por eso el servidor no se puede importar ni probar sin reproducir ese arranque.
- **Sin pruebas automatizadas** y sin logging: se usa `print`, y en el cliente, al ser una aplicación de ventana, los errores no quedan registrados en ningún lado.
- **Interfaz repetitiva:** cada campo se construye a mano con el mismo patrón de etiqueta + entrada + `pack`. Se podría generar con un bucle.

### 5.2 Mantenibilidad y portabilidad

#### Mantenibilidad

| Aspecto | Estado | Comentario |
|---|:-:|---|
| Tamaño y claridad | ✅ | Un docente con conocimientos de Python lo entiende en una tarde. |
| Dependencias | ✅ | Son pocas y populares (Flask, Waitress, Requests, CustomTkinter). |
| **Build reproducible** | ❌ | `pyproject.toml`, `poetry.lock` y `*.spec` están en el `.gitignore`. **No hay forma de regenerar los `.exe`** ni de saber con qué versión de Python o PyInstaller se generaron. |
| **Binarios en git** | ❌ | Hay 25 MB de `.exe` versionados, sin firma y sin un hash publicado. No se puede comprobar que correspondan al código fuente. Además, cada versión nueva infla el repositorio. Conviene publicarlos como *Releases*, generados por un proceso automático de integración continua. |
| Versionado del protocolo | ❌ | El cliente y el servidor no intercambian su versión. Un cliente viejo contra un servidor nuevo falla de formas impredecibles. |
| Configuración | ⚠️ | Todo está fijo en el código: puerto, rutas relativas al directorio de trabajo y módulos. |
| Pruebas | ❌ | No hay ninguna. |
| Bus factor | ⚠️ | Lo mantiene un solo autor. Es otra razón para tener pruebas y un build documentado. |

#### Portabilidad

| Aspecto | Estado | Comentario |
|---|:-:|---|
| Código Python multiplataforma | ✅ | Flask, Requests y Tkinter funcionan en Windows, Linux y macOS. Incluso `os.system("cls"/"clear")` contempla los dos casos. El servidor debería funcionar en la notebook Linux o Mac de un docente ejecutándolo con Python. |
| **Ejecutables** | ⚠️ | Solo hay `.exe` de Windows x64. No hay builds para macOS ni Linux. |
| **Futuras versiones de Windows** | ⚠️ | Python 3.12+ requiere **Windows 10 o posterior**: si alguna PC del laboratorio tiene Windows 7 u 8.1, no va a funcionar. En equipos Windows con procesador ARM, el `.exe` x64 corre en emulación. |
| **Antivirus y SmartScreen** | ⚠️ | Los `.exe` de PyInstaller en modo *onefile*, sin firmar, suelen ser **marcados como sospechosos** por Defender y SmartScreen. Además, se descomprimen en `%TEMP%` en cada ejecución. Si las PCs del laboratorio restringen `%TEMP%` o la ejecución de programas no firmados, el cliente no va a arrancar. Hay que probarlo en una PC real del laboratorio. |
| **Escalado de pantalla** | ⚠️ | La ventana del cliente mide 500 × 700 y **no se puede redimensionar** (`cliente_alumno.py:30-31`). Con un escalado de Windows del 125 % o 150 % en una pantalla de 768 px de alto, el botón "Entregar Examen" puede quedar **fuera de la pantalla**. |
| Fuente "Roboto" | 🟡 | No viene instalada en Windows. Se reemplaza sin aviso por otra fuente. Es solo estético. |
| Red | ⚠️ | Solo IPv4 y puerto fijo. `obtener_ip_local()` puede mostrar la IP equivocada si la PC tiene varias interfaces de red (WiFi + cable, VPN o hotspot), y muestra `127.0.0.1` si no hay ruta por defecto. |
| Rutas relativas | ⚠️ | Las entregas se guardan en la carpeta desde donde se ejecuta el programa. Si el docente abre el `.exe` desde un acceso directo o desde Descargas, las entregas quedan en un lugar inesperado. |

### 5.3 Seguridad

#### 5.3.1 Ante fallos del sistema

| Escenario | Qué pasa hoy | Riesgo |
|---|---|:-:|
| El docente abre el CSV en Excel | Todas las entregas siguientes fallan (B2) | 🔴 |
| Dos envíos iguales en el mismo segundo | Se sobrescribe el archivo (B1) | 🔴 |
| La entrega llega, pero la respuesta se demora más de 10 segundos (WiFi saturado) | El alumno ve un error, reintenta y se genera una entrega duplicada sin marca de cuál es la final | 🟠 |
| El servidor se cae a mitad de un `archivo.save()` | Puede quedar un archivo **truncado** sin fila en el CSV. El guardado no es atómico: lo correcto es escribir en un archivo temporal y después renombrarlo. | 🟠 |
| Se cierra la consola del servidor por error | El servidor se detiene sin pedir confirmación. Al reiniciarlo se genera un **PIN nuevo** y hay que avisar a toda el aula. | 🟠 |
| El puerto 5000 está ocupado | El servidor termina con un traceback, sin un mensaje entendible. | 🟡 |
| Disco lleno | Error 500, que se convierte en un error invisible para el alumno (B3/B4). | 🟡 |
| Respaldo | Las entregas quedan en **un solo lugar** hasta que el docente las sube al Drive. El modelo actual exige que estén en dos lugares antes de borrar. | 🟡 |

#### 5.3.2 Ante ataques

Se considera como atacante a un alumno del aula, con el PIN del pizarrón y acceso a la misma red WiFi.

| # | Ataque | Factibilidad | Impacto | Detalle |
|---|---|:-:|:-:|---|
| S1 | **Suplantar a otro alumno** | Trivial | 🔴 | Basta con escribir los datos de otro alumno. Como no hay control de reentregas, un alumno puede enviar **después** que la víctima un archivo vacío o con errores a su nombre, y esa queda como la entrega más reciente *(verificado)*. El `hostname` también se puede falsificar porque lo informa el cliente. Solo la IP es un dato confiable. |
| S2 | **Capturar exámenes ajenos en la red** | Media | 🔴 | El tráfico va por HTTP sin cifrar. En una red WiFi abierta, o con clave compartida, otro equipo puede capturar el contenido de los exámenes y el PIN. |
| S3 | **Falsificar líneas en la consola del docente** | Trivial | 🟠 | Los datos se imprimen sin sanitizar. Un apellido con saltos de línea agrega a la consola líneas falsas del tipo `[+] Nueva entrega: ...` *(verificado)*. Como hoy la consola es el "panel" del docente, un alumno puede aparentar que otro ya entregó, o que entregó él mismo. |
| S4 | **Inyección de fórmulas en el CSV** | Trivial | 🟠 | Un apellido como `=HYPERLINK("http://…";"clic")` se guarda tal cual *(verificado)* y Excel lo interpreta como una fórmula cuando el docente abre el CSV. Así se pueden mostrar datos falsos o enlaces maliciosos. |
| S5 | **Adivinar el PIN por fuerza bruta** | Fácil | 🟠 | El PIN tiene 4 dígitos (9000 combinaciones), se genera con `random`, que no es criptográfico, y **no hay límite de intentos**. Un script lo encuentra en minutos. Esto importa en la modalidad de "entrega supervisada", donde el PIN no se escribe en el pizarrón. |
| S6 | **Denegación de servicio** | Fácil | 🟠 | El servidor no limita el tamaño: el límite de 1 MB está **solo en el cliente**. Waitress acepta hasta 1 GB por request *(verificado con 5 MB)*. Con un script se puede llenar el disco del docente, o saturar sus 4 hilos con conexiones lentas, justo en el pico de entregas. |
| S7 | **Servidor falso** | Media | 🟡 | El `servidor_docente.exe` está en el mismo repositorio que el cliente. Un alumno puede levantar uno propio y pasarle a un compañero una IP falsa, por ejemplo "me equivoqué, es esta otra". El cliente no tiene forma de verificar que habla con el servidor del docente. |
| S8 | **Archivo malicioso para el docente** | Baja | 🟡 | El contenido de los `.zip` no se valida. Un proyecto NetBeans puede incluir scripts de compilación (Ant) que se ejecutan cuando el docente lo abre para corregir. El servidor no descomprime nada, así que no hay riesgo de *zip slip*. |
| S9 | **Datos que hacen fallar el guardado** | Trivial | 🟡 | Un apellido con un carácter nulo o de más de unos 250 caracteres provoca un error 500 *(verificado)*. Afecta solo a quien lo envía, pero es otro indicio de que faltan validaciones de entrada. |
| S10 | **Recorrido de rutas (*path traversal*)** | — | ✅ | **No es vulnerable.** `limpiar_cadena()` elimina `\` y `:` y reemplaza `/`, así que no se puede escribir fuera de la carpeta de entregas. |

---

## 6. Recomendaciones priorizadas

### Antes de usarlo en un examen real (bloqueantes)

1. **Registro de alumnos y reentregas (R8, R8b).** Identificar a cada alumno por su legajo/DNI y rechazar una segunda entrega salvo habilitación del docente. Guardar todas las entregas con un nombre único (con un contador o un identificador aleatorio en lugar de los segundos) y marcar cuál es la final. Esto resuelve B1, buena parte de S1 y el problema de los duplicados.
2. **Panel del docente (R10).** Debe permitir buscar a un alumno, ver si entregó y la hora, verificar el hash, habilitar una reentrega y ver la lista de entregas. Puede ser una página web local que sirva el mismo servidor, accesible **solo desde `localhost`**. Así no hace falta construir una interfaz de escritorio.
3. **No depender del CSV como fuente de datos (B2, S4).** Usar SQLite como registro y exportar el CSV a pedido. Si se mantiene el CSV, abrirlo y cerrarlo con manejo de errores, y anteponer `'` a los campos que empiecen con `=`, `+`, `-` o `@`.
4. **Corregir el manejo de errores del cliente (B3, B4).** Capturar el mensaje en una variable antes de la `lambda`, leer el JSON solo si la respuesta lo es, y mostrar siempre un mensaje claro.
5. **Límite de tamaño en el servidor (S6).** Configurar `MAX_CONTENT_LENGTH` en Flask y `max_request_body_size` en Waitress.
6. **Sanitizar lo que se imprime en la consola (S3)**, o reemplazar la consola por el panel.
7. **Alinear las extensiones con la metodología:** decidir qué hacer con `.rinfo` y `.crmi` en Concurrente y con el `.zip` en Objetos, y unificar las validaciones del cliente y del servidor en un módulo compartido.
8. **Probar en una PC real del laboratorio:** firewall, antivirus, SmartScreen, escalado de pantalla y la red WiFi con su posible aislamiento entre equipos.

### Mejoras importantes

9. **Fecha, turno y aula.** Al iniciar el servidor, pedir el turno y el aula, y crear `entregas/<fecha>_<turno>/<aula>/` con su propio registro. Esto replica la organización del Drive.
10. **Comprobante para el alumno (R11).** Que el cliente calcule y envíe el hash, que el servidor lo verifique (R5) y que devuelva un código corto (por ejemplo, `A7F3-21`) para que el alumno lo anote en la hoja del examen. Eso sirve como evidencia ante los reclamos de "yo entregué y no llegó".
11. **PIN más robusto (S5).** Usar `secrets`, más caracteres y un límite de intentos por IP.
12. **Guardado atómico.** Escribir en un archivo temporal y renombrarlo, y verificar el hash después de guardar.
13. **Timeouts y reintentos.** Ampliar el timeout del cliente y hacer que reintentar sea seguro: si llega un archivo con el mismo hash del mismo alumno, responder OK sin crear un duplicado.
14. **Descubrimiento del servidor.** Que el cliente encuentre el servidor del aula sin que el alumno escriba la IP, por ejemplo con un anuncio por *broadcast* o mDNS. Evita errores de tipeo y dificulta S7.

### Calidad y mantenimiento

15. **Build reproducible.** Versionar `pyproject.toml`, `poetry.lock` y el archivo `.spec`, generar los `.exe` en GitHub Actions y publicarlos como *Releases* con su hash.
16. **Pruebas automatizadas** del servidor con el cliente de pruebas de Flask, cubriendo los casos de la sección 5.3.
17. **Configuración y constantes** en un módulo compartido: puerto, límites y extensiones por módulo.
18. **Versión del protocolo** en `/ping`, para que el cliente detecte si es incompatible con el servidor.
19. **HTTPS** con un certificado autofirmado que el cliente tenga incorporado (*certificate pinning*). Resuelve S2 y S7 sin depender de internet.
