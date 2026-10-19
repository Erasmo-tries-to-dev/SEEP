"""
Módulo de pruebas unitarias y de caracterización para la capa de red del cliente SEEP.
Verifica que los escenarios de comunicación HTTP (éxitos, bloqueos, timeouts)
se mapeen correctamente a los Objetos de Transferencia de Datos (DTOs) esperados.
"""

import pytest
import requests
from typing import Any
from requests_mock import Mocker

from cliente_modulos.cliente_red import DatosEntrega, enviar_examen

# -----------------------------------------------------------------------------
# CONSTANTES DE PRUEBA (Magic values extraídos)
# -----------------------------------------------------------------------------
IP_PRUEBA: str = "192.168.1.50"
PUERTO_PRUEBA: int = 5000
URL_PING: str = f"http://{IP_PRUEBA}:{PUERTO_PRUEBA}/ping"
URL_UPLOAD: str = f"http://{IP_PRUEBA}:{PUERTO_PRUEBA}/upload"

PIN_PRUEBA: str = "1234"
APELLIDOS_PRUEBA: str = "Perez"
NOMBRES_PRUEBA: str = "Juan"
LEGAJO_PRUEBA: str = "12345-6"

NOMBRE_ARCHIVO_PRUEBA: str = "parcial_prueba.pas"
CONTENIDO_ARCHIVO_PRUEBA: str = "program prueba; begin end."

COMPROBANTE_EXITO: str = "A1B2C3"

HTTP_OK: int = 200
HTTP_FORBIDDEN: int = 403
HTTP_UPGRADE_REQUIRED: int = 426
HTTP_INTERNAL_SERVER_ERROR: int = 500


# -----------------------------------------------------------------------------
# FIXTURES
# -----------------------------------------------------------------------------
@pytest.fixture
def datos_prueba(tmp_path: Any) -> DatosEntrega:
    """
    Genera un archivo temporal en disco y construye un DTO de entrega válido
    para inyectar en los casos de prueba.

    Args:
        tmp_path (Any): Directorio temporal gestionado de forma automática por Pytest.

    Returns:
        DatosEntrega: Objeto con los metadatos requeridos y la ruta al archivo simulado.
    """
    archivo_falso = tmp_path / NOMBRE_ARCHIVO_PRUEBA
    archivo_falso.write_text(CONTENIDO_ARCHIVO_PRUEBA)

    return DatosEntrega(
        ip=IP_PRUEBA,
        pin=PIN_PRUEBA,
        apellidos=APELLIDOS_PRUEBA,
        nombres=NOMBRES_PRUEBA,
        identificador=LEGAJO_PRUEBA,
        ruta_archivo=str(archivo_falso),
    )


# -----------------------------------------------------------------------------
# CASOS DE PRUEBA: VERIFICACIÓN DE CONECTIVIDAD (PING)
# -----------------------------------------------------------------------------
def test_ping_timeout(datos_prueba: DatosEntrega, requests_mock: Mocker) -> None:
    """
    Verifica el manejo de errores temprano (Fail-Fast) cuando la IP destino
    no responde a la petición inicial de ping.

    Args:
        datos_prueba (DatosEntrega): DTO inyectado por el fixture.
        requests_mock (Mocker): Interceptor de peticiones HTTP de requests.
    """
    requests_mock.get(URL_PING, exc=requests.exceptions.Timeout)

    resultado_entrega = enviar_examen(datos_prueba)

    assert not resultado_entrega.exito
    assert "Tiempo de espera agotado" in resultado_entrega.mensaje_error
    assert not resultado_entrega.bloqueado_por_reentrega


def test_ping_version_incompatible(
    datos_prueba: DatosEntrega, requests_mock: Mocker
) -> None:
    """
    Verifica el mapeo correcto del código HTTP 426 al DTO de resultado
    cuando el cliente detecta que su versión está obsoleta.

    Args:
        datos_prueba (DatosEntrega): DTO inyectado por el fixture.
        requests_mock (Mocker): Interceptor de peticiones HTTP.
    """
    requests_mock.get(
        URL_PING,
        status_code=HTTP_UPGRADE_REQUIRED,
        json={"error": "Versión incompatible. Requiere actualización."},
    )

    resultado_entrega = enviar_examen(datos_prueba)

    assert not resultado_entrega.exito
    assert "Versión incompatible" in resultado_entrega.mensaje_error


# -----------------------------------------------------------------------------
# CASOS DE PRUEBA: TRANSMISIÓN DE EXAMEN (UPLOAD)
# -----------------------------------------------------------------------------
def test_upload_exitoso(datos_prueba: DatosEntrega, requests_mock: Mocker) -> None:
    """
    Verifica el flujo ideal de transmisión, asegurando que un ping exitoso seguido
    de un upload exitoso genere el comprobante correspondiente en el DTO de retorno.

    Args:
        datos_prueba (DatosEntrega): DTO inyectado por el fixture.
        requests_mock (Mocker): Interceptor de peticiones HTTP.
    """
    requests_mock.get(URL_PING, status_code=HTTP_OK, json={"status": "ok"})
    requests_mock.post(
        URL_UPLOAD,
        status_code=HTTP_OK,
        json={
            "mensaje": "Parcial entregado exitosamente",
            "comprobante": COMPROBANTE_EXITO,
        },
    )

    resultado_entrega = enviar_examen(datos_prueba)

    assert resultado_entrega.exito is True
    assert resultado_entrega.comprobante == COMPROBANTE_EXITO
    assert resultado_entrega.mensaje_error is None
    assert resultado_entrega.bloqueado_por_reentrega is False


def test_upload_reentrega_bloqueada(
    datos_prueba: DatosEntrega, requests_mock: Mocker
) -> None:
    """
    Verifica la detección del bloqueo por política de reentrega (HTTP 403),
    asegurando que se active la bandera específica 'bloqueado_por_reentrega' en el DTO.

    Args:
        datos_prueba (DatosEntrega): DTO inyectado por el fixture.
        requests_mock (Mocker): Interceptor de peticiones HTTP.
    """
    requests_mock.get(URL_PING, status_code=HTTP_OK, json={"status": "ok"})
    requests_mock.post(
        URL_UPLOAD,
        status_code=HTTP_FORBIDDEN,
        json={
            "error": "Ya registramos una entrega tuya. Pedile autorización al docente."
        },
    )

    resultado_entrega = enviar_examen(datos_prueba)

    assert not resultado_entrega.exito
    assert resultado_entrega.bloqueado_por_reentrega is True


def test_upload_error_interno(
    datos_prueba: DatosEntrega, requests_mock: Mocker
) -> None:
    """
    Verifica la resiliencia del cliente ante fallos internos del servidor (HTTP 500),
    asegurando que se capture el mensaje y no se interprete erróneamente como un bloqueo de política.

    Args:
        datos_prueba (DatosEntrega): DTO inyectado por el fixture.
        requests_mock (Mocker): Interceptor de peticiones HTTP.
    """
    requests_mock.get(URL_PING, status_code=HTTP_OK, json={"status": "ok"})
    requests_mock.post(
        URL_UPLOAD,
        status_code=HTTP_INTERNAL_SERVER_ERROR,
        json={"error": "Error interno al escribir en disco."},
    )

    resultado_entrega = enviar_examen(datos_prueba)

    assert not resultado_entrega.exito
    assert resultado_entrega.bloqueado_por_reentrega is False
    assert "Error interno" in resultado_entrega.mensaje_error
