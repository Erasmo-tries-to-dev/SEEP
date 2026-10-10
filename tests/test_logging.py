import os
import io
import sys
import logging
import subprocess


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
        # SOLUCIÓN 1: Usar io.BytesIO para que Flask lo reconozca como archivo real
        "file": (io.BytesIO(b"codigo"), "examen.pas"),
    }

    with caplog.at_level(logging.WARNING):
        respuesta = cliente_pruebas.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    assert respuesta.status_code == 403
    assert "PIN incorrecto ingresado" in caplog.text


def test_cliente_crea_archivo_log_fisico():
    """
    Verifica que la configuración del cliente efectivamente haya
    creado el archivo seep_cliente.log en el disco.
    """
    # Borramos el archivo si ya existía de pruebas anteriores
    if os.path.exists("seep_cliente.log"):
        os.remove("seep_cliente.log")

    # Importamos el cliente y forzamos un mensaje de log para simular actividad,
    # ya que al importarlo no arranca la interfaz gráfica automáticamente.
    comando = "import cliente_alumno; cliente_alumno.logging.info('Prueba de escritura de log')"
    subprocess.run([sys.executable, "-c", comando], capture_output=True)

    assert os.path.exists(
        "seep_cliente.log"
    ), "El archivo seep_cliente.log no se generó."

    with open("seep_cliente.log", "r", encoding="utf-8") as f:
        contenido = f.read()

    assert len(contenido) > 0, "El archivo log se creó pero está vacío."
    assert "Prueba de escritura de log" in contenido, "El log no registró el mensaje."
