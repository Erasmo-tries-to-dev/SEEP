"""Cliente alumno de SEEP.

Interfaz gráfica para que el alumno complete sus datos, seleccione el archivo
del parcial y lo envíe al servidor del docente. El envío de red se ejecuta en
un hilo secundario y las actualizaciones de la interfaz se devuelven al hilo
principal mediante una cola.
"""

import logging
import os
import queue
import socket
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from cliente_modulos import cliente_red
import seep_config

logging.basicConfig(
    filename="seep_cliente.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)

COLOR_ERROR = "#e74c3c"
COLOR_PROCESANDO = "#f1c40f"
COLOR_EXITO = "#2ecc71"
COLOR_NEUTRO = "gray"
INTERVALO_COLA_MS = 100

MODULOS = ["Imperativo", "Objetos", "Concurrente"]
TIPOS_ARCHIVO_POR_MODULO = {
    "Imperativo": [("Archivos Pascal", "*.pas")],
    "Objetos": [("Archivos ZIP", "*.zip")],
}
TIPOS_ARCHIVO_POR_DEFECTO = [("Todos los archivos", "*.*")]

CAMPOS_FORMULARIO = [
    {
        "id": "ip",
        "label": "IP:",
        "placeholder": "Ej: Ver pizarrón o preguntar a docente",
        "es_password": False,
    },
    {
        "id": "pin",
        "label": "PIN de Seguridad:",
        "placeholder": "Ingrese el PIN",
        "es_password": True,
    },
    {
        "id": "apellidos",
        "label": "Apellidos:",
        "placeholder": "Pérez García",
        "es_password": False,
    },
    {
        "id": "nombres",
        "label": "Nombres:",
        "placeholder": "Juan Martín",
        "es_password": False,
    },
    {
        "id": "identificador",
        "label": "Legajo o DNI:",
        "placeholder": "Ej: 12345/6 o 40123456",
        "es_password": False,
    },
]


class AppAlumno(ctk.CTk):
    """Ventana principal del cliente alumno.

    Captura los datos del estudiante, valida el archivo seleccionado y
    transmite el parcial al servidor docente.
    """

    def __init__(self):
        """Crea la ventana, construye el formulario y arranca el procesamiento de la cola."""
        super().__init__()
        logging.info("Iniciando aplicación Cliente Alumno SEEP.")

        self.title("SEEP - Taller de Programación")
        # 1. Reducimos la altura base para que entre cómoda en 14"
        self.geometry("450x550")
        self.resizable(False, True)

        self.ruta_archivo = None
        self.entradas = {}
        self.cola_mensajes = queue.Queue()

        self._construir_interfaz()
        self.procesar_cola()

    def _construir_interfaz(self):
        """Crea y ubica todos los widgets de la ventana."""
        self.lbl_titulo = ctk.CTkLabel(
            self, text="Entrega de Parcial", font=("Roboto", 24, "bold")
        )
        self.lbl_titulo.pack(pady=(15, 5))

        # 2. Cambiamos CTkFrame por CTkScrollableFrame y le agregamos expand=True
        self.frame_form = ctk.CTkScrollableFrame(self)
        self.frame_form.pack(pady=5, padx=20, fill="both", expand=True)

        self._crear_campos_formulario()

        ctk.CTkLabel(self.frame_form, text="Módulo a rendir:", anchor="w").pack(
            pady=0, padx=20, fill="x"
        )
        self.combo_modulo = ctk.CTkOptionMenu(
            self.frame_form,
            values=MODULOS,
            command=self.al_cambiar_modulo,
        )
        # 3. Compactamos los paddings (pady)
        self.combo_modulo.pack(pady=(2, 10), padx=20, fill="x")

        self.btn_archivo = ctk.CTkButton(
            self.frame_form,
            text="Seleccionar Archivo del Parcial",
            fg_color="gray",
            hover_color="darkgray",
            command=self.seleccionar_archivo,
        )
        self.btn_archivo.pack(pady=(5, 5), padx=20)

        self.lbl_archivo_seleccionado = ctk.CTkLabel(
            self.frame_form, text="Ningún archivo seleccionado", text_color=COLOR_NEUTRO
        )
        self.lbl_archivo_seleccionado.pack(pady=(0, 10), padx=20)

        self.lbl_estado = ctk.CTkLabel(self, text="", font=("Roboto", 14, "bold"))
        self.lbl_estado.pack(pady=(5, 5))

        self.btn_enviar = ctk.CTkButton(
            self,
            text="Entregar Examen",
            font=("Roboto", 16, "bold"),
            height=40,
            command=self.iniciar_entrega,
        )
        self.btn_enviar.pack(pady=(5, 15), padx=40, fill="x")

    def _crear_campos_formulario(self):
        """Crea las etiquetas y campos de texto definidos en CAMPOS_FORMULARIO."""
        for indice, campo in enumerate(CAMPOS_FORMULARIO):
            # Compactamos el margen superior del primer elemento
            pad_superior = 5 if indice == 0 else 0

            ctk.CTkLabel(self.frame_form, text=campo["label"], anchor="w").pack(
                pady=(pad_superior, 0), padx=20, fill="x"
            )
            entrada = ctk.CTkEntry(
                self.frame_form,
                placeholder_text=campo["placeholder"],
                show="*" if campo["es_password"] else "",
            )
            # Reducimos los márgenes entre input y siguiente label
            entrada.pack(pady=(2, 8), padx=20, fill="x")
            self.entradas[campo["id"]] = entrada

    def procesar_cola(self):
        """Consume objetos ResultadoEntrega de la cola y actualiza la GUI.

        Se reprograma cada INTERVALO_COLA_MS milisegundos.
        """
        try:
            while True:
                resultado = self.cola_mensajes.get_nowait()
                if isinstance(resultado, cliente_red.ResultadoEntrega):
                    self._aplicar_resultado(resultado)
        except queue.Empty:
            pass
        self.after(INTERVALO_COLA_MS, self.procesar_cola)

    def al_cambiar_modulo(self, _):
        """Descarta el archivo seleccionado al cambiar de módulo.

        Así el alumno debe elegir un archivo con la extensión que exige el nuevo módulo.

        Args:
            _ (str): Nuevo valor del selector de módulo (no se usa).
        """
        self._quitar_seleccion()
        self.mostrar_estado("", COLOR_NEUTRO)

    def _quitar_seleccion(self):
        """Olvida el archivo seleccionado y restaura el texto por defecto."""
        self.ruta_archivo = None
        self.lbl_archivo_seleccionado.configure(
            text="Ningún archivo seleccionado", text_color=COLOR_NEUTRO
        )

    def seleccionar_archivo(self):
        """Abre el explorador de archivos filtrado por el módulo y valida el archivo elegido.

        Rechaza archivos que superen el tamaño máximo o que no tengan la
        extensión requerida por el módulo.
        """
        modulo = self.combo_modulo.get()
        tipos = TIPOS_ARCHIVO_POR_MODULO.get(modulo, TIPOS_ARCHIVO_POR_DEFECTO)

        ruta = filedialog.askopenfilename(title="Seleccionar parcial", filetypes=tipos)
        if not ruta:
            return

        nombre_archivo = os.path.basename(ruta)

        if os.path.getsize(ruta) > seep_config.MAX_TAMANO_BYTES:
            self.marcar_error_archivo(
                f"Error: El archivo pesa más de {seep_config.MAX_TAMANO_MB}MB"
            )
            return

        es_valido, resultado = seep_config.validar_extension(nombre_archivo, modulo)
        if not es_valido:
            self.marcar_error_archivo(resultado)
            return

        self.ruta_archivo = ruta
        self.lbl_archivo_seleccionado.configure(text=f"📁 {nombre_archivo}")
        self.mostrar_estado("", COLOR_NEUTRO)
        logging.info(f"Archivo válido seleccionado: {ruta}")

    def marcar_error_archivo(self, mensaje):
        """Muestra un error de selección de archivo y descarta la selección actual.

        Args:
            mensaje (str): Motivo del rechazo, que se muestra al alumno.
        """
        self.mostrar_estado(mensaje, COLOR_ERROR)
        self._quitar_seleccion()
        logging.warning(f"Validación de archivo fallida: {mensaje}")

    def mostrar_estado(self, mensaje, color):
        """Actualiza la etiqueta de estado inferior.

        Args:
            mensaje (str): Texto a mostrar.
            color (str): Color del texto.
        """
        self.lbl_estado.configure(text=mensaje, text_color=color)

    def iniciar_entrega(self):
        """Valida el formulario y lanza el envío en un hilo secundario."""
        valores = {
            campo["id"]: self.entradas[campo["id"]].get().strip()
            for campo in CAMPOS_FORMULARIO
        }

        if not all(valores.values()):
            self.mostrar_estado("Error: Completá todos los campos", COLOR_ERROR)
            return

        if not self.ruta_archivo:
            self.mostrar_estado("Error: Seleccioná tu archivo del parcial", COLOR_ERROR)
            return

        self.btn_enviar.configure(state="disabled", text="Enviando...")
        self.mostrar_estado("Conectando con la PC del docente...", COLOR_PROCESANDO)

        datos = cliente_red.DatosEntrega(
            ip=valores["ip"],
            pin=valores["pin"],
            apellidos=valores["apellidos"],
            nombres=valores["nombres"],
            identificador=valores["identificador"],
            ruta_archivo=self.ruta_archivo,
        )

        logging.info(
            f"Iniciando intento de entrega hacia {datos.ip} para {datos.identificador}"
        )

        # Lanzamos el hilo como daemon para evitar bloqueos si el alumno cierra la app.
        threading.Thread(
            target=self._hilo_enviar_red, args=(datos,), daemon=True
        ).start()

    def _hilo_enviar_red(self, datos: cliente_red.DatosEntrega):
        """Ejecuta la capa de red y encola el resultado para la interfaz visual."""
        resultado = cliente_red.enviar_examen(datos)
        self.cola_mensajes.put(resultado)

    def _aplicar_resultado(self, resultado: cliente_red.ResultadoEntrega):
        """Actualiza los widgets basándose en el DTO recibido."""
        if resultado.exito:
            logging.info(f"Entrega confirmada. Comprobante: {resultado.comprobante}")
            self.mostrar_estado(
                f"✅ Entregado. Comprobante: {resultado.comprobante}", COLOR_EXITO
            )
            self.btn_enviar.configure(text="Entregado", state="disabled")
            messagebox.showinfo(
                "Entrega Exitosa",
                f"El servidor recibió tu examen correctamente.\n\nTU COMPROBANTE ES:\n{resultado.comprobante}\n\nPor favor, anotá este código o sacale una foto antes de cerrar.",
            )
        else:
            logging.error(f"Rechazo del servidor: {resultado.mensaje_error}")
            self.mostrar_estado(f"❌ Error: {resultado.mensaje_error}", COLOR_ERROR)
            self.btn_enviar.configure(state="normal", text="Reintentar Entrega")

            if resultado.bloqueado_por_reentrega:
                messagebox.showwarning("Reentrega Bloqueada", resultado.mensaje_error)


if __name__ == "__main__":
    app = AppAlumno()
    app.mainloop()
