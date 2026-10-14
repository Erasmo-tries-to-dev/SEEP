"""
Módulo API de SEEP.
Contiene la configuración de Flask, las rutas web, funciones de validación
y el arranque del servidor WSGI.
Está 100% libre de código de interfaz gráfica (Tkinter).
"""

import errno
import logging
import os
import secrets
import string
import time
import socket
import sys
from datetime import datetime
from threading import Thread, Lock
from typing import Any, Callable, Dict, Tuple

from flask import Flask, current_app, jsonify, request
from flask.wrappers import Response
from waitress import serve

import seep_config
from servidor_modulos import persistencia

# -----------------------------------------------------------------------------
# CONSTANTES DE CONFIGURACIÓN Y LÍMITES (Magic Numbers extraídos)
# -----------------------------------------------------------------------------
CARACTERES_INVALIDOS_EN_NOMBRE: list[str] = ["<", ">", ":", '"', "\\", "|", "?", "*"]
MAX_LONGITUD_NOMBRES: int = 80
MAX_LONGITUD_LEGAJO: int = 30
PIN_MIN: int = 1000
PIN_MAX: int = 9999
HOST_BIND: str = "0.0.0.0"
IP_DUMMY_CONEXION: str = "10.255.255.255"
CODIGO_ERROR_PUERTO_WIN: int = 10048
MAX_INTENTOS_PIN: int = 5
TIEMPO_BLOQUEO_SEG: int = 60

# --- ESTADOS COMPARTIDOS EN MEMORIA ---
registro_intentos_ip: Dict[str, Tuple[int, float]] = {}

# --- CERROJOS (LOCKS) DE CONCURRENCIA ---
lock_rate_limit = Lock()
lock_entregas = Lock()

# -----------------------------------------------------------------------------
# FUNCIONES DE UTILIDAD GENERAL
# -----------------------------------------------------------------------------


def obtener_directorio_base() -> str:
    """
    Devuelve la ruta absoluta del directorio donde se ejecuta el programa.
    Maneja la diferencia entre ejecutar como script (.py) o como binario compilado (.exe).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def obtener_ip_local() -> str:
    """
    Determina la dirección IP local del equipo abriendo una conexión UDP simulada.
    Retorna '127.0.0.1' como fallback si no hay interfaz de red activa.
    """
    conexion_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        conexion_socket.connect((IP_DUMMY_CONEXION, 1))
        ip_local = conexion_socket.getsockname()[0]
    except Exception:
        ip_local = "127.0.0.1"
    finally:
        conexion_socket.close()
    return ip_local


def limpiar_cadena(texto: str) -> str:
    """
    Sanitiza un texto ingresado por el usuario para prevenir inyecciones
    y asegurar compatibilidad con el sistema de archivos del SO.
    """
    if not texto:
        return ""
    texto_limpio = (
        texto.replace("\0", "").replace("\n", "").replace("\r", "").replace("\t", "_")
    )
    texto_limpio = texto_limpio.replace(" ", "_").replace("/", "-")
    for caracter in CARACTERES_INVALIDOS_EN_NOMBRE:
        texto_limpio = texto_limpio.replace(caracter, "")
    return texto_limpio.strip()


def _generar_pin() -> str:
    """Genera un PIN alfanumérico seguro de 6 caracteres (excluyendo ambiguos como O y 0)."""
    caracteres = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(caracteres) for _ in range(6))


def _respuesta_version_incompatible(version_cliente: str) -> Tuple[Response, int]:
    """Genera la respuesta estándar HTTP 426 cuando el cliente está desactualizado."""
    return (
        jsonify(
            {
                "error": f"Versión del cliente ({version_cliente}) incompatible. "
                f"El servidor requiere la versión {seep_config.VERSION_SEEP}. Pedí el nuevo programa."
            }
        ),
        426,
    )


# -----------------------------------------------------------------------------
# FUNCIONES AUXILIARES DE LA RUTA UPLOAD
# -----------------------------------------------------------------------------


def _validar_datos_entrega(
    req: request, config: dict
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Fase 1: Extrae, sanitiza y valida el payload del formulario HTTP.
    Retorna un booleano de éxito, los datos procesados (o el error), y el código HTTP.
    """
    version = req.form.get("version")
    if version != seep_config.VERSION_SEEP:
        return (
            False,
            {"error": f"Versión incompatible. Requiere {seep_config.VERSION_SEEP}."},
            426,
        )

    pin = req.form.get("pin")
    apellidos = req.form.get("apellidos")
    nombres = req.form.get("nombres")
    identificador = req.form.get("identificador")
    hash_cliente = req.form.get("hash_cliente")
    archivo = req.files.get("file")

    if not all([pin, apellidos, nombres, identificador, archivo]):
        return False, {"error": "Faltan datos requeridos"}, 400

    ap_seguro = limpiar_cadena(apellidos)
    nom_seguro = limpiar_cadena(nombres)
    id_seguro = limpiar_cadena(identificador)
    host_seguro = limpiar_cadena(req.form.get("hostname", "Desconocido"))

    if (
        len(ap_seguro) > MAX_LONGITUD_NOMBRES
        or len(nom_seguro) > MAX_LONGITUD_NOMBRES
        or len(id_seguro) > MAX_LONGITUD_LEGAJO
    ):
        return False, {"error": "Los campos exceden la longitud máxima permitida"}, 400

    ip_cliente = req.remote_addr
    ahora = time.time()

    with lock_rate_limit:
        fallos, ultimo_intento = registro_intentos_ip.get(ip_cliente, (0, 0.0))

        if fallos >= MAX_INTENTOS_PIN:
            if (ahora - ultimo_intento) < TIEMPO_BLOQUEO_SEG:
                tiempo_restante = int(TIEMPO_BLOQUEO_SEG - (ahora - ultimo_intento))
                return (
                    False,
                    {
                        "error": f"Demasiados intentos fallidos. IP bloqueada por {tiempo_restante} segundos."
                    },
                    429,
                )
            else:
                fallos = 0

        if pin != config["PIN"]:
            registro_intentos_ip[ip_cliente] = (fallos + 1, ahora)
            intentos_restantes = MAX_INTENTOS_PIN - (fallos + 1)
            return (
                False,
                {"error": f"PIN incorrecto. Te quedan {intentos_restantes} intentos."},
                403,
            )

        if ip_cliente in registro_intentos_ip:
            del registro_intentos_ip[ip_cliente]

    modulo_activo = config["MODULO"]
    es_valido, resultado_ext = seep_config.validar_extension(
        archivo.filename, modulo_activo
    )
    if not es_valido:
        return False, {"error": resultado_ext}, 400

    momento_entrega = datetime.now()
    timestamp = momento_entrega.strftime("%Y%m%d_%H%M%S_%f")
    nombre_final = f"{ap_seguro}_{nom_seguro}_{id_seguro}_{timestamp}{resultado_ext}"

    datos_limpios = {
        "apellidos": ap_seguro,
        "nombres": nom_seguro,
        "identificador": id_seguro,
        "hostname": host_seguro,
        "ip": req.remote_addr,
        "archivo": archivo,
        "nombre_final": nombre_final,
        "momento_entrega": momento_entrega,
        "hash_cliente": hash_cliente,
    }
    return True, datos_limpios, 200


