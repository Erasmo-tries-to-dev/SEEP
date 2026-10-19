"""
Módulo de Configuración Compartida para SEEP (Cliente y Servidor).
Define la única fuente de verdad para validaciones, constantes de red y límites.
Centraliza el contrato de Auto-Discovery (Faro UDP) para mantener coherencia entre ambos extremos.
"""

import hashlib
from typing import Any, Dict, List, Tuple

# -----------------------------------------------------------------------------
# CONSTANTES DE RED Y AUTO-DISCOVERY (CONTRATO COMPARTIDO)
# -----------------------------------------------------------------------------
PUERTO_API: int = 5000
PUERTO_BEACON: int = 5555
IDENTIFICADOR_BEACON: str = "SEEP_BEACON"
CODIFICACION_TEXTO: str = "utf-8"
TAMANO_BUFFER_UDP: int = 1024

TIMEOUT_PING: int = 3
TIMEOUT_UPLOAD: int = 30

# -----------------------------------------------------------------------------
# CONSTANTES DE SISTEMA Y RESTRICCIONES
# -----------------------------------------------------------------------------
VERSION_SEEP: str = "0.7.0"
MAX_TAMANO_MB: int = 1
MAX_TAMANO_BYTES: int = MAX_TAMANO_MB * 1024 * 1024
TAMANO_BLOQUE_HASH: int = 4096

# Definición de Módulos Académicos
MODULO_IMPERATIVO: str = "imperativo"
MODULO_OBJETOS: str = "objetos"
MODULO_CONCURRENTE: str = "concurrente"

MODULOS_SOPORTADOS: List[str] = [
    MODULO_IMPERATIVO,
    MODULO_OBJETOS,
    MODULO_CONCURRENTE,
]

# Definición de Extensiones
EXT_PASCAL: str = ".pas"
EXT_ZIP: str = ".zip"

# Configuración de exploración de archivos para las interfaces GUI
FILTROS_ARCHIVO_POR_MODULO: Dict[str, List[Tuple[str, str]]] = {
    MODULO_IMPERATIVO: [("Archivos Pascal", f"*{EXT_PASCAL}")],
    MODULO_OBJETOS: [("Archivos ZIP", f"*{EXT_ZIP}")],
}
FILTRO_ARCHIVO_POR_DEFECTO: List[Tuple[str, str]] = [("Todos los archivos", "*.*")]


# -----------------------------------------------------------------------------
# LÓGICA DE UTILIDAD COMPARTIDA
# -----------------------------------------------------------------------------
def calcular_hash(archivo_binario: Any) -> str:
    """
    Calcula el hash SHA-256 de un archivo en memoria.

    Args:
        archivo_binario (Any): Objeto archivo (File-like object) en modo lectura binaria.

    Returns:
        str: El checksum SHA-256 en formato hexadecimal.

    Notes:
        RATIONALE: Se lee el archivo en bloques (chunks) de tamaño TAMANO_BLOQUE_HASH
        para no saturar la memoria RAM en caso de recibir entregas de gran tamaño,
        y luego se rebobina el puntero (seek) para permitir su guardado físico.
    """
    hash_sha256 = hashlib.sha256()
    for bloque_bytes in iter(lambda: archivo_binario.read(TAMANO_BLOQUE_HASH), b""):
        hash_sha256.update(bloque_bytes)

    archivo_binario.seek(0)
    return hash_sha256.hexdigest()


def validar_extension(nombre_archivo: str, modulo_evaluado: str) -> Tuple[bool, str]:
    """
    Verifica que el archivo entregado tenga la extensión obligatoria según el módulo.

    Args:
        nombre_archivo (str): Nombre completo del archivo enviado por el alumno.
        modulo_evaluado (str): Nombre del módulo académico actualmente en evaluación.

    Returns:
        Tuple[bool, str]: Tupla que indica el éxito de la validación y la extensión final
                          (o el mensaje de error explicativo en caso de rechazo).
    """
    nombre_minusculas = nombre_archivo.lower()
    modulo_normalizado = modulo_evaluado.lower()

    if modulo_normalizado == MODULO_IMPERATIVO:
        if not nombre_minusculas.endswith(EXT_PASCAL):
            return False, "Módulo Imperativo: Solo se permiten archivos .pas"
        return True, EXT_PASCAL

    if modulo_normalizado == MODULO_OBJETOS:
        if not nombre_minusculas.endswith(EXT_ZIP):
            return False, "Módulo Objetos: Solo se permiten archivos .zip"
        return True, EXT_ZIP

    if modulo_normalizado == MODULO_CONCURRENTE:
        if "." in nombre_minusculas:
            mensaje_error_concurrente = "Módulo Concurrente: Seleccioná el archivo generado por R-Info (sin extensión)"
            return False, mensaje_error_concurrente
        return True, ""

    return False, "Módulo desconocido"
