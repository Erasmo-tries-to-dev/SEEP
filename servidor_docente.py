import os
import random
import socket
import hashlib
import csv
from datetime import datetime
import threading

# Waitress es un servidor de produccion, lo elegi porque reemplazar el servidor de desarrollo de flask por este fue muy muy sencillo
# Por supuesto podemos explorar alternativas, pero por lo que lei parece muy solido.
# Link a la documentacion: https://docs.pylonsproject.org/projects/waitress/en/stable/
from waitress import serve
from flask import Flask, request, jsonify, current_app

csv_lock = threading.Lock()


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
    """Sanitiza una cadena de texto para uso seguro en Windows."""
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
    # Usamos current_app en lugar de la variable global 'app'
    nombre_archivo_csv = current_app.config.get(
        "ARCHIVO_CSV", f"registro_entregas_{current_app.config['MODULO']}.csv"
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
            print(
                "[!] ADVERTENCIA: No se pudo escribir en el CSV porque está abierto en otro programa."
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


def validar_extension(nombre_archivo, modulo):
    """Verifica que el archivo entregado tenga la extensión correcta."""
    nombre_lower = nombre_archivo.lower()

    if modulo == "imperativo":
        if not nombre_lower.endswith(".pas"):
            return False, "Módulo Imperativo: Solo se permiten archivos .pas"
        return True, ".pas"
    elif modulo == "objetos":
        if not nombre_lower.endswith(".zip"):
            return False, "Módulo Objetos: Solo se permiten archivos .zip"
        return True, ".zip"
    elif modulo == "concurrente":
        if "." in nombre_lower:
            return (
                False,
                "Módulo Concurrente: Seleccioná el archivo generado por R-Info (sin extensión)",
            )
        return True, ""

    return False, "Módulo desconocido"


def crear_app(modulo_elegido, pin_fijo=None, carpeta_elegida=None):
    """
    Application Factory: Crea y configura una instancia de la aplicación Flask.
    Esto elimina el estado global y permite testing limpio.
    """
    app = Flask(__name__)

    # Inyectamos las configuraciones en la app
    app.config["PIN"] = pin_fijo if pin_fijo else str(random.randint(1000, 9999))
    app.config["MODULO"] = modulo_elegido
    app.config["CARPETA_ENTREGAS"] = (
        carpeta_elegida if carpeta_elegida else f"entregas_{modulo_elegido}"
    )

    os.makedirs(app.config["CARPETA_ENTREGAS"], exist_ok=True)

    @app.route("/ping", methods=["GET"])
    def ping():
        return jsonify({"status": "ok", "mensaje": "Servidor activo"}), 200

    @app.route("/upload", methods=["POST"])
    def upload():
        pin_recibido = request.form.get("pin")
        apellidos = request.form.get("apellidos")
        nombres = request.form.get("nombres")
        identificador = request.form.get("identificador")
        archivo = request.files.get("file")

        hostname_cliente = request.form.get("hostname", "Desconocido")
        ip_cliente = request.remote_addr

        if not all([pin_recibido, apellidos, nombres, identificador, archivo]):
            return jsonify({"error": "Faltan datos requeridos"}), 400

        # Ahora el PIN se lee de la configuración segura de Flask
        if pin_recibido != current_app.config["PIN"]:
            return jsonify({"error": "PIN incorrecto"}), 403

        modulo_activo = current_app.config["MODULO"]
        nombre_original = archivo.filename

        es_valido, resultado_validacion = validar_extension(
            nombre_original, modulo_activo
        )
        if not es_valido:
            return jsonify({"error": resultado_validacion}), 400

        apellidos_seguro = limpiar_cadena(apellidos)
        nombres_seguro = limpiar_cadena(nombres)
        id_seguro = limpiar_cadena(identificador)
        momento_entrega = datetime.now()

        timestamp = momento_entrega.strftime("%Y%m%d_%H%M%S_%f")
        hora_legible = momento_entrega.strftime("%H:%M:%S")

        carpeta_destino = current_app.config["CARPETA_ENTREGAS"]
        nombre_final = f"{apellidos_seguro}_{nombres_seguro}_{id_seguro}_{timestamp}{resultado_validacion}"
        ruta_guardado = os.path.join(carpeta_destino, nombre_final)

        hash_archivo = calcular_hash(archivo)

        try:
            archivo.save(ruta_guardado)
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

            print(
                f"[+] Nueva entrega: {apellidos} {nombres} | a las {hora_legible} | DNI/Legajo: {id_seguro}   | PC: {hostname_cliente} | IP: {ip_cliente}"
            )
            return (
                jsonify(
                    {"mensaje": f"Parcial de {modulo_activo} entregado exitosamente"}
                ),
                200,
            )

        except Exception as e:
            print(f"[-] ERROR GRAVE guardando entrega de {apellidos}: {str(e)}")
            return jsonify({"error": f"Error interno al guardar: {str(e)}"}), 500

    return app


if __name__ == "__main__":
    modulo_elegido, carpeta_elegida = configurar_modulo()

    # Creamos la app de forma profesional
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

    serve(app, host="0.0.0.0", port=5000)
