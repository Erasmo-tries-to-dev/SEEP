import os
import io


def test_entrega_con_csv_bloqueado(cliente_pruebas):
    """
    Verifica el Bug B2: Si el CSV está bloqueado por otro programa (ej. Excel),
    el servidor debe guardar el archivo del alumno igual y no devolver error 500.
    """
    # Extraemos la app ya configurada desde el fixture
    app = cliente_pruebas.application

    # 2. EL TRUCO PARA FORZAR EL ERROR
    # Creamos una carpeta con el nombre del CSV.
    # Al intentar hacer open(..., "a") sobre una carpeta, Windows tira PermissionError idéntico al de Excel.
    ruta_csv = app.config["ARCHIVO_CSV"]
    os.mkdir(ruta_csv)

    # 3. Simulamos a un alumno entregando
    datos = {
        "apellidos": "Hacker",
        "nombres": "CSV_Bloqueado",
        "identificador": "0000X",
        "pin": "0000",
        "file": (io.BytesIO(b"begin end."), "examen_bloqueado.pas"),
    }

    with app.test_client() as cliente:
        respuesta = cliente.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    # VERIFICACIONES

    # El servidor debe devolver 200 OK (no 500 Internal Server Error)
    assert (
        respuesta.status_code == 200
    ), f"Se esperaba 200, pero devolvió {respuesta.status_code}"

    # El archivo físico del parcial DEBE existir en disco a pesar del error del CSV
    carpeta_temp = app.config["CARPETA_ENTREGAS"]
    archivos_en_disco = [f for f in os.listdir(carpeta_temp) if f.endswith(".pas")]
    assert (
        len(archivos_en_disco) == 1
    ), "El parcial no se guardó en el disco por culpa del CSV"
