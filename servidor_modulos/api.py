"""
Módulo API de SEEP.
Contiene la configuración de Flask, las rutas web, funciones de validación
y el arranque del servidor WSGI.
#NOTA(Refactor): Claramente este archivo es demasiado largo, un refactor posible es mover la logica de negocio y funciones de utilidad a otros modulos.
"""

import errno
import logging
import os
import secrets
import socket
import sys
import time
import json
from datetime import datetime
from threading import Thread, Lock
from typing import Any, Callable, Dict, Tuple, List, Optional

from flask import Flask, current_app, jsonify, request, Request
from flask.wrappers import Response
from waitress import serve

import seep_config
from servidor_modulos import persistencia

# -----------------------------------------------------------------------------
# CONSTANTES GLOBALES Y LÍMITES
# -----------------------------------------------------------------------------
CARACTERES_INVALIDOS_EN_NOMBRE: List[str] = ["<", ">", ":", '"', "\\", "|", "?", "*"]
MAX_LONGITUD_NOMBRES: int = 80
MAX_LONGITUD_LEGAJO: int = 30
PIN_MIN: int = 1000
PIN_MAX: int = 9999
HOST_BIND: str = "0.0.0.0"
CODIGO_ERROR_PUERTO_WIN: int = 10048
MAX_INTENTOS_PIN: int = 5
TIEMPO_BLOQUEO_SEG: int = 60
INTERVALO_FARO_SEG: int = 2
IP_BROADCAST: str = "255.255.255.255"
IP_LOCALHOST: str = "127.0.0.1"
CARACTERES_PIN: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LONGITUD_PIN: int = 6

# -----------------------------------------------------------------------------
# ESTADOS COMPARTIDOS Y CERROJOS (LOCKS) DE CONCURRENCIA
# -----------------------------------------------------------------------------
registro_intentos_ip: Dict[str, Tuple[int, float]] = {}
cerrojo_rate_limit = Lock()
cerrojo_entregas = Lock()


