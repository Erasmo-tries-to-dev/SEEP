import threading
import os
import io
import servidor_docente


def test_sobrescritura_milisegundos(cliente_pruebas):
    """
    Verifica el Bug B1: Múltiples entregas en el mismo milisegundo
    no deben pisar el archivo en disco.
    """

    # 1. Configurar estado global necesario para el test
    servidor_docente.PIN_ACTUAL = "0000"
    app_configurada = cliente_pruebas.application

    # Simulamos que el docente eligió el módulo imperativo al arrancar
    app_configurada.config["MODULO"] = "imperativo"

    # 2. Definimos la función que simula a un alumno entregando
    def entregar_mock(numero):
        datos = {
            "apellidos": "Hacker",
            "nombres": f"Clon_{numero}",
            "identificador": f"0000{numero}",  # Corregido a "identificador"
            "pin": "0000",
            "file": (
                io.BytesIO(b"begin end."),
                f"examen_{numero}.pas",
            ),  # Corregido a "file"
        }

        # Cada hilo crea su propio cliente aislado
        with app_configurada.test_client() as cliente_hilo:
            cliente_hilo.post("/upload", data=datos, content_type="multipart/form-data")

    # 3. Lanzamos 5 hilos en paralelo para simular concurrencia extrema
    hilos = []
    for i in range(5):
        h = threading.Thread(target=entregar_mock, args=(i,))
        hilos.append(h)
        h.start()

    for h in hilos:
        h.join()

    # 4. VERIFICACIÓN (Asserts)
    carpeta_temp = app_configurada.config["CARPETA_ENTREGAS"]
    archivos_en_disco = [f for f in os.listdir(carpeta_temp) if f.endswith(".pas")]

    # Si el bug B1 está arreglado, tiene que haber exactamente 5 archivos en disco
    assert (
        len(archivos_en_disco) == 5
    ), f"Se esperaban 5 archivos, pero hay {len(archivos_en_disco)}"
