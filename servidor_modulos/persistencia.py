"""
Módulo de Persistencia de SEEP (Servidor Docente).
Aísla toda la interacción con la base de datos SQLite mediante el patrón Repositorio.
Garantiza transacciones atómicas (commit/rollback) y el cierre seguro de conexiones.
"""

import os
import sqlite3
import csv
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, List, Optional, Tuple

# -----------------------------------------------------------------------------
# CONSTANTES GLOBALES Y ESTADOS DE NEGOCIO
# -----------------------------------------------------------------------------
PERMISO_DENEGADO: int = 0
PERMISO_HABILITADO: int = 1

ENTREGA_INACTIVA: int = 0
ENTREGA_ACTIVA: int = 1

DELIMITADOR_CSV: str = ";"
CODIFICACION_CSV: str = "utf-8-sig"


# -----------------------------------------------------------------------------
# MOTOR DE TRANSACCIONES Y ESQUEMA
# -----------------------------------------------------------------------------
@contextmanager
def conexion_db(ruta_base_datos: str) -> Iterator[sqlite3.Cursor]:
    """
    Maneja la conexión a SQLite de forma segura actuando como Gestor de Contexto.
    Garantiza el cierre incondicional de la conexión incluso ante excepciones.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.

    Yields:
        sqlite3.Cursor: Cursor activo para ejecutar sentencias SQL.
    """
    conexion = sqlite3.connect(ruta_base_datos)
    try:
        # RATIONALE: El bloque 'with conexion' delega al motor de SQLite el manejo
        # de la transacción ACID (ejecutando COMMIT si no hay errores, o ROLLBACK
        # si se lanza una excepción durante la ejecución del cursor).
        with conexion:
            yield conexion.cursor()
    finally:
        conexion.close()


