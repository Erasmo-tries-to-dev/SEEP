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
