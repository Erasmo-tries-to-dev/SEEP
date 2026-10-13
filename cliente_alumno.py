import os
import threading
import requests
import queue
import socket
import logging

# Configuración del log físico para auditoría en la PC del alumno
logging.basicConfig(
    filename="seep_cliente.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)

import seep_config
from tkinter import messagebox
import customtkinter as ctk
from tkinter import filedialog

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class AppAlumno(ctk.CTk):
    """
    Clase principal de la interfaz gráfica del Cliente Alumno del SEEP.
    Gestiona la captura de datos del estudiante, la selección validada del archivo
    y la transmisión segura del mismo hacia el servidor docente.
    """

    def __init__(self):
        """
        Inicializa la ventana principal, define sus dimensiones y construye
        todos los elementos visuales (etiquetas, campos de texto y botones)
        mediante generación dinámica.
        """
        super().__init__()
        logging.info("Iniciando aplicación Cliente Alumno SEEP.")

        self.title("SEEP - Taller de Programación")
        # Cambiamos 500x700 por 500x600 y permitimos redimensionar el alto (True)
        self.geometry("500x600")
        self.resizable(False, True)

        self.ruta_archivo = None
        self.entradas = {}  # Diccionario para guardar referencias a los CTkEntry

        self.lbl_titulo = ctk.CTkLabel(
            self, text="Entrega de Parcial", font=("Roboto", 24, "bold")
        )
        self.lbl_titulo.pack(pady=(20, 10))

        self.frame_form = ctk.CTkFrame(self)
        self.frame_form.pack(pady=10, padx=20, fill="both")

        # ---------------------------------------------------------
        # REFACTOR: Generación dinámica de los campos del formulario
        # ---------------------------------------------------------
        campos_formulario = [
            {
                "id": "ip",
                "label": "IP:",
                "placeholder": "Ej: Ver pizarrón o preguntar a docente",
                "is_password": False,
            },
            {
                "id": "pin",
                "label": "PIN de Seguridad:",
                "placeholder": "Ingrese el PIN",
                "is_password": True,
            },
            {
                "id": "apellidos",
                "label": "Apellidos:",
                "placeholder": "Pérez García",
                "is_password": False,
            },
            {
                "id": "nombres",
                "label": "Nombres:",
                "placeholder": "Juan Martín",
                "is_password": False,
            },
            {
                "id": "identificador",
                "label": "Legajo o DNI:",
                "placeholder": "Ej: 12345/6 o 40123456",
                "is_password": False,
            },
        ]

        for i, campo in enumerate(campos_formulario):
            # El primer label tiene un margen superior un poco más grande
            pad_top = 15 if i == 0 else 0

            lbl = ctk.CTkLabel(self.frame_form, text=campo["label"], anchor="w")
            lbl.pack(pady=(pad_top, 0), padx=20, fill="x")

            entry = ctk.CTkEntry(
                self.frame_form,
                placeholder_text=campo["placeholder"],
                show="*" if campo["is_password"] else "",
            )
            entry.pack(pady=(5, 10), padx=20, fill="x")

            # Guardamos la referencia para poder extraer el texto después
            self.entradas[campo["id"]] = entry
        # ---------------------------------------------------------

        self.lbl_modulo = ctk.CTkLabel(
            self.frame_form, text="Módulo a rendir:", anchor="w"
        )
        self.lbl_modulo.pack(pady=0, padx=20, fill="x")
        self.combo_modulo = ctk.CTkOptionMenu(
            self.frame_form,
            values=["Imperativo", "Objetos", "Concurrente"],
            command=self.al_cambiar_modulo,
        )
        self.combo_modulo.pack(pady=(5, 15), padx=20, fill="x")

        self.btn_archivo = ctk.CTkButton(
            self.frame_form,
            text="Seleccionar Archivo del Parcial",
            fg_color="gray",
            hover_color="darkgray",
            command=self.seleccionar_archivo,
        )
        self.btn_archivo.pack(pady=(10, 5), padx=20)

        self.lbl_archivo_seleccionado = ctk.CTkLabel(
            self.frame_form, text="Ningún archivo seleccionado", text_color="gray"
        )
        self.lbl_archivo_seleccionado.pack(pady=(0, 15), padx=20)

        self.lbl_estado = ctk.CTkLabel(self, text="", font=("Roboto", 14, "bold"))
        self.lbl_estado.pack(pady=(5, 5))

        self.btn_enviar = ctk.CTkButton(
            self,
            text="Entregar Examen",
            font=("Roboto", 16, "bold"),
            height=40,
            command=self.iniciar_entrega,
        )
        self.btn_enviar.pack(pady=(5, 20), padx=40, fill="x")

        self.cola_mensajes = queue.Queue()
        self.procesar_cola()

    def procesar_cola(self):
        """Revisa si hay actualizaciones pendientes de otros hilos y las dibuja de forma segura."""
        try:
            while True:
                tarea = self.cola_mensajes.get_nowait()
                tarea()
        except queue.Empty:
            pass
        self.after(100, self.procesar_cola)

    def al_cambiar_modulo(self, _):
        """
        Limpia el archivo actualmente seleccionado si el alumno cambia de módulo,
        forzándolo a seleccionar un archivo que coincida con la nueva extensión requerida.
        """
        self.ruta_archivo = None
        self.lbl_archivo_seleccionado.configure(
            text="Ningún archivo seleccionado", text_color="gray"
        )
        self.mostrar_estado("", "gray")

    def seleccionar_archivo(self):
        """
        Abre el explorador de archivos nativo de Windows filtrando por la extensión
        correspondiente al módulo seleccionado. Realiza validaciones delegadas a seep_config.
        """
        modulo_seleccionado = self.combo_modulo.get()

        if modulo_seleccionado == "Imperativo":
            tipos_archivo = [("Archivos Pascal", "*.pas")]
        elif modulo_seleccionado == "Objetos":
            tipos_archivo = [("Archivos ZIP", "*.zip")]
        else:
            tipos_archivo = [("Todos los archivos", "*.*")]

        ruta = filedialog.askopenfilename(
            title="Seleccionar parcial",
            filetypes=tipos_archivo,
        )

        if ruta:
            nombre_archivo = os.path.basename(ruta)

            if os.path.getsize(ruta) > seep_config.MAX_TAMANO_BYTES:
                self.marcar_error_archivo(
                    f"Error: El archivo pesa más de {seep_config.MAX_TAMANO_MB}MB"
                )
                return

            es_valido, resultado = seep_config.validar_extension(
                nombre_archivo, modulo_seleccionado
            )
            if not es_valido:
                self.marcar_error_archivo(resultado)
                return

            self.ruta_archivo = ruta
            self.lbl_archivo_seleccionado.configure(text=f"📁 {nombre_archivo}")
            self.mostrar_estado("", "gray")
            logging.info(f"Archivo válido seleccionado: {ruta}")

    def marcar_error_archivo(self, mensaje):
        """
        Helper para mostrar mensajes de error relacionados a la selección
        del archivo y limpiar cualquier selección inválida previa.
        """
        self.mostrar_estado(mensaje, "#e74c3c")
        self.ruta_archivo = None
        self.lbl_archivo_seleccionado.configure(
            text="Ningún archivo seleccionado", text_color="gray"
        )
        logging.warning(f"Validación de archivo fallida: {mensaje}")

    def mostrar_estado(self, mensaje, color):
        """
        Actualiza el label inferior de la interfaz gráfica para comunicar
        al usuario el estado de su operación o posibles errores.
        """
        self.lbl_estado.configure(text=mensaje, text_color=color)

    def iniciar_entrega(self):
        """
        Valida que todos los campos del formulario estén completos.
        Bloquea la interfaz temporalmente y lanza un hilo secundario
        para gestionar la comunicación de red sin congelar la ventana.
        """
        # Extraemos dinámicamente los valores usando nuestro diccionario 'entradas'
        ip = self.entradas["ip"].get().strip()
        pin = self.entradas["pin"].get().strip()
        apellidos = self.entradas["apellidos"].get().strip()
        nombres = self.entradas["nombres"].get().strip()
        identificador = self.entradas["identificador"].get().strip()

        if not all([ip, pin, apellidos, nombres, identificador]):
            self.mostrar_estado("Error: Completá todos los campos", "#e74c3c")
            return

        if not self.ruta_archivo:
            self.mostrar_estado("Error: Seleccioná tu archivo del parcial", "#e74c3c")
            return

        self.btn_enviar.configure(state="disabled", text="Enviando...")
        self.mostrar_estado("Conectando con la PC del docente...", "#f1c40f")

        logging.info(f"Iniciando intento de entrega hacia {ip} para {identificador}")

        hilo = threading.Thread(
            target=self.enviar_red,
            args=(ip, pin, apellidos, nombres, identificador, self.ruta_archivo),
        )
        hilo.start()

    def enviar_red(self, ip, pin, apellidos, nombres, identificador, ruta):
        """
        Función ejecutada en segundo plano. Utiliza seep_config para los
        timeouts y puertos unificados, transmitiendo el examen al servidor.
        """
        url_ping = f"http://{ip}:{seep_config.PUERTO_API}/ping"
        url_upload = f"http://{ip}:{seep_config.PUERTO_API}/upload"

        try:
            # 1. Agregamos el parámetro de versión al ping
            respuesta_ping = requests.get(
                url_ping,
                params={"version": seep_config.VERSION_SEEP},
                timeout=seep_config.TIMEOUT_PING,
            )

            # 2. Si el servidor nos rechaza el ping (por versión vieja o cualquier otro error), abortamos
            if respuesta_ping.status_code != 200:
                try:
                    texto_error = respuesta_ping.json().get(
                        "error",
                        f"Error en el servidor (HTTP {respuesta_ping.status_code})",
                    )
                except ValueError:
                    texto_error = f"Error crítico en el servidor (HTTP {respuesta_ping.status_code})"

                logging.error(f"Ping rechazado: {texto_error}")
                self.cola_mensajes.put(
                    lambda m=texto_error: self.mostrar_estado(
                        f"❌ Error: {m}", "#e74c3c"
                    )
                )
                self.cola_mensajes.put(self.reactivar_boton)
                return  # IMPORTANTE: Salimos de la función para NO ejecutar el upload

            # Si el ping fue exitoso (200 OK), procedemos a leer y enviar el archivo
            with open(ruta, "rb") as f:
                archivos = {"file": f}
                datos = {
                    "pin": pin,
                    "apellidos": apellidos,
                    "nombres": nombres,
                    "identificador": identificador,
                    "hostname": socket.gethostname(),
                    "version": seep_config.VERSION_SEEP,
                }

                respuesta = requests.post(
                    url_upload,
                    data=datos,
                    files=archivos,
                    timeout=seep_config.TIMEOUT_UPLOAD,
                )

                if respuesta.status_code == 200:
                    datos_respuesta = respuesta.json()
                    comprobante = datos_respuesta.get("comprobante", "SIN-CODIGO")

                    logging.info(
                        f"Entrega confirmada por el servidor. Comprobante: {comprobante}"
                    )

                    self.cola_mensajes.put(
                        lambda c=comprobante: self.mostrar_estado(
                            f"✅ Entregado. Comprobante: {c}", "#2ecc71"
                        )
                    )
                    self.cola_mensajes.put(
                        lambda: self.btn_enviar.configure(
                            text="Entregado", state="disabled"
                        )
                    )
                    # Mostramos el comprobante gigante al alumno
                    self.cola_mensajes.put(
                        lambda c=comprobante: messagebox.showinfo(
                            "Entrega Exitosa",
                            f"El servidor recibió tu examen correctamente.\n\nTU COMPROBANTE ES:\n{c}\n\nPor favor, anotá este código o sacale una foto antes de cerrar el programa.",
                        )
                    )
                else:
                    try:
                        texto_error = respuesta.json().get(
                            "error", "Error en el servidor"
                        )
                    except ValueError:
                        texto_error = (
                            f"Error crítico en servidor (HTTP {respuesta.status_code})"
                        )

                    logging.error(f"Rechazo del servidor: {texto_error}")

                    # Si el servidor devolvió un 403 (candado de reentrega) mostramos un cartel evidente
                    if respuesta.status_code == 403 and "autorización" in texto_error:
                        self.cola_mensajes.put(
                            lambda m=texto_error: messagebox.showwarning(
                                "Reentrega Bloqueada", m
                            )
                        )

                    self.cola_mensajes.put(
                        lambda m=texto_error: self.mostrar_estado(
                            f"❌ Error: {m}", "#e74c3c"
                        )
                    )
                    self.cola_mensajes.put(self.reactivar_boton)

        except requests.exceptions.Timeout:
            logging.error("Timeout al intentar conectar con el servidor.")
            self.cola_mensajes.put(
                lambda: self.mostrar_estado(
                    "❌ Tiempo de espera agotado. Verificá la IP.", "#e74c3c"
                )
            )
            self.cola_mensajes.put(self.reactivar_boton)
        except requests.exceptions.ConnectionError:
            logging.error("Fallo de conexión de red (ConnectionError).")
            self.cola_mensajes.put(
                lambda: self.mostrar_estado(
                    "❌ No se pudo conectar. Verificá la IP.", "#e74c3c"
                )
            )
            self.cola_mensajes.put(self.reactivar_boton)
        except Exception as e:
            mensaje_error = str(e)
            logging.error(f"Excepción inesperada en envío: {mensaje_error}")
            self.cola_mensajes.put(
                lambda m=mensaje_error: self.mostrar_estado(
                    f"❌ Error inesperado: {m}", "#e74c3c"
                )
            )
            self.cola_mensajes.put(self.reactivar_boton)

    def reactivar_boton(self):
        """
        Restaura el botón de envío a su estado original permitiendo al alumno
        corregir sus datos y realizar un nuevo intento de entrega.
        """
        self.btn_enviar.configure(state="normal", text="Reintentar Entrega")


if __name__ == "__main__":
    app = AppAlumno()
    app.mainloop()
