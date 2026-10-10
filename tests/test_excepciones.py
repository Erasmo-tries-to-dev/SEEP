import io
from unittest.mock import patch
import servidor_docente


def test_b6_excepcion_json_500(cliente_pruebas):
    """
    Verifica el Bug B6: Si ocurre un error interno grave (ej. disco lleno),
    el servidor debe devolver un JSON con código 500, no un HTML.
    """
    servidor_docente.PIN_ACTUAL = "0000"
    app = cliente_pruebas.application
    app.config["MODULO"] = "imperativo"

    datos = {
        "apellidos": "Turing",
        "nombres": "Alan",
        "identificador": "999",
        "pin": "0000",
        "file": (io.BytesIO(b"codigo"), "examen.pas"),
    }

    # Simulamos que el disco duro está lleno y el sistema operativo rechaza el guardado
    with patch(
        "werkzeug.datastructures.FileStorage.save",
        side_effect=OSError("No hay espacio en disco"),
    ):
        respuesta = cliente_pruebas.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    # El servidor debe reconocer que falló (500) pero devolver un JSON, no romper la app
    assert (
        respuesta.status_code == 500
    ), f"Se esperaba 500, se obtuvo {respuesta.status_code}"
    assert (
        respuesta.is_json
    ), "Bug B6: El servidor devolvió HTML crudo en lugar de un JSON"
    assert "error" in respuesta.json, "El JSON devuelto no contiene el mensaje de error"
