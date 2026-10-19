"""
Módulo de pruebas unitarias y de integración para el servidor docente SEEP.
Valida la inicialización de la API, las políticas de seguridad (PIN),
la idempotencia de entregas y el control de concurrencia/reentregas.
"""

import os
import sqlite3
from io import BytesIO
from typing import Any, Dict, Tuple

import pytest
from flask.testing import FlaskClient

import seep_config
from servidor_modulos.api import crear_app
from servidor_modulos.persistencia import _crear_esquema

# -----------------------------------------------------------------------------
# CONSTANTES DE PRUEBA (Magic values extraídos)
# -----------------------------------------------------------------------------
PIN_PRUEBA: str = "1234"
PIN_INVALIDO: str = "9999"
MODULO_PRUEBA: str = "imperativo"
FECHA_PRUEBA: str = "20261013"
TURNO_PRUEBA: str = "TA"
AULA_PRUEBA: str = "LAB3"

LEGAJO_PRUEBA: str = "12345-6"
APELLIDOS_PRUEBA: str = "Perez"
NOMBRES_PRUEBA: str = "Juan"
HOSTNAME_PRUEBA: str = "PC-TEST"

VERSION_ANTIGUA: str = "0.0.1"
CONTENIDO_ARCHIVO_TEST: bytes = b"program Hola; begin end."
NOMBRE_ARCHIVO_TEST: str = "parcial.pas"

HTTP_OK: int = 200
HTTP_FORBIDDEN: int = 403
HTTP_UPGRADE_REQUIRED: int = 426


# -----------------------------------------------------------------------------
# FIXTURES Y FUNCIONES AUXILIARES
# -----------------------------------------------------------------------------
@pytest.fixture
def entorno_prueba(tmp_path: Any) -> Tuple[FlaskClient, str]:
    """
    Fixture que levanta una base de datos SQLite en disco temporal y
    configura una instancia de prueba de Flask.

    Args:
        tmp_path (Any): Directorio temporal provisto automáticamente por Pytest.

    Returns:
        Tuple[FlaskClient, str]: Cliente HTTP de prueba y la ruta física de la base de datos efímera.
    """
    ruta_base_datos = tmp_path / "test_registro.db"
    carpeta_entregas = tmp_path / "entregas"

    conexion = sqlite3.connect(str(ruta_base_datos))
    cursor_activo = conexion.cursor()
    _crear_esquema(cursor_activo)
    cursor_activo.execute(
        "INSERT INTO configuracion (pin, modulo, fecha, turno, aula) VALUES (?, ?, ?, ?, ?)",
        (PIN_PRUEBA, MODULO_PRUEBA, FECHA_PRUEBA, TURNO_PRUEBA, AULA_PRUEBA),
    )
    conexion.commit()
    conexion.close()

    aplicacion_flask = crear_app(
        modulo_elegido=MODULO_PRUEBA,
        pin_fijo=PIN_PRUEBA,
        carpeta_elegida=str(carpeta_entregas),
        ruta_base_datos=str(ruta_base_datos),
    )
    aplicacion_flask.config["TESTING"] = True

    return aplicacion_flask.test_client(), str(ruta_base_datos)


def generar_payload_base(
    pin_seguridad: str = PIN_PRUEBA, identificador_alumno: str = LEGAJO_PRUEBA
) -> Dict[str, Any]:
    """
    Genera un diccionario estructurado como formulario multipart/form-data válido
    para simular una entrega de red desde el cliente alumno.

    Args:
        pin_seguridad (str): PIN de sesión (por defecto, el válido).
        identificador_alumno (str): Legajo a utilizar en la entrega simulada.

    Returns:
        Dict[str, Any]: Payload formateado y listo para requests HTTP.
    """
    return {
        "version": seep_config.VERSION_SEEP,
        "pin": pin_seguridad,
        "apellidos": APELLIDOS_PRUEBA,
        "nombres": NOMBRES_PRUEBA,
        "identificador": identificador_alumno,
        "hostname": HOSTNAME_PRUEBA,
        "file": (BytesIO(CONTENIDO_ARCHIVO_TEST), NOMBRE_ARCHIVO_TEST),
    }


# -----------------------------------------------------------------------------
# CASOS DE PRUEBA (TESTS)
# -----------------------------------------------------------------------------
def test_ping_version_correcta(entorno_prueba: Tuple[FlaskClient, str]) -> None:
    """
    Verifica que el servidor responda exitosamente ante un ping de validación
    cuando el cliente posee la versión requerida actual.

    Args:
        entorno_prueba (Tuple[FlaskClient, str]): Dependencias inyectadas por el fixture.
    """
    cliente_api, _ = entorno_prueba
    respuesta_http = cliente_api.get(f"/ping?version={seep_config.VERSION_SEEP}")

    assert respuesta_http.status_code == HTTP_OK
    assert respuesta_http.json["status"] == "ok"


def test_ping_version_incorrecta(entorno_prueba: Tuple[FlaskClient, str]) -> None:
    """
    Verifica que el servidor rechace la conexión con el código HTTP correspondiente
    si la versión del software cliente es obsoleta.

    Args:
        entorno_prueba (Tuple[FlaskClient, str]): Dependencias inyectadas por el fixture.
    """
    cliente_api, _ = entorno_prueba
    respuesta_http = cliente_api.get(f"/ping?version={VERSION_ANTIGUA}")

    assert respuesta_http.status_code == HTTP_UPGRADE_REQUIRED
    assert "incompatible" in respuesta_http.json["error"]