# -----------------------------------------------------------------------------
# FUNCIONES DE UTILIDAD GENERAL
# -----------------------------------------------------------------------------
def obtener_directorio_base() -> str:
    """
    Devuelve la ruta absoluta del directorio donde se ejecuta el programa.
    Maneja la diferencia de rutas entre la ejecución como script y binario compilado.

    Returns:
        str: Ruta absoluta del directorio base.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def obtener_ips_locales() -> List[str]:
    """
    Escanea la máquina local y devuelve todas las direcciones IPv4 válidas
    de las placas de red conectadas (físicas o virtuales).

    Returns:
        List[str]: Lista de direcciones IP en formato string.
    """
    ips_validas: List[str] = []
    try:
        nombre_host = socket.gethostname()
        _, _, direcciones_ip = socket.gethostbyname_ex(nombre_host)
        for ip_detectada in direcciones_ip:
            if not ip_detectada.startswith("127."):
                ips_validas.append(ip_detectada)
    except Exception:
        pass

    if not ips_validas:
        ips_validas = [IP_LOCALHOST]

    return ips_validas


# NOTA (Refactor): Considerar si vale la pena moverlo a un modulo utils.
def limpiar_cadena(texto_ingresado: str) -> str:
    """
    Sanitiza un texto ingresado por el usuario para prevenir inyecciones
    y asegurar compatibilidad estricta con el sistema de archivos del sistema operativo.

    Args:
        texto_ingresado (str): La cadena de texto cruda.

    Returns:
        str: La cadena sanitizada y segura para utilizarse como nombre de archivo.
    """
    if not texto_ingresado:
        return ""
    texto_limpio = (
        texto_ingresado.replace("\0", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace("\t", "_")
    )
    texto_limpio = texto_limpio.replace(" ", "_").replace("/", "-")
    for caracter_invalido in CARACTERES_INVALIDOS_EN_NOMBRE:
        texto_limpio = texto_limpio.replace(caracter_invalido, "")
    return texto_limpio.strip()


# NOTA (Refactor): Probablemente sea buena idea mover a un modulo utils o a persistencia.
# Sobre el pin: Hay que llegar a un compromiso entre comodidad y seguridad. Un pin muy seguro tambien es muy engorroso, un pin muy sencillo tambien es muy inseguro.
# Este me parecio un buen compromiso, pero quizas sea un poquito engorroso.
def _generar_pin() -> str:
    """
    Genera un código PIN alfanumérico seguro descartando caracteres visualmente ambiguos.

    Returns:
        str: Código PIN de longitud determinada por LONGITUD_PIN.
    """
    return "".join(secrets.choice(CARACTERES_PIN) for _ in range(LONGITUD_PIN))


def _respuesta_version_incompatible(version_cliente: str) -> Tuple[Response, int]:
    """
    Genera la respuesta HTTP estándar cuando el cliente intenta conectarse con un ejecutable desactualizado.

    Args:
        version_cliente (str): La versión reportada por la petición.

    Returns:
        Tuple[Response, int]: Respuesta JSON estructurada y código HTTP 426.
    """
    mensaje_error = (
        f"Versión del cliente ({version_cliente}) incompatible. "
        f"El servidor requiere la versión {seep_config.VERSION_SEEP}. Pedí el nuevo programa."
    )
    return jsonify({"error": mensaje_error}), 426


# -----------------------------------------------------------------------------
# FUNCIONES AUXILIARES DE LA RUTA UPLOAD
# -----------------------------------------------------------------------------


# NOTA (Refactor): Varios extract methods posibles, aportarian a la legibilidad, considerarlos.
def _validar_datos_entrega(
    peticion_http: Request, configuracion_servidor: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Extrae, sanitiza y valida completamente el payload del formulario HTTP recibido.

    Args:
        peticion_http (Request): Objeto de petición HTTP entrante de Flask.
        configuracion_servidor (Dict[str, Any]): Diccionario con las variables globales activas del servidor.

    Returns:
        Tuple[bool, Dict[str, Any], int]: Indicador de éxito, diccionario con los datos procesados (o el error) y el código de estado HTTP.
    """
    version_cliente = peticion_http.form.get("version")
    if version_cliente != seep_config.VERSION_SEEP:
        mensaje_version = f"Versión incompatible. Requiere {seep_config.VERSION_SEEP}."
        return False, {"error": mensaje_version}, 426

    pin_ingresado = peticion_http.form.get("pin")
    apellidos_crudos = peticion_http.form.get("apellidos")
    nombres_crudos = peticion_http.form.get("nombres")
    identificador_crudo = peticion_http.form.get("identificador")
    hash_cliente = peticion_http.form.get("hash_cliente")
    archivo_recibido = peticion_http.files.get("file")

    if not all(
        [
            pin_ingresado,
            apellidos_crudos,
            nombres_crudos,
            identificador_crudo,
            archivo_recibido,
        ]
    ):
        return False, {"error": "Faltan datos requeridos"}, 400

    apellidos_seguro = limpiar_cadena(apellidos_crudos)
    nombres_seguro = limpiar_cadena(nombres_crudos)
    identificador_seguro = limpiar_cadena(identificador_crudo)
    hostname_seguro = limpiar_cadena(peticion_http.form.get("hostname", "Desconocido"))

    if (
        len(apellidos_seguro) > MAX_LONGITUD_NOMBRES
        or len(nombres_seguro) > MAX_LONGITUD_NOMBRES
        or len(identificador_seguro) > MAX_LONGITUD_LEGAJO
    ):
        return False, {"error": "Los campos exceden la longitud máxima permitida"}, 400

    ip_origen = peticion_http.remote_addr
    tiempo_actual = time.time()

    with cerrojo_rate_limit:
        intentos_fallidos, momento_ultimo_intento = registro_intentos_ip.get(
            ip_origen, (0, 0.0)
        )

        if intentos_fallidos >= MAX_INTENTOS_PIN:
            tiempo_transcurrido = tiempo_actual - momento_ultimo_intento
            if tiempo_transcurrido < TIEMPO_BLOQUEO_SEG:
                tiempo_restante = int(TIEMPO_BLOQUEO_SEG - tiempo_transcurrido)
                mensaje_bloqueo = f"Demasiados intentos fallidos. IP bloqueada por {tiempo_restante} segundos."
                return False, {"error": mensaje_bloqueo}, 429
            else:
                intentos_fallidos = 0

        if pin_ingresado != configuracion_servidor["PIN"]:
            registro_intentos_ip[ip_origen] = (intentos_fallidos + 1, tiempo_actual)
            intentos_restantes = MAX_INTENTOS_PIN - (intentos_fallidos + 1)
            mensaje_pin_invalido = (
                f"PIN incorrecto. Te quedan {intentos_restantes} intentos."
            )
            return False, {"error": mensaje_pin_invalido}, 403

        if ip_origen in registro_intentos_ip:
            del registro_intentos_ip[ip_origen]

    modulo_activo = configuracion_servidor["MODULO"]
    es_extension_valida, mensaje_extension = seep_config.validar_extension(
        archivo_recibido.filename, modulo_activo
    )
    if not es_extension_valida:
        return False, {"error": mensaje_extension}, 400

    momento_entrega = datetime.now()
    marca_temporal = momento_entrega.strftime("%Y%m%d_%H%M%S_%f")
    nombre_archivo_final = f"{apellidos_seguro}_{nombres_seguro}_{identificador_seguro}_{marca_temporal}{mensaje_extension}"

    datos_validados = {
        "apellidos": apellidos_seguro,
        "nombres": nombres_seguro,
        "identificador": identificador_seguro,
        "hostname": hostname_seguro,
        "ip_origen": ip_origen,
        "archivo": archivo_recibido,
        "nombre_final": nombre_archivo_final,
        "momento_entrega": momento_entrega,
        "hash_cliente": hash_cliente,
    }
    return True, datos_validados, 200


