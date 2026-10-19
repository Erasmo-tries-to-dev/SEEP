"""
Módulo de Red del Cliente SEEP.
Aísla completamente la comunicación HTTP y UDP (Auto-Discovery) de la interfaz gráfica.
Expone Objetos de Transferencia de Datos (DTOs) para mantener un bajo acoplamiento
con los componentes visuales de la aplicación.
"""

import ipaddress
import logging
import socket
import json
from dataclasses import dataclass
from typing import Optional

import requests

import seep_config

# -----------------------------------------------------------------------------
# CONSTANTES LOCALES Y ESTADOS HTTP
# -----------------------------------------------------------------------------
HOST_ESCUCHA_UDP: str = "0.0.0.0"

HTTP_OK: int = 200
HTTP_FORBIDDEN: int = 403


# -----------------------------------------------------------------------------
# DTOs (DATA TRANSFER OBJECTS)
# -----------------------------------------------------------------------------
@dataclass
class DatosEntrega:
    """
    Encapsula la información ingresada por el estudiante y la ruta física de su examen
    para ser transmitida de forma consolidada hacia la capa de red.
    """

    ip: str
    pin: str
    apellidos: str
    nombres: str
    identificador: str
    ruta_archivo: str


@dataclass
class ResultadoEntrega:
    """
    Representa el estado final de una transacción de red, encapsulando el éxito o fracaso,
    los mensajes de error (si los hay) y el comprobante devuelto por el servidor.
    """

    exito: bool
    comprobante: Optional[str] = None
    mensaje_error: Optional[str] = None
    bloqueado_por_reentrega: bool = False


# -----------------------------------------------------------------------------
# AUTO-DISCOVERY (DESCUBRIMIENTO UDP)
# -----------------------------------------------------------------------------
def buscar_servidor_en_red(timeout_segundos: int = 5) -> Optional[str]:
    """
    Abre un socket UDP efímero para escuchar las transmisiones multidifusión (Beacon) del servidor docente.

    Args:
        timeout_segundos (int): Tiempo máximo de espera en segundos antes de abortar la escucha.

    Returns:
        Optional[str]: La dirección IP del servidor detectada en formato string, o None si expira el tiempo.

    Notes:
        RATIONALE: Se utiliza `SO_REUSEADDR` para permitir que múltiples instancias del cliente
        en la misma computadora (ej. durante pruebas) puedan vincularse al mismo puerto UDP
        simultáneamente sin generar un error de sistema operativo.
    """
    socket_escucha = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_escucha.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socket_escucha.bind((HOST_ESCUCHA_UDP, seep_config.PUERTO_BEACON))
    socket_escucha.settimeout(timeout_segundos)

    logging.info(
        f"Buscando servidor SEEP en red local (Puerto UDP {seep_config.PUERTO_BEACON})..."
    )

    try:
        while True:
            paquete_bytes, direccion_origen = socket_escucha.recvfrom(
                seep_config.TAMANO_BUFFER_UDP
            )
            try:
                carga_util = json.loads(
                    paquete_bytes.decode(seep_config.CODIFICACION_TEXTO)
                )

                if carga_util.get("tipo") == seep_config.IDENTIFICADOR_BEACON:
                    ip_detectada = carga_util.get("ip")
                    logging.info(
                        f"¡Servidor detectado automáticamente en IP: {ip_detectada}!"
                    )
                    return ip_detectada
            except json.JSONDecodeError:
                continue

    except socket.timeout:
        logging.warning(
            "Tiempo de espera agotado. No se detectó ningún servidor en la red local."
        )
        return None
    finally:
        socket_escucha.close()


# -----------------------------------------------------------------------------
# COMUNICACIÓN HTTP
# -----------------------------------------------------------------------------
def _obtener_texto_error(
    respuesta_http: requests.Response, mensaje_por_defecto: str
) -> str:
    """
    Intenta extraer y decodificar el mensaje de error estructurado del cuerpo JSON
    de una respuesta HTTP fallida.

    Args:
        respuesta_http (requests.Response): El objeto de respuesta proveído por la librería requests.
        mensaje_por_defecto (str): Mensaje de caída libre en caso de que la respuesta no sea JSON válido.

    Returns:
        str: El texto explicativo del error.
    """
    try:
        return respuesta_http.json().get("error", mensaje_por_defecto)
    except ValueError:
        return f"Error en el servidor (HTTP {respuesta_http.status_code})"


