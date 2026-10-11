import os
import io
import sys
import logging
import subprocess
import seep_config


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
