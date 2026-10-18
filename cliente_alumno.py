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
        # 1. Reducimos la altura base para que entre cómoda en 14"[cite: 8]
        self.geometry("450x550")  # [cite: 8]
        self.resizable(False, True)  # [cite: 8]

        self.ruta_archivo = None  # [cite: 8]
        self.entradas = {}  # [cite: 8]
        self.cola_mensajes = queue.Queue()  # [cite: 8]

        self._construir_interfaz()  # [cite: 8]
        self.procesar_cola()  # [cite: 8]

        # --- NUEVO: Iniciar la búsqueda del servidor al arrancar ---
        self._iniciar_auto_discovery()

    def _iniciar_auto_discovery(self) -> None:
        """Inicia el proceso de búsqueda del servidor en un hilo secundario."""
        # Preparamos visualmente el campo IP
        entrada_ip = self.entradas["ip"]
        entrada_ip.configure(state="normal")
        entrada_ip.delete(0, "end")
        entrada_ip.insert(0, "Buscando servidor en la red...")
        entrada_ip.configure(state="disabled", text_color=COLOR_PROCESANDO)

        # Lanzamos el hilo de búsqueda
        threading.Thread(target=self._hilo_buscar_servidor, daemon=True).start()

    def _hilo_buscar_servidor(self) -> None:
        """Ejecuta la búsqueda de red y encola el resultado para la GUI."""
        ip_detectada = cliente_red.buscar_servidor_en_red(timeout_segundos=5)
        # Encolamos un diccionario simple para que procesar_cola lo interprete
        self.cola_mensajes.put({"tipo": "AUTO_DISCOVERY", "ip": ip_detectada})

    def _aplicar_auto_discovery(self, ip_detectada: str | None) -> None:
        """Actualiza la GUI según el resultado de la búsqueda de red."""
        entrada_ip = self.entradas["ip"]
        entrada_ip.configure(state="normal")
        entrada_ip.delete(0, "end")

        if ip_detectada:
            entrada_ip.insert(0, ip_detectada)
            entrada_ip.configure(state="disabled", text_color=COLOR_EXITO)
            self.mostrar_estado("Servidor detectado automáticamente", COLOR_EXITO)
        else:
            entrada_ip.configure(text_color=("black", "white"))
            # Fallback: El campo queda vacío y habilitado para ingreso manual
            self.mostrar_estado("Ingresá manualmente la IP del servidor", COLOR_NEUTRO)

    def _construir_interfaz(self):
        """Crea y ubica todos los widgets de la ventana."""
        self.lbl_titulo = ctk.CTkLabel(  # [cite: 8]
            self, text="Entrega de Parcial", font=("Roboto", 24, "bold")  # [cite: 8]
        )  # [cite: 8]
        self.lbl_titulo.pack(pady=(15, 5))  # [cite: 8]

        # 2. Cambiamos CTkFrame por CTkScrollableFrame y le agregamos expand=True[cite: 8]
        self.frame_form = ctk.CTkScrollableFrame(self)  # [cite: 8]
        self.frame_form.pack(pady=5, padx=20, fill="both", expand=True)  # [cite: 8]

        self._crear_campos_formulario()  # [cite: 8]

        ctk.CTkLabel(
            self.frame_form, text="Módulo a rendir:", anchor="w"
        ).pack(  # [cite: 8]
            pady=0, padx=20, fill="x"  # [cite: 8]
        )  # [cite: 8]
        self.combo_modulo = ctk.CTkOptionMenu(  # [cite: 8]
            self.frame_form,  # [cite: 8]
            values=MODULOS,  # [cite: 8]
            command=self.al_cambiar_modulo,  # [cite: 8]
        )  # [cite: 8]
        # 3. Compactamos los paddings (pady)[cite: 8]
        self.combo_modulo.pack(pady=(2, 10), padx=20, fill="x")  # [cite: 8]

        self.btn_archivo = ctk.CTkButton(  # [cite: 8]
            self.frame_form,  # [cite: 8]
            text="Seleccionar Archivo del Parcial",  # [cite: 8]
            fg_color="gray",  # [cite: 8]
            hover_color="darkgray",  # [cite: 8]
            command=self.seleccionar_archivo,  # [cite: 8]
        )  # [cite: 8]
        self.btn_archivo.pack(pady=(5, 5), padx=20)  # [cite: 8]

        self.lbl_archivo_seleccionado = ctk.CTkLabel(  # [cite: 8]
            self.frame_form,
            text="Ningún archivo seleccionado",
            text_color=COLOR_NEUTRO,  # [cite: 8]
        )  # [cite: 8]
        self.lbl_archivo_seleccionado.pack(pady=(0, 10), padx=20)  # [cite: 8]

        self.lbl_estado = ctk.CTkLabel(
            self, text="", font=("Roboto", 14, "bold")
        )  # [cite: 8]
        self.lbl_estado.pack(pady=(5, 5))  # [cite: 8]

        self.btn_enviar = ctk.CTkButton(  # [cite: 8]
            self,  # [cite: 8]
            text="Entregar Examen",  # [cite: 8]
            font=("Roboto", 16, "bold"),  # [cite: 8]
            height=40,  # [cite: 8]
            command=self.iniciar_entrega,  # [cite: 8]
        )  # [cite: 8]
        self.btn_enviar.pack(pady=(5, 15), padx=40, fill="x")  # [cite: 8]

    def _crear_campos_formulario(self):
        """Crea las etiquetas y campos de texto definidos en CAMPOS_FORMULARIO."""
        for indice, campo in enumerate(CAMPOS_FORMULARIO):  # [cite: 8]
            # Compactamos el margen superior del primer elemento[cite: 8]
            pad_superior = 5 if indice == 0 else 0  # [cite: 8]

            ctk.CTkLabel(
                self.frame_form, text=campo["label"], anchor="w"
            ).pack(  # [cite: 8]
                pady=(pad_superior, 0), padx=20, fill="x"  # [cite: 8]
            )  # [cite: 8]
            entrada = ctk.CTkEntry(  # [cite: 8]
                self.frame_form,  # [cite: 8]
                placeholder_text=campo["placeholder"],  # [cite: 8]
                show="*" if campo["es_password"] else "",  # [cite: 8]
            )  # [cite: 8]
            # Reducimos los márgenes entre input y siguiente label[cite: 8]
            entrada.pack(pady=(2, 8), padx=20, fill="x")  # [cite: 8]
            self.entradas[campo["id"]] = entrada  # [cite: 8]

    def procesar_cola(self):
        """Consume mensajes de la cola y actualiza la GUI.

        Se reprograma cada INTERVALO_COLA_MS milisegundos.
        """
        try:
            while True:
                mensaje = self.cola_mensajes.get_nowait()
                # --- NUEVO: Procesar el mensaje de Auto-Discovery ---
                if (
                    isinstance(mensaje, dict)
                    and mensaje.get("tipo") == "AUTO_DISCOVERY"
                ):
                    self._aplicar_auto_discovery(mensaje.get("ip"))
                # Procesar el resultado de la entrega HTTP
                elif isinstance(mensaje, cliente_red.ResultadoEntrega):
                    self._aplicar_resultado(mensaje)
        except queue.Empty:
            pass
        self.after(INTERVALO_COLA_MS, self.procesar_cola)  # [cite: 8]

    def al_cambiar_modulo(self, _):
        """Descarta el archivo seleccionado al cambiar de módulo.

        Así el alumno debe elegir un archivo con la extensión que exige el nuevo módulo.

        Args:
            _ (str): Nuevo valor del selector de módulo (no se usa).
        """
        self._quitar_seleccion()  # [cite: 8]
        self.mostrar_estado("", COLOR_NEUTRO)  # [cite: 8]

    def _quitar_seleccion(self):
        """Olvida el archivo seleccionado y restaura el texto por defecto."""
        self.ruta_archivo = None  # [cite: 8]
        self.lbl_archivo_seleccionado.configure(  # [cite: 8]
            text="Ningún archivo seleccionado", text_color=COLOR_NEUTRO  # [cite: 8]
        )  # [cite: 8]

    def seleccionar_archivo(self):
        """Abre el explorador de archivos filtrado por el módulo y valida el archivo elegido.

        Rechaza archivos que superen el tamaño máximo o que no tengan la
        extensión requerida por el módulo.
        """
        modulo = self.combo_modulo.get()  # [cite: 8]
        tipos = TIPOS_ARCHIVO_POR_MODULO.get(
            modulo, TIPOS_ARCHIVO_POR_DEFECTO
        )  # [cite: 8]

        ruta = filedialog.askopenfilename(
            title="Seleccionar parcial", filetypes=tipos
        )  # [cite: 8]
        if not ruta:  # [cite: 8]
            return  # [cite: 8]

        nombre_archivo = os.path.basename(ruta)  # [cite: 8]

        if os.path.getsize(ruta) > seep_config.MAX_TAMANO_BYTES:  # [cite: 8]
            self.marcar_error_archivo(  # [cite: 8]
                f"Error: El archivo pesa más de {seep_config.MAX_TAMANO_MB}MB"  # [cite: 8]
            )  # [cite: 8]
            return  # [cite: 8]

        es_valido, resultado = seep_config.validar_extension(
            nombre_archivo, modulo
        )  # [cite: 8]
        if not es_valido:  # [cite: 8]
            self.marcar_error_archivo(resultado)  # [cite: 8]
            return  # [cite: 8]

        self.ruta_archivo = ruta  # [cite: 8]
        self.lbl_archivo_seleccionado.configure(
            text=f"📁 {nombre_archivo}"
        )  # [cite: 8]
        self.mostrar_estado("", COLOR_NEUTRO)  # [cite: 8]
        logging.info(f"Archivo válido seleccionado: {ruta}")  # [cite: 8]

    def marcar_error_archivo(self, mensaje):
        """Muestra un error de selección de archivo y descarta la selección actual.

        Args:
            mensaje (str): Motivo del rechazo, que se muestra al alumno.
        """
        self.mostrar_estado(mensaje, COLOR_ERROR)  # [cite: 8]
        self._quitar_seleccion()  # [cite: 8]
        logging.warning(f"Validación de archivo fallida: {mensaje}")  # [cite: 8]

    def mostrar_estado(self, mensaje, color):
        """Actualiza la etiqueta de estado inferior.

        Args:
            mensaje (str): Texto a mostrar.
            color (str): Color del texto.
        """
        self.lbl_estado.configure(text=mensaje, text_color=color)  # [cite: 8]

    def iniciar_entrega(self):
        """Valida el formulario y lanza el envío en un hilo secundario."""
        valores = {  # [cite: 8]
            campo["id"]: self.entradas[campo["id"]].get().strip()  # [cite: 8]
            for campo in CAMPOS_FORMULARIO  # [cite: 8]
        }  # [cite: 8]

        if not all(valores.values()):  # [cite: 8]
            self.mostrar_estado(
                "Error: Completá todos los campos", COLOR_ERROR
            )  # [cite: 8]
            return  # [cite: 8]

        if not self.ruta_archivo:  # [cite: 8]
            self.mostrar_estado(
                "Error: Seleccioná tu archivo del parcial", COLOR_ERROR
            )  # [cite: 8]
            return  # [cite: 8]

        self.btn_enviar.configure(state="disabled", text="Enviando...")  # [cite: 8]
        self.mostrar_estado(
            "Conectando con la PC del docente...", COLOR_PROCESANDO
        )  # [cite: 8]

        datos = cliente_red.DatosEntrega(  # [cite: 8]
            ip=valores["ip"],  # [cite: 8]
            pin=valores["pin"],  # [cite: 8]
            apellidos=valores["apellidos"],  # [cite: 8]
            nombres=valores["nombres"],  # [cite: 8]
            identificador=valores["identificador"],  # [cite: 8]
            ruta_archivo=self.ruta_archivo,  # [cite: 8]
        )  # [cite: 8]

        logging.info(  # [cite: 8]
            f"Iniciando intento de entrega hacia {datos.ip} para {datos.identificador}"  # [cite: 8]
        )  # [cite: 8]

        # Lanzamos el hilo como daemon para evitar bloqueos si el alumno cierra la app.[cite: 8]
        threading.Thread(  # [cite: 8]
            target=self._hilo_enviar_red, args=(datos,), daemon=True  # [cite: 8]
        ).start()  # [cite: 8]

    def _hilo_enviar_red(self, datos: cliente_red.DatosEntrega):
        """Ejecuta la capa de red y encola el resultado para la interfaz visual."""
        resultado = cliente_red.enviar_examen(datos)  # [cite: 8]
        self.cola_mensajes.put(resultado)  # [cite: 8]

    def _aplicar_resultado(self, resultado: cliente_red.ResultadoEntrega):
        """Actualiza los widgets basándose en el DTO recibido."""
        if resultado.exito:  # [cite: 8]
            logging.info(
                f"Entrega confirmada. Comprobante: {resultado.comprobante}"
            )  # [cite: 8]
            self.mostrar_estado(  # [cite: 8]
                f"✅ Entregado. Comprobante: {resultado.comprobante}",
                COLOR_EXITO,  # [cite: 8]
            )  # [cite: 8]
            self.btn_enviar.configure(text="Entregado", state="disabled")  # [cite: 8]
            messagebox.showinfo(  # [cite: 8]
                "Entrega Exitosa",  # [cite: 8]
                f"El servidor recibió tu examen correctamente.\n\nTU COMPROBANTE ES:\n{resultado.comprobante}\n\nPor favor, anotá este código o sacale una foto antes de cerrar.",  # [cite: 8]
            )  # [cite: 8]
        else:
            logging.error(
                f"Rechazo del servidor: {resultado.mensaje_error}"
            )  # [cite: 8]
            self.mostrar_estado(
                f"❌ Error: {resultado.mensaje_error}", COLOR_ERROR
            )  # [cite: 8]
            self.btn_enviar.configure(
                state="normal", text="Reintentar Entrega"
            )  # [cite: 8]

            if resultado.bloqueado_por_reentrega:  # [cite: 8]
                messagebox.showwarning(
                    "Reentrega Bloqueada", resultado.mensaje_error
                )  # [cite: 8]


if __name__ == "__main__":
    app = AppAlumno()  # [cite: 8]
    app.mainloop()  # [cite: 8]
