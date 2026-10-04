# SEEP - Sistema de Entrega de Exámenes Parciales

Esta versión del **SEEP** implementa una arquitectura de **Triangulación en la Nube** (basada en el patrón Productor-Consumidor). Está diseñada para sortear las estrictas limitaciones de conectividad de la facultad utilizando la salida a Internet estándar de las computadoras.

## Arquitectura y Actores

En esta rama, el sistema deja de ser P2P (Peer-to-Peer local). Ambos actores actúan como clientes de un servidor puente externo (SEEP-Buffer):

1. **Cliente Docente (Consumidor):** Inicia una sesión con el servidor puente, obtiene un `PIN` efímero y realiza un _polling_ silencioso cada 5 segundos para descargar las entregas. Los archivos se guardan físicamente en la PC del docente y luego se ordenan borrar de la nube.
2. **Cliente Alumno (Productor):** Interfaz gráfica optimizada. Al tener una URL fija en la nube, se elimina la necesidad de ingresar direcciones IP manualmente. Empaqueta el examen y lo transmite de forma segura.

## Instalación y Uso

### 1. Preparar el entorno local

Descargar el repositorio y crear el entorno virtual:

```bash
python -m venv venv

# En Windows:
venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Flujo del Examen

**Paso A: El Docente abre el buzón**
En la computadora de la mesa de control, activar el entorno virtual y ejecutar:

```bash
python cliente_docente.py
```

Seleccionar el módulo a evaluar. El sistema conectará automáticamente con la nube y mostrará en pantalla un **PIN de 4 dígitos** (Ej: `4592`). Escribir este PIN en el pizarrón del aula.

**Paso B: Los Alumnos entregan**
En las computadoras de los alumnos, una vez finalizado el examen, ejecutar:

```bash
python cliente_alumno.py
```

Completar los datos personales, ingresar el PIN copiado del pizarrón, adjuntar el archivo (el programa validará extensión y peso) y presionar entregar. El examen viajará a la nube y bajará directo a la carpeta local del docente.
