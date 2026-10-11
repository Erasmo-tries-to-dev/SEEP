import os
import io
import csv
import logging
import threading
import seep_config


def test_camino_feliz_persistencia_total(cliente_pruebas, caplog):
    """
    Camino Feliz End-to-End: Verifica que una entrega válida dispare los 3 efectos
    secundarios esperados: Guardado del archivo, registro en CSV y logueo de auditoría.
    """
    app = cliente_pruebas.application
    app.config["MODULO"] = "imperativo"

    datos = {
        "apellidos": "Lovelace",
        "nombres": "Ada",
        "identificador": "111",
        "pin": "0000",
        "version": seep_config.VERSION_SEEP,
        "file": (io.BytesIO(b"begin writeln('Hola'); end."), "examen.pas"),
    }

    with caplog.at_level(logging.INFO):
        with app.test_client() as cliente:
            respuesta = cliente.post(
                "/upload", data=datos, content_type="multipart/form-data"
            )

    # 1. Validación HTTP
    assert respuesta.status_code == 200

    # 2. Validación de FileSystem (El archivo existe y filtramos el CSV)
    carpeta = app.config["CARPETA_ENTREGAS"]

    # Buscamos específicamente archivos que tengan el apellido de la alumna
    archivos_entrega = [f for f in os.listdir(carpeta) if "Lovelace" in f]
    assert (
        len(archivos_entrega) == 1
    ), "No se encontró exactamente 1 archivo para Lovelace"

    nombre_archivo_final = archivos_entrega[0]
    assert "Lovelace_Ada_111" in nombre_archivo_final

    # 3. Validación de CSV (Se agregó la fila con los datos correctos)
    ruta_csv = app.config["ARCHIVO_CSV"]
    assert os.path.exists(ruta_csv), "El archivo CSV no se creó"

    with open(ruta_csv, "r", encoding="utf-8") as f:
        # ¡IMPORTANTE! Agregar el delimiter=";" acá:
        lector = csv.reader(f, delimiter=";")
        filas = list(lector)
        ultima_fila = filas[-1]

    assert "Lovelace" in ultima_fila
    assert "111" in ultima_fila
    assert (
        nombre_archivo_final in ultima_fila
    )  # El nombre final del archivo debe coincidir con el anotado

    # 4. Validación de Logger (Dejó rastros de auditoría)
    assert "NUEVA ENTREGA: Lovelace Ada" in caplog.text


def test_entrega_con_csv_bloqueado(cliente_pruebas):
    """
    Verifica el Bug B2: Si el CSV está bloqueado por otro programa (ej. Excel),
    el servidor debe guardar el archivo del alumno igual y no devolver error 500.
    """
    app = cliente_pruebas.application
    app.config["MODULO"] = "imperativo"

    # Forzamos el PermissionError de Windows creando una carpeta en lugar de un archivo
    ruta_csv = app.config["ARCHIVO_CSV"]
    os.mkdir(ruta_csv)

    datos = {
        "apellidos": "Hacker",
        "nombres": "CSV_Bloqueado",
        "identificador": "0000X",
        "pin": "0000",
        "version": seep_config.VERSION_SEEP,
        "file": (io.BytesIO(b"begin end."), "examen_bloqueado.pas"),
    }

    with app.test_client() as cliente:
        respuesta = cliente.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    # El servidor debe absorber el error del CSV y devolver 200 OK
    assert (
        respuesta.status_code == 200
    ), f"Se esperaba 200, pero devolvió {respuesta.status_code}"

    # El parcial DEBE estar en disco a pesar de la falla del CSV
    carpeta_temp = app.config["CARPETA_ENTREGAS"]
    archivos_en_disco = [f for f in os.listdir(carpeta_temp) if f.endswith(".pas")]
    assert (
        len(archivos_en_disco) == 1
    ), "El parcial no se guardó en el disco por culpa del CSV"


def test_sobrescritura_milisegundos(cliente_pruebas):
    """
    Verifica el Bug B1: Múltiples entregas en el mismo milisegundo
    no deben pisar el archivo en disco (deben generar timestamps/hashes únicos).
    """
    app = cliente_pruebas.application
    app.config["MODULO"] = "imperativo"

    def entregar_mock(numero):
        datos = {
            "apellidos": "Hacker",
            "nombres": f"Clon_{numero}",
            "identificador": f"0000{numero}",
            "pin": "0000",
            "version": seep_config.VERSION_SEEP,
            "file": (io.BytesIO(b"begin end."), f"examen_{numero}.pas"),
        }

        with app.test_client() as cliente_hilo:
            cliente_hilo.post("/upload", data=datos, content_type="multipart/form-data")

    # Bombardeamos el servidor con 5 hilos simultáneos
    hilos = []
    for i in range(5):
        h = threading.Thread(target=entregar_mock, args=(i,))
        hilos.append(h)
        h.start()

    for h in hilos:
        h.join()

    carpeta_temp = app.config["CARPETA_ENTREGAS"]
    archivos_en_disco = [f for f in os.listdir(carpeta_temp) if f.endswith(".pas")]

    # Si hay menos de 5 archivos, hubo colisión y sobrescritura
    assert (
        len(archivos_en_disco) == 5
    ), f"Se esperaban 5 archivos, pero hay {len(archivos_en_disco)}"
