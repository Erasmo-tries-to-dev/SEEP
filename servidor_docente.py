"""Servidor de entregas de SEEP.

Ofrece una interfaz gráfica para configurar la sesión de evaluación y, una vez
iniciada, levanta una API Flask (servida con Waitress) que recibe las entregas
de los alumnos y las registra en una base SQLite local.
"""

import errno
import hashlib
import logging
import os
import random
import socket
import sqlite3
import sys
import threading
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk
from flask import Flask, current_app, jsonify, request
from waitress import serve

import seep_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("seep_servidor.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

CARACTERES_INVALIDOS_EN_NOMBRE = ["<", ">", ":", '"', "\\", "|", "?", "*"]
INTERVALO_ACTUALIZACION_MS = 3000
NOMBRE_ARCHIVO_DB = "seep_registro.db"


def obtener_directorio_base():
    """Devuelve la carpeta donde se encuentra el ejecutable o el script.

    Returns:
        str: Ruta absoluta del directorio base de la aplicación.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def obtener_ip_local():
    """Determina la dirección IP local de la máquina.

    Abre un socket UDP hacia una dirección no enrutable (sin enviar datos) para
    que el sistema operativo elija la interfaz de salida.

    Returns:
        str: IP local, o "127.0.0.1" si no puede determinarse.
    """
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
    """Sanitiza un texto para usarlo de forma segura en nombres de archivo y en la consola.

    Elimina caracteres nulos y saltos de línea, reemplaza tabulaciones, espacios
    y barras, y quita los caracteres no permitidos en nombres de archivo de Windows.

    Args:
        texto (str | None): Texto recibido del alumno.

    Returns:
        str: Texto sanitizado, sin espacios en los extremos. Cadena vacía si la entrada es vacía.
    """
    if not texto:
        return ""

    texto = (
        texto.replace("\0", "").replace("\n", "").replace("\r", "").replace("\t", "_")
    )
    texto = texto.replace(" ", "_").replace("/", "-")

    for caracter in CARACTERES_INVALIDOS_EN_NOMBRE:
        texto = texto.replace(caracter, "")

    return texto.strip()


def calcular_hash(archivo):
    """Calcula el hash SHA-256 de un archivo leyéndolo por bloques.

    Al terminar, rebobina el archivo al inicio para que pueda volver a leerse.

    Args:
        archivo: Objeto de archivo abierto en modo binario (o similar con read/seek).

    Returns:
        str: Hash SHA-256 en hexadecimal.
    """
    sha256_hash = hashlib.sha256()
    for bloque in iter(lambda: archivo.read(4096), b""):
        sha256_hash.update(bloque)
    archivo.seek(0)
    return sha256_hash.hexdigest()


def _generar_pin():
    """Genera un PIN numérico de 4 dígitos para la sesión.

    Returns:
        str: PIN entre "1000" y "9999".
    """
    return str(random.randint(1000, 9999))


def _crear_esquema(cursor):
    """Crea las tablas de una base de datos de sesión nueva.

    Args:
        cursor (sqlite3.Cursor): Cursor abierto sobre la base de datos.
    """
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


def inicializar_entorno(modulo, turno, aula):
    """Crea la carpeta de la sesión y prepara su base de datos SQLite.

    Si la base ya existe (la sesión se reabrió el mismo día), recupera el PIN
    original en lugar de generar uno nuevo.

    Args:
        modulo (str): Módulo a evaluar (ej. "imperativo").
        turno (str): Turno de cursada (ej. "TA").
        aula (str): Aula de la sesión (ej. "LAB3").

    Returns:
        tuple[str, str, str]: Ruta de la carpeta de sesión, ruta de la base de datos y PIN.
    """
    fecha_hoy = datetime.now().strftime("%Y%m%d")

    nombre_carpeta = f"entregas_{modulo}_{fecha_hoy}_{turno}_{aula}"
    ruta_carpeta = os.path.join(obtener_directorio_base(), nombre_carpeta)
    os.makedirs(ruta_carpeta, exist_ok=True)

    ruta_db = os.path.join(ruta_carpeta, NOMBRE_ARCHIVO_DB)
    db_existe = os.path.exists(ruta_db)

    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()

    if not db_existe:
        _crear_esquema(cursor)
        pin_sesion = _generar_pin()
        cursor.execute(
            """
            INSERT INTO configuracion (pin, modulo, fecha, turno, aula)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pin_sesion, modulo, fecha_hoy, turno, aula),
        )
        conn.commit()
    else:
        cursor.execute("SELECT pin FROM configuracion LIMIT 1")
        resultado = cursor.fetchone()
        pin_sesion = resultado[0] if resultado else _generar_pin()

    conn.close()
    return ruta_carpeta, ruta_db, pin_sesion


