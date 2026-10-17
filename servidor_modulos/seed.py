import os
import glob
import sqlite3
import random
import hashlib
from datetime import datetime, timedelta

# --- LISTAS DE DATOS MOCK ---
NOMBRES = [
    "Juan",
    "Maria",
    "Carlos",
    "Ana",
    "Luis",
    "Elena",
    "Pedro",
    "Lucia",
    "Diego",
    "Sofia",
    "Martin",
    "Valeria",
    "Facundo",
    "Camila",
    "Matias",
    "Florencia",
]
APELLIDOS = [
    "Gomez",
    "Perez",
    "Rodriguez",
    "Fernandez",
    "Lopez",
    "Martinez",
    "Gonzalez",
    "Romero",
    "Sosa",
    "Torres",
    "Alvarez",
    "Ruiz",
    "Ramirez",
    "Flores",
]


def generar_mock_data(cantidad=50):
    """Genera una lista de diccionarios con datos de parciales realistas."""
    datos = []
    tiempo_base = datetime.now() - timedelta(
        hours=2
    )  # Los parciales arrancaron hace 2 horas

    for _ in range(cantidad):
        nombre = random.choice(NOMBRES)
        apellido = random.choice(APELLIDOS)
        legajo = f"{random.randint(10000, 99999)}/{random.randint(0, 9)}"

        # IP asignada al conectarse
        ip_base = f"192.168.1.{random.randint(100, 200)}"

        # Simulamos que un 10% de los alumnos tiene una IP de origen distinta al entregar (Suplantación / Cambio de red)
        ip_origen = (
            ip_base
            if random.random() > 0.1
            else f"192.168.1.{random.randint(201, 250)}"
        )

        # Distribuimos las entregas a lo largo de las 2 horas
        minutos_random = random.randint(1, 120)
        timestamp = tiempo_base + timedelta(minutes=minutos_random)

        # Generamos un hash realista
        hash_str = hashlib.sha256(f"{legajo}{timestamp}".encode()).hexdigest()
        comprobante = f"{hash_str[:4].upper()}-{hash_str[4:8].upper()}"

        datos.append(
            {
                "legajo": legajo,
                "apellidos": apellido,
                "nombres": nombre,
                "ip_vinculada": ip_base,
                "hostname": f"PC-{apellido.upper()}",
                "timestamp": timestamp,
                "nombre_archivo": f"{apellido}_{nombre}_{legajo.replace('/','-')}_parcial.zip",
                "hash_archivo": hash_str,
                "comprobante": comprobante,
                "ip_origen": ip_origen,
            }
        )
    return datos


def obtener_ultima_bd():
    """Busca la carpeta de entregas más reciente y retorna la ruta a su base de datos."""
    carpetas = [d for d in glob.glob("entregas_*") if os.path.isdir(d)]
    if not carpetas:
        return None

    carpeta_mas_nueva = max(carpetas, key=os.path.getmtime)
    ruta_db = os.path.join(carpeta_mas_nueva, "seep_registro.db")

    if os.path.exists(ruta_db):
        return ruta_db
    return None


def poblar_base_de_datos():
    ruta_db = obtener_ultima_bd()
    if not ruta_db:
        print(
            "❌ No se encontró ninguna base de datos activa. Abrí el servidor docente primero."
        )
        return

    print(f"📂 Base de datos detectada: {ruta_db}")
    alumnos = generar_mock_data(50)

    with sqlite3.connect(ruta_db) as conn:
        cursor = conn.cursor()

        for a in alumnos:
            # 1. Insertamos el alumno
            cursor.execute(
                """
                INSERT OR IGNORE INTO alumnos (legajo, apellidos, nombres, ip_vinculada, hostname_vinculado, reentrega_habilitada)
                VALUES (?, ?, ?, ?, ?, 0)
            """,
                (
                    a["legajo"],
                    a["apellidos"],
                    a["nombres"],
                    a["ip_vinculada"],
                    a["hostname"],
                ),
            )

            # 2. Insertamos la entrega
            cursor.execute(
                """
                INSERT INTO entregas (legajo, timestamp, nombre_archivo, hash_archivo, codigo_comprobante, ip_origen, es_activa)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
                (
                    a["legajo"],
                    str(a["timestamp"]),
                    a["nombre_archivo"],
                    a["hash_archivo"],
                    a["comprobante"],
                    a["ip_origen"],
                ),
            )

    print(f"✅ ¡Éxito! Se inyectaron {len(alumnos)} parciales simulados.")


if __name__ == "__main__":
    poblar_base_de_datos()
