import pytest
import os
import tempfile
from servidor_docente import crear_app


@pytest.fixture
def cliente_pruebas():
    # Creamos un directorio temporal para no ensuciar el disco
    with tempfile.TemporaryDirectory() as carpeta_temp:

        # Usamos la Factory para crear una app aislada.
        # Le inyectamos "imperativo" como módulo por defecto y "0000" como PIN fijo para los tests.
        app = crear_app(
            modulo_elegido="imperativo", pin_fijo="0000", carpeta_elegida=carpeta_temp
        )

        app.config["TESTING"] = True
        app.config["ARCHIVO_CSV"] = os.path.join(carpeta_temp, "registro_test.csv")

        # Le decimos a la app de Flask que nos dé un "cliente" falso para hacerle peticiones
        with app.test_client() as client:
            yield client
