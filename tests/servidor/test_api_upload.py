import io
import pytest
import seep_config
from unittest.mock import patch


@pytest.fixture
def datos_base():
    """Fixture local con los datos mínimos válidos para no repetirlos."""
    return {
        "apellidos": "Turing",
        "nombres": "Alan",
        "identificador": "999",
        "pin": "0000",
        "version": seep_config.VERSION_SEEP,
    }


# --- 1. CAMINOS TRISTES: Formulario Incompleto ---
@pytest.mark.parametrize(
    "campo_a_eliminar, codigo_esperado",
    [
        ("apellidos", 400),
        ("nombres", 400),
        ("identificador", 400),
        ("pin", 400),
        ("file", 400),
    ],
)
def test_upload_rechaza_datos_incompletos(
    cliente_pruebas, datos_base, campo_a_eliminar, codigo_esperado
):
    """Verifica que el servidor aborte con 400 si falta CUALQUIER campo obligatorio."""
    app = cliente_pruebas.application
    app.config["MODULO"] = "imperativo"

    datos = datos_base.copy()

    # Eliminamos el campo que toca en esta partición
    if campo_a_eliminar != "file":
        del datos[campo_a_eliminar]
        datos["file"] = (io.BytesIO(b"codigo"), "examen.pas")
    # Si el campo a eliminar es "file", simplemente no lo agregamos al diccionario

    with app.test_client() as cliente:
        respuesta = cliente.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    assert (
        respuesta.status_code == codigo_esperado
    ), f"El servidor no rechazó la falta del campo '{campo_a_eliminar}'"


# --- 2. CAMINOS TRISTES: Autenticación ---
def test_upload_rechaza_pin_incorrecto(cliente_pruebas, datos_base):
    """Verifica el rechazo explícito (HTTP 403) ante un PIN inválido."""
    app = cliente_pruebas.application
    app.config["MODULO"] = "imperativo"

    datos = datos_base.copy()
    datos["pin"] = "PIN_FALSO"
    datos["file"] = (io.BytesIO(b"codigo"), "examen.pas")

    with app.test_client() as cliente:
        respuesta = cliente.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    assert respuesta.status_code == 403
    assert "PIN incorrecto" in respuesta.get_json()["error"]


# --- 3. VALORES LÍMITE (Boundary Values): Tamaño de Archivo ---
@pytest.mark.parametrize(
    "tamano_bytes, codigo_esperado",
    [
        (0, 200),  # Límite Inferior: Archivo vacío pero válido
        (1024, 200),  # Valor Normal: 1 KB
        (
            5 * 1024 * 1024 + 1024,
            413,
        ),  # Límite Superior Excedido: 5 MB + 1 KB (Debe dar HTTP 413 Payload Too Large)
    ],
)
def test_upload_limites_tamano_archivo(
    cliente_pruebas, datos_base, tamano_bytes, codigo_esperado
):
    """
    Verifica cómo responde el servidor en los límites matemáticos del tamaño del archivo.
    Flask intercepta nativamente los archivos > MAX_CONTENT_LENGTH con un HTTP 413.
    """
    app = cliente_pruebas.application
    app.config["MODULO"] = "imperativo"

    # Aseguramos que el límite en el entorno de pruebas sea exactamente 5 MB
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    datos = datos_base.copy()
    # Generamos un archivo falso en memoria con el tamaño exacto en bytes
    archivo_simulado = io.BytesIO(b"0" * tamano_bytes)
    datos["file"] = (archivo_simulado, "examen.pas")

    with app.test_client() as cliente:
        respuesta = cliente.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    assert respuesta.status_code == codigo_esperado, (
        f"Fallo en valor límite: Archivo de {tamano_bytes} bytes. "
        f"Esperaba {codigo_esperado} pero devolvió {respuesta.status_code}"
    )


# --- 4. CAMINOS TRISTES: Fallo Crítico del Sistema (500) ---
def test_upload_excepcion_json_500(cliente_pruebas, datos_base):
    """
    Verifica el Bug B6: Si ocurre un error interno grave (ej. disco lleno),
    el servidor debe devolver un JSON estructurado con código 500, no crashear con HTML.
    """
    app = cliente_pruebas.application
    app.config["MODULO"] = "imperativo"

    datos = datos_base.copy()
    datos["file"] = (io.BytesIO(b"codigo"), "examen.pas")

    # Simulamos que el disco duro está lleno al intentar guardar
    with patch(
        "werkzeug.datastructures.FileStorage.save",
        side_effect=OSError("No hay espacio en disco"),
    ):
        with app.test_client() as cliente:
            respuesta = cliente.post(
                "/upload", data=datos, content_type="multipart/form-data"
            )

    assert (
        respuesta.status_code == 500
    ), f"Se esperaba 500, se obtuvo {respuesta.status_code}"
    assert (
        respuesta.is_json
    ), "Bug B6 regresión: El servidor devolvió HTML crudo en lugar de un JSON"
    assert (
        "error" in respuesta.get_json()
    ), "El JSON devuelto no contiene el mensaje de error"
    assert "Error interno al guardar" in respuesta.get_json()["error"]
