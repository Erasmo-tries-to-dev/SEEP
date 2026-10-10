import pytest
import os
import tempfile
from servidor_docente import app


@pytest.fixture
def cliente_pruebas():
    # Creamos un directorio temporal para no ensuciar el disco
    with tempfile.TemporaryDirectory() as carpeta_temp:
        # Configuramos Flask en modo testing
        app.config["TESTING"] = True
        app.config["CARPETA_ENTREGAS"] = carpeta_temp
        app.config["ARCHIVO_CSV"] = os.path.join(carpeta_temp, "registro_test.csv")

        # Le decimos a la app de Flask que nos dé un "cliente" falso para hacerle peticiones
        with app.test_client() as client:
            yield client