def _verificar_politica_reentrega(
    ruta_base_datos: str, legajo_alumno: str
) -> Tuple[bool, bool, str]:
    """
    Verifica mediante la base de datos local si el alumno tiene permitido realizar una entrega.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.
        legajo_alumno (str): Identificador único del alumno.

    Returns:
        Tuple[bool, bool, str]: Bandera de autorización, bandera si es alumno nuevo, y mensaje de error en caso de rechazo.
    """
    resultado_consulta = persistencia.consultar_estado_alumno(
        ruta_base_datos, legajo_alumno
    )
    if resultado_consulta is None:
        return True, True, ""

    tiene_permiso_activo = resultado_consulta[0]
    if tiene_permiso_activo == 0:
        mensaje_rechazo = "Ya registramos una entrega tuya. Si necesitás reentregar, pedile autorización al docente."
        return False, False, mensaje_rechazo

    return True, False, ""


# Nota (refactor): Considerar si mover a persistencia, utils u otro modulo
def _guardar_archivo_atomico(
    archivo_recibido: Any, carpeta_destino: str, nombre_final: str, hash_esperado: str
) -> Tuple[bool, str]:
    """
    Escribe el archivo en disco de forma transaccional para evitar archivos a medio escribir
    en caso de caídas del sistema o remoción prematura de la unidad.

    Args:
        archivo_recibido (Any): Objeto archivo provisto por el framework web.
        carpeta_destino (str): Directorio donde persistir la entrega.
        nombre_final (str): Nombre de archivo sanitizado y calculado.
        hash_esperado (str): Checksum criptográfico calculado en memoria antes de la escritura.

    Returns:
        Tuple[bool, str]: Indicador de éxito de la operación IO y mensaje de error en caso de falla.
    """
    ruta_guardado_definitiva = os.path.join(carpeta_destino, nombre_final)
    ruta_guardado_temporal = ruta_guardado_definitiva + ".tmp"

    try:
        archivo_recibido.save(ruta_guardado_temporal)

        with open(ruta_guardado_temporal, "rb") as archivo_temporal:
            hash_escrito_en_disco = seep_config.calcular_hash(archivo_temporal)

        if hash_escrito_en_disco != hash_esperado:
            os.remove(ruta_guardado_temporal)
            mensaje_corrupcion = (
                "Error de hardware: El archivo se corrompió al escribirse en el disco."
            )
            return False, mensaje_corrupcion

        os.replace(ruta_guardado_temporal, ruta_guardado_definitiva)
        return True, ""
    except Exception as excepcion_io:
        if os.path.exists(ruta_guardado_temporal):
            try:
                os.remove(ruta_guardado_temporal)
            except Exception:
                pass
        return False, str(excepcion_io)


