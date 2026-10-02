import os
import random
import socket
import hashlib
import csv
from datetime import datetime
import threading  # Para el modulo de registrar entregas en el csv, evitar que dos hilos escriban al mismo tiempo.

# Waitress es un servidor de produccion, lo elegi porque reemplazar el servidor de desarrollo de flask por este fue muy muy sencillo
# Por supuesto podemos explorar alternativas, pero por lo que lei parece muy solido.
# Link a la documentacion: https://docs.pylonsproject.org/projects/waitress/en/stable/
from waitress import serve
from flask import Flask, request, jsonify

app = Flask(__name__)

PIN_ACTUAL = str(
    random.randint(1000, 9999)
)  # Genera un PIN de cuatro digitos para el aula
csv_lock = threading.Lock()


def obtener_ip_local():
    """
    Establece una conexión de prueba para determinar y retornar la dirección IP local
    de la máquina del docente dentro de la red actual.
    """
    # Nota importante: Si implemento la alternativa de levantar un hotspot esta funcion debe asegurarse de poder devolver la ip del hotspot y no la de la red de la facultad.
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
    """
    Sanitiza una cadena de texto eliminando o reemplazando caracteres inválidos
    para garantizar que pueda ser utilizada de forma segura en nombres de archivos
    dentro del sistema operativo Windows.
    """
    texto = texto.replace(" ", "_").replace("/", "-")
    for caracter_invalido in ["<", ">", ":", '"', "\\", "|", "?", "*"]:
        texto = texto.replace(caracter_invalido, "")
    return texto.strip()


def calcular_hash(archivo):
    """
    Calcula el hash SHA-256 del archivo para detectar copias exactas y garantizar la integridad.
    Lee el archivo en bloques para optimizar memoria y reposiciona el puntero al inicio
    tras finalizar la lectura para evitar guardar un archivo vacío en pasos posteriores.
    """
    sha256_hash = hashlib.sha256()

    for byte_block in iter(lambda: archivo.read(4096), b""):
        sha256_hash.update(byte_block)

    archivo.seek(0)

    return sha256_hash.hexdigest()


def registrar_en_csv(datos_fila):
    """
    Guarda los datos de la entrega en un archivo CSV, utilizando codificación utf-8-sig
    y separador de punto y coma para asegurar la correcta lectura de acentos y columnas
    al abrirse directamente con el software de hojas de cálculo de los docentes.
    """
    nombre_archivo_csv = f"registro_entregas_{app.config['MODULO']}.csv"

    with csv_lock:
        archivo_existe = os.path.isfile(nombre_archivo_csv)

        with open(nombre_archivo_csv, mode="a", newline="", encoding="utf-8-sig") as f:
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


def configurar_modulo():
    """
    Presenta un menú interactivo en consola para que el docente seleccione el módulo a evaluar.
    Retorna una tupla con el nombre del módulo y el nombre de la carpeta de destino correspondiente.
    """
    # Por supuesto esto va a ser reemplazado por una interfaz grafica ni bien pueda sentarme a hacerla.
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
    """
    Verifica que el archivo entregado tenga la extensión correcta según el módulo evaluado.
    Retorna una tupla: (es_valido, extension_o_mensaje_de_error).
    """
    if modulo == "imperativo":
        if not nombre_archivo.endswith(".pas"):
            return False, "Módulo Imperativo: Solo se permiten archivos .pas"
        return True, ".pas"

    elif modulo == "objetos":
        if not nombre_archivo.endswith(".zip"):
            return False, "Módulo Objetos: Solo se permiten archivos .zip"
        return True, ".zip"

    elif modulo == "concurrente":
        # Concurrente es un tema, porque los archivos que genera R-info no tienen extension. Asi que valido que no tenga extension.
        if "." in nombre_archivo:
            return (
                False,
                "Módulo Concurrente: Seleccioná el archivo generado por R-Info (sin extensión)",
            )
        return True, ""

    return False, "Módulo desconocido"


