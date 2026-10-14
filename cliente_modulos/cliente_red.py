"""
Módulo de red del cliente SEEP.
Aísla la comunicación HTTP y expone objetos de transferencia de datos (DTOs)
para desacoplar la lógica de red de la interfaz gráfica.
"""

import ipaddress
import logging
import socket
from dataclasses import dataclass
from typing import Optional

import requests

import seep_config


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