def _crear_esquema(cursor_activo: sqlite3.Cursor) -> None:
    """
    Construye la estructura de tablas para una nueva base de datos de sesión.

    Args:
        cursor_activo (sqlite3.Cursor): Cursor con transacción abierta.
    """
    cursor_activo.execute("""
        CREATE TABLE configuracion (
            pin TEXT, 
            modulo TEXT, 
            fecha TEXT, 
            turno TEXT, 
            aula TEXT
        )
    """)
    cursor_activo.execute(f"""
        CREATE TABLE alumnos (
            legajo TEXT PRIMARY KEY, 
            apellidos TEXT, 
            nombres TEXT,
            ip_vinculada TEXT, 
            hostname_vinculado TEXT, 
            reentrega_habilitada INTEGER DEFAULT {PERMISO_DENEGADO}
        )
    """)
    cursor_activo.execute(f"""
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
    ruta_base_datos: str,
    modulo_evaluado: str,
    fecha_hoy: str,
    turno: str,
    aula: str,
    pin_generado: str,
) -> str:
    """
    Inicializa el repositorio. Crea el esquema si el archivo no existe y registra
    (o recupera) el PIN maestro de la sesión docente.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.
        modulo_evaluado (str): Módulo académico de la sesión.
        fecha_hoy (str): Fecha actual de inicialización.
        turno (str): Turno asignado al laboratorio.
        aula (str): Identificador físico del laboratorio.
        pin_generado (str): Código PIN autogenerado por el servidor.

    Returns:
        str: El PIN activo para la sesión actual (el generado o el recuperado).
    """
    base_datos_existe = os.path.exists(ruta_base_datos)
    with conexion_db(ruta_base_datos) as cursor_activo:
        if not base_datos_existe:
            _crear_esquema(cursor_activo)
            cursor_activo.execute(
                """
                INSERT INTO configuracion (pin, modulo, fecha, turno, aula) 
                VALUES (?, ?, ?, ?, ?)
                """,
                (pin_generado, modulo_evaluado, fecha_hoy, turno, aula),
            )
            return pin_generado

        cursor_activo.execute("SELECT pin FROM configuracion LIMIT 1")
        resultado_consulta = cursor_activo.fetchone()
        return str(resultado_consulta[0]) if resultado_consulta else pin_generado


def consultar_estado_alumno(
    ruta_base_datos: str, legajo_alumno: str
) -> Optional[Tuple[int]]:
    """
    Verifica la existencia de un alumno en la base y su estado de permisos de entrega.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.
        legajo_alumno (str): Identificador único del alumno.

    Returns:
        Optional[Tuple[int]]: Tupla con el valor del permiso, o None si no existe registro previo.
    """
    with conexion_db(ruta_base_datos) as cursor_activo:
        cursor_activo.execute(
            "SELECT reentrega_habilitada FROM alumnos WHERE legajo = ?",
            (legajo_alumno,),
        )
        return cursor_activo.fetchone()


def obtener_datos_entrega_previa(
    ruta_base_datos: str, legajo_alumno: str
) -> Optional[Tuple[str, str]]:
    """
    Recupera la firma criptográfica y el comprobante de la última entrega realizada por un alumno.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.
        legajo_alumno (str): Identificador único del alumno.

    Returns:
        Optional[Tuple[str, str]]: Tupla conteniendo (hash_archivo, codigo_comprobante), o None.
    """
    with conexion_db(ruta_base_datos) as cursor_activo:
        cursor_activo.execute(
            """
            SELECT hash_archivo, codigo_comprobante 
            FROM entregas 
            WHERE legajo = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
            """,
            (legajo_alumno,),
        )
        return cursor_activo.fetchone()


def registrar_entrega_exitosa(
    ruta_db: str,
    legajo: str,
    apellidos: str,
    nombres: str,
    ip_peticion_actual: str,
    hostname: str,
    timestamp: datetime,
    nombre_archivo: str,
    hash_archivo: str,
    codigo_comprobante: str,
    es_nuevo_alumno: bool,
) -> None:
    """
    Registra de forma atómica la recepción de un examen, gestionando altas de alumnos,
    revocación de permisos de reentrega y soft-deletion de entregas previas.

    Args:
        ruta_db (str): Ubicación física de la base SQLite.
        legajo (str): Identificador único del alumno.
        apellidos (str): Apellidos del alumno.
        nombres (str): Nombres del alumno.
        ip_peticion_actual (str): Dirección IP desde donde se transmitió el examen.
        hostname (str): Nombre de red del equipo de origen.
        timestamp (datetime): Marca de tiempo exacta de la recepción en servidor.
        nombre_archivo (str): Nombre final del archivo persistido en disco.
        hash_archivo (str): Checksum criptográfico del contenido.
        codigo_comprobante (str): Identificador de recibo generado.
        es_nuevo_alumno (bool): Bandera que indica si requiere inserción en tabla alumnos.
    """
    with conexion_db(ruta_db) as cursor_activo:
        if es_nuevo_alumno:
            cursor_activo.execute(
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
            cursor_activo.execute(
                "UPDATE alumnos SET reentrega_habilitada = ? WHERE legajo = ?",
                (PERMISO_DENEGADO, legajo),
            )

        cursor_activo.execute(
            "UPDATE entregas SET es_activa = ? WHERE legajo = ?",
            (ENTREGA_INACTIVA, legajo),
        )

        cursor_activo.execute(
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
                ip_peticion_actual,
                ENTREGA_ACTIVA,
            ),
        )


def habilitar_reentrega(ruta_base_datos: str, legajo_alumno: str) -> None:
    """
    Concede autorización excepcional a un alumno para sobrescribir su entrega.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.
        legajo_alumno (str): Identificador único del alumno autorizado.
    """
    with conexion_db(ruta_base_datos) as cursor_activo:
        cursor_activo.execute(
            "UPDATE alumnos SET reentrega_habilitada = ? WHERE legajo = ?",
            (PERMISO_HABILITADO, legajo_alumno),
        )


def contar_entregas(ruta_base_datos: str) -> int:
    """
    Obtiene el volumen total de entregas almacenadas en el sistema.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.

    Returns:
        int: Cantidad absoluta de entregas.
    """
    with conexion_db(ruta_base_datos) as cursor_activo:
        cursor_activo.execute("SELECT COUNT(*) FROM entregas")
        resultado_conteo = cursor_activo.fetchone()
        return int(resultado_conteo[0]) if resultado_conteo else 0


def listar_entregas_activas(ruta_base_datos: str) -> List[Tuple[Any, ...]]:
    """
    Recupera el listado consolidado de exámenes activos, calculando las alertas
    de seguridad en tiempo de ejecución.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.

    Returns:
        List[Tuple[Any, ...]]: Lista de tuplas con la información estructurada de entregas y auditoría.

    Notes:
        Se emplea `COUNT() OVER(PARTITION BY)` para delegar al motor SQL la detección de
        colisiones criptográficas (plagios) en una única pasada, en lugar de calcularlo
        vía diccionarios en Python.
    """
    with conexion_db(ruta_base_datos) as cursor_activo:
        cursor_activo.execute(f"""
            SELECT a.legajo, a.apellidos, a.nombres, e.timestamp, e.codigo_comprobante, 
                   a.ip_vinculada, e.ip_origen, 
                   COUNT(e.hash_archivo) OVER(PARTITION BY e.hash_archivo) as repeticiones_hash
            FROM entregas e
            JOIN alumnos a ON e.legajo = a.legajo
            WHERE e.es_activa = {ENTREGA_ACTIVA}
            ORDER BY e.timestamp DESC
        """)
        filas_extraidas = cursor_activo.fetchall()

    filas_consolidadas = []

    for fila_cruda in filas_extraidas:
        (
            legajo,
            apellidos,
            nombres,
            marca_temporal,
            comprobante,
            ip_vinculada,
            ip_origen,
            repeticiones_hash,
        ) = fila_cruda

        alertas_detectadas: List[str] = []

        if ip_vinculada != ip_origen:
            alertas_detectadas.append(
                f"• Posible suplantacion:\nSe registró con {ip_vinculada} pero ultima entrega desde {ip_origen}."
            )

        if repeticiones_hash > 1:
            alertas_detectadas.append(
                f"• Posible plagio:\nEl archivo entregado tiene el mismo contenido exacto que la entrega de otro alumno."
            )

        filas_consolidadas.append(
            (
                legajo,
                apellidos,
                nombres,
                marca_temporal,
                comprobante,
                ip_vinculada,
                ip_origen,
                alertas_detectadas,
            )
        )

    return filas_consolidadas


def exportar_asistencia_csv(ruta_base_datos: str, ruta_archivo_csv: str) -> None:
    """
    Vuelca el historial íntegro de la base de datos hacia un archivo de texto tabulado.

    Args:
        ruta_base_datos (str): Ubicación física de la base SQLite.
        ruta_archivo_csv (str): Ruta absoluta de destino para el reporte.

    Notes:
        RATIONALE: Se utiliza la codificación `utf-8-sig` (con Byte Order Mark) para
        forzar a Microsoft Excel en entornos Windows a renderizar correctamente los
        caracteres acentuados sin necesidad de importar datos manualmente.
    """
    with conexion_db(ruta_base_datos) as cursor_activo:
        cursor_activo.execute("""
            SELECT a.legajo, a.apellidos, a.nombres, e.timestamp, e.codigo_comprobante, 
                   e.nombre_archivo, e.es_activa, a.ip_vinculada, e.ip_origen, 
                   COUNT(e.hash_archivo) OVER(PARTITION BY e.hash_archivo) as repeticiones_hash
            FROM entregas e
            JOIN alumnos a ON e.legajo = a.legajo
            ORDER BY a.apellidos ASC, a.nombres ASC, e.timestamp ASC
        """)
        filas_historicas = cursor_activo.fetchall()

    with open(
        ruta_archivo_csv, mode="w", newline="", encoding=CODIFICACION_CSV
    ) as archivo_salida:
        escritor_csv = csv.writer(archivo_salida, delimiter=DELIMITADOR_CSV)

        escritor_csv.writerow(
            [
                "Legajo/DNI",
                "Apellidos",
                "Nombres",
                "Hora",
                "Comprobante",
                "Nombre del Archivo",
                "Tipo de Entrega",
                "Auditoría / Alertas",
            ]
        )

        for registro in filas_historicas:
            (
                legajo,
                apellidos,
                nombres,
                marca_temporal,
                comprobante,
                nombre_archivo,
                estado_actividad,
                ip_vinculada,
                ip_origen,
                repeticiones_hash,
            ) = registro

            hora_formateada = str(marca_temporal)[11:19]
            tipo_entrega_etiqueta = (
                "FINAL"
                if estado_actividad == ENTREGA_ACTIVA
                else "ANTERIOR (Re-entregada)"
            )
            # NOTA(refactor): esta logica se encuentra repetida en otra funcion, considerar un extract method
            alertas_detectadas: List[str] = []
            if ip_vinculada != ip_origen:
                alertas_detectadas.append("IP Difiere")
            if repeticiones_hash > 1:
                alertas_detectadas.append("Clonación de Hash")

            etiqueta_auditoria = (
                " | ".join(alertas_detectadas) if alertas_detectadas else "OK"
            )

            escritor_csv.writerow(
                [
                    legajo,
                    apellidos,
                    nombres,
                    hora_formateada,
                    comprobante,
                    nombre_archivo,
                    tipo_entrega_etiqueta,
                    etiqueta_auditoria,
                ]
            )
