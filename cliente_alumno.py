import os
import threading
import requests

# CustomTkinter es un fork de Tkinter
import customtkinter as ctk
from tkinter import filedialog

# --- CONFIGURACIÓN DE LA NUBE ---
# Reemplazá esta URL por la que te asigne Render cuando subas el SEEP-Buffer
URL_NUBE = ""
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class AppAlumno(ctk.CTk):
    """
    Clase principal de la interfaz gráfica del Cliente Alumno del SEEP.
    Gestiona la captura de datos del estudiante, la selección validada del archivo
    y la transmisión segura del mismo hacia el servidor puente en la nube.
    """

    def __init__(self):
        super().__init__()

        self.title("SEEP - Taller de Programación")
        self.geometry("500x620")  # Altura reducida al quitar el campo IP
        self.resizable(False, False)

        self.ruta_archivo = None

        self.lbl_titulo = ctk.CTkLabel(
            self, text="Entrega de Parcial", font=("Roboto", 24, "bold")
        )
        self.lbl_titulo.pack(pady=(20, 10))

        self.frame_form = ctk.CTkFrame(self)
        self.frame_form.pack(pady=10, padx=20, fill="both")

        # --- SE ELIMINÓ EL CAMPO IP ---

        self.lbl_pin = ctk.CTkLabel(
            self.frame_form, text="PIN de Seguridad:", anchor="w"
        )
        self.lbl_pin.pack(pady=(15, 0), padx=20, fill="x")

        self.entry_pin = ctk.CTkEntry(
            self.frame_form, placeholder_text="Ingrese el PIN", show="*"
        )
        self.entry_pin.pack(pady=(5, 10), padx=20, fill="x")

        self.lbl_apellidos = ctk.CTkLabel(
            self.frame_form, text="Apellidos:", anchor="w"
        )
        self.lbl_apellidos.pack(pady=0, padx=20, fill="x")
        self.entry_apellidos = ctk.CTkEntry(
            self.frame_form, placeholder_text="Pérez García"
        )
        self.entry_apellidos.pack(pady=(5, 10), padx=20, fill="x")

        self.lbl_nombres = ctk.CTkLabel(self.frame_form, text="Nombres:", anchor="w")
        self.lbl_nombres.pack(pady=0, padx=20, fill="x")
        self.entry_nombres = ctk.CTkEntry(
            self.frame_form, placeholder_text="Juan Martín"
        )
        self.entry_nombres.pack(pady=(5, 10), padx=20, fill="x")

        self.lbl_id = ctk.CTkLabel(self.frame_form, text="Legajo o DNI:", anchor="w")
        self.lbl_id.pack(pady=0, padx=20, fill="x")
        self.entry_id = ctk.CTkEntry(
            self.frame_form, placeholder_text="Ej: 12345/6 o 40123456"
        )
        self.entry_id.pack(pady=(5, 10), padx=20, fill="x")

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

    def al_cambiar_modulo(self, _):
        self.ruta_archivo = None
        self.lbl_archivo_seleccionado.configure(
            text="Ningún archivo seleccionado", text_color="gray"
        )
        self.mostrar_estado("", "gray")

    def seleccionar_archivo(self):
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

            if (
                modulo_seleccionado == "Imperativo"
                and not nombre_archivo.lower().endswith(".pas")
            ):
                self.marcar_error_archivo("Error: El archivo debe ser .pas")
                return
            elif (
                modulo_seleccionado == "Objetos"
                and not nombre_archivo.lower().endswith(".zip")
            ):
                self.marcar_error_archivo("Error: El archivo debe ser .zip")
                return
            elif modulo_seleccionado == "Concurrente" and "." in nombre_archivo:
                self.marcar_error_archivo(
                    "Error: Seleccioná el archivo de R-Info (sin extensión)"
                )
                return

            if os.path.getsize(ruta) > 1048576:
                self.marcar_error_archivo("Error: El archivo pesa más de 1MB")
                return

            self.ruta_archivo = ruta
            self.lbl_archivo_seleccionado.configure(
                text=f"📁 {nombre_archivo}", text_color="white"
            )
            self.mostrar_estado("", "gray")

    def marcar_error_archivo(self, mensaje):
        self.mostrar_estado(mensaje, "#e74c3c")
        self.ruta_archivo = None
        self.lbl_archivo_seleccionado.configure(
            text="Ningún archivo seleccionado", text_color="gray"
        )

    def mostrar_estado(self, mensaje, color):
        self.lbl_estado.configure(text=mensaje, text_color=color)

    def iniciar_entrega(self):
        pin = self.entry_pin.get().strip()
        apellidos = self.entry_apellidos.get().strip()
        nombres = self.entry_nombres.get().strip()
        identificador = self.entry_id.get().strip()

        if not all([pin, apellidos, nombres, identificador]):
            self.mostrar_estado("Error: Completá todos los campos", "#e74c3c")
            return

        if not self.ruta_archivo:
            self.mostrar_estado("Error: Seleccioná tu archivo del parcial", "#e74c3c")
            return

        self.btn_enviar.configure(state="disabled", text="Enviando...")
        self.mostrar_estado("Conectando con la nube...", "#f1c40f")

        hilo = threading.Thread(
            target=self.enviar_red,
            args=(pin, apellidos, nombres, identificador, self.ruta_archivo),
        )
        hilo.start()

    def enviar_red(self, pin, apellidos, nombres, identificador, ruta):
        try:
            with open(ruta, "rb") as f:
                # El buffer.py espera que la clave del archivo sea 'archivo'
                archivos = {"archivo": f}

                # Las claves del form de datos se ajustan a lo que espera buffer.py
                datos = {
                    "pin": pin,
                    "apellidos": apellidos,
                    "nombres": nombres,
                    "legajo": identificador,
                }

                # Timeout de 15 segundos para contemplar conexiones de internet lentas
                respuesta = requests.post(
                    URL_NUBE, data=datos, files=archivos, timeout=15
                )

                if respuesta.status_code == 200:
                    self.after(
                        0, lambda: self.mostrar_estado("✅ Entrega exitosa.", "#2ecc71")
                    )
                    self.after(0, lambda: self.btn_enviar.configure(text="Entregado"))
                else:
                    # buffer.py devuelve el error en texto plano (ej: "PIN inválido o buzón cerrado")
                    msg_error = respuesta.text
                    self.after(
                        0,
                        lambda: self.mostrar_estado(
                            f"❌ Error: {msg_error}", "#e74c3c"
                        ),
                    )
                    self.after(0, self.reactivar_boton)

        except requests.exceptions.Timeout:
            self.after(
                0,
                lambda: self.mostrar_estado(
                    "❌ Tiempo de espera agotado. Verificá tu internet.", "#e74c3c"
                ),
            )
            self.after(0, self.reactivar_boton)
        except requests.exceptions.ConnectionError:
            self.after(
                0,
                lambda: self.mostrar_estado(
                    "❌ No hay conexión a internet.", "#e74c3c"
                ),
            )
            self.after(0, self.reactivar_boton)
        except Exception as e:
            self.after(
                0,
                lambda: self.mostrar_estado(
                    f"❌ Error inesperado: {str(e)}", "#e74c3c"
                ),
            )
            self.after(0, self.reactivar_boton)

    def reactivar_boton(self):
        self.btn_enviar.configure(state="normal", text="Reintentar Entrega")


if __name__ == "__main__":
    app = AppAlumno()
    app.mainloop()
