import os
import random
import socket
import hashlib
import logging
from datetime import datetime
import threading
import sys
import errno
import sqlite3

# Configuración de Logging para el servidor (Consola + Archivo físico)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("seep_servidor.log", encoding="utf-8"),  # Guarda en archivo
        logging.StreamHandler(sys.stdout),  # Muestra en consola
    ],
)

# Waitress es un servidor de produccion
from waitress import serve
from flask import Flask, request, jsonify, current_app

# Importamos nuestra nueva Única Fuente de Verdad compartida
import seep_config


def obtener_directorio_base():
    """Obtiene la ruta absoluta donde se encuentra el ejecutable o el script."""
    if getattr(sys, "frozen", False):
        # Si está corriendo como un ejecutable (.exe) compilado por PyInstaller
        return os.path.dirname(sys.executable)
    # Si está corriendo como un script .py normal
    return os.path.dirname(os.path.abspath(__file__))


def obtener_ip_local():
    """Establece una conexión de prueba para determinar y retornar la dirección IP local."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def limpiar_cadena(texto):
    """Sanitiza una cadena de texto para uso seguro en Windows y evita inyecciones."""
    if not texto:
        return ""

    # S3 y S9: Eliminar caracteres nulos, saltos de línea y tabulaciones (para proteger la consola y el OS)
    texto = (
        texto.replace("\0", "").replace("\n", "").replace("\r", "").replace("\t", "_")
    )
    texto = texto.replace(" ", "_").replace("/", "-")

    for caracter_invalido in ["<", ">", ":", '"', "\\", "|", "?", "*"]:
        texto = texto.replace(caracter_invalido, "")

    return texto.strip()


def calcular_hash(archivo):
    """Calcula el hash SHA-256 del archivo en bloques."""
    sha256_hash = hashlib.sha256()
    for byte_block in iter(lambda: archivo.read(4096), b""):
        sha256_hash.update(byte_block)
    archivo.seek(0)
    return sha256_hash.hexdigest()


def configurar_sesion():
    """Menú interactivo para configurar la sesión exacta del examen."""
    print("=" * 60)
    print(" CONFIGURACIÓN DE LA SESIÓN DE EXAMEN ")
    print("=" * 60)

    # 1. Módulo
    while True:
        print(" Módulos: 1. Imperativo | 2. Objetos | 3. Concurrente")
        opcion = input(" Seleccione el módulo (1-3): ").strip()
        if opcion == "1":
            modulo = "imperativo"
            break
        elif opcion == "2":
            modulo = "objetos"
            break
        elif opcion == "3":
            modulo = "concurrente"
            break
        print(" [!] Opción inválida. Ingrese 1, 2 o 3.\n")

    # 2. Turno
    while True:
        turno = input(" Ingrese el turno (ej. TA, TB, TC): ").strip().upper()
        if turno:
            break
        print(" [!] El turno no puede estar vacío.\n")

    # 3. Aula
    while True:
        aula = input(" Ingrese el aula (ej. 3, 10A, Lab4): ").strip().upper()
        if aula:
            break
        print(" [!] El aula no puede estar vacía.\n")

    return modulo, turno, aula


def inicializar_entorno(modulo, turno, aula):
    """
    Crea la carpeta de la sesión y configura la base de datos SQLite.
    Retorna la ruta de la carpeta, la ruta de la DB y el PIN (nuevo o recuperado).
    """
    fecha_hoy = datetime.now().strftime("%Y%m%d")

    # Ej: entregas_imperativo_20261011_TA_LAB3
    nombre_carpeta = f"entregas_{modulo}_{fecha_hoy}_{turno}_{aula}"
    directorio_base = obtener_directorio_base()
    ruta_carpeta = os.path.join(directorio_base, nombre_carpeta)

    os.makedirs(ruta_carpeta, exist_ok=True)

    ruta_db = os.path.join(ruta_carpeta, "seep_registro.db")
    db_existe = os.path.exists(ruta_db)

    # Conectamos a SQLite (crea el archivo si no existe)
    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()

    if not db_existe:
        # Primera vez que se abre esta sesión: Creamos el esquema completo
        cursor.execute("""
            CREATE TABLE configuracion (
                pin TEXT,
                modulo TEXT,
                fecha TEXT,
                turno TEXT,
                aula TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE alumnos (
                legajo TEXT PRIMARY KEY,
                apellidos TEXT,
                nombres TEXT,
                ip_vinculada TEXT,
                hostname_vinculado TEXT,
                reentrega_habilitada INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE entregas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                legajo TEXT,
                timestamp DATETIME,
                nombre_archivo TEXT,
                hash_archivo TEXT,
                codigo_comprobante TEXT,
                ip_origen TEXT,
                es_activa INTEGER DEFAULT 1,
                FOREIGN KEY(legajo) REFERENCES alumnos(legajo)
            )
        """)

        # Generamos un PIN nuevo y guardamos el contexto de la sesión
        pin_sesion = str(random.randint(1000, 9999))
        cursor.execute(
            """
            INSERT INTO configuracion (pin, modulo, fecha, turno, aula)
            VALUES (?, ?, ?, ?, ?)
        """,
            (pin_sesion, modulo, fecha_hoy, turno, aula),
        )
        conn.commit()
    else:
        # La base ya existe (el docente la cerró y la volvió a abrir). Recuperamos el PIN original.
        cursor.execute("SELECT pin FROM configuracion LIMIT 1")
        resultado = cursor.fetchone()
        pin_sesion = resultado[0] if resultado else str(random.randint(1000, 9999))

    conn.close()

    return ruta_carpeta, ruta_db, pin_sesion


def crear_app(modulo_elegido, pin_fijo, carpeta_elegida, ruta_db):
    """
    Application Factory: Crea y configura una instancia de la aplicación Flask.
    """
    app = Flask(__name__)

    # Inyectamos las configuraciones en la app
    app.config["PIN"] = pin_fijo
    app.config["MODULO"] = modulo_elegido
    app.config["CARPETA_ENTREGAS"] = carpeta_elegida
    app.config["RUTA_DB"] = (
        ruta_db  # ¡Acá guardamos la ruta de SQLite para usarla después!
    )

    # Rechazamos archivos más grandes que el límite establecido
    app.config["MAX_CONTENT_LENGTH"] = seep_config.MAX_TAMANO_BYTES

    # (La carpeta ya se creó en inicializar_entorno, pero aseguramos por las dudas)
    os.makedirs(app.config["CARPETA_ENTREGAS"], exist_ok=True)

    # Rechazamos archivos más grandes que el límite establecido en la configuración compartida
    app.config["MAX_CONTENT_LENGTH"] = seep_config.MAX_TAMANO_BYTES

    os.makedirs(app.config["CARPETA_ENTREGAS"], exist_ok=True)

    @app.route("/ping", methods=["GET"])
    def ping():
        version_cliente = request.args.get("version", "")

        if version_cliente != seep_config.VERSION_SEEP:
            logging.warning(
                f"Ping rechazado por versión incompatible: {version_cliente} vs {seep_config.VERSION_SEEP}"
            )
            return (
                jsonify(
                    {
                        "error": f"Versión del cliente ({version_cliente}) incompatible. El servidor requiere la versión {seep_config.VERSION_SEEP}. Pedí el nuevo programa."
                    }
                ),
                426,
            )

        return jsonify({"status": "ok", "mensaje": "Servidor activo"}), 200

    @app.route("/upload", methods=["POST"])
    def upload():
        version_cliente = request.form.get("version")

        # Validamos que el cliente no sea de una versión vieja
        if version_cliente != seep_config.VERSION_SEEP:
            logging.warning(
                f"Intento de conexión con versión incompatible: {version_cliente} vs {seep_config.VERSION_SEEP}"
            )
            return (
                jsonify(
                    {
                        "error": f"Versión del cliente ({version_cliente}) incompatible. El servidor requiere la versión {seep_config.VERSION_SEEP}. Pedí el nuevo programa."
                    }
                ),
                426,
            )

        pin_recibido = request.form.get("pin")
        apellidos = request.form.get("apellidos")
        nombres = request.form.get("nombres")
        identificador = request.form.get("identificador")
        archivo = request.files.get("file")

        hostname_cliente = request.form.get("hostname", "Desconocido")
        ip_cliente = request.remote_addr

        if not all([pin_recibido, apellidos, nombres, identificador, archivo]):
            logging.warning(
                f"Intento de subida fallido (datos incompletos) desde IP: {ip_cliente}"
            )
            return jsonify({"error": "Faltan datos requeridos"}), 400

        # S9 y S3: Sanitizamos inmediatamente todo lo que viene del alumno
        apellidos_seguro = limpiar_cadena(apellidos)
        nombres_seguro = limpiar_cadena(nombres)
        id_seguro = limpiar_cadena(identificador)
        hostname_seguro = limpiar_cadena(hostname_cliente)

        if (
            len(apellidos_seguro) > 80
            or len(nombres_seguro) > 80
            or len(id_seguro) > 30
        ):
            logging.warning(
                f"Payload rechazado por longitud extrema desde IP: {ip_cliente}"
            )
            return (
                jsonify({"error": "Los campos exceden la longitud máxima permitida"}),
                400,
            )

        if pin_recibido != current_app.config["PIN"]:
            logging.warning(
                f"PIN incorrecto ingresado por {apellidos_seguro} ({id_seguro}) desde IP: {ip_cliente}"
            )
            return jsonify({"error": "PIN incorrecto"}), 403

        modulo_activo = current_app.config["MODULO"]
        nombre_original = archivo.filename

        # Delegamos la validación a seep_config
        es_valido, resultado_validacion = seep_config.validar_extension(
            nombre_original, modulo_activo
        )
        if not es_valido:
            logging.warning(
                f"Extensión inválida enviada por {apellidos_seguro} ({id_seguro})"
            )
            return jsonify({"error": resultado_validacion}), 400

        momento_entrega = datetime.now()
        timestamp = momento_entrega.strftime("%Y%m%d_%H%M%S_%f")

        carpeta_destino = current_app.config["CARPETA_ENTREGAS"]
        nombre_final = f"{apellidos_seguro}_{nombres_seguro}_{id_seguro}_{timestamp}{resultado_validacion}"

        ruta_guardado = os.path.join(carpeta_destino, nombre_final)
        ruta_temporal = ruta_guardado + ".tmp"

        hash_archivo = calcular_hash(archivo)

        # R11: Generamos el código corto de comprobante (los primeros 6 caracteres del hash en mayúsculas)
        codigo_comprobante = hash_archivo[:6].upper()

        try:
            # 1. Guarda físicamente en el archivo temporal
            archivo.save(ruta_temporal)

            # 2. Guardado Atómico
            os.replace(ruta_temporal, ruta_guardado)

            # 3. Guardado en Base de Datos SQLite (Reemplaza al CSV)
            ruta_db = current_app.config["RUTA_DB"]
            conn = sqlite3.connect(ruta_db)
            cursor = conn.cursor()

            # Paso 3A: Insertar al alumno si no existe (el IGNORE evita error si ya está registrado)
            cursor.execute(
                """
                INSERT OR IGNORE INTO alumnos (legajo, apellidos, nombres, ip_vinculada, hostname_vinculado)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    id_seguro,
                    apellidos_seguro,
                    nombres_seguro,
                    ip_cliente,
                    hostname_seguro,
                ),
            )

            # (Fase 2: Aquí irá el bloqueo duro de reentregas. Por ahora, si un alumno vuelve a entregar,
            # marcamos como inactivas sus entregas previas para que la actual sea la única activa)
            cursor.execute(
                "UPDATE entregas SET es_activa = 0 WHERE legajo = ?", (id_seguro,)
            )

            # Paso 3B: Insertar la entrega en el historial inmutable
            cursor.execute(
                """
                INSERT INTO entregas (legajo, timestamp, nombre_archivo, hash_archivo, codigo_comprobante, ip_origen, es_activa)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
                (
                    id_seguro,
                    momento_entrega,
                    nombre_final,
                    hash_archivo,
                    codigo_comprobante,
                    ip_cliente,
                ),
            )

            conn.commit()
            conn.close()

            logging.info(
                f"NUEVA ENTREGA: {apellidos_seguro} {nombres_seguro} | DNI/Legajo: {id_seguro} | IP: {ip_cliente} | Comprobante: {codigo_comprobante}"
            )

            # Devolvemos el código de comprobante al cliente (lo usaremos en la Fase 3)
            return (
                jsonify(
                    {
                        "mensaje": f"Parcial de {modulo_activo} entregado exitosamente",
                        "comprobante": codigo_comprobante,
                    }
                ),
                200,
            )

        except Exception as e:
            if os.path.exists(ruta_temporal):
                try:
                    os.remove(ruta_temporal)
                except Exception:
                    pass

            logging.error(
                f"ERROR GRAVE guardando entrega de {apellidos_seguro}: {str(e)}",
                exc_info=True,
            )
            return jsonify({"error": f"Error interno al guardar: {str(e)}"}), 500

    return app


def arrancar_servidor():
    """
    Inicializa la aplicación Flask, imprime la interfaz de consola para el docente
    y arranca el servidor WSGI (Waitress) capturando posibles errores de red/puertos.
    """
    modulo, turno, aula = configurar_sesion()
    ruta_carpeta, ruta_db, pin_sesion = inicializar_entorno(modulo, turno, aula)

    app = crear_app(
        modulo_elegido=modulo,
        pin_fijo=pin_sesion,
        carpeta_elegida=ruta_carpeta,
        ruta_db=ruta_db,
    )

    ip_local = obtener_ip_local()
    os.system("cls" if os.name == "nt" else "clear")

    print("=" * 60)
    print(
        f" SISTEMA DE ENTREGA DE EXÁMENES PARCIALES (SEEP) - MÓDULO {modulo.upper()} "
    )
    print("=" * 60)
    print(f" TURNO: {turno} | AULA: {aula}")
    print(f" IP: {ip_local}")
    print(f" PIN PARA ALUMNOS: {app.config['PIN']}")
    print(f" LOS PARCIALES SE GUARDARÁN EN:\n   {ruta_carpeta}")
    print(f" BASE DE DATOS (SQLite):\n   {ruta_db}")
    print("=" * 60)
    print("SEEP - ESPERANDO EXÁMENES...\n")

    # Inicia el servidor usando el puerto de la configuración unificada
    try:
        serve(app, host="0.0.0.0", port=seep_config.PUERTO_API)
    except OSError as e:
        # Compara contra EADDRINUSE (Linux/Mac) o el WinError 10048 (Windows)
        es_puerto_ocupado = (getattr(e, "errno", None) == errno.EADDRINUSE) or (
            getattr(e, "winerror", None) == 10048
        )

        print("\n" + "!" * 60)
        print(" ❌ ERROR CRÍTICO AL INICIAR EL SERVIDOR")
        print("!" * 60)

        if es_puerto_ocupado:
            print(
                f" El puerto {seep_config.PUERTO_API} ya está ocupado por otro programa."
            )
            print(" Esto casi siempre ocurre porque ya hay OTRA ventana negra de")
            print(" SEEP abierta en esta computadora.")
            print("\n Solución:")
            print(" 1. Busque en la barra de tareas y cierre cualquier otro servidor.")
            print(" 2. Vuelva a abrir este programa.")
        else:
            print(" Ocurrió un error inesperado a nivel de sistema operativo o red.")
            print(f" Detalle técnico: {str(e)}")
            print(
                "\n Sugerencia: Verifique su conexión de red o permisos de administrador."
            )

        print("!" * 60 + "\n")
        input(" Presione ENTER para cerrar esta ventana...")
        sys.exit(1)


if __name__ == "__main__":
    arrancar_servidor()
