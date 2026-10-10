import io


def test_b5_extensiones_mayusculas(cliente_pruebas):
    """
    Verifica el Bug B5: El servidor debe aceptar extensiones válidas
    independientemente de si están en mayúsculas o minúsculas.
    """

    # Extraemos la app ya configurada desde el fixture
    app = cliente_pruebas.application

    datos = {
        "apellidos": "Lovelace",
        "nombres": "Ada",
        "identificador": "123",
        "pin": "0000",
        # Enviamos el archivo con la extensión en mayúsculas
        "file": (io.BytesIO(b"begin end."), "EXAMEN.PAS"),
    }

    with app.test_client() as cliente:
        respuesta = cliente.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    # Si el bug existe, el servidor devuelve 400 Bad Request
    assert (
        respuesta.status_code == 200
    ), f"Bug B5: El servidor rechazó una extensión válida en mayúsculas. Código: {respuesta.status_code}"