def _verificar_politica_reentrega(ruta_db: str, legajo: str) -> Tuple[bool, bool, str]:
    """
    Fase 2: Verifica en base de datos si el alumno tiene permitido entregar.
    Retorna (puede_entregar, es_nuevo_alumno, mensaje_de_error).
    """
    resultado = persistencia.consultar_estado_alumno(ruta_db, legajo)
    if resultado is None:
        return True, True, ""

    tiene_permiso = resultado[0]
    if tiene_permiso == 0:
        return (
            False,
            False,
            "Ya registramos una entrega tuya. Si necesitás reentregar, pedile autorización al docente.",
        )

    return True, False, ""


def _guardar_archivo_atomico(
    archivo: Any, carpeta_destino: str, nombre_final: str, hash_esperado: str
) -> Tuple[bool, str]:
    """
    Fase 3: Escribe el archivo parcial primero con extensión temporal (.tmp).
    Luego de escribirlo, lee el disco y recalcula el hash para asegurar que
    no hubo corrupción de I/O. Si todo está bien, lo renombra al final.
    """
    ruta_guardado = os.path.join(carpeta_destino, nombre_final)
    ruta_temporal = ruta_guardado + ".tmp"

    try:
        archivo.save(ruta_temporal)

        with open(ruta_temporal, "rb") as f_tmp:
            hash_disco = seep_config.calcular_hash(f_tmp)

        if hash_disco != hash_esperado:
            os.remove(ruta_temporal)
            return (
                False,
                "Error de hardware: El archivo se corrompió al escribirse en el disco.",
            )

        os.replace(ruta_temporal, ruta_guardado)
        return True, ""
    except Exception as e:
        if os.path.exists(ruta_temporal):
            try:
                os.remove(ruta_temporal)
            except Exception:
                pass
        return False, str(e)


# -----------------------------------------------------------------------------
# APPLICATION FACTORY Y RUTAS FLASK
# -----------------------------------------------------------------------------


