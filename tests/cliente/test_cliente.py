import pytest
from unittest.mock import patch, MagicMock
from cliente_alumno import AppAlumno


def test_b3_error_inesperado():
    """Prueba que un error genérico no rompa la interfaz por NameError (Bug B3)"""
    app = AppAlumno()
    app.mostrar_estado("Conectando con la PC del docente...", "#f1c40f")

    with patch("requests.get", side_effect=Exception("Falla_catastrofica_simulada")):
        app.enviar_red("127.0.0.1", "0000", "Perez", "Juan", "123", "dummy.pas")

        app.procesar_cola()
        app.update()

        texto_pantalla = app.lbl_estado.cget("text")


def test_b4_error_json_500():
    """Prueba que una caída del servidor (500 HTML) no rompa el cliente (Bug B4)"""
    app = AppAlumno()
    app.mostrar_estado("Conectando con la PC del docente...", "#f1c40f")

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json.side_effect = ValueError(
        "Excepción simulada al decodificar JSON"
    )

    with patch("requests.get"):
        with patch("requests.post", return_value=mock_response):
            with patch("builtins.open", MagicMock()):
                app.enviar_red("127.0.0.1", "0000", "Perez", "Juan", "123", "dummy.pas")

                app.procesar_cola()
                app.update()

                texto_pantalla = app.lbl_estado.cget("text")


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
