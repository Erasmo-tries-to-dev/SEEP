import pytest
import seep_config


@pytest.mark.parametrize(
    "version_enviada, codigo_esperado",
    [
        # --- Partición Válida: Paridad estricta ---
        (seep_config.VERSION_SEEP, 200),
        # --- Particiones Inválidas (Deben dar 426 Upgrade Required) ---
        ("v0.1.0-antigua", 426),
        ("v99.9.9-futura", 426),
        ("", 426),
    ],
)
def test_particiones_version_ping(cliente_pruebas, version_enviada, codigo_esperado):
    """
    Verifica que el endpoint /ping funcione como handshake oficial,
    exigiendo la versión correcta antes de permitir operaciones pesadas.
    """
    app = cliente_pruebas.application

    with app.test_client() as cliente:
        # Hacemos un GET al endpoint ping pasando la versión como query parameter
        respuesta = cliente.get(f"/ping?version={version_enviada}")

    assert respuesta.status_code == codigo_esperado, (
        f"Fallo en handshake /ping con versión '{version_enviada}'. "
        f"Esperaba {codigo_esperado} pero devolvió {respuesta.status_code}"
    )

    if codigo_esperado == 426:
        datos_respuesta = respuesta.get_json()
        assert "error" in datos_respuesta
        assert "incompatible" in datos_respuesta["error"].lower()