def crear_app(
    modulo_elegido: str, pin_fijo: str, carpeta_elegida: str, ruta_db: str
) -> Flask:
    """Configura e inicializa la aplicación Flask y sus rutas (endpoints)."""
    app = Flask(__name__)
    app.config["PIN"] = pin_fijo
    app.config["MODULO"] = modulo_elegido
    app.config["CARPETA_ENTREGAS"] = carpeta_elegida
    app.config["RUTA_DB"] = ruta_db
    app.config["MAX_CONTENT_LENGTH"] = seep_config.MAX_TAMANO_BYTES

    os.makedirs(carpeta_elegida, exist_ok=True)

    @app.route("/ping", methods=["GET"])
    def ping() -> Tuple[Response, int]:
        """Endpoint para que el cliente verifique conexión y versión del servidor."""
        version = request.args.get("version", "")
        if version != seep_config.VERSION_SEEP:
            return _respuesta_version_incompatible(version)
        return jsonify({"status": "ok", "mensaje": "Servidor activo"}), 200

    @app.route("/upload", methods=["POST"])
    def upload() -> Tuple[Response, int]:
        """Endpoint orquestador de recepción de parciales."""

        # 1. Validación de Entrada (Puede ocurrir en paralelo)
        es_valido, payload, status = _validar_datos_entrega(request, current_app.config)
        if not es_valido:
            return jsonify(payload), status

        legajo = payload["identificador"]
        ruta_db = current_app.config["RUTA_DB"]
        archivo = payload["archivo"]
        hash_cliente = payload["hash_cliente"]

        # 2. Verificación de Integridad Criptográfica (R5)
        hash_servidor = seep_config.calcular_hash(archivo)
        if hash_cliente and hash_cliente != hash_servidor:
            logging.warning(
                f"Archivo corrupto detectado (Hash mismatch) para {payload['apellidos']} ({legajo})"
            )
            return (
                jsonify(
                    {
                        "error": "Error de integridad: El archivo se corrompió durante el envío. Volvé a entregarlo."
                    }
                ),
                400,
            )

        with lock_entregas:
            # 3. Reglas de Negocio e Idempotencia (Reentregas)
            puede_entregar, es_nuevo, msj_error = _verificar_politica_reentrega(
                ruta_db, legajo
            )

            if not puede_entregar:
                entrega_previa = persistencia.obtener_datos_entrega_previa(
                    ruta_db, legajo
                )

                if entrega_previa:
                    hash_previo, comprobante_previo = entrega_previa
                    if hash_previo == hash_servidor:
                        logging.info(
                            f"IDEMPOTENCIA: Reintento silencioso validado para legajo {legajo}."
                        )
                        return (
                            jsonify(
                                {
                                    "mensaje": "Parcial entregado exitosamente (Reintento validado)",
                                    "comprobante": comprobante_previo,
                                }
                            ),
                            200,
                        )

                logging.warning(
                    f"Reentrega bloqueada para {payload['apellidos']} ({legajo}) - IP: {payload['ip']}. Intento de sobreescritura."
                )
                return jsonify({"error": msj_error}), 403

            # 4. Persistencia en Disco Físico
            exito_io, msj_falla = _guardar_archivo_atomico(
                archivo,
                current_app.config["CARPETA_ENTREGAS"],
                payload["nombre_final"],
                hash_servidor,
            )
            if not exito_io:
                logging.error(
                    f"Error IO guardando entrega de {payload['apellidos']}: {msj_falla}",
                    exc_info=True,
                )
                return jsonify({"error": f"Error interno al guardar: {msj_falla}"}), 500

            # 5. Persistencia en Base de Datos
            codigo_comprobante = (
                f"{hash_servidor[:4].upper()}-{hash_servidor[4:8].upper()}"
            )

            try:
                persistencia.registrar_entrega_exitosa(
                    ruta_db=ruta_db,
                    legajo=legajo,
                    apellidos=payload["apellidos"],
                    nombres=payload["nombres"],
                    ip_vinculada=payload["ip"],
                    hostname=payload["hostname"],
                    timestamp=payload["momento_entrega"],
                    nombre_archivo=payload["nombre_final"],
                    hash_archivo=hash_servidor,
                    codigo_comprobante=codigo_comprobante,
                    es_nuevo_alumno=es_nuevo,
                )
            except Exception as e:
                logging.error(
                    f"Error DB asintiendo entrega de {payload['apellidos']}: {str(e)}",
                    exc_info=True,
                )
                return jsonify({"error": "Error interno en base de datos"}), 500

            # Éxito Total
            logging.info(
                f"NUEVA ENTREGA: {payload['apellidos']} {payload['nombres']} | Legajo: {legajo} | IP: {payload['ip']} | Comp: {codigo_comprobante}"
            )
            return (
                jsonify(
                    {
                        "mensaje": "Parcial entregado exitosamente",
                        "comprobante": codigo_comprobante,
                    }
                ),
                200,
            )

    return app


# -----------------------------------------------------------------------------
# EJECUCIÓN DEL SERVIDOR WSGI
# -----------------------------------------------------------------------------


def iniciar_servidor_en_hilo(
    app: Flask, callback_error: Callable[[str, str], None]
) -> Thread:
    """
    Ejecuta el servidor Waitress en un hilo demonio secundario.
    Captura errores de red (ej. puerto ocupado) y notifica a la interfaz gráfica
    mediante el callback proporcionado.
    """

    def _run() -> None:
        try:
            serve(
                app,
                host=HOST_BIND,
                port=seep_config.PUERTO_API,
                max_request_body_size=seep_config.MAX_TAMANO_BYTES,
            )
        except OSError as e:
            es_puerto_ocupado = (getattr(e, "errno", None) == errno.EADDRINUSE) or (
                getattr(e, "winerror", None) == CODIGO_ERROR_PUERTO_WIN
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

    hilo = Thread(target=_run, daemon=True)
    hilo.start()
    return hilo