def _respuesta_version_incompatible(version_cliente):
    """Arma la respuesta HTTP 426 para clientes con una versión distinta a la del servidor.

    Args:
        version_cliente (str | None): Versión informada por el cliente.

    Returns:
        tuple: Respuesta JSON y código de estado 426.
    """
    return (
        jsonify(
            {
                "error": f"Versión del cliente ({version_cliente}) incompatible. "
                f"El servidor requiere la versión {seep_config.VERSION_SEEP}. "
                "Pedí el nuevo programa."
            }
        ),
        426,
    )


def crear_app(modulo_elegido, pin_fijo, carpeta_elegida, ruta_db):
    """Crea y configura la aplicación Flask de recepción de entregas (application factory).

    Args:
        modulo_elegido (str): Módulo activo de la sesión.
        pin_fijo (str): PIN que deben ingresar los alumnos.
        carpeta_elegida (str): Carpeta donde se guardan los archivos entregados.
        ruta_db (str): Ruta de la base de datos SQLite de la sesión.

    Returns:
        Flask: Instancia de la aplicación lista para servirse.
    """
    app = Flask(__name__)
    app.config["PIN"] = pin_fijo
    app.config["MODULO"] = modulo_elegido
    app.config["CARPETA_ENTREGAS"] = carpeta_elegida
    app.config["RUTA_DB"] = ruta_db
    app.config["MAX_CONTENT_LENGTH"] = seep_config.MAX_TAMANO_BYTES

    os.makedirs(carpeta_elegida, exist_ok=True)

    @app.route("/ping", methods=["GET"])
    def ping():
        """Verifica que el servidor esté activo y que la versión del cliente sea compatible."""
        version_cliente = request.args.get("version", "")

        if version_cliente != seep_config.VERSION_SEEP:
            logging.warning(
                f"Ping rechazado por versión incompatible: {version_cliente} vs {seep_config.VERSION_SEEP}"
            )
            return _respuesta_version_incompatible(version_cliente)

        return jsonify({"status": "ok", "mensaje": "Servidor activo"}), 200

    @app.route("/upload", methods=["POST"])
    def upload():
        """Recibe una entrega de alumno, la valida y la registra en la base de datos.

        Flujo: valida versión, PIN y datos; aplica la política de reentregas;
        guarda el archivo de forma atómica y registra la entrega. Devuelve un
        código de comprobante de 6 caracteres si todo sale bien.

        Returns:
            tuple: Respuesta JSON con el resultado y el código de estado HTTP.
        """
        version_cliente = request.form.get("version")

        if version_cliente != seep_config.VERSION_SEEP:
            logging.warning(
                f"Intento de conexión con versión incompatible: {version_cliente} vs {seep_config.VERSION_SEEP}"
            )
            return _respuesta_version_incompatible(version_cliente)

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
        es_valido, resultado_validacion = seep_config.validar_extension(
            archivo.filename, modulo_activo
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
        codigo_comprobante = hash_archivo[:6].upper()

        try:
            conn = sqlite3.connect(current_app.config["RUTA_DB"])
            cursor = conn.cursor()

            cursor.execute(
                "SELECT reentrega_habilitada FROM alumnos WHERE legajo = ?",
                (id_seguro,),
            )
            resultado_alumno = cursor.fetchone()

            if resultado_alumno is not None:
                tiene_permiso = resultado_alumno[0]
                if tiene_permiso == 0:
                    conn.close()
                    logging.warning(
                        f"Reentrega bloqueada para {apellidos_seguro} ({id_seguro}) - IP: {ip_cliente}"
                    )
                    return (
                        jsonify(
                            {
                                "error": "Ya registramos una entrega tuya. Si necesitás reentregar, levantá la mano y pedile autorización al docente."
                            }
                        ),
                        403,
                    )
                cursor.execute(
                    "UPDATE alumnos SET reentrega_habilitada = 0 WHERE legajo = ?",
                    (id_seguro,),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO alumnos (legajo, apellidos, nombres, ip_vinculada, hostname_vinculado, reentrega_habilitada)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (
                        id_seguro,
                        apellidos_seguro,
                        nombres_seguro,
                        ip_cliente,
                        hostname_seguro,
                    ),
                )

            cursor.execute(
                "UPDATE entregas SET es_activa = 0 WHERE legajo = ?", (id_seguro,)
            )

            archivo.save(ruta_temporal)
            os.replace(ruta_temporal, ruta_guardado)

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
    """Sirve la aplicación con Waitress y, si falla el arranque, muestra el error al docente.

    Pensada para ejecutarse en un hilo secundario. Ante un error de red o de
    puerto muestra un cuadro de diálogo y finaliza el proceso.

    Args:
        app (Flask): Aplicación a servir.
    """
    try:
        serve(app, host="0.0.0.0", port=seep_config.PUERTO_API)
    except OSError as e:
        _mostrar_error_arranque(e)
        os._exit(1)


def _mostrar_error_arranque(error):
    """Muestra un cuadro de error explicando por qué no pudo iniciarse el servidor.

    Args:
        error (OSError): Excepción capturada al intentar servir la aplicación.
    """
    es_puerto_ocupado = (getattr(error, "errno", None) == errno.EADDRINUSE) or (
        getattr(error, "winerror", None) == 10048
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
        messagebox.showerror("❌ ERROR CRÍTICO - Puerto Ocupado", mensaje)
    else:
        mensaje = (
            "Ocurrió un error inesperado a nivel de sistema operativo o red.\n\n"
            f"Detalle técnico: {str(error)}\n\n"
            "Sugerencia: Verifique su conexión de red o permisos de administrador."
        )
        messagebox.showerror("❌ ERROR CRÍTICO", mensaje)


def arrancar_servidor():
    """Punto de entrada principal.

    Muestra la pantalla de configuración de la sesión; al iniciar, levanta el
    servidor web en segundo plano y cambia al panel docente, que muestra las
    entregas en tiempo real.
    """
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    ventana = ctk.CTk()
    ventana.title("SEEP - Configuración Inicial")
    ventana.geometry("700x500")

    estado = {"ruta_db": None, "ultimo_conteo": -1}

    frame_config = ctk.CTkFrame(ventana)
    frame_config.pack(pady=40, padx=40, fill="both", expand=True)

    ctk.CTkLabel(
        frame_config, text="Configuración de la Sesión", font=("Roboto", 24, "bold")
    ).pack(pady=20)

    ctk.CTkLabel(frame_config, text="Módulo a evaluar:").pack(pady=(10, 0))
    var_modulo = ctk.StringVar(value="imperativo")
    ctk.CTkOptionMenu(
        frame_config,
        values=["imperativo", "objetos", "concurrente"],
        variable=var_modulo,
    ).pack(pady=5)

    ctk.CTkLabel(frame_config, text="Turno (ej. TA, TB):").pack(pady=(10, 0))
    entrada_turno = ctk.CTkEntry(frame_config, placeholder_text="Ingrese turno...")
    entrada_turno.pack(pady=5)

    ctk.CTkLabel(frame_config, text="Aula (ej. Lab3):").pack(pady=(10, 0))
    entrada_aula = ctk.CTkEntry(frame_config, placeholder_text="Ingrese aula...")
    entrada_aula.pack(pady=5)

    lbl_error = ctk.CTkLabel(frame_config, text="", text_color="red")
    lbl_error.pack(pady=5)

    frame_dashboard = ctk.CTkFrame(ventana)

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

    frame_lista = ctk.CTkScrollableFrame(
        frame_dashboard, label_text="Entregas Recibidas (Actualización en tiempo real)"
    )
    frame_lista.pack(pady=10, padx=20, fill="both", expand=True)

    def habilitar_reentrega(legajo_alumno, nombres, apellidos):
        """Habilita una única reentrega para un alumno y avisa al docente.

        Args:
            legajo_alumno (str): Legajo o DNI del alumno.
            nombres (str): Nombres del alumno, para el mensaje.
            apellidos (str): Apellidos del alumno, para el mensaje.
        """
        if not estado["ruta_db"]:
            return
        try:
            conn = sqlite3.connect(estado["ruta_db"])
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE alumnos SET reentrega_habilitada = 1 WHERE legajo = ?",
                (legajo_alumno,),
            )
            conn.commit()
            conn.close()

            messagebox.showinfo(
                "Reentrega Autorizada",
                f"Se habilitó UNA (1) nueva entrega para:\n{apellidos}, {nombres}\n(Legajo/DNI: {legajo_alumno}).\n\nEl alumno ya puede darle a 'Entregar' en su computadora.",
            )
        except Exception as e:
            logging.error(f"Error habilitando reentrega: {e}")
            messagebox.showerror(
                "Error de Base de Datos", f"No se pudo habilitar: {str(e)}"
            )

    def dibujar_encabezados():
        """Dibuja la fila de títulos de la grilla de entregas."""
        encabezados = [
            "Legajo/DNI",
            "Apellidos",
            "Nombres",
            "Hora",
            "Comprobante",
            "Alerta IP",
            "Acciones",
        ]
        for col, texto in enumerate(encabezados):
            ctk.CTkLabel(frame_lista, text=texto, font=("Roboto", 14, "bold")).grid(
                row=0, column=col, padx=10, pady=5, sticky="w"
            )

    def dibujar_fila(indice, fila):
        """Dibuja una entrega en la grilla.

        Args:
            indice (int): Número de fila (1 en adelante; la 0 es el encabezado).
            fila (tuple): Datos de la entrega, en el orden de la consulta de actualizar_grilla.
        """
        legajo, apellidos, nombres, timestamp, comprobante, ip_vinculada, ip_origen = (
            fila
        )

        hora_str = str(timestamp)[11:19]
        ip_difiere = ip_vinculada != ip_origen
        alerta_ip = "⚠️ Difiere" if ip_difiere else "OK"
        color_ip = "orange" if ip_difiere else "gray"

        celdas = [
            (ctk.CTkLabel(frame_lista, text=legajo), 0),
            (ctk.CTkLabel(frame_lista, text=apellidos), 1),
            (ctk.CTkLabel(frame_lista, text=nombres), 2),
            (ctk.CTkLabel(frame_lista, text=hora_str), 3),
            (ctk.CTkLabel(frame_lista, text=comprobante, font=("Consolas", 12)), 4),
            (ctk.CTkLabel(frame_lista, text=alerta_ip, text_color=color_ip), 5),
        ]
        for widget, col in celdas:
            widget.grid(row=indice, column=col, padx=10, pady=2, sticky="w")

        ctk.CTkButton(
            frame_lista,
            text="Habilitar",
            width=80,
            fg_color="#8B0000",
            hover_color="#FF0000",
            command=lambda l=legajo, n=nombres, a=apellidos: habilitar_reentrega(
                l, n, a
            ),
        ).grid(row=indice, column=6, padx=10, pady=2, sticky="w")

    def actualizar_grilla():
        """Consulta SQLite y redibuja la grilla solo si cambió la cantidad de entregas.

        Se reprograma a sí misma cada INTERVALO_ACTUALIZACION_MS milisegundos.
        """
        if not estado["ruta_db"]:
            return

        try:
            conn = sqlite3.connect(estado["ruta_db"])
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM entregas")
                conteo_actual = cursor.fetchone()[0]

                if conteo_actual != estado["ultimo_conteo"]:
                    estado["ultimo_conteo"] = conteo_actual

                    for widget in frame_lista.winfo_children():
                        widget.destroy()

                    dibujar_encabezados()

                    cursor.execute("""
                        SELECT a.legajo, a.apellidos, a.nombres, e.timestamp, e.codigo_comprobante, a.ip_vinculada, e.ip_origen
                        FROM entregas e
                        JOIN alumnos a ON e.legajo = a.legajo
                        WHERE e.es_activa = 1
                        ORDER BY e.timestamp DESC
                    """)
                    for indice, fila in enumerate(cursor.fetchall(), start=1):
                        dibujar_fila(indice, fila)
            finally:
                conn.close()
        except Exception as e:
            logging.error(f"Error actualizando grilla: {e}")

        ventana.after(INTERVALO_ACTUALIZACION_MS, actualizar_grilla)

    def iniciar_sistema():
        """Valida los datos de configuración, arranca el servidor y cambia al panel docente."""
        turno = entrada_turno.get().strip().upper()
        aula = entrada_aula.get().strip().upper()
        modulo = var_modulo.get()

        if not turno or not aula:
            lbl_error.configure(text="Error: Debe completar el Turno y el Aula.")
            return

        ruta_carpeta, ruta_db, pin_sesion = inicializar_entorno(modulo, turno, aula)
        estado["ruta_db"] = ruta_db

        app = crear_app(
            modulo_elegido=modulo,
            pin_fijo=pin_sesion,
            carpeta_elegida=ruta_carpeta,
            ruta_db=ruta_db,
        )
        ip_local = obtener_ip_local()

        threading.Thread(target=ejecutar_waitress, args=(app,), daemon=True).start()

        ventana.title(f"SEEP - Panel Docente | Módulo: {modulo.upper()} | Aula: {aula}")
        frame_config.pack_forget()
        frame_dashboard.pack(pady=20, padx=20, fill="both", expand=True)

        lbl_info_dash.configure(text=f"IP: {ip_local}   |   PIN: {pin_sesion}")
        lbl_ruta_dash.configure(text=f"Guardando en: {ruta_carpeta}")

        actualizar_grilla()

    ctk.CTkButton(
        frame_config,
        text="Iniciar Servidor",
        command=iniciar_sistema,
        font=("Roboto", 14, "bold"),
    ).pack(pady=20)

    ventana.mainloop()


if __name__ == "__main__":
    arrancar_servidor()
