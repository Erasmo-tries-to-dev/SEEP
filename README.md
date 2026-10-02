# Sistema de Entrega de Exámenes Parciales (SEEP)

> **Notas:**

- Unifiqué el cliente alumno y el servidor docente en el mismo repositorio para simplificar las cosas.

- Para mis proyectos personales suelo usar poetry, así que antes de subirlo exporté las dependencias a requirements.txt.

- En la carpeta dist se encuentran los ejecutables listos para correr sobre Windows.

- Está de más decir que cualquier sugerencia, crítica o corrección es bienvenida.

---

## Resumen

El Sistema de Entrega de Exámenes Parciales (SEEP) tiene como objetivo reemplazar el uso de pendrives para la entrega de exámenes parciales de la materia Taller de Programación.

SEEP implementa una arquitectura cliente-servidor, y se busca que el producto final sea lo más sencillo posible para el/los docente/s del aula, de manera que facilite el proceso de entrega de exámenes y no resulte más engorroso que la metodología actual.

El sistema consta de dos ejecutables:

- **Cliente Alumno:** Una interfaz gráfica minimalista en la que el alumno ingresa sus datos y examen para enviarlos de forma segura al docente. Esta interfaz además realiza algunas validaciones para evitar los errores más típicos (ej: enviar un archivo `.o` en lugar de `.pas` en el módulo imperativo).
- **Servidor Docente:** Un proceso que recibe las entregas en tiempo real, las almacena en un directorio local y genera automáticamente un log (`.csv`) con el registro de los datos para lograr trazabilidad y detectar anomalías.

_[NOTA: El Servidor Docente opera actualmente mediante una interfaz de consola (CLI) completamente funcional y más o menos intuitiva. Pause el desarrollo de su interfaz gráfica para poder validar primero el funcionamiento del sistema tal cual esta. Una vez hecho esto implementar la interfaz deberia ser un proceso rapido]._

En su estado actual el sistema soporta la entrega de parciales de los tres módulos (Imperativo, Objetos, Concurrente), está pensado para ser usado sobre el sistema operativo Windows (utilizado en las computadoras de los laboratorios) y utiliza el protocolo HTTP.

---

## Flujo de Uso (El Camino Feliz)

### Fase 1: Apertura del servidor

El docente ejecuta `servidor_docente.exe`. El servidor pregunta cuál es el módulo que se está tomando ese día y el docente selecciona (1. Imperativo, 2. Objetos, 3. Concurrente). El sistema inicializa el servidor receptor y muestra en pantalla grande una IP local y un PIN generado. Crea automáticamente una carpeta vacía y un archivo `registro_entregas.csv`.

### Fase 2: Entrega

El alumno ejecuta `Cliente_Alumno.exe`. La interfaz le solicita sus Apellidos, Nombres, Legajo/DNI, la IP local del servidor, el PIN del aula y su archivo de examen. El flujo de ingreso del PIN puede adaptarse a la dinámica que se prefiera:

- **Entrega Supervisada (Mantener el control presencial):** El propio docente es quien ingresa el PIN secreto del aula para autorizar el envío.
- **Entrega Ágil:** Se anota el PIN del aula en el pizarrón y los alumnos lo ingresan para realizar el envio

De cualquier manera, al hacer click en “Entregar Examen”, este se envía al servidor docente.

### Fase 3: Recepción

El servidor docente recibe el archivo, lo renombra estandarizándolo (ej. `Apellidos_Nombres_Legajo_TimeStamp`) y lo guarda. Además, añade una fila al archivo `.csv` con la Hora, Módulo, Datos del alumno, IP de origen, Hostname y el Hash SHA-256 del archivo.

Las columnas IP de origen, Hash SHA-256 y Hostname tienen como objetivo detectar anomalías. En particular, el Hash SHA-256 podria ser usado para garantizar que el archivo no sufrió ninguna corrupción al viajar por la red o incluso como medida para detectar si alumnos se copiaron (de alguna manera entregaron el mismo parcial).

### Fase 4: Cierre y Respaldo

Al finalizar, el docente apaga el servidor. Se puede contrastar que los parciales hayan llegado a la carpeta local revisando los logs. Luego solo quedaría subir los archivos al Drive.

---

## Restricciones de la red y Alternativas

El camino feliz presupone que todas las computadoras están conectadas a la misma red WiFi, con comunicación par a par habilitada. Si existieran restricciones como _Access Point Isolation_, pensé en alternativas que pueden ser implementadas en el codigo de este sistema. Estas eliminan la dependencia de la configuracion de red de la facultad y son transparentes a los usuarios -El flujo del camino feliz no cambia desde la perspectiva de docentes y alumnos-.

1. **HotSpot Local:** El sistema convierte la máquina del docente en un router aprovechando una función nativa de Windows. Esto crea una red 100% local, aislada de la red Wifi y que se puede usar incluso si no hay internet en la facultad. El único límite es el máximo de conexiones simultáneas de windows (8), pero esto es salvable implementando un gestor de conexión efímera en el codigo del cliente alumno.
2. **Patron productor-consumidor:** Transformar el servidor docente en un cliente que consulte a un servidor puente ligero, que podria ser desplegado por ejemplo en la nube (con Render o servicio similar). Alumnos y docentes harían peticiones de salida estándar, puenteando cualquier bloqueo local, aunque esto si requeriría conexión a internet durante el examen.

---

## Instrucciones de ejecución

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
# En una terminal ejecutar el servidor:
python servidor_docente.py

# En otra terminal (o computadora de la misma red) ejecutar el cliente:
python cliente_alumno.py
```
