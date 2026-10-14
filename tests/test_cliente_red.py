"""
Suite de pruebas de caracterización para la capa de red del cliente SEEP.
Verifica que los escenarios de HTTP se mapeen correctamente a los DTOs ResultadoEntrega.
"""

import pytest
import requests
from requests_mock import Mocker

from cliente_modulos.cliente_red import DatosEntrega, enviar_examen

# -----------------------------------------------------------------------------
# FIXTURES
# -----------------------------------------------------------------------------


@pytest.fixture
def datos_prueba(tmp_path):
    """Genera un archivo temporal y un DTO de entrega válido para usar en los tests."""
    archivo_falso = tmp_path / "parcial_prueba.pas"
    archivo_falso.write_text("program prueba; begin end.")

    return DatosEntrega(
        ip="192.168.1.50",
        pin="1234",
        apellidos="Perez",
        nombres="Juan",
        identificador="12345-6",
        ruta_archivo=str(archivo_falso),
    )


# -----------------------------------------------------------------------------
# TESTS DE PING (Fase 1)
# -----------------------------------------------------------------------------


def test_ping_timeout(datos_prueba, requests_mock: Mocker):
    """Caracteriza el fallo temprano si la IP no responde o no existe."""
    # Simulamos que cualquier GET a la IP lanza un Timeout
    requests_mock.get("http://192.168.1.50:5000/ping", exc=requests.exceptions.Timeout)

    resultado = enviar_examen(datos_prueba)

    assert not resultado.exito
    assert "Tiempo de espera agotado" in resultado.mensaje_error
    assert not resultado.bloqueado_por_reentrega


def test_ping_version_incompatible(datos_prueba, requests_mock: Mocker):
    """Caracteriza el mapeo del HTTP 426 al DTO de error."""
    requests_mock.get(
        "http://192.168.1.50:5000/ping",
        status_code=426,
        json={"error": "Versión incompatible. Requiere v0.5.0."},
    )

    resultado = enviar_examen(datos_prueba)

    assert not resultado.exito
    assert "Versión incompatible" in resultado.mensaje_error


# -----------------------------------------------------------------------------
# TESTS DE UPLOAD (Fase 2)
# -----------------------------------------------------------------------------


def test_upload_exitoso(datos_prueba, requests_mock: Mocker):
    """Caracteriza el final feliz: ping OK y upload OK con comprobante."""
    requests_mock.get(
        "http://192.168.1.50:5000/ping", status_code=200, json={"status": "ok"}
    )
    requests_mock.post(
        "http://192.168.1.50:5000/upload",
        status_code=200,
        json={"mensaje": "Parcial entregado exitosamente", "comprobante": "A1B2C3"},
    )

    resultado = enviar_examen(datos_prueba)

    assert resultado.exito is True
    assert resultado.comprobante == "A1B2C3"
    assert resultado.mensaje_error is None
    assert resultado.bloqueado_por_reentrega is False


def test_upload_reentrega_bloqueada(datos_prueba, requests_mock: Mocker):
    """Caracteriza la detección del bloqueo por política (HTTP 403 + palabra 'autorización')."""
    requests_mock.get(
        "http://192.168.1.50:5000/ping", status_code=200, json={"status": "ok"}
    )
    requests_mock.post(
        "http://192.168.1.50:5000/upload",
        status_code=403,
        json={
            "error": "Ya registramos una entrega tuya. Pedile autorización al docente."
        },
    )

    resultado = enviar_examen(datos_prueba)

    assert not resultado.exito
    assert resultado.bloqueado_por_reentrega is True


def test_upload_error_interno(datos_prueba, requests_mock: Mocker):
    """Caracteriza la resiliencia del cliente ante una falla 500 del servidor."""
    requests_mock.get(
        "http://192.168.1.50:5000/ping", status_code=200, json={"status": "ok"}
    )
    requests_mock.post(
        "http://192.168.1.50:5000/upload",
        status_code=500,
        json={"error": "Error interno al escribir en disco."},
    )

    resultado = enviar_examen(datos_prueba)

    assert not resultado.exito
    assert resultado.bloqueado_por_reentrega is False
    assert "Error interno" in resultado.mensaje_error
