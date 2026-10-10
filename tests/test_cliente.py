import pytest
from unittest.mock import patch, MagicMock
from cliente_alumno import AppAlumno


def test_b3_error_inesperado():
    """Prueba que un error genérico no rompa la interfaz por NameError (Bug B3)"""
    app = AppAlumno()
    app.mostrar_estado("Conectando con la PC del docente...", "#f1c40f")

    # Simulamos que la librería requests tira un error crudo
    with patch("requests.get", side_effect=Exception("Falla_catastrofica_simulada")):
        app.enviar_red("127.0.0.1", "0000", "Perez", "Juan", "123", "dummy.pas")
        app.update()  # Forzamos a Tkinter a procesar el lambda

        # VERIFICACIÓN VISUAL
        texto_pantalla = app.lbl_estado.cget("text")

        app.destroy()

        # Si el bug B3 existe, el texto se queda en "Conectando...". Si está arreglado, debe decir el error.
        assert (
            "Falla_catastrofica_simulada" in texto_pantalla
        ), "Bug B3: La interfaz gráfica no actualizó el mensaje de error."


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
                app.update()

                texto_pantalla = app.lbl_estado.cget("text")
                app.destroy()

                assert (
                    "HTTP 500" in texto_pantalla
                ), "Bug B4: El cliente no supo manejar una respuesta no-JSON del servidor."