# -----------------------------------------------------------------------------
# APPLICATION FACTORY Y RUTAS FLASK
# -----------------------------------------------------------------------------
def crear_app(
    modulo_elegido: str, pin_fijo: str, carpeta_elegida: str, ruta_base_datos: str
) -> Flask:
    """
    Configura e inicializa la aplicación Flask y registra los endpoints HTTP.

    Args:
        modulo_elegido (str): Modalidad del parcial.
        pin_fijo (str): Contraseña autogenerada para autorizar conexiones.
        carpeta_elegida (str): Ruta al directorio de guardado de parciales.
        ruta_base_datos (str): Ruta de acceso al archivo SQLite.

    Returns:
        Flask: Instancia completamente configurada de la aplicación web.
    """
    aplicacion_flask = Flask(__name__)
    aplicacion_flask.config["PIN"] = pin_fijo
    aplicacion_flask.config["MODULO"] = modulo_elegido
    aplicacion_flask.config["CARPETA_ENTREGAS"] = carpeta_elegida
    aplicacion_flask.config["RUTA_DB"] = ruta_base_datos
    aplicacion_flask.config["MAX_CONTENT_LENGTH"] = seep_config.MAX_TAMANO_BYTES

    os.makedirs(carpeta_elegida, exist_ok=True)

    @aplicacion_flask.route("/ping", methods=["GET"])
    def ping() -> Tuple[Response, int]:
        """
        Endpoint ligero para verificar disponibilidad de red y compatibilidad de versiones.

        Returns:
            Tuple[Response, int]: Respuesta en formato JSON con el estado de salud.
        """
        version_solicitante = request.args.get("version", "")
        if version_solicitante != seep_config.VERSION_SEEP:
            return _respuesta_version_incompatible(version_solicitante)
        return jsonify({"status": "ok", "mensaje": "Servidor activo"}), 200

    @aplicacion_flask.route("/upload", methods=["POST"])
    def upload() -> Tuple[Response, int]:
        """
        Endpoint orquestador de recepción, validación y persistencia de entregas estudiantiles.

        Returns:
            Tuple[Response, int]: Mensaje de respuesta y comprobante (o error) con su respectivo estado HTTP.
        """
        es_payload_valido, payload_procesado, codigo_estado_http = (
            _validar_datos_entrega(request, current_app.config)
        )
        if not es_payload_valido:
            return jsonify(payload_procesado), codigo_estado_http

        legajo_alumno = payload_procesado["identificador"]
        referencia_bd = current_app.config["RUTA_DB"]
        archivo_parcial = payload_procesado["archivo"]
        hash_enviado_cliente = payload_procesado["hash_cliente"]

        hash_calculado_servidor = seep_config.calcular_hash(archivo_parcial)
        if hash_enviado_cliente and hash_enviado_cliente != hash_calculado_servidor:
            logging.warning(
                f"Archivo corrupto detectado (Hash mismatch) para {payload_procesado['apellidos']} ({legajo_alumno})"
            )
            mensaje_corrupcion = "Error de integridad: El archivo se corrompió durante el envío. Volvé a entregarlo."
            return jsonify({"error": mensaje_corrupcion}), 400

        with cerrojo_entregas:
            puede_entregar, es_alumno_nuevo, mensaje_error_negocio = (
                _verificar_politica_reentrega(referencia_bd, legajo_alumno)
            )

            if not puede_entregar:
                registro_entrega_previa = persistencia.obtener_datos_entrega_previa(
                    referencia_bd, legajo_alumno
                )

                if registro_entrega_previa:
                    hash_almacenado, comprobante_generado_previamente = (
                        registro_entrega_previa
                    )
                    if hash_almacenado == hash_calculado_servidor:
                        logging.info(
                            f"Idempotencia: Reintento silencioso validado para legajo {legajo_alumno}."
                        )
                        respuesta_idempotente = {
                            "mensaje": "Parcial entregado exitosamente (Reintento validado)",
                            "comprobante": comprobante_generado_previamente,
                        }
                        return jsonify(respuesta_idempotente), 200

                logging.warning(
                    f"Reentrega bloqueada para {payload_procesado['apellidos']} ({legajo_alumno}) - IP: {payload_procesado['ip_origen']}. Intento de sobreescritura."
                )
                return jsonify({"error": mensaje_error_negocio}), 403

            es_escritura_exitosa, mensaje_falla_escritura = _guardar_archivo_atomico(
                archivo_parcial,
                current_app.config["CARPETA_ENTREGAS"],
                payload_procesado["nombre_final"],
                hash_calculado_servidor,
            )

            if not es_escritura_exitosa:
                logging.error(
                    f"Error de E/S guardando entrega de {payload_procesado['apellidos']}: {mensaje_falla_escritura}",
                    exc_info=True,
                )
                mensaje_falla_interna = (
                    f"Error interno al guardar: {mensaje_falla_escritura}"
                )
                return jsonify({"error": mensaje_falla_interna}), 500

            codigo_comprobante_final = f"{hash_calculado_servidor[:4].upper()}-{hash_calculado_servidor[4:8].upper()}"

            try:
                persistencia.registrar_entrega_exitosa(
                    ruta_db=referencia_bd,
                    legajo=legajo_alumno,
                    apellidos=payload_procesado["apellidos"],
                    nombres=payload_procesado["nombres"],
                    ip_peticion_actual=payload_procesado["ip_origen"],
                    hostname=payload_procesado["hostname"],
                    timestamp=payload_procesado["momento_entrega"],
                    nombre_archivo=payload_procesado["nombre_final"],
                    hash_archivo=hash_calculado_servidor,
                    codigo_comprobante=codigo_comprobante_final,
                    es_nuevo_alumno=es_alumno_nuevo,
                )
            except Exception as excepcion_base_datos:
                logging.error(
                    f"Error de BD asintiendo entrega de {payload_procesado['apellidos']}: {str(excepcion_base_datos)}",
                    exc_info=True,
                )
                return jsonify({"error": "Error interno en base de datos"}), 500

            logging.info(
                f"NUEVA ENTREGA: {payload_procesado['apellidos']} {payload_procesado['nombres']} | Legajo: {legajo_alumno} | IP: {payload_procesado['ip_origen']} | Comp: {codigo_comprobante_final}"
            )

            respuesta_exitosa = {
                "mensaje": "Parcial entregado exitosamente",
                "comprobante": codigo_comprobante_final,
            }
            return jsonify(respuesta_exitosa), 200

    return aplicacion_flask


