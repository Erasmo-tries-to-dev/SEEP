"""
Módulo de red del cliente SEEP.
Aísla la comunicación HTTP y expone objetos de transferencia de datos (DTOs)
para desacoplar la lógica de red de la interfaz gráfica.
"""

import ipaddress
import logging
import socket
import json
from dataclasses import dataclass
from typing import Optional

import requests

import seep_config

PUERTO_BEACON = 5555


@dataclass
class DatosEntrega:
    ip: str
    pin: str
    apellidos: str
    nombres: str
    identificador: str
    ruta_archivo: str


@dataclass
class ResultadoEntrega:
    exito: bool
    comprobante: Optional[str] = None
    mensaje_error: Optional[str] = None
    bloqueado_por_reentrega: bool = False


def buscar_servidor_en_red(timeout_segundos: int = 5) -> Optional[str]:
    """
    Abre un socket UDP para escuchar el faro (Beacon) del servidor docente.
    Retorna la IP detectada en formato string, o None si expira el tiempo
    de espera (Timeout) debido a aislamiento de red o ausencia del servidor.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    sock.bind(("0.0.0.0", PUERTO_BEACON))
    sock.settimeout(timeout_segundos)

    logging.info(f"Buscando servidor SEEP en red local (Puerto UDP {PUERTO_BEACON})...")

    try:
        while True:
            datos, direccion_origen = sock.recvfrom(1024)
            try:
                payload = json.loads(datos.decode("utf-8"))

                # Validamos que el paquete sea de nuestra aplicación y no ruido de la red
                if payload.get("tipo") == "SEEP_BEACON":
                    ip_detectada = payload.get("ip")
                    logging.info(
                        f"¡Servidor detectado automáticamente en IP: {ip_detectada}!"
                    )
                    return ip_detectada
            except json.JSONDecodeError:
                continue  # Ignoramos paquetes que no sean JSON válido

    except socket.timeout:
        logging.warning(
            "Tiempo de espera agotado. No se detectó ningún servidor en la red local."
        )
        return None
    finally:
        sock.close()


def _obtener_texto_error(respuesta: requests.Response, mensaje_por_defecto: str) -> str:
    """Intenta extraer el mensaje de error del JSON; si falla, devuelve un texto genérico."""
    try:
        return respuesta.json().get("error", mensaje_por_defecto)
    except ValueError:
        return f"Error en el servidor (HTTP {respuesta.status_code})"


def enviar_examen(datos: DatosEntrega) -> ResultadoEntrega:
    """
    Ejecuta el ciclo de red completo (Ping + Upload) de forma segura.
    """
    # Fase 0: Validar IP antes de intentar conectarse (Fail-Fast)
    try:
        ipaddress.ip_address(datos.ip)
    except ValueError:
        return ResultadoEntrega(
            exito=False, mensaje_error="El formato de la IP ingresada no es válido."
        )

    url_base = f"http://{datos.ip}:{seep_config.PUERTO_API}"

    # Fase 1: Ping de validación
    try:
        res_ping = requests.get(
            f"{url_base}/ping",
            params={"version": seep_config.VERSION_SEEP},
            timeout=seep_config.TIMEOUT_PING,
        )
        if res_ping.status_code != 200:
            error_ping = _obtener_texto_error(
                res_ping, f"Error en servidor (HTTP {res_ping.status_code})"
            )
            return ResultadoEntrega(
                exito=False, mensaje_error=f"Ping rechazado: {error_ping}"
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
    except Exception as e:
        return ResultadoEntrega(
            exito=False, mensaje_error=f"Error inesperado de red: {e}"
        )

    # Fase 2: Envío de carga útil (Upload)
    payload = {
        "pin": datos.pin,
        "apellidos": datos.apellidos,
        "nombres": datos.nombres,
        "identificador": datos.identificador,
        "hostname": socket.gethostname(),
        "version": seep_config.VERSION_SEEP,
    }

    try:
        with open(datos.ruta_archivo, "rb") as archivo:

            hash_cliente = seep_config.calcular_hash(archivo)

            payload["hash_cliente"] = hash_cliente

            res_upload = requests.post(
                f"{url_base}/upload",
                data=payload,
                files={"file": archivo},
                timeout=seep_config.TIMEOUT_UPLOAD,
            )

        if res_upload.status_code == 200:
            try:
                comprobante = res_upload.json().get("comprobante", "SIN-CODIGO")
            except ValueError:
                comprobante = "GUARDADO-OK"
            return ResultadoEntrega(exito=True, comprobante=comprobante)

        error_upload = _obtener_texto_error(
            res_upload, "Error al procesar la entrega en el servidor"
        )

        es_bloqueo = res_upload.status_code == 403

        return ResultadoEntrega(
            exito=False, mensaje_error=error_upload, bloqueado_por_reentrega=es_bloqueo
        )

    except Exception as e:
        return ResultadoEntrega(
            exito=False, mensaje_error=f"Error local al subir el archivo: {e}"
        )
