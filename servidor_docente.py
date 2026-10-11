import os
import random
import socket
import hashlib
import logging
from datetime import datetime
import threading
import sys
import errno
import sqlite3
import customtkinter as ctk
from tkinter import messagebox

# Configuración de Logging para el servidor (Consola + Archivo físico)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("seep_servidor.log", encoding="utf-8"),  # Guarda en archivo
        logging.StreamHandler(sys.stdout),  # Muestra en consola
    ],
)

# Waitress es un servidor de produccion
from waitress import serve
from flask import Flask, request, jsonify, current_app

# Importamos nuestra nueva Única Fuente de Verdad compartida
import seep_config


def obtener_directorio_base():
    """Obtiene la ruta absoluta donde se encuentra el ejecutable o el script."""
    if getattr(sys, "frozen", False):
        # Si está corriendo como un ejecutable (.exe) compilado por PyInstaller
        return os.path.dirname(sys.executable)
    # Si está corriendo como un script .py normal
    return os.path.dirname(os.path.abspath(__file__))


def obtener_ip_local():
    """Establece una conexión de prueba para determinar y retornar la dirección IP local."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def limpiar_cadena(texto):
    """Sanitiza una cadena de texto para uso seguro en Windows y evita inyecciones."""
    if not texto:
        return ""

    # S3 y S9: Eliminar caracteres nulos, saltos de línea y tabulaciones (para proteger la consola y el OS)
    texto = (
        texto.replace("\0", "").replace("\n", "").replace("\r", "").replace("\t", "_")
    )
    texto = texto.replace(" ", "_").replace("/", "-")

    for caracter_invalido in ["<", ">", ":", '"', "\\", "|", "?", "*"]:
        texto = texto.replace(caracter_invalido, "")

    return texto.strip()


def calcular_hash(archivo):
    """Calcula el hash SHA-256 del archivo en bloques."""
    sha256_hash = hashlib.sha256()
    for byte_block in iter(lambda: archivo.read(4096), b""):
        sha256_hash.update(byte_block)
    archivo.seek(0)
    return sha256_hash.hexdigest()


def inicializar_entorno(modulo, turno, aula):
    """
    Crea la carpeta de la sesión y configura la base de datos SQLite.
    Retorna la ruta de la carpeta, la ruta de la DB y el PIN (nuevo o recuperado).
    """
    fecha_hoy = datetime.now().strftime("%Y%m%d")

    # Ej: entregas_imperativo_20261011_TA_LAB3
    nombre_carpeta = f"entregas_{modulo}_{fecha_hoy}_{turno}_{aula}"
    directorio_base = obtener_directorio_base()
    ruta_carpeta = os.path.join(directorio_base, nombre_carpeta)

    os.makedirs(ruta_carpeta, exist_ok=True)

    ruta_db = os.path.join(ruta_carpeta, "seep_registro.db")
    db_existe = os.path.exists(ruta_db)

    # Conectamos a SQLite (crea el archivo si no existe)
    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()

    if not db_existe:
        # Primera vez que se abre esta sesión: Creamos el esquema completo
        cursor.execute("""
            CREATE TABLE configuracion (
                pin TEXT,
                modulo TEXT,
                fecha TEXT,
                turno TEXT,
                aula TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE alumnos (
                legajo TEXT PRIMARY KEY,
                apellidos TEXT,
                nombres TEXT,
                ip_vinculada TEXT,
                hostname_vinculado TEXT,
                reentrega_habilitada INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE entregas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                legajo TEXT,
                timestamp DATETIME,
                nombre_archivo TEXT,
                hash_archivo TEXT,
                codigo_comprobante TEXT,
                ip_origen TEXT,
                es_activa INTEGER DEFAULT 1,
                FOREIGN KEY(legajo) REFERENCES alumnos(legajo)
            )
        """)

        # Generamos un PIN nuevo y guardamos el contexto de la sesión
        pin_sesion = str(random.randint(1000, 9999))
        cursor.execute(
            """
            INSERT INTO configuracion (pin, modulo, fecha, turno, aula)
            VALUES (?, ?, ?, ?, ?)
        """,
            (pin_sesion, modulo, fecha_hoy, turno, aula),
        )
        conn.commit()
    else:
        # La base ya existe (el docente la cerró y la volvió a abrir). Recuperamos el PIN original.
        cursor.execute("SELECT pin FROM configuracion LIMIT 1")
        resultado = cursor.fetchone()
        pin_sesion = resultado[0] if resultado else str(random.randint(1000, 9999))

    conn.close()

    return ruta_carpeta, ruta_db, pin_sesion


def crear_app(modulo_elegido, pin_fijo, carpeta_elegida, ruta_db):
    """
    Application Factory: Crea y configura una instancia de la aplicación Flask.
    """
    app = Flask(__name__)

    # Inyectamos las configuraciones en la app
    app.config["PIN"] = pin_fijo
    app.config["MODULO"] = modulo_elegido
    app.config["CARPETA_ENTREGAS"] = carpeta_elegida
    app.config["RUTA_DB"] = (
        ruta_db  # ¡Acá guardamos la ruta de SQLite para usarla después!
    )

    # Rechazamos archivos más grandes que el límite establecido
    app.config["MAX_CONTENT_LENGTH"] = seep_config.MAX_TAMANO_BYTES

    # (La carpeta ya se creó en inicializar_entorno, pero aseguramos por las dudas)
    os.makedirs(app.config["CARPETA_ENTREGAS"], exist_ok=True)

    # Rechazamos archivos más grandes que el límite establecido en la configuración compartida
    app.config["MAX_CONTENT_LENGTH"] = seep_config.MAX_TAMANO_BYTES

    os.makedirs(app.config["CARPETA_ENTREGAS"], exist_ok=True)

    @app.route("/ping", methods=["GET"])
    def ping():
        version_cliente = request.args.get("version", "")

        if version_cliente != seep_config.VERSION_SEEP:
            logging.warning(
                f"Ping rechazado por versión incompatible: {version_cliente} vs {seep_config.VERSION_SEEP}"
            )
            return (
                jsonify(
                    {
                        "error": f"Versión del cliente ({version_cliente}) incompatible. El servidor requiere la versión {seep_config.VERSION_SEEP}. Pedí el nuevo programa."
                    }
                ),
                426,
            )

        return jsonify({"status": "ok", "mensaje": "Servidor activo"}), 200

    @app.route("/upload", methods=["POST"])
    def upload():
        version_cliente = request.form.get("version")

        # Validamos que el cliente no sea de una versión vieja
        if version_cliente != seep_config.VERSION_SEEP:
            logging.warning(
                f"Intento de conexión con versión incompatible: {version_cliente} vs {seep_config.VERSION_SEEP}"
            )
            return (
                jsonify(
                    {
                        "error": f"Versión del cliente ({version_cliente}) incompatible. El servidor requiere la versión {seep_config.VERSION_SEEP}. Pedí el nuevo programa."
                    }
                ),
                426,
            )

        pin_recibido = request.form.get("pin")
        apellidos = request.form.get("apellidos")
        nombres = request.form.get("nombres")
        identificador = request.form.get("identificador")
        archivo = request.files.get("file")

        hostname_cliente = request.form.get("hostname", "Desconocido")
        ip_cliente = request.remote_addr

        if not all([pin_recibido, apellidos, nombres, identificador, archivo]):
            logging.warning(
                f"Intento de subida fallido (datos incompletos) desde IP: {ip_cliente}"
            )
            return jsonify({"error": "Faltan datos requeridos"}), 400

        # S9 y S3: Sanitizamos inmediatamente todo lo que viene del alumno
        apellidos_seguro = limpiar_cadena(apellidos)
        nombres_seguro = limpiar_cadena(nombres)
        id_seguro = limpiar_cadena(identificador)
        hostname_seguro = limpiar_cadena(hostname_cliente)

        if (
            len(apellidos_seguro) > 80
            or len(nombres_seguro) > 80
            or len(id_seguro) > 30
        ):
            logging.warning(
                f"Payload rechazado por longitud extrema desde IP: {ip_cliente}"
            )
            return (
                jsonify({"error": "Los campos exceden la longitud máxima permitida"}),
                400,
            )

        if pin_recibido != current_app.config["PIN"]:
            logging.warning(
                f"PIN incorrecto ingresado por {apellidos_seguro} ({id_seguro}) desde IP: {ip_cliente}"
            )
            return jsonify({"error": "PIN incorrecto"}), 403

        modulo_activo = current_app.config["MODULO"]
        nombre_original = archivo.filename

        # Delegamos la validación a seep_config
        es_valido, resultado_validacion = seep_config.validar_extension(
            nombre_original, modulo_activo
        )
        if not es_valido:
            logging.warning(
                f"Extensión inválida enviada por {apellidos_seguro} ({id_seguro})"
            )
            return jsonify({"error": resultado_validacion}), 400

        momento_entrega = datetime.now()
        timestamp = momento_entrega.strftime("%Y%m%d_%H%M%S_%f")

        carpeta_destino = current_app.config["CARPETA_ENTREGAS"]
        nombre_final = f"{apellidos_seguro}_{nombres_seguro}_{id_seguro}_{timestamp}{resultado_validacion}"

        ruta_guardado = os.path.join(carpeta_destino, nombre_final)
        ruta_temporal = ruta_guardado + ".tmp"

        hash_archivo = calcular_hash(archivo)

        # R11: Generamos el código corto de comprobante (los primeros 6 caracteres del hash en mayúsculas)
        codigo_comprobante = hash_archivo[:6].upper()

        try:
            # 1. Guarda físicamente en el archivo temporal
            archivo.save(ruta_temporal)

            # 2. Guardado Atómico
            os.replace(ruta_temporal, ruta_guardado)

            # 3. Guardado en Base de Datos SQLite (Reemplaza al CSV)
            ruta_db = current_app.config["RUTA_DB"]
            conn = sqlite3.connect(ruta_db)
            cursor = conn.cursor()

            # Paso 3A: Insertar al alumno si no existe (el IGNORE evita error si ya está registrado)
            cursor.execute(
                """
                INSERT OR IGNORE INTO alumnos (legajo, apellidos, nombres, ip_vinculada, hostname_vinculado)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    id_seguro,
                    apellidos_seguro,
                    nombres_seguro,
                    ip_cliente,
                    hostname_seguro,
                ),
            )

            # (Fase 2: Aquí irá el bloqueo duro de reentregas. Por ahora, si un alumno vuelve a entregar,
            # marcamos como inactivas sus entregas previas para que la actual sea la única activa)
            cursor.execute(
                "UPDATE entregas SET es_activa = 0 WHERE legajo = ?", (id_seguro,)
            )

            # Paso 3B: Insertar la entrega en el historial inmutable
            cursor.execute(
                """
                INSERT INTO entregas (legajo, timestamp, nombre_archivo, hash_archivo, codigo_comprobante, ip_origen, es_activa)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
                (
                    id_seguro,
                    momento_entrega,
                    nombre_final,
                    hash_archivo,
                    codigo_comprobante,
                    ip_cliente,
                ),
            )

            conn.commit()
            conn.close()

            logging.info(
                f"NUEVA ENTREGA: {apellidos_seguro} {nombres_seguro} | DNI/Legajo: {id_seguro} | IP: {ip_cliente} | Comprobante: {codigo_comprobante}"
            )

            # Devolvemos el código de comprobante al cliente (lo usaremos en la Fase 3)
            return (
                jsonify(
                    {
                        "mensaje": f"Parcial de {modulo_activo} entregado exitosamente",
                        "comprobante": codigo_comprobante,
                    }
                ),
                200,
            )

        except Exception as e:
            if os.path.exists(ruta_temporal):
                try:
                    os.remove(ruta_temporal)
                except Exception:
                    pass

            logging.error(
                f"ERROR GRAVE guardando entrega de {apellidos_seguro}: {str(e)}",
                exc_info=True,
            )
            return jsonify({"error": f"Error interno al guardar: {str(e)}"}), 500

    return app


def ejecutar_waitress(app):
    """Ejecuta el servidor web en un hilo secundario y maneja errores de red visualmente."""
    try:
        serve(app, host="0.0.0.0", port=seep_config.PUERTO_API)
    except OSError as e:
        es_puerto_ocupado = (getattr(e, "errno", None) == errno.EADDRINUSE) or (
            getattr(e, "winerror", None) == 10048
        )

        if es_puerto_ocupado:
            mensaje = (
                f"El puerto {seep_config.PUERTO_API} ya está ocupado por otro programa.\n\n"
                "Esto casi siempre ocurre porque ya hay OTRA ventana de SEEP abierta "
                "en esta computadora.\n\n"
                "Solución:\n"
                "1. Busque en la barra de tareas y cierre cualquier otro servidor.\n"
                "2. Vuelva a abrir este programa."
            )
            # Muestra un pop-up crítico bloqueante
            messagebox.showerror("❌ ERROR CRÍTICO - Puerto Ocupado", mensaje)
        else:
            mensaje = (
                "Ocurrió un error inesperado a nivel de sistema operativo o red.\n\n"
                f"Detalle técnico: {str(e)}\n\n"
                "Sugerencia: Verifique su conexión de red o permisos de administrador."
            )
            messagebox.showerror("❌ ERROR CRÍTICO", mensaje)

        # Una vez que el docente cierra el pop-up de error, matamos el proceso limpiamente
        os._exit(1)


def arrancar_servidor():
    """
    Punto de entrada principal. Levanta la interfaz gráfica, permite configurar
    la sesión visualmente y luego inicia Waitress de fondo.
    """
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    ventana = ctk.CTk()
    ventana.title("SEEP - Configuración Inicial")
    ventana.geometry("700x500")

    # --- PANTALLA 1: CONFIGURACIÓN ---
    frame_config = ctk.CTkFrame(ventana)
    frame_config.pack(pady=40, padx=40, fill="both", expand=True)

    ctk.CTkLabel(
        frame_config, text="Configuración de la Sesión", font=("Roboto", 24, "bold")
    ).pack(pady=20)

    # Selector de Módulo
    ctk.CTkLabel(frame_config, text="Módulo a evaluar:").pack(pady=(10, 0))
    var_modulo = ctk.StringVar(value="imperativo")
    combo_modulo = ctk.CTkOptionMenu(
        frame_config,
        values=["imperativo", "objetos", "concurrente"],
        variable=var_modulo,
    )
    combo_modulo.pack(pady=5)

    # Input de Turno
    ctk.CTkLabel(frame_config, text="Turno (ej. TA, TB):").pack(pady=(10, 0))
    entrada_turno = ctk.CTkEntry(frame_config, placeholder_text="Ingrese turno...")
    entrada_turno.pack(pady=5)

    # Input de Aula
    ctk.CTkLabel(frame_config, text="Aula (ej. Lab3):").pack(pady=(10, 0))
    entrada_aula = ctk.CTkEntry(frame_config, placeholder_text="Ingrese aula...")
    entrada_aula.pack(pady=5)

    # Etiqueta para mostrar errores si dejan campos vacíos
    lbl_error = ctk.CTkLabel(frame_config, text="", text_color="red")
    lbl_error.pack(pady=5)

    # --- PANTALLA 2: DASHBOARD (Oculta al inicio) ---
    frame_dashboard = ctk.CTkFrame(ventana)

    # Variables de estado atadas a la ventana para evitar usar variables globales
    ventana.ruta_db = None
    ventana.ultimo_conteo = -1

    # Encabezado del dashboard
    lbl_titulo_dash = ctk.CTkLabel(
        frame_dashboard,
        text="SERVIDOR ACTIVO",
        font=("Roboto", 24, "bold"),
        text_color="green",
    )
    lbl_info_dash = ctk.CTkLabel(frame_dashboard, text="", font=("Roboto", 18, "bold"))
    lbl_ruta_dash = ctk.CTkLabel(frame_dashboard, text="", font=("Roboto", 12))

    lbl_titulo_dash.pack(pady=10)
    lbl_info_dash.pack(pady=5)
    lbl_ruta_dash.pack(pady=(0, 10))

    # La grilla de entregas (Scrollable Frame)
    frame_lista = ctk.CTkScrollableFrame(
        frame_dashboard, label_text="Entregas Recibidas (Actualización en tiempo real)"
    )
    frame_lista.pack(pady=10, padx=20, fill="both", expand=True)

    def actualizar_grilla():
        """Consulta SQLite y redibuja la lista si hay entregas nuevas."""
        if not ventana.ruta_db:
            return

        try:
            conn = sqlite3.connect(ventana.ruta_db)
            cursor = conn.cursor()

            # Optimizamos: solo redibujamos si el conteo de entregas activas cambió
            cursor.execute("SELECT COUNT(*) FROM entregas WHERE es_activa = 1")
            conteo_actual = cursor.fetchone()[0]

            if conteo_actual != ventana.ultimo_conteo:
                ventana.ultimo_conteo = conteo_actual

                # Limpiamos todos los datos viejos de la grilla
                for widget in frame_lista.winfo_children():
                    widget.destroy()

                # Dibujamos los encabezados
                encabezados = [
                    "Legajo/DNI",
                    "Apellidos",
                    "Nombres",
                    "Hora",
                    "Comprobante",
                    "Alerta IP",
                ]
                for col, texto in enumerate(encabezados):
                    ctk.CTkLabel(
                        frame_lista, text=texto, font=("Roboto", 14, "bold")
                    ).grid(row=0, column=col, padx=10, pady=5, sticky="w")

                # Buscamos las entregas activas cruzando las dos tablas
                cursor.execute("""
                    SELECT a.legajo, a.apellidos, a.nombres, e.timestamp, e.codigo_comprobante, a.ip_vinculada, e.ip_origen
                    FROM entregas e
                    JOIN alumnos a ON e.legajo = a.legajo
                    WHERE e.es_activa = 1
                    ORDER BY e.timestamp DESC
                """)

                # Dibujamos fila por fila
                for fila_idx, fila_datos in enumerate(cursor.fetchall(), start=1):
                    (
                        legajo,
                        apellidos,
                        nombres,
                        timestamp,
                        comprobante,
                        ip_vinculada,
                        ip_origen,
                    ) = fila_datos

                    # Extraemos solo HH:MM:SS del timestamp "YYYY-MM-DD HH:MM:SS.mmmmmm"
                    hora_str = str(timestamp)[11:19]

                    # Chequeo de seguridad visual (Suplantación S1)
                    alerta_ip = "⚠️ Difiere" if ip_vinculada != ip_origen else "OK"
                    color_ip = "orange" if ip_vinculada != ip_origen else "gray"

                    ctk.CTkLabel(frame_lista, text=legajo).grid(
                        row=fila_idx, column=0, padx=10, pady=2, sticky="w"
                    )
                    ctk.CTkLabel(frame_lista, text=apellidos).grid(
                        row=fila_idx, column=1, padx=10, pady=2, sticky="w"
                    )
                    ctk.CTkLabel(frame_lista, text=nombres).grid(
                        row=fila_idx, column=2, padx=10, pady=2, sticky="w"
                    )
                    ctk.CTkLabel(frame_lista, text=hora_str).grid(
                        row=fila_idx, column=3, padx=10, pady=2, sticky="w"
                    )
                    ctk.CTkLabel(
                        frame_lista, text=comprobante, font=("Consolas", 12)
                    ).grid(row=fila_idx, column=4, padx=10, pady=2, sticky="w")
                    ctk.CTkLabel(frame_lista, text=alerta_ip, text_color=color_ip).grid(
                        row=fila_idx, column=5, padx=10, pady=2, sticky="w"
                    )

            conn.close()
        except Exception as e:
            logging.error(f"Error actualizando grilla: {e}")

        # Programamos el próximo chequeo en 3000 ms (3 segundos)
        ventana.after(3000, actualizar_grilla)

    def iniciar_sistema():
        """Valida los datos, arranca el servidor y cambia la pantalla."""
        turno = entrada_turno.get().strip().upper()
        aula = entrada_aula.get().strip().upper()
        modulo = var_modulo.get()

        if not turno or not aula:
            lbl_error.configure(text="Error: Debe completar el Turno y el Aula.")
            return

        # 1. Inicializamos entorno y base de datos local
        ruta_carpeta, ruta_db, pin_sesion = inicializar_entorno(modulo, turno, aula)
        ventana.ruta_db = ruta_db  # Guardamos la ruta para que la lea la grilla

        app = crear_app(
            modulo_elegido=modulo,
            pin_fijo=pin_sesion,
            carpeta_elegida=ruta_carpeta,
            ruta_db=ruta_db,
        )
        ip_local = obtener_ip_local()

        # 2. Arrancar servidor web en hilo secundario
        hilo_web = threading.Thread(target=ejecutar_waitress, args=(app,), daemon=True)
        hilo_web.start()

        # 3. Transición de interfaz gráfica
        ventana.title(f"SEEP - Panel Docente | Módulo: {modulo.upper()} | Aula: {aula}")
        frame_config.pack_forget()
        frame_dashboard.pack(pady=20, padx=20, fill="both", expand=True)

        # 4. Poblar el dashboard con la información de la sesión
        lbl_info_dash.configure(text=f"IP: {ip_local}   |   PIN: {pin_sesion}")
        lbl_ruta_dash.configure(text=f"Guardando en: {ruta_carpeta}")

        # 5. Disparamos el bucle infinito y no-bloqueante de la grilla
        actualizar_grilla()

    btn_iniciar = ctk.CTkButton(
        frame_config,
        text="Iniciar Servidor",
        command=iniciar_sistema,
        font=("Roboto", 14, "bold"),
    )
    btn_iniciar.pack(pady=20)

    ventana.mainloop()


if __name__ == "__main__":
    arrancar_servidor()
