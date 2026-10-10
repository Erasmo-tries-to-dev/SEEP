import threading
import os
import io


def test_sobrescritura_milisegundos(cliente_pruebas):
    """
    Verifica el Bug B1: Múltiples entregas en el mismo milisegundo
    no deben pisar el archivo en disco.
    """

    # Extraemos la app ya configurada desde el fixture
    app = cliente_pruebas.application

    def entregar_mock(numero):
        datos = {
            "apellidos": "Hacker",
            "nombres": f"Clon_{numero}",
            "identificador": f"0000{numero}",
            "pin": "0000",
            "file": (
                io.BytesIO(b"begin end."),
                f"examen_{numero}.pas",
            ),
        }

        # Usamos app.test_client() en lugar de app_configurada
        with app.test_client() as cliente_hilo:
            cliente_hilo.post("/upload", data=datos, content_type="multipart/form-data")

    # Lanzamos 5 hilos en paralelo para simular concurrencia extrema
    hilos = []
    for i in range(5):
        h = threading.Thread(target=entregar_mock, args=(i,))
        hilos.append(h)
        h.start()

    for h in hilos:
        h.join()

    # VERIFICACIÓN (Asserts) usando app.config
    carpeta_temp = app.config["CARPETA_ENTREGAS"]
    archivos_en_disco = [f for f in os.listdir(carpeta_temp) if f.endswith(".pas")]

    # Si el bug B1 está arreglado, tiene que haber exactamente 5 archivos en disco
    assert (
        len(archivos_en_disco) == 5
    ), f"Se esperaban 5 archivos, pero hay {len(archivos_en_disco)}"
