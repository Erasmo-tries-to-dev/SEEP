"""
Módulo de configuración compartida para SEEP (Cliente y Servidor).
Define la única fuente de verdad para validaciones, constantes de red y límites.
"""

PUERTO_API = 5000
MAX_TAMANO_MB = 1
MAX_TAMANO_BYTES = MAX_TAMANO_MB * 1024 * 1024
TIMEOUT_PING = 3
TIMEOUT_UPLOAD = 10


def validar_extension(nombre_archivo, modulo):
    """
    Verifica que el archivo entregado tenga la extensión correcta según el módulo evaluado.
    Retorna una tupla: (es_valido, extension_o_mensaje_de_error).
    """
    nombre_lower = nombre_archivo.lower()
    modulo = modulo.lower()  # Normalizamos para que coincida entre cliente y servidor

    if modulo == "imperativo":
        if not nombre_lower.endswith(".pas"):
            return False, "Módulo Imperativo: Solo se permiten archivos .pas"
        return True, ".pas"
    elif modulo == "objetos":
        if not nombre_lower.endswith(".zip"):
            return False, "Módulo Objetos: Solo se permiten archivos .zip"
        return True, ".zip"
    elif modulo == "concurrente":
        if "." in nombre_lower:
            return (
                False,
                "Módulo Concurrente: Seleccioná el archivo generado por R-Info (sin extensión)",
            )
        return True, ""

    return False, "Módulo desconocido"
