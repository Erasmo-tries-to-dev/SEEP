"""
Módulo de persistencia de SEEP-Servidor Docente.
Aísla toda la interacción con SQLite mediante el patrón Repositorio.
Garantiza transacciones atómicas (commit/rollback) y el cierre seguro de conexiones.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, List, Optional, Tuple

# -----------------------------------------------------------------------------
# CONSTANTES DE ESTADOS DE BASE DE DATOS
# -----------------------------------------------------------------------------
PERMISO_DENEGADO: int = 0
PERMISO_HABILITADO: int = 1

ENTREGA_INACTIVA: int = 0
ENTREGA_ACTIVA: int = 1


# -----------------------------------------------------------------------------
# MOTOR DE TRANSACCIONES
# -----------------------------------------------------------------------------


@contextmanager
def conexion_db(ruta_db: str) -> Iterator[sqlite3.Cursor]:
    """
    Maneja la conexión a SQLite garantizando commit automático en caso de éxito,
    rollback en caso de excepción, y el cierre incondicional de la conexión.
    Actúa como un Gestor de Contexto (utilizable con la sentencia 'with').
    """
    conn = sqlite3.connect(ruta_db)
    try:
        # El bloque 'with conn' maneja la transacción ACID (commit o rollback)
        with conn:
            yield conn.cursor()
    finally:
        # El bloque 'finally' asegura que no queden bases de datos "bloqueadas"
        conn.close()


def _crear_esquema(cursor: sqlite3.Cursor) -> None:
    """Crea las tablas estructurales de una base de datos de sesión nueva."""
    cursor.execute("""
        CREATE TABLE configuracion (
            pin TEXT, 
            modulo TEXT, 
            fecha TEXT, 
            turno TEXT, 
            aula TEXT
        )
    """)
    cursor.execute(f"""
        CREATE TABLE alumnos (
            legajo TEXT PRIMARY KEY, 
            apellidos TEXT, 
            nombres TEXT,
            ip_vinculada TEXT, 
            hostname_vinculado TEXT, 
            reentrega_habilitada INTEGER DEFAULT {PERMISO_DENEGADO}
        )
    """)
    cursor.execute(f"""
        CREATE TABLE entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            legajo TEXT, 
            timestamp DATETIME,
            nombre_archivo TEXT, 
            hash_archivo TEXT, 
            codigo_comprobante TEXT,
            ip_origen TEXT, 
            es_activa INTEGER DEFAULT {ENTREGA_ACTIVA},
            FOREIGN KEY(legajo) REFERENCES alumnos(legajo)
        )
    """)


# -----------------------------------------------------------------------------
# REPOSITORIO DE DATOS (Funciones expuestas a la API e Interfaz)
# -----------------------------------------------------------------------------


def inicializar_base_datos(
    ruta_db: str, modulo: str, fecha_hoy: str, turno: str, aula: str, pin_generado: str
) -> str:
    """
    Crea el esquema si no existe y registra (o recupera) el PIN de la sesión.
    Retorna el PIN activo que debe usar la API.
    """
    db_existe = os.path.exists(ruta_db)
    with conexion_db(ruta_db) as cursor:
        if not db_existe:
            _crear_esquema(cursor)
            cursor.execute(
                """
                INSERT INTO configuracion (pin, modulo, fecha, turno, aula) 
                VALUES (?, ?, ?, ?, ?)
                """,
                (pin_generado, modulo, fecha_hoy, turno, aula),
            )
            return pin_generado
        else:
            cursor.execute("SELECT pin FROM configuracion LIMIT 1")
            resultado = cursor.fetchone()
            return str(resultado[0]) if resultado else pin_generado


def consultar_estado_alumno(ruta_db: str, legajo: str) -> Optional[Tuple[int]]:
    """
    Busca si el alumno ya existe en el sistema.
    Retorna una tupla (reentrega_habilitada,) o None si el alumno es nuevo.
    """
    with conexion_db(ruta_db) as cursor:
        cursor.execute(
            "SELECT reentrega_habilitada FROM alumnos WHERE legajo = ?", (legajo,)
        )
        return cursor.fetchone()


def obtener_datos_entrega_previa(ruta_db: str, legajo: str):
    """Busca el hash y comprobante de la ÚLTIMA entrega del alumno."""
    with conexion_db(ruta_db) as cursor:
        cursor.execute(
            """
            SELECT hash_archivo, codigo_comprobante 
            FROM entregas 
            WHERE legajo = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
            """,
            (legajo,),
        )
        return cursor.fetchone()


def registrar_entrega_exitosa(
    ruta_db: str,
    legajo: str,
    apellidos: str,
    nombres: str,
    ip_peticion_actual: str,  # <--- CAMBIADO para mayor claridad semántica
    hostname: str,
    timestamp: datetime,
    nombre_archivo: str,
    hash_archivo: str,
    codigo_comprobante: str,
    es_nuevo_alumno: bool,
) -> None:
    """
    Transacción principal y crítica: Registra un alumno si no existe,
    le consume el permiso de reentrega, desactiva sus parciales anteriores
    y asienta la nueva entrega como activa, todo de forma atómica.
    """
    with conexion_db(ruta_db) as cursor:
        if es_nuevo_alumno:
            cursor.execute(
                """
                INSERT INTO alumnos (legajo, apellidos, nombres, ip_vinculada, hostname_vinculado, reentrega_habilitada)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    legajo,
                    apellidos,
                    nombres,
                    ip_peticion_actual,
                    hostname,
                    PERMISO_DENEGADO,
                ),
            )
        else:
            # Si ya existía, le consumimos el permiso para que no envíe infinitamente
            cursor.execute(
                "UPDATE alumnos SET reentrega_habilitada = ? WHERE legajo = ?",
                (PERMISO_DENEGADO, legajo),
            )

        # Desactivar entregas anteriores (Soft Delete)
        cursor.execute(
            "UPDATE entregas SET es_activa = ? WHERE legajo = ?",
            (ENTREGA_INACTIVA, legajo),
        )

        # Insertar la nueva entrega
        cursor.execute(
            """
            INSERT INTO entregas (legajo, timestamp, nombre_archivo, hash_archivo, codigo_comprobante, ip_origen, es_activa)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                legajo,
                str(timestamp),
                nombre_archivo,
                hash_archivo,
                codigo_comprobante,
                ip_peticion_actual,  # <--- La entrega siempre guarda la IP desde la cual se envió el archivo
                ENTREGA_ACTIVA,
            ),
        )


def habilitar_reentrega(ruta_db: str, legajo: str) -> None:
    """Abre el candado en la tabla alumnos para permitir que un legajo envíe nuevamente."""
    with conexion_db(ruta_db) as cursor:
        cursor.execute(
            "UPDATE alumnos SET reentrega_habilitada = ? WHERE legajo = ?",
            (PERMISO_HABILITADO, legajo),
        )


def contar_entregas(ruta_db: str) -> int:
    """Devuelve la cantidad total de entregas (utilizado para polling y detección de cambios en GUI)."""
    with conexion_db(ruta_db) as cursor:
        cursor.execute("SELECT COUNT(*) FROM entregas")
        resultado = cursor.fetchone()
        return int(resultado[0]) if resultado else 0


def listar_entregas_activas(ruta_db: str) -> List[Tuple[Any, ...]]:
    """
    Obtiene los datos de los alumnos y sus entregas activas.
    Utiliza Window Functions en SQL para contar colisiones de hash a nivel motor,
    y aplica el MOTOR DE REGLAS DE SEGURIDAD agregando una lista de alertas.
    """
    with conexion_db(ruta_db) as cursor:
        cursor.execute(f"""
            SELECT a.legajo, a.apellidos, a.nombres, e.timestamp, e.codigo_comprobante, 
                   a.ip_vinculada, e.ip_origen, 
                   COUNT(e.hash_archivo) OVER(PARTITION BY e.hash_archivo) as repeticiones_hash
            FROM entregas e
            JOIN alumnos a ON e.legajo = a.legajo
            WHERE e.es_activa = {ENTREGA_ACTIVA}
            ORDER BY e.timestamp DESC
        """)
        filas_crudas = cursor.fetchall()

    filas_procesadas = []

    for fila in filas_crudas:
        # Desempaquetamos sabiendo que SQLite ya hizo el conteo por nosotros
        (
            legajo,
            apellidos,
            nombres,
            timestamp,
            comprobante,
            ip_vinculada,
            ip_origen,
            repeticiones_hash,
        ) = fila
        alertas = []

        # --- MOTOR DE REGLAS DE SEGURIDAD ---
        if ip_vinculada != ip_origen:
            alertas.append(
                f"• Posible suplantacion:\nSe registró con {ip_vinculada} pero ultima entrega desde {ip_origen}."
            )

        if repeticiones_hash > 1:
            alertas.append(
                f"• Posible plagio:\nEl archivo entregado tiene el mismo contenido exacto que la entrega de otro alumno."
            )
        # ------------------------------------

        filas_procesadas.append(
            (
                legajo,
                apellidos,
                nombres,
                timestamp,
                comprobante,
                ip_vinculada,
                ip_origen,
                alertas,
            )
        )

    return filas_procesadas
