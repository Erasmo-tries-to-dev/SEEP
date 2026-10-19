# Sistema de Entrega de Exámenes Parciales (SEEP) - v0.7.0

> **Notas:**
>
> - El sistema unifica el cliente alumno y el servidor docente en el mismo repositorio para simplificar el despliegue.
> - Se gestionan las dependencias mediante `requirements.txt` y se compilan los ejecutables nativos para Windows mediante flujos automatizados.
> - Se reconoce que el tamaño del codigo ha crecido significativamente en relacion a la anterior version presentada y se destaca la necesidad de manejar esto con un refactoring mas estructural para garantizar la mantenibilidad del proyecto a largo plazo.Varios comentarios a lo largo del codigo marcan futuros refactorings puntuales.
> - Se dejo pendiente el certificate pinning (Punto 19, recomendacions priorizadas), esto requiere cambiar de waitress a otro servidor y debe analizarse con tiempo cual es mas conveniente.
> - Cualquier sugerencia, crítica o corrección es bienvenida.

---

## Resumen

El Sistema de Entrega de Exámenes Parciales (SEEP) tiene como objetivo reemplazar el uso de pendrives para la entrega de exámenes parciales de la materia Taller de Programación en la Facultad de Informática (UNLP).

SEEP implementa una arquitectura cliente-servidor orientada a entornos presenciales de examen. Su premisa es simplificar al máximo el flujo para los docentes manteniendo estrictos estándares de seguridad, auditoría e integridad de los datos.

El sistema consta de dos aplicaciones principales empaquetadas en interfaces gráficas modernas construidas con CustomTkinter:

- **Cliente Alumno (`Cliente_Alumno.exe`):** Una aplicación de escritorio minimalista y segura en la que el estudiante completa sus datos identificatorios, busca de forma automática o manual el servidor docente, selecciona su archivo de examen y lo transmite cifrado y validado contra restricciones de tamaño y extensión según el módulo académico.
- **Servidor Docente (`Servidor_Docente.exe`):** Un panel de control en tiempo real que levanta una API WSGI local en segundo plano (Waitress/Flask). Recibe las entregas, calcula hashes de integridad, aplica validaciones de reentrega e interactúa con un motor de auditoría basado en SQLite para detectar anomalías o posibles plagios.

En su estado actual, SEEP soporta los tres módulos de la cursada (`Imperativo`, `Objetos` y `Concurrente`), está optimizado para ejecutarse en entornos Windows (computadoras de los laboratorios) y utiliza un protocolo mixto de red (UDP Auto-Discovery + HTTP).

---

## Novedades Clave de la Versión 0.7.0

1. **Interfaces Gráficas Completas (CustomTkinter):** Tanto el docente como el alumno operan con interfaces gráficas modernas, soportando temas claros/oscuros y eliminando la antigua dependencia de la consola (CLI).
2. **Auto-Discovery por UDP (Faro Multidifusión):** El servidor docente emite pings de red automáticos en un hilo aislado. El cliente alumno detecta la IP del docente de forma transparente sin necesidad de tipearla manualmente.
3. **Bases de Datos Efímeras (SQLite):** Cada sesión de examen genera un archivo autónomo `seep_registro.db` dentro del directorio de entregas, aislando los datos y permitiendo persistencia transaccional y control de concurrencia.
4. **Control de Reentregas:** El servidor implementa una política estricta de una sola entrega por alumno, bloqueando reentregas a menos que el docente la habilite explícitamente desde su panel.
5. **Motor Anti-Plagio e Integridad (SHA-256):** Cada archivo se evalúa mediante sumas de verificación criptográficas para descartar corrupción en tránsito y detectar colisiones de contenido exacto entre entregas.
6. **Exportación de Auditoría a CSV:** Generación opcional de reportes compatibles con Microsoft Excel.

---

## Flujo de Uso (El Camino Feliz)

### Fase 1: Apertura del Servidor Docente

El docente ejecuta el servidor, selecciona el **módulo a evaluar** (Imperativo, Objetos o Concurrente), e ingresa el **Turno** y **Aula**. El sistema inicializa una base de datos SQLite aislada, genera un **PIN de seguridad alfanumérico de 6 caracteres** y enciende el faro UDP automático. El panel muestra en pantalla las IPs activas y el PIN del aula.

### Fase 2: Descubrimiento y Entrega (Cliente Alumno)

El alumno abre el cliente en su PC. El sistema detecta automáticamente la IP del docente mediante UDP. El alumno completa sus datos (Apellidos, Nombres, Legajo/DNI, PIN) y selecciona el archivo de su parcial (ej. `.pas` para Imperativo, `.zip` para Objetos, sin extension para concurrente). Al presionar **Entregar Examen**, el archivo se transmite con validación de hash en memoria.

### Fase 3: Recepción y Auditoría en Tiempo Real

El servidor recibe la entrega de forma atómica. Sanitiza el nombre del archivo (`Apellidos_Nombres_Legajo_Timestamp.ext`), verifica el hash contra alteraciones, comprueba la política de reentregas y actualiza dinámicamente la grilla visual del docente en tiempo real. Si detecta que un alumno entregó desde una IP distinta a la inicial (Suplantación) o que el código es bit a bit idéntico al de otro compañero (Plagio), emite alertas visuales automáticas en el panel.

### Fase 4: Cierre y Respaldo

Al finalizar la evaluación, el docente puede exportar el historial completo a CSV y abrir directamente la carpeta física para subir los exámenes a Google Drive.

---

## Instrucciones de Ejecución (Desarrollo)

```bash
# 1. Clonar el repositorio
git clone [https://github.com/Erasmo-tries-to-dev/SEEP.git](https://github.com/Erasmo-tries-to-dev/SEEP.git)
cd SEEP

# 2. Crear y activar el entorno virtual
python -m venv venv
# En Windows:
venv\Scripts\activate
# En Mac/Linux:
source venv/bin/activate

# 3. Instalar las dependencias
pip install -r requirements.txt

# 4. Ejecutar las aplicaciones
# Servidor Docente (GUI):
python servidor_docente.py

# Cliente Alumno (GUI):
python cliente_alumno.py
```
