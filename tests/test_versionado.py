import io
import seep_config


def test_version_cliente_incompatible(cliente_pruebas):
    """
    Verifica que el servidor rechace con un código HTTP 426 (Upgrade Required)
    a cualquier cliente que intente enviar un examen con una versión desactualizada.
    """
    datos = {
        "apellidos": "Estudiante",
        "nombres": "Desactualizado",
        "identificador": "12345",
        "pin": cliente_pruebas.application.config["PIN"],
        "version": "0.1-antigua",  # Versión vieja simulada
        "file": (io.BytesIO(b"codigo obsolescente"), "examen.pas"),
    }

    respuesta = cliente_pruebas.post(
        "/upload", data=datos, content_type="multipart/form-data"
    )

    # El servidor debe exigir actualización de protocolo (426)
    assert (
        respuesta.status_code == 426
    ), f"Se esperaba código 426, se obtuvo {respuesta.status_code}"

    # Validamos que la respuesta contenga el JSON explicando el motivo
    datos_respuesta = respuesta.get_json()
    assert "error" in datos_respuesta
    assert "incompatible" in datos_respuesta["error"].lower()