# -----------------------------------------------------------------------------
# AUTO-DISCOVERY (FARO MULTIDIFUSIÓN UDP)
# -----------------------------------------------------------------------------


# Nota (Reflexion): Admito que aca estoy tocando bastante de oido. Quizas haya una mejor manera de lograr el descubirmiento del servidor.
def _faro_udp_multired(ips_locales_detectadas: List[str], modulo_activo: str) -> None:
    """
    Mantiene un ciclo perpetuo emitiendo paquetes de descubrimiento UDP por cada interfaz de red.

    Args:
        ips_locales_detectadas (List[str]): Listado de IPs disponibles para la transmisión local.
        modulo_activo (str): Identificador del examen que el faro anunciará a los clientes.
    """
    logging.info(
        f"Faro UDP Multidifusión encendido en puerto {seep_config.PUERTO_BEACON}. Escaneando {len(ips_locales_detectadas)} red(es)."
    )

    while True:
        for ip_origen in ips_locales_detectadas:
            socket_transmisor = None
            try:
                socket_transmisor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                socket_transmisor.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                socket_transmisor.bind((ip_origen, 0))

                datos_descubrimiento = {
                    "tipo": seep_config.IDENTIFICADOR_BEACON,
                    "ip": ip_origen,
                    "modulo": modulo_activo,
                }
                paquete_codificado = json.dumps(datos_descubrimiento).encode(
                    seep_config.CODIFICACION_TEXTO
                )

                socket_transmisor.sendto(
                    paquete_codificado, (IP_BROADCAST, seep_config.PUERTO_BEACON)
                )
            except Exception:
                pass
            finally:
                if socket_transmisor:
                    socket_transmisor.close()

        time.sleep(INTERVALO_FARO_SEG)


