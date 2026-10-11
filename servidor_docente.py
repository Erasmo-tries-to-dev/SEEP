import os
import random
import socket
import hashlib
import csv
import logging
from datetime import datetime
import threading
import sys
import errno

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

csv_lock = threading.Lock()


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


def registrar_en_csv(datos_fila):
    """Guarda los datos de la entrega en un archivo CSV."""
    directorio_base = obtener_directorio_base()
    nombre_archivo = f"registro_entregas_{current_app.config['MODULO']}.csv"

    nombre_archivo_csv = current_app.config.get(
        "ARCHIVO_CSV", os.path.join(directorio_base, nombre_archivo)
    )

    with csv_lock:
        archivo_existe = os.path.isfile(nombre_archivo_csv)
        try:
            with open(
                nombre_archivo_csv, mode="a", newline="", encoding="utf-8-sig"
            ) as f:
                writer = csv.writer(f, delimiter=";")
                if not archivo_existe:
                    writer.writerow(
                        [
                            "Hora",
                            "Módulo",
                            "Legajo/DNI",
                            "Apellidos",
                            "Nombres",
                            "IP Origen",
                            "Hostname",
                            "Hash SHA-256",
                            "Nombre de Archivo",
                        ]
                    )
                writer.writerow(datos_fila)
        except PermissionError:
            logging.warning(
                "No se pudo escribir en el CSV porque está abierto en otro programa (ej. Excel)."
            )


def configurar_modulo():
    """Menú interactivo en consola."""
    print("=" * 60)
    print(" SELECCIONE EL MÓDULO A EVALUAR ")
    print("=" * 60)
    print(" 1. Imperativo (.pas)")
    print(" 2. Objetos (.zip)")
    print(" 3. Concurrente (Archivo sin extensión de R-Info)")
    print("=" * 60)

    while True:
        opcion = input("Ingrese la opción (1, 2 o 3): ").strip()
        if opcion == "1":
            return "imperativo", "entregas_imperativo"
        elif opcion == "2":
            return "objetos", "entregas_objetos"
        elif opcion == "3":
            return "concurrente", "entregas_concurrente"
        else:
            print("Opción inválida. Ingrese 1, 2 o 3.")


def crear_app(modulo_elegido, pin_fijo=None, carpeta_elegida=None):
    """
    Application Factory: Crea y configura una instancia de la aplicación Flask.
    """
    app = Flask(__name__)

    # Inyectamos las configuraciones en la app
    app.config["PIN"] = pin_fijo if pin_fijo else str(random.randint(1000, 9999))
    app.config["MODULO"] = modulo_elegido
    # Forzamos que la carpeta de entregas se cree al lado del ejecutable
    directorio_base = obtener_directorio_base()
    carpeta_relativa = (
        carpeta_elegida if carpeta_elegida else f"entregas_{modulo_elegido}"
    )
    app.config["CARPETA_ENTREGAS"] = os.path.join(directorio_base, carpeta_relativa)

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

        if pin_recibido != current_app.config["PIN"]:
            logging.warning(
                f"PIN incorrecto ingresado por {apellidos} ({identificador}) desde IP: {ip_cliente}"
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
                f"Extensión inválida enviada por {apellidos} ({identificador})"
            )
            return jsonify({"error": resultado_validacion}), 400

        apellidos_seguro = limpiar_cadena(apellidos)
        nombres_seguro = limpiar_cadena(nombres)
        id_seguro = limpiar_cadena(identificador)
        momento_entrega = datetime.now()

        timestamp = momento_entrega.strftime("%Y%m%d_%H%M%S_%f")
        hora_legible = momento_entrega.strftime("%H:%M:%S")

        carpeta_destino = current_app.config["CARPETA_ENTREGAS"]
        nombre_final = f"{apellidos_seguro}_{nombres_seguro}_{id_seguro}_{timestamp}{resultado_validacion}"
        # Define la ruta final y una ruta temporal
        ruta_guardado = os.path.join(carpeta_destino, nombre_final)
        ruta_temporal = ruta_guardado + ".tmp"

        hash_archivo = calcular_hash(archivo)

        try:
            # 2. Guarda físicamente en el archivo temporal
            archivo.save(ruta_temporal)

            # Guardado Atómico: Renombra de .tmp a la extensión final

            os.replace(ruta_temporal, ruta_guardado)

            datos_auditoria = [
                hora_legible,
                modulo_activo,
                identificador,
                apellidos,
                nombres,
                ip_cliente,
                hostname_cliente,
                hash_archivo,
                nombre_final,
            ]
            registrar_en_csv(datos_auditoria)

            logging.info(
                f"NUEVA ENTREGA: {apellidos} {nombres} | DNI/Legajo: {id_seguro} | PC: {hostname_cliente} | IP: {ip_cliente}"
            )
            return (
                jsonify(
                    {"mensaje": f"Parcial de {modulo_activo} entregado exitosamente"}
                ),
                200,
            )

        except Exception as e:
            # Si falló, intenta limpiar el archivo temporal por prolijidad
            if os.path.exists(ruta_temporal):
                try:
                    os.remove(ruta_temporal)
                except Exception:
                    pass  # Ignora errores de borrado durante una excepción mayor

            logging.error(
                f"ERROR GRAVE guardando entrega de {apellidos}: {str(e)}", exc_info=True
            )
            return jsonify({"error": f"Error interno al guardar: {str(e)}"}), 500

    return app


def arrancar_servidor():
    """
    Inicializa la aplicación Flask, imprime la interfaz de consola para el docente
    y arranca el servidor WSGI (Waitress) capturando posibles errores de red/puertos.
    """
    modulo_elegido, carpeta_elegida = configurar_modulo()

    app = crear_app(modulo_elegido=modulo_elegido, carpeta_elegida=carpeta_elegida)

    ip_local = obtener_ip_local()
    os.system("cls" if os.name == "nt" else "clear")

    print("=" * 60)
    print(
        f" SISTEMA DE ENTREGA DE EXÁMENES PARCIALES (SEEP) - MÓDULO {modulo_elegido.upper()} "
    )
    print("=" * 60)
    print(f" IP: {ip_local}")
    print(f" PIN PARA ALUMNOS: {app.config['PIN']}")
    print(f" LOS PARCIALES SE GUARDARÁN EN: ./{carpeta_elegida}/")
    print(f" LOS LOGS SE GUARDARÁN EN: ./registro_entregas_{modulo_elegido}.csv")
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
            # Si es OTRO error del sistema operativo (permisos, red caída, etc.)
            print(" Ocurrió un error inesperado a nivel de sistema operativo o red.")
            print(f" Detalle técnico: {str(e)}")
            print(
                "\n Sugerencia: Verifique su conexión de red o permisos de administrador."
            )

        print("!" * 60 + "\n")

        # Pausamos la consola para que el docente llegue a leer el mensaje en Windows
        input(" Presione ENTER para cerrar esta ventana...")
        sys.exit(1)


if __name__ == "__main__":
    arrancar_servidor()
