import threading
import os
import io
import seep_config


def test_sobrescritura_milisegundos(cliente_pruebas):
    """
    Verifica el Bug B1: Múltiples entregas en el mismo milisegundo
    no deben pisar el archivo en disco.
    """

    app = cliente_pruebas.application

    def entregar_mock(numero):
        datos = {
            "apellidos": "Hacker",
            "nombres": f"Clon_{numero}",
            "identificador": f"0000{numero}",
            "pin": "0000",
            "version": seep_config.VERSION_SEEP,
            "file": (
                io.BytesIO(b"begin end."),
                f"examen_{numero}.pas",
            ),
        }

        with app.test_client() as cliente_hilo:
            cliente_hilo.post("/upload", data=datos, content_type="multipart/form-data")

    hilos = []
    for i in range(5):
        h = threading.Thread(target=entregar_mock, args=(i,))
        hilos.append(h)
        h.start()

    for h in hilos:
        h.join()

    carpeta_temp = app.config["CARPETA_ENTREGAS"]
    archivos_en_disco = [f for f in os.listdir(carpeta_temp) if f.endswith(".pas")]

    assert (
        len(archivos_en_disco) == 5
    ), f"Se esperaban 5 archivos, pero hay {len(archivos_en_disco)}"