def iniciar_faro_en_hilo(ips_locales_detectadas: List[str], modulo_activo: str) -> None:
    """
    Lanza la ejecución del faro UDP en un hilo en segundo plano asilado.

    Args:
        ips_locales_detectadas (List[str]): Direcciones IP locales a utilizar.
        modulo_activo (str): Módulo actualmente siendo evaluado.
    """
    if not ips_locales_detectadas:
        return

    hilo_faro = Thread(
        target=_faro_udp_multired,
        args=(ips_locales_detectadas, modulo_activo),
        daemon=True,
    )
    hilo_faro.start()


# -----------------------------------------------------------------------------
# EJECUCIÓN DEL SERVIDOR WSGI
# -----------------------------------------------------------------------------
def iniciar_servidor_en_hilo(
    aplicacion_flask: Flask, callback_error: Callable[[str, str], None]
) -> Tuple[Thread, List[str]]:
    """
    Orquesta el levantamiento del ecosistema de red: Escaneo, Auto-Discovery y HTTP de entrega.

    Args:
        aplicacion_flask (Flask): Instancia de la aplicación previamente configurada.
        callback_error (Callable[[str, str], None]): Función delegada de Tkinter para mostrar alertas visuales.

    Returns:
        Tuple[Thread, List[str]]: Hilo en ejecución del servidor HTTP y la lista de direcciones IP descubiertas.
    """
    ips_locales_disponibles = obtener_ips_locales()

    if ips_locales_disponibles:
        iniciar_faro_en_hilo(ips_locales_disponibles, aplicacion_flask.config["MODULO"])

    def ejecutar_servidor() -> None:
        try:
            serve(
                aplicacion_flask,
                host=HOST_BIND,
                port=seep_config.PUERTO_API,
                max_request_body_size=seep_config.MAX_TAMANO_BYTES,
            )
        except OSError as excepcion_sistema:
            es_puerto_ocupado = (
                getattr(excepcion_sistema, "errno", None) == errno.EADDRINUSE
            ) or (
                getattr(excepcion_sistema, "winerror", None) == CODIGO_ERROR_PUERTO_WIN
            )

            if es_puerto_ocupado:
                titulo_alerta = "❌ ERROR CRÍTICO - Puerto Ocupado"
                mensaje_alerta = (
                    f"El puerto {seep_config.PUERTO_API} ya está ocupado.\n\n"
                    "Esto ocurre porque ya hay OTRA ventana de SEEP abierta.\n"
                    "Cierre el otro servidor y vuelva a intentar."
                )
            else:
                titulo_alerta = "❌ ERROR CRÍTICO de Red"
                mensaje_alerta = f"Ocurrió un error inesperado:\n{excepcion_sistema}"
            # Nota(observacion): No me queda claro si una restriccion de Tkinker impide que se ejecute el callable en determiandas circunstancias, investigar mas.
            # Hay parches en el codigo para mitigar esto por ahora (ver notas en servidor_docente.py)
            callback_error(titulo_alerta, mensaje_alerta)

    hilo_servidor_http = Thread(target=ejecutar_servidor, daemon=True)
    hilo_servidor_http.start()

    return hilo_servidor_http, ips_locales_disponibles
