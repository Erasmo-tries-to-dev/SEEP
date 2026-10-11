import os
import io
import seep_config
import threading
import sys
import logging
import subprocess


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
        "version": seep_config.VERSION_SEEP,
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


def test_servidor_loggea_pin_incorrecto(cliente_pruebas, caplog):
    """
    Verifica que el servidor registre un WARNING formal en el sistema
    cuando un alumno intenta entregar con un PIN falso.
    """
    datos = {
        "apellidos": "Turing",
        "nombres": "Alan",
        "identificador": "999",
        "pin": "PIN_TOTALMENTE_FALSO",
        "file": (io.BytesIO(b"codigo"), "examen.pas"),
        "version": seep_config.VERSION_SEEP,
    }

    with caplog.at_level(logging.WARNING):
        respuesta = cliente_pruebas.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    assert respuesta.status_code == 403
    assert "PIN incorrecto ingresado" in caplog.text


def test_cliente_loggea_errores_en_archivo_fisico():
    """
    Verifica que la lógica del cliente efectivamente escriba los
    eventos y advertencias reales de la interfaz en el log físico.
    """
    if os.path.exists("seep_cliente.log"):
        os.remove("seep_cliente.log")

    # Armamos un script que simula el comportamiento de la interfaz
    script = """
import sys
import os
# Aseguramos que la raíz del proyecto esté en el path para que encuentre el módulo
sys.path.insert(0, os.path.abspath(os.getcwd()))
import cliente_alumno

# 1. Al crear la app, el __init__ debe loggear automáticamente "Iniciando aplicación..."
app = cliente_alumno.AppAlumno()

# 2. Simulamos que el alumno intentó subir un archivo prohibido
app.marcar_error_archivo("Simulación: El archivo pesa más de 1MB")
"""

    # Ejecutamos el script capturando la salida y los errores
    resultado = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )

    # Si el archivo no existe, ahora el assert nos va a imprimir el error exacto que dio Python
    assert os.path.exists("seep_cliente.log"), (
        f"El archivo seep_cliente.log no se generó.\n\n"
        f"--- STDOUT (Consola) ---\n{resultado.stdout}\n"
        f"--- STDERR (Errores) ---\n{resultado.stderr}"
    )

    with open("seep_cliente.log", "r", encoding="utf-8") as f:
        contenido = f.read()

    # Verificamos que los logs reales de negocio del cliente estén en el archivo
    assert (
        "Iniciando aplicación Cliente Alumno SEEP." in contenido
    ), "Falta el log de inicialización."
    assert (
        "Validación de archivo fallida: Simulación: El archivo pesa más de 1MB"
        in contenido
    ), "Falta el log del error de validación."