def enviar_examen(datos_entrega: DatosEntrega) -> ResultadoEntrega:
    """
    Ejecuta el ciclo de red completo para enviar el parcial del alumno al servidor.
    Incluye una validación temprana (Fail-Fast), un ping de control de versiones y conectividad,
    y finalmente la transmisión binaria del archivo.

    Args:
        datos_entrega (DatosEntrega): Instancia de DTO con los metadatos y ruta del examen.

    Returns:
        ResultadoEntrega: DTO que refleja el dictamen definitivo (éxito o rechazo detallado).
    """
    try:
        ipaddress.ip_address(datos_entrega.ip)
    except ValueError:
        return ResultadoEntrega(
            exito=False, mensaje_error="El formato de la IP ingresada no es válido."
        )

    url_servidor_base = f"http://{datos_entrega.ip}:{seep_config.PUERTO_API}"

    try:
        respuesta_ping = requests.get(
            f"{url_servidor_base}/ping",
            params={"version": seep_config.VERSION_SEEP},
            timeout=seep_config.TIMEOUT_PING,
        )
        if respuesta_ping.status_code != HTTP_OK:
            texto_error_ping = _obtener_texto_error(
                respuesta_ping, f"Error en servidor (HTTP {respuesta_ping.status_code})"
            )
            return ResultadoEntrega(
                exito=False, mensaje_error=f"Ping rechazado: {texto_error_ping}"
            )

    except requests.exceptions.Timeout:
        return ResultadoEntrega(
            exito=False, mensaje_error="Tiempo de espera agotado. Verificá la IP."
        )
    except requests.exceptions.ConnectionError:
        return ResultadoEntrega(
            exito=False,
            mensaje_error="No se pudo conectar. Verificá la IP o el cable de red.",
        )
    except Exception as excepcion_ping:
        return ResultadoEntrega(
            exito=False, mensaje_error=f"Error inesperado de red: {excepcion_ping}"
        )

    # Transmisión del Examen (Upload)
    carga_util_formulario = {
        "pin": datos_entrega.pin,
        "apellidos": datos_entrega.apellidos,
        "nombres": datos_entrega.nombres,
        "identificador": datos_entrega.identificador,
        "hostname": socket.gethostname(),
        "version": seep_config.VERSION_SEEP,
    }

    try:
        with open(datos_entrega.ruta_archivo, "rb") as puntero_archivo:

            hash_calculado_cliente = seep_config.calcular_hash(puntero_archivo)
            carga_util_formulario["hash_cliente"] = hash_calculado_cliente

            respuesta_carga = requests.post(
                f"{url_servidor_base}/upload",
                data=carga_util_formulario,
                files={"file": puntero_archivo},
                timeout=seep_config.TIMEOUT_UPLOAD,
            )

        if respuesta_carga.status_code == HTTP_OK:
            try:
                codigo_comprobante_final = respuesta_carga.json().get(
                    "comprobante", "SIN-CODIGO"
                )
            except ValueError:
                codigo_comprobante_final = "GUARDADO-OK"
            return ResultadoEntrega(exito=True, comprobante=codigo_comprobante_final)

        texto_error_carga = _obtener_texto_error(
            respuesta_carga, "Error al procesar la entrega en el servidor"
        )
        es_bloqueo_por_reentrega = respuesta_carga.status_code == HTTP_FORBIDDEN

        return ResultadoEntrega(
            exito=False,
            mensaje_error=texto_error_carga,
            bloqueado_por_reentrega=es_bloqueo_por_reentrega,
        )

    except Exception as excepcion_io:
        return ResultadoEntrega(
            exito=False,
            mensaje_error=f"Error local al subir el archivo: {excepcion_io}",
        )