@app.route("/ping", methods=["GET"])
def ping():
    """
    Endpoint de prueba de conectividad para verificar que el servidor se encuentra activo.
    """
    return jsonify({"status": "ok", "mensaje": "Servidor activo"}), 200


@app.route("/upload", methods=["POST"])
def upload():
    """
    Endpoint principal para la recepción de exámenes.
    Valida el PIN, los datos del alumno y el formato del archivo según el módulo activo.
    Sanitiza los datos, guarda el archivo físico de forma segura y registra la entrega en los logs.
    """
    pin_recibido = request.form.get("pin")
    apellidos = request.form.get("apellidos")
    nombres = request.form.get("nombres")
    identificador = request.form.get("identificador")
    archivo = request.files.get("file")

    # Por lo que vi, las compus de los laboratorios suelen tener un hostname como lab07-22, asi que me parecio un campo util
    hostname_cliente = request.form.get("hostname", "Desconocido")
    ip_cliente = request.remote_addr

    if not all([pin_recibido, apellidos, nombres, identificador, archivo]):
        return jsonify({"error": "Faltan datos requeridos"}), 400

    if pin_recibido != PIN_ACTUAL:
        return jsonify({"error": "PIN incorrecto"}), 403

    modulo_activo = app.config["MODULO"]
    nombre_original = archivo.filename

    # Estas validaciones por supuesto tambien se hacen del lado del cliente
    es_valido, resultado_validacion = validar_extension(nombre_original, modulo_activo)
    if not es_valido:
        return jsonify({"error": resultado_validacion}), 400

    ext_guardado = resultado_validacion

    apellidos_seguro = limpiar_cadena(apellidos)
    nombres_seguro = limpiar_cadena(nombres)
    id_seguro = limpiar_cadena(identificador)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hora_legible = datetime.now().strftime("%H:%M:%S")

    # Fuerzo el nombre final del archivo para evitar errores de los alumnos como poner el nombre primero.
    # Esta de mas decir que es un nombre muy largo, despues podemos ver que es lo que realmente interesa guardar.
    carpeta_destino = app.config["CARPETA_ENTREGAS"]
    nombre_final = (
        f"{apellidos_seguro}_{nombres_seguro}_{id_seguro}_{timestamp}{ext_guardado}"
    )
    ruta_guardado = os.path.join(carpeta_destino, nombre_final)

    hash_archivo = calcular_hash(archivo)

    archivo.save(ruta_guardado)

    # Aca tambien quizas sean demasiados datos, por ahora los deje asi, luego podemos ver los mas interesantes para guardar en el csv.
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

    # Se imprime en pantalla para poder ver la entrega en tiempo real. (En un futuro habra una interfaz grafica)
    print(
        f"[+] Nueva entrega: {apellidos} {nombres} | a las {hora_legible} | DNI/Legajo: {id_seguro}   | PC: {hostname_cliente} | IP: {ip_cliente}"
    )

    return (
        jsonify({"mensaje": f"Parcial de {modulo_activo} entregado exitosamente"}),
        200,
    )


if __name__ == "__main__":
    modulo_elegido, carpeta_elegida = configurar_modulo()

    app.config["MODULO"] = modulo_elegido
    app.config["CARPETA_ENTREGAS"] = carpeta_elegida

    os.makedirs(carpeta_elegida, exist_ok=True)
    ip_local = obtener_ip_local()
    os.system("cls" if os.name == "nt" else "clear")

    print("=" * 60)
    print(
        f" SISTEMA DE ENTREGA DE EXÁMENES PARCIALES (SEEP) - MÓDULO {modulo_elegido.upper()} "
    )
    print("=" * 60)
    print(f" IP: {ip_local}")
    print(f" PIN PARA ALUMNOS: {PIN_ACTUAL}")
    print(f" LOS PARCIALES SE GUARDARÁN EN: ./{carpeta_elegida}/")
    print(f" LOS LOGS SE GUARDARÁN EN: ./registro_entregas_{modulo_elegido}.csv")
    print("=" * 60)
    print("SEEP - ESPERANDO EXÁMENES...\n")

    serve(app, host="0.0.0.0", port=5000)
