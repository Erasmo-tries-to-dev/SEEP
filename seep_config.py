"""
Módulo de configuración compartida para SEEP (Cliente y Servidor).
Define la única fuente de verdad para validaciones, constantes de red y límites.
"""

import hashlib
from typing import Any

PUERTO_API = 5000
MAX_TAMANO_MB = 1
MAX_TAMANO_BYTES = MAX_TAMANO_MB * 1024 * 1024
TIMEOUT_PING = 3
TIMEOUT_UPLOAD = 30  # Deberia ser razonable, puede bajarse.
VERSION_SEEP = "0.5.0"
TAMANO_BLOQUE_HASH: int = 4096


def calcular_hash(archivo: Any) -> str:
    """
    Calcula el hash SHA-256 de un archivo en memoria leyendo en bloques
    para no saturar la RAM con archivos grandes, y luego rebobina el puntero.
    """
    sha256_hash = hashlib.sha256()
    for bloque in iter(lambda: archivo.read(TAMANO_BLOQUE_HASH), b""):
        sha256_hash.update(bloque)
    archivo.seek(0)
    return sha256_hash.hexdigest()


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