def test_upload_pin_incorrecto(entorno_prueba: Tuple[FlaskClient, str]) -> None:
    """
    Verifica que el endpoint de entrega valide estrictamente el PIN de seguridad
    y rechace peticiones inválidas.

    Args:
        entorno_prueba (Tuple[FlaskClient, str]): Dependencias inyectadas por el fixture.
    """
    cliente_api, _ = entorno_prueba
    payload_invalido = generar_payload_base(pin_seguridad=PIN_INVALIDO)

    respuesta_http = cliente_api.post(
        "/upload", data=payload_invalido, content_type="multipart/form-data"
    )

    assert respuesta_http.status_code == HTTP_FORBIDDEN
    assert "PIN incorrecto" in respuesta_http.json["error"]


def test_upload_entrega_nueva_exitosa(entorno_prueba: Tuple[FlaskClient, str]) -> None:
    """
    Verifica el "camino feliz" de una entrega inicial, comprobando la respuesta HTTP exitosa
    y la persistencia correcta de los metadatos y estados en la base de datos local.

    Args:
        entorno_prueba (Tuple[FlaskClient, str]): Dependencias inyectadas por el fixture.
    """
    cliente_api, ruta_base_datos = entorno_prueba
    payload_valido = generar_payload_base()

    respuesta_http = cliente_api.post(
        "/upload", data=payload_valido, content_type="multipart/form-data"
    )

    assert respuesta_http.status_code == HTTP_OK
    assert "comprobante" in respuesta_http.json

    conexion = sqlite3.connect(ruta_base_datos)
    cursor_activo = conexion.cursor()
    cursor_activo.execute(
        "SELECT legajo FROM alumnos WHERE legajo = ?", (LEGAJO_PRUEBA,)
    )
    assert cursor_activo.fetchone() is not None

    cursor_activo.execute(
        "SELECT es_activa FROM entregas WHERE legajo = ?", (LEGAJO_PRUEBA,)
    )
    assert cursor_activo.fetchone()[0] == 1
    conexion.close()


def test_upload_reentrega_bloqueada(entorno_prueba: Tuple[FlaskClient, str]) -> None:
    """
    Verifica la política de seguridad que bloquea automáticamente un segundo intento
    de entrega de un mismo alumno sin autorización explícita previa.

    Args:
        entorno_prueba (Tuple[FlaskClient, str]): Dependencias inyectadas por el fixture.
    """
    cliente_api, _ = entorno_prueba

    cliente_api.post(
        "/upload", data=generar_payload_base(), content_type="multipart/form-data"
    )

    payload_reentrega = generar_payload_base()
    payload_reentrega["file"] = (
        BytesIO(b"program Hola2; begin end."),
        "parcial_v2.pas",
    )

    respuesta_http = cliente_api.post(
        "/upload", data=payload_reentrega, content_type="multipart/form-data"
    )

    assert respuesta_http.status_code == HTTP_FORBIDDEN
    assert "Ya registramos una entrega tuya" in respuesta_http.json["error"]


def test_upload_reentrega_habilitada_y_consumida(
    entorno_prueba: Tuple[FlaskClient, str],
) -> None:
    """
    Verifica que un alumno autorizado pueda reentregar su examen exitosamente, validando
    que dicho permiso de un solo uso se consuma inmediatamente y que la base de datos
    marque la nueva entrega como la única activa.

    Args:
        entorno_prueba (Tuple[FlaskClient, str]): Dependencias inyectadas por el fixture.
    """
    cliente_api, ruta_base_datos = entorno_prueba

    cliente_api.post(
        "/upload",
        data=generar_payload_base(identificador_alumno=LEGAJO_PRUEBA),
        content_type="multipart/form-data",
    )

    conexion = sqlite3.connect(ruta_base_datos)
    cursor_activo = conexion.cursor()
    cursor_activo.execute(
        "UPDATE alumnos SET reentrega_habilitada = 1 WHERE legajo = ?", (LEGAJO_PRUEBA,)
    )
    conexion.commit()
    conexion.close()

    payload_reentrega = generar_payload_base(identificador_alumno=LEGAJO_PRUEBA)
    payload_reentrega["file"] = (
        BytesIO(b"program Hola3; begin end."),
        "parcial_v3.pas",
    )
    respuesta_http = cliente_api.post(
        "/upload", data=payload_reentrega, content_type="multipart/form-data"
    )

    assert respuesta_http.status_code == HTTP_OK

    conexion = sqlite3.connect(ruta_base_datos)
    cursor_activo = conexion.cursor()

    cursor_activo.execute(
        "SELECT reentrega_habilitada FROM alumnos WHERE legajo = ?", (LEGAJO_PRUEBA,)
    )
    assert cursor_activo.fetchone()[0] == 0

    cursor_activo.execute(
        "SELECT COUNT(*) FROM entregas WHERE legajo = ? AND es_activa = 1",
        (LEGAJO_PRUEBA,),
    )
    assert cursor_activo.fetchone()[0] == 1

    cursor_activo.execute(
        "SELECT COUNT(*) FROM entregas WHERE legajo = ?", (LEGAJO_PRUEBA,)
    )
    assert cursor_activo.fetchone()[0] == 2
    conexion.close()
