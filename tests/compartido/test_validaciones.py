import io
import pytest
import seep_config


@pytest.mark.parametrize(
    "nombre_archivo, modulo, codigo_esperado",
    [
        # --- Partición Válida: Imperativo (.pas) ---
        ("examen.pas", "imperativo", 200),
        ("EXAMEN.PAS", "imperativo", 200),
        # --- Partición Válida: Objetos (.zip) ---
        ("entrega.zip", "objetos", 200),
        ("ENTREGA.ZIP", "objetos", 200),
        # --- Partición Válida: Concurrente (rinfo, sin extensión) ---
        ("ejercicio_robot", "concurrente", 200),
        ("entrega_rinfo_final", "concurrente", 200),
        # --- Partición Inválida: Cruce de Módulos (Deben dar 400) ---
        ("entrega.zip", "imperativo", 400),
        ("examen.pas", "concurrente", 400),
        # --- Partición Inválida General (Deben dar 400) ---
        ("documento.pdf", "imperativo", 400),
        ("script.py", "objetos", 400),
        ("virus.exe", "concurrente", 400),
    ],
)
def test_particiones_extensiones(
    cliente_pruebas, nombre_archivo, modulo, codigo_esperado
):
    """
    Verifica las clases de equivalencia cruzando extensiones vs módulos.
    """
    app = cliente_pruebas.application

    # ¡LA CLAVE ESTÁ ACÁ! Simulamos que el docente configuró el servidor para este módulo
    app.config["MODULO"] = modulo

    datos = {
        "apellidos": "Lovelace",
        "nombres": "Ada",
        "identificador": "123",
        "pin": "0000",
        # Ya no hace falta mandar "modulo" acá
        "file": (io.BytesIO(b"contenido simulado"), nombre_archivo),
        "version": seep_config.VERSION_SEEP,
    }

    with app.test_client() as cliente:
        respuesta = cliente.post(
            "/upload", data=datos, content_type="multipart/form-data"
        )

    assert respuesta.status_code == codigo_esperado, (
        f"Fallo partición: archivo '{nombre_archivo}' en módulo '{modulo}'. "
        f"Esperaba {codigo_esperado} pero devolvió {respuesta.status_code}"
    )
