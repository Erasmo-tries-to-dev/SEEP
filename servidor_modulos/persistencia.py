"""
Módulo de persistencia de SEEP-Servidor Docente.
Aísla toda la interacción con SQLite mediante el patrón Repositorio.
Garantiza transacciones atómicas (commit/rollback) y el cierre seguro de conexiones.
"""

import os
import sqlite3
from contextlib import contextmanager

# -----------------------------------------------------------------------------
# MOTOR DE TRANSACCIONES
# -----------------------------------------------------------------------------


@contextmanager
def conexion_db(ruta_db):
    """
    Maneja la conexión a SQLite garantizando commit automático en caso de éxito,
    rollback en caso de excepción, y el cierre incondicional de la conexión.
    """
    conn = sqlite3.connect(ruta_db)
    try:
        # El bloque 'with conn' maneja la transacción (commit o rollback)
        with conn:
            yield conn.cursor()
    finally:
        # El bloque 'finally' asegura que no queden bases de datos "bloqueadas"
        conn.close()


def _crear_esquema(cursor):
    """Crea las tablas de una base de datos de sesión nueva."""
    cursor.execute("""
        CREATE TABLE configuracion (
            pin TEXT, modulo TEXT, fecha TEXT, turno TEXT, aula TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE alumnos (
            legajo TEXT PRIMARY KEY, apellidos TEXT, nombres TEXT,
            ip_vinculada TEXT, hostname_vinculado TEXT, reentrega_habilitada INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, legajo TEXT, timestamp DATETIME,
            nombre_archivo TEXT, hash_archivo TEXT, codigo_comprobante TEXT,
            ip_origen TEXT, es_activa INTEGER DEFAULT 1,
            FOREIGN KEY(legajo) REFERENCES alumnos(legajo)
        )
    """)


# -----------------------------------------------------------------------------
# REPOSITORIO DE DATOS (Funciones expuestas)
# -----------------------------------------------------------------------------


def inicializar_base_datos(ruta_db, modulo, fecha_hoy, turno, aula, pin_generado):
    """
    Crea el esquema si no existe y registra (o recupera) el PIN de la sesión.
    Retorna el PIN activo.
    """
    db_existe = os.path.exists(ruta_db)
    with conexion_db(ruta_db) as cursor:
        if not db_existe:
            _crear_esquema(cursor)
            cursor.execute(
                "INSERT INTO configuracion (pin, modulo, fecha, turno, aula) VALUES (?, ?, ?, ?, ?)",
                (pin_generado, modulo, fecha_hoy, turno, aula),
            )
            return pin_generado
        else:
            cursor.execute("SELECT pin FROM configuracion LIMIT 1")
            resultado = cursor.fetchone()
            return resultado[0] if resultado else pin_generado


def consultar_estado_alumno(ruta_db, legajo):
    """
    Busca si el alumno existe.
    Retorna una tupla (reentrega_habilitada,) o None si es nuevo.
    """
    with conexion_db(ruta_db) as cursor:
        cursor.execute(
            "SELECT reentrega_habilitada FROM alumnos WHERE legajo = ?", (legajo,)
        )
        return cursor.fetchone()


def registrar_entrega_exitosa(
    ruta_db,
    legajo,
    apellidos,
    nombres,
    ip_vinculada,
    hostname,
    timestamp,
    nombre_archivo,
    hash_archivo,
    codigo_comprobante,
    es_nuevo_alumno,
):
    """
    Transacción principal: Registra un alumno si no existe, le consume el permiso
    de reentrega, desactiva sus parciales anteriores y asienta la nueva entrega.
    """
    with conexion_db(ruta_db) as cursor:
        if es_nuevo_alumno:
            cursor.execute(
                """
                INSERT INTO alumnos (legajo, apellidos, nombres, ip_vinculada, hostname_vinculado, reentrega_habilitada)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (legajo, apellidos, nombres, ip_vinculada, hostname),
            )
        else:
            # Si ya existía, le consumimos el permiso para que no envíe infinitamente
            cursor.execute(
                "UPDATE alumnos SET reentrega_habilitada = 0 WHERE legajo = ?",
                (legajo,),
            )

        # Desactivar entregas anteriores
        cursor.execute("UPDATE entregas SET es_activa = 0 WHERE legajo = ?", (legajo,))

        # Insertar la nueva entrega (forzando str() en el timestamp por compatibilidad Python 3.12+)
        cursor.execute(
            """
            INSERT INTO entregas (legajo, timestamp, nombre_archivo, hash_archivo, codigo_comprobante, ip_origen, es_activa)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                legajo,
                str(timestamp),
                nombre_archivo,
                hash_archivo,
                codigo_comprobante,
                ip_vinculada,
            ),
        )


def habilitar_reentrega(ruta_db, legajo):
    """Abre el candado para permitir que un legajo envíe nuevamente."""
    with conexion_db(ruta_db) as cursor:
        cursor.execute(
            "UPDATE alumnos SET reentrega_habilitada = 1 WHERE legajo = ?", (legajo,)
        )


def contar_entregas(ruta_db):
    """Devuelve la cantidad total de entregas (para detectar cambios en la UI)."""
    with conexion_db(ruta_db) as cursor:
        cursor.execute("SELECT COUNT(*) FROM entregas")
        return cursor.fetchone()[0]


def listar_entregas_activas(ruta_db):
    """Obtiene los datos cruzados para poblar la grilla del docente."""
    with conexion_db(ruta_db) as cursor:
        cursor.execute("""
            SELECT a.legajo, a.apellidos, a.nombres, e.timestamp, e.codigo_comprobante, a.ip_vinculada, e.ip_origen
            FROM entregas e
            JOIN alumnos a ON e.legajo = a.legajo
            WHERE e.es_activa = 1
            ORDER BY e.timestamp DESC
        """)
        return cursor.fetchall()
