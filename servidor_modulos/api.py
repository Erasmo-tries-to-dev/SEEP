"""
Módulo API de SEEP.
Contiene la configuración de Flask, las rutas web, funciones de validación
y el arranque del servidor WSGI.
Está 100% libre de código de interfaz gráfica (Tkinter).
"""

import errno
import hashlib
import logging
import os
import socket
from datetime import datetime
from threading import Thread
import sys
from flask import Flask, current_app, jsonify, request
from waitress import serve
import random
import seep_config
from servidor_modulos import persistencia

CARACTERES_INVALIDOS_EN_NOMBRE = ["<", ">", ":", '"', "\\", "|", "?", "*"]


def obtener_directorio_base():
    """Devuelve la carpeta donde se encuentra el ejecutable o el script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _generar_pin():
    """Genera un PIN numérico de 4 dígitos para la sesión."""
    return str(random.randint(1000, 9999))


def obtener_ip_local():
    """Determina la dirección IP local de la máquina."""
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
    """Sanitiza un texto para usarlo de forma segura en nombres de archivo."""
    if not texto:
        return ""
    texto = (
        texto.replace("\0", "").replace("\n", "").replace("\r", "").replace("\t", "_")
    )
    texto = texto.replace(" ", "_").replace("/", "-")
    for caracter in CARACTERES_INVALIDOS_EN_NOMBRE:
        texto = texto.replace(caracter, "")
    return texto.strip()


def calcular_hash(archivo):
    """Calcula el hash SHA-256 de un archivo y rebobina el puntero."""
    sha256_hash = hashlib.sha256()
    for bloque in iter(lambda: archivo.read(4096), b""):
        sha256_hash.update(bloque)
    archivo.seek(0)
    return sha256_hash.hexdigest()


def _respuesta_version_incompatible(version_cliente):
    """Devuelve el JSON estándar para error 426 de versión vieja."""
    return (
        jsonify(
            {
                "error": f"Versión del cliente ({version_cliente}) incompatible. "
                f"El servidor requiere la versión {seep_config.VERSION_SEEP}. Pedí el nuevo programa."
            }
        ),
        426,
    )


def crear_app(modulo_elegido, pin_fijo, carpeta_elegida, ruta_db):
    """Application Factory: Crea y configura Flask."""
    app = Flask(__name__)
    app.config["PIN"] = pin_fijo
    app.config["MODULO"] = modulo_elegido
    app.config["CARPETA_ENTREGAS"] = carpeta_elegida
    app.config["RUTA_DB"] = ruta_db
    app.config["MAX_CONTENT_LENGTH"] = seep_config.MAX_TAMANO_BYTES

    os.makedirs(carpeta_elegida, exist_ok=True)

    @app.route("/ping", methods=["GET"])
    def ping():
        version_cliente = request.args.get("version", "")
        if version_cliente != seep_config.VERSION_SEEP:
            logging.warning(
                f"Ping rechazado por versión incompatible: {version_cliente} vs {seep_config.VERSION_SEEP}"
            )
            return _respuesta_version_incompatible(version_cliente)
        return jsonify({"status": "ok", "mensaje": "Servidor activo"}), 200

    @app.route("/upload", methods=["POST"])
    def upload():
        version_cliente = request.form.get("version")
        if version_cliente != seep_config.VERSION_SEEP:
            return _respuesta_version_incompatible(version_cliente)

        pin_recibido = request.form.get("pin")
        apellidos = request.form.get("apellidos")
        nombres = request.form.get("nombres")
        identificador = request.form.get("identificador")
        archivo = request.files.get("file")
        hostname_cliente = request.form.get("hostname", "Desconocido")
        ip_cliente = request.remote_addr

        if not all([pin_recibido, apellidos, nombres, identificador, archivo]):
            return jsonify({"error": "Faltan datos requeridos"}), 400

        apellidos_seguro = limpiar_cadena(apellidos)
        nombres_seguro = limpiar_cadena(nombres)
        id_seguro = limpiar_cadena(identificador)
        hostname_seguro = limpiar_cadena(hostname_cliente)

        if (
            len(apellidos_seguro) > 80
            or len(nombres_seguro) > 80
            or len(id_seguro) > 30
        ):
            return (
                jsonify({"error": "Los campos exceden la longitud máxima permitida"}),
                400,
            )

        if pin_recibido != current_app.config["PIN"]:
            return jsonify({"error": "PIN incorrecto"}), 403

        modulo_activo = current_app.config["MODULO"]
        es_valido, resultado_validacion = seep_config.validar_extension(
            archivo.filename, modulo_activo
        )
        if not es_valido:
            return jsonify({"error": resultado_validacion}), 400

        momento_entrega = datetime.now()
        timestamp = momento_entrega.strftime("%Y%m%d_%H%M%S_%f")
        carpeta_destino = current_app.config["CARPETA_ENTREGAS"]
        nombre_final = f"{apellidos_seguro}_{nombres_seguro}_{id_seguro}_{timestamp}{resultado_validacion}"
        ruta_guardado = os.path.join(carpeta_destino, nombre_final)
        ruta_temporal = ruta_guardado + ".tmp"

        hash_archivo = calcular_hash(archivo)
        codigo_comprobante = hash_archivo[:6].upper()

        try:
            ruta_db = current_app.config["RUTA_DB"]

            # Consultar base de datos a través del repositorio
            resultado_alumno = persistencia.consultar_estado_alumno(ruta_db, id_seguro)
            es_nuevo_alumno = False

            if resultado_alumno is not None:
                tiene_permiso = resultado_alumno[0]
                if tiene_permiso == 0:
                    logging.warning(
                        f"Reentrega bloqueada para {apellidos_seguro} ({id_seguro}) - IP: {ip_cliente}"
                    )
                    return (
                        jsonify(
                            {
                                "error": "Ya registramos una entrega tuya. Si necesitás reentregar, levantá la mano y pedile autorización al docente."
                            }
                        ),
                        403,
                    )
            else:
                es_nuevo_alumno = True

            archivo.save(ruta_temporal)
            os.replace(ruta_temporal, ruta_guardado)

            # Persistir a través del repositorio
            persistencia.registrar_entrega_exitosa(
                ruta_db=ruta_db,
                legajo=id_seguro,
                apellidos=apellidos_seguro,
                nombres=nombres_seguro,
                ip_vinculada=ip_cliente,
                hostname=hostname_seguro,
                timestamp=momento_entrega,
                nombre_archivo=nombre_final,
                hash_archivo=hash_archivo,
                codigo_comprobante=codigo_comprobante,
                es_nuevo_alumno=es_nuevo_alumno,
            )

            logging.info(
                f"NUEVA ENTREGA: {apellidos_seguro} {nombres_seguro} | DNI/Legajo: {id_seguro} | IP: {ip_cliente} | Comprobante: {codigo_comprobante}"
            )
            return (
                jsonify(
                    {
                        "mensaje": f"Parcial entregado exitosamente",
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


def iniciar_servidor_en_hilo(app, callback_error):
    """
    Ejecuta el servidor Waitress en un hilo secundario.
    Si ocurre un error a nivel de red (ej: puerto ocupado), ejecuta el callback.
    """

    def _run():
        try:
            serve(app, host="0.0.0.0", port=seep_config.PUERTO_API)
        except OSError as e:
            es_puerto_ocupado = (getattr(e, "errno", None) == errno.EADDRINUSE) or (
                getattr(e, "winerror", None) == 10048
            )

            if es_puerto_ocupado:
                titulo = "❌ ERROR CRÍTICO - Puerto Ocupado"
                mensaje = (
                    f"El puerto {seep_config.PUERTO_API} ya está ocupado.\n\n"
                    "Esto ocurre porque ya hay OTRA ventana de SEEP abierta.\n"
                    "Cierre el otro servidor y vuelva a intentar."
                )
            else:
                titulo = "❌ ERROR CRÍTICO de Red"
                mensaje = f"Ocurrió un error inesperado:\n{e}"

            callback_error(titulo, mensaje)
            os._exit(1)

    hilo = Thread(target=_run, daemon=True)
    hilo.start()
    return hilo
