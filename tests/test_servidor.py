import os
import sqlite3
from io import BytesIO

import pytest

import seep_config
import sys

# Cambiar esto, es horrible, pero es necesario para que los tests puedan importar el módulo del servidor.
ruta_servidor = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "servidor_docente")
)
sys.path.insert(0, ruta_servidor)

from api import crear_app
from persistencia import _crear_esquema


@pytest.fixture
def entorno_prueba(tmp_path):
    """Fixture que levanta una BD SQLite en memoria/disco temporal y configura Flask."""
    ruta_db = tmp_path / "test_registro.db"
    carpeta_entregas = tmp_path / "entregas"

    # 1. Preparar Base de Datos con esquema
    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()
    _crear_esquema(cursor)
    cursor.execute(
        "INSERT INTO configuracion (pin, modulo, fecha, turno, aula) VALUES (?, ?, ?, ?, ?)",
        ("1234", "imperativo", "20261013", "TA", "LAB3"),
    )
    conn.commit()
    conn.close()

    # 2. Levantar Application Factory
    app = crear_app(
        modulo_elegido="imperativo",
        pin_fijo="1234",
        carpeta_elegida=str(carpeta_entregas),
        ruta_db=str(ruta_db),
    )
    app.config["TESTING"] = True

    return app.test_client(), str(ruta_db)


def generar_payload_base(pin="1234", identificador="12345/6"):
    """Helper para generar un formulario multipart válido."""
    return {
        "version": seep_config.VERSION_SEEP,
        "pin": pin,
        "apellidos": "Perez",
        "nombres": "Juan",
        "identificador": identificador,
        "hostname": "PC-TEST",
        "file": (BytesIO(b"program Hola; begin end."), "parcial.pas"),
    }


def test_ping_version_correcta(entorno_prueba):
    cliente, _ = entorno_prueba
    respuesta = cliente.get(f"/ping?version={seep_config.VERSION_SEEP}")
    assert respuesta.status_code == 200
    assert respuesta.json["status"] == "ok"


def test_ping_version_incorrecta(entorno_prueba):
    cliente, _ = entorno_prueba
    respuesta = cliente.get("/ping?version=0.0.1")
    assert respuesta.status_code == 426
    assert "incompatible" in respuesta.json["error"]


def test_upload_pin_incorrecto(entorno_prueba):
    cliente, _ = entorno_prueba
    payload = generar_payload_base(pin="9999")

    respuesta = cliente.post(
        "/upload", data=payload, content_type="multipart/form-data"
    )
    assert respuesta.status_code == 403
    assert "PIN incorrecto" in respuesta.json["error"]


def test_upload_entrega_nueva_exitosa(entorno_prueba):
    cliente, ruta_db = entorno_prueba
    payload = generar_payload_base()

    respuesta = cliente.post(
        "/upload", data=payload, content_type="multipart/form-data"
    )

    assert respuesta.status_code == 200
    assert "comprobante" in respuesta.json

    # Verificar persistencia
    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()
    cursor.execute("SELECT legajo FROM alumnos WHERE legajo = '12345-6'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT es_activa FROM entregas WHERE legajo = '12345-6'")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_upload_reentrega_bloqueada(entorno_prueba):
    cliente, _ = entorno_prueba

    # 1. Primera entrega (exitosa)
    cliente.post(
        "/upload", data=generar_payload_base(), content_type="multipart/form-data"
    )

    # 2. Segunda entrega (mismo identificador, debe fallar)
    payload_reentrega = generar_payload_base()
    payload_reentrega["file"] = (
        BytesIO(b"program Hola2; begin end."),
        "parcial_v2.pas",
    )

    respuesta = cliente.post(
        "/upload", data=payload_reentrega, content_type="multipart/form-data"
    )

    assert respuesta.status_code == 403
    assert "Ya registramos una entrega tuya" in respuesta.json["error"]


def test_upload_reentrega_habilitada_y_consumida(entorno_prueba):
    cliente, ruta_db = entorno_prueba
    legajo = "12345-6"

    # 1. Primera entrega
    cliente.post(
        "/upload",
        data=generar_payload_base(identificador=legajo),
        content_type="multipart/form-data",
    )

    # 2. Docente habilita la reentrega (Simulando la interfaz)
    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE alumnos SET reentrega_habilitada = 1 WHERE legajo = ?", (legajo,)
    )
    conn.commit()
    conn.close()

    # 3. Alumno reentrega
    payload_reentrega = generar_payload_base(identificador=legajo)
    payload_reentrega["file"] = (
        BytesIO(b"program Hola3; begin end."),
        "parcial_v3.pas",
    )
    respuesta = cliente.post(
        "/upload", data=payload_reentrega, content_type="multipart/form-data"
    )

    assert respuesta.status_code == 200

    # 4. Verificar que el permiso se consumió y el historial se actualizó
    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT reentrega_habilitada FROM alumnos WHERE legajo = ?", (legajo,)
    )
    assert cursor.fetchone()[0] == 0  # Permiso consumido

    cursor.execute(
        "SELECT COUNT(*) FROM entregas WHERE legajo = ? AND es_activa = 1", (legajo,)
    )
    assert cursor.fetchone()[0] == 1  # Solo la última entrega está activa

    cursor.execute("SELECT COUNT(*) FROM entregas WHERE legajo = ?", (legajo,))
    assert cursor.fetchone()[0] == 2  # Historial inmutable tiene 2 registros
    conn.close()
