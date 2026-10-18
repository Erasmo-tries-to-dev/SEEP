"""
Módulo Cliente Alumno de SEEP.
Provee la interfaz gráfica de usuario (GUI) para que el estudiante complete
sus datos, seleccione el archivo de examen y lo transmita al servidor docente.
Implementa un diseño multihilo para aislar las operaciones de red (Auto-Discovery y HTTP)
del hilo principal, asegurando que la interfaz no se congele.
"""

import logging
import os
import queue
import threading
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk

import seep_config
from cliente_modulos import cliente_red

# -----------------------------------------------------------------------------
# CONSTANTES DE CONFIGURACIÓN Y ESTILOS VISUALES
# -----------------------------------------------------------------------------
ARCHIVO_LOG: str = "seep_cliente.log"
FORMATO_LOG: str = "%(asctime)s [%(levelname)s] %(message)s"
CODIFICACION_TEXTO: str = "utf-8"

GEOMETRIA_VENTANA: str = "450x550"
INTERVALO_COLA_MS: int = 100
TIMEOUT_BUSQUEDA_SEG: int = 5

COLOR_ERROR: str = "#e74c3c"
COLOR_PROCESANDO: str = "#f1c40f"
COLOR_EXITO: str = "#2ecc71"
COLOR_NEUTRO: str = "gray"
COLOR_TEXTO_HABILITADO: Tuple[str, str] = ("black", "white")

FUENTE_TITULO: Tuple[str, int, str] = ("Roboto", 24, "bold")
FUENTE_NORMAL_BOLD: Tuple[str, int, str] = ("Roboto", 14, "bold")
FUENTE_BOTON: Tuple[str, int, str] = ("Roboto", 16, "bold")

# Nota(refactor): extraer y mover a seep_config
MODULOS_DISPONIBLES: List[str] = ["Imperativo", "Objetos", "Concurrente"]
TIPOS_ARCHIVO_POR_MODULO: Dict[str, List[Tuple[str, str]]] = {
    "Imperativo": [("Archivos Pascal", "*.pas")],
    "Objetos": [("Archivos ZIP", "*.zip")],
}
TIPOS_ARCHIVO_POR_DEFECTO: List[Tuple[str, str]] = [("Todos los archivos", "*.*")]

CAMPOS_FORMULARIO: List[Dict[str, Any]] = [
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

# -----------------------------------------------------------------------------
# CONFIGURACIÓN INICIAL DE LOGGING
# -----------------------------------------------------------------------------
logging.basicConfig(
    filename=ARCHIVO_LOG,
    level=logging.INFO,
    format=FORMATO_LOG,
    encoding=CODIFICACION_TEXTO,
)


class AppAlumno(ctk.CTk):
    """
    Ventana principal del cliente alumno.
    Captura los datos del estudiante, gestiona la validación de archivos locales,
    orquesta el descubrimiento automático del servidor y transmite el parcial.
    """

    def __init__(self) -> None:
        """
        Inicializa la ventana, construye los componentes visuales, arranca el bucle
        de procesamiento de la cola de eventos y dispara el rastreo del servidor de red.
        """
        super().__init__()
        logging.info("Iniciando aplicación Cliente Alumno SEEP.")

        self.title("SEEP - Taller de Programación")
        self.geometry(GEOMETRIA_VENTANA)
        self.resizable(False, True)

        self.ruta_archivo_seleccionado: Optional[str] = None
        self.entradas_interfaz: Dict[str, ctk.CTkEntry] = {}
        self.cola_mensajes_hilos: queue.Queue = queue.Queue()

        self._construir_interfaz()
        self.procesar_cola()

        self._iniciar_auto_discovery()

    # -----------------------------------------------------------------------------
    # AUTO-DISCOVERY (DESCUBRIMIENTO UDP)
    # -----------------------------------------------------------------------------
    def _iniciar_auto_discovery(self) -> None:
        """
        Configura visualmente la interfaz para el estado de búsqueda e inicia
        el rastreo UDP en un hilo secundario aislado.
        """
        entrada_ip = self.entradas_interfaz["ip"]
        entrada_ip.configure(state="normal")
        entrada_ip.delete(0, "end")
        entrada_ip.insert(0, "Buscando servidor en la red...")
        entrada_ip.configure(state="disabled", text_color=COLOR_PROCESANDO)

        hilo_busqueda = threading.Thread(target=self._hilo_buscar_servidor, daemon=True)
        hilo_busqueda.start()

    def _hilo_buscar_servidor(self) -> None:
        """
        Rutina de hilo secundario que ejecuta la escucha UDP y encola el resultado
        para que el hilo principal lo consuma sin bloquear la GUI.
        """
        ip_detectada_en_red = cliente_red.buscar_servidor_en_red(
            timeout_segundos=TIMEOUT_BUSQUEDA_SEG
        )
        mensaje_encolado = {"tipo": "AUTO_DISCOVERY", "ip": ip_detectada_en_red}
        self.cola_mensajes_hilos.put(mensaje_encolado)

    def _aplicar_auto_discovery(self, ip_detectada: Optional[str]) -> None:
        """
        Interpreta el resultado de la búsqueda de red y actualiza el campo IP.

        Args:
            ip_detectada (Optional[str]): Dirección IP encontrada o None si falló/expiró.
        """
        entrada_ip = self.entradas_interfaz["ip"]
        entrada_ip.configure(state="normal")
        entrada_ip.delete(0, "end")

        if ip_detectada:
            entrada_ip.insert(0, ip_detectada)
            entrada_ip.configure(state="disabled", text_color=COLOR_EXITO)
            self.mostrar_estado("Servidor detectado automáticamente", COLOR_EXITO)
        else:
            entrada_ip.configure(text_color=COLOR_TEXTO_HABILITADO)
            self.mostrar_estado("Ingresá manualmente la IP del servidor", COLOR_NEUTRO)

    # -----------------------------------------------------------------------------
    # CONSTRUCCIÓN DE COMPONENTES VISUALES
    # -----------------------------------------------------------------------------
    def _construir_interfaz(self) -> None:
        """
        Posiciona e instancia todos los widgets primarios de la ventana.
        """
        self.lbl_titulo = ctk.CTkLabel(
            self, text="Entrega de Parcial", font=FUENTE_TITULO
        )
        self.lbl_titulo.pack(pady=(15, 5))

        self.marco_formulario = ctk.CTkScrollableFrame(self)
        self.marco_formulario.pack(pady=5, padx=20, fill="both", expand=True)

        self._crear_campos_formulario()

        ctk.CTkLabel(self.marco_formulario, text="Módulo a rendir:", anchor="w").pack(
            pady=0, padx=20, fill="x"
        )
        self.combo_modulo = ctk.CTkOptionMenu(
            self.marco_formulario,
            values=MODULOS_DISPONIBLES,
            command=self.al_cambiar_modulo,
        )
        self.combo_modulo.pack(pady=(2, 10), padx=20, fill="x")

        self.btn_seleccionar_archivo = ctk.CTkButton(
            self.marco_formulario,
            text="Seleccionar Archivo del Parcial",
            fg_color="gray",
            hover_color="darkgray",
            command=self.seleccionar_archivo,
        )
        self.btn_seleccionar_archivo.pack(pady=(5, 5), padx=20)

        self.lbl_archivo_seleccionado = ctk.CTkLabel(
            self.marco_formulario,
            text="Ningún archivo seleccionado",
            text_color=COLOR_NEUTRO,
        )
        self.lbl_archivo_seleccionado.pack(pady=(0, 10), padx=20)

        self.lbl_estado_general = ctk.CTkLabel(self, text="", font=FUENTE_NORMAL_BOLD)
        self.lbl_estado_general.pack(pady=(5, 5))

        self.btn_ejecutar_entrega = ctk.CTkButton(
            self,
            text="Entregar Examen",
            font=FUENTE_BOTON,
            height=40,
            command=self.iniciar_entrega,
        )
        self.btn_ejecutar_entrega.pack(pady=(5, 15), padx=40, fill="x")

    def _crear_campos_formulario(self) -> None:
        """
        Itera sobre la configuración estructurada de campos para generar dinámicamente
        las etiquetas y los controles de entrada (Inputs).
        """
        for indice_campo, definicion_campo in enumerate(CAMPOS_FORMULARIO):
            margen_superior = 5 if indice_campo == 0 else 0

            ctk.CTkLabel(
                self.marco_formulario, text=definicion_campo["label"], anchor="w"
            ).pack(pady=(margen_superior, 0), padx=20, fill="x")
            entrada_generada = ctk.CTkEntry(
                self.marco_formulario,
                placeholder_text=definicion_campo["placeholder"],
                show="*" if definicion_campo["es_password"] else "",
            )
            entrada_generada.pack(pady=(2, 8), padx=20, fill="x")

            self.entradas_interfaz[definicion_campo["id"]] = entrada_generada

    # -----------------------------------------------------------------------------
    # MOTOR DE COINCIDENCIA DE HILOS (QUEUE PROCESSING)
    # -----------------------------------------------------------------------------
    def procesar_cola(self) -> None:
        """
        Bucle de sondeo (polling) que consume mensajes provenientes de hilos secundarios
        para actualizar la interfaz de manera segura sin violar el acceso a memoria de Tkinter.
        """
        try:
            while True:
                mensaje_recibido = self.cola_mensajes_hilos.get_nowait()

                if (
                    isinstance(mensaje_recibido, dict)
                    and mensaje_recibido.get("tipo") == "AUTO_DISCOVERY"
                ):
                    self._aplicar_auto_discovery(mensaje_recibido.get("ip"))

                elif isinstance(mensaje_recibido, cliente_red.ResultadoEntrega):
                    self._aplicar_resultado(mensaje_recibido)

        except queue.Empty:
            pass

        self.after(INTERVALO_COLA_MS, self.procesar_cola)

    # -----------------------------------------------------------------------------
    # EVENTOS Y LÓGICA DE INTERFAZ
    # -----------------------------------------------------------------------------
    def al_cambiar_modulo(self, _modulo_ignorado: str) -> None:
        """
        Restablece la selección de archivos cuando el usuario modifica la asignatura,
        obligándolo a escoger un archivo con la extensión correcta.

        Args:
            _modulo_ignorado (str): Valor actual del selector provisto por el evento (no utilizado).
        """
        self._quitar_seleccion()
        self.mostrar_estado("", COLOR_NEUTRO)

    def _quitar_seleccion(self) -> None:
        """
        Anula el archivo actualmente preparado para su envío y reinicia la vista.
        """
        self.ruta_archivo_seleccionado = None
        self.lbl_archivo_seleccionado.configure(
            text="Ningún archivo seleccionado", text_color=COLOR_NEUTRO
        )

    def seleccionar_archivo(self) -> None:
        """
        Despliega el diálogo nativo del sistema operativo para la selección de archivos.
        Filtra y valida la extensión y el tamaño del documento escogido.
        """
        modulo_activo = self.combo_modulo.get()
        tipos_permitidos = TIPOS_ARCHIVO_POR_MODULO.get(
            modulo_activo, TIPOS_ARCHIVO_POR_DEFECTO
        )

        ruta_explorador = filedialog.askopenfilename(
            title="Seleccionar parcial", filetypes=tipos_permitidos
        )

        if not ruta_explorador:
            return

        nombre_archivo_puro = os.path.basename(ruta_explorador)

        if os.path.getsize(ruta_explorador) > seep_config.MAX_TAMANO_BYTES:
            self.marcar_error_archivo(
                f"Error: El archivo pesa más de {seep_config.MAX_TAMANO_MB}MB"
            )
            return

        es_extension_valida, mensaje_validacion = seep_config.validar_extension(
            nombre_archivo_puro, modulo_activo
        )

        if not es_extension_valida:
            self.marcar_error_archivo(mensaje_validacion)
            return

        self.ruta_archivo_seleccionado = ruta_explorador
        self.lbl_archivo_seleccionado.configure(text=f"📁 {nombre_archivo_puro}")
        self.mostrar_estado("", COLOR_NEUTRO)
        logging.info(f"Archivo válido seleccionado: {ruta_explorador}")

    def marcar_error_archivo(self, mensaje_error: str) -> None:
        """
        Muestra una alerta visual ante selecciones inválidas y purga la selección.

        Args:
            mensaje_error (str): Texto explicativo del motivo de rechazo.
        """
        self.mostrar_estado(mensaje_error, COLOR_ERROR)
        self._quitar_seleccion()
        logging.warning(f"Validación de archivo fallida: {mensaje_error}")

    def mostrar_estado(self, mensaje_estado: str, color_hexadecimal: str) -> None:
        """
        Modifica el texto y color de la etiqueta de estado general de la aplicación.

        Args:
            mensaje_estado (str): Contenido textual a mostrar.
            color_hexadecimal (str): Código de color para el texto.
        """
        self.lbl_estado_general.configure(
            text=mensaje_estado, text_color=color_hexadecimal
        )

    # -----------------------------------------------------------------------------
    # ORQUESTACIÓN DE RED Y ENVÍO
    # -----------------------------------------------------------------------------
    def iniciar_entrega(self) -> None:
        """
        Punto de entrada para el ciclo de envío. Valida la completitud del formulario,
        bloquea la interfaz gráfica y delega el trabajo pesado a un hilo de red.
        """
        valores_formulario = {
            definicion["id"]: self.entradas_interfaz[definicion["id"]].get().strip()
            for definicion in CAMPOS_FORMULARIO
        }

        if not all(valores_formulario.values()):
            self.mostrar_estado("Error: Completá todos los campos", COLOR_ERROR)
            return

        if not self.ruta_archivo_seleccionado:
            self.mostrar_estado("Error: Seleccioná tu archivo del parcial", COLOR_ERROR)
            return

        self.btn_ejecutar_entrega.configure(state="disabled", text="Enviando...")
        self.mostrar_estado("Conectando con la PC del docente...", COLOR_PROCESANDO)

        dto_entrega = cliente_red.DatosEntrega(
            ip=valores_formulario["ip"],
            pin=valores_formulario["pin"],
            apellidos=valores_formulario["apellidos"],
            nombres=valores_formulario["nombres"],
            identificador=valores_formulario["identificador"],
            ruta_archivo=self.ruta_archivo_seleccionado,
        )

        logging.info(
            f"Iniciando intento de entrega hacia {dto_entrega.ip} para {dto_entrega.identificador}"
        )

        hilo_transmision = threading.Thread(
            target=self._hilo_enviar_red, args=(dto_entrega,), daemon=True
        )
        hilo_transmision.start()

    def _hilo_enviar_red(self, datos_entrega: cliente_red.DatosEntrega) -> None:
        """
        Envuelve la función bloqueante de red y transfiere el DTO de resultado a la cola.

        Args:
            datos_entrega (cliente_red.DatosEntrega): Objeto contenedor de información de entrega.
        """
        resultado_operacion = cliente_red.enviar_examen(datos_entrega)
        self.cola_mensajes_hilos.put(resultado_operacion)

    def _aplicar_resultado(self, resultado_red: cliente_red.ResultadoEntrega) -> None:
        """
        Interpreta la respuesta definitiva de la capa de red y actualiza permanentemente
        el estado visual, notificando el éxito o el rechazo al estudiante.

        Args:
            resultado_red (cliente_red.ResultadoEntrega): Objeto contenedor del dictamen del servidor.
        """
        if resultado_red.exito:
            logging.info(
                f"Entrega confirmada. Comprobante: {resultado_red.comprobante}"
            )
            self.mostrar_estado(
                f"✅ Entregado. Comprobante: {resultado_red.comprobante}", COLOR_EXITO
            )
            self.btn_ejecutar_entrega.configure(text="Entregado", state="disabled")

            mensaje_aprobacion = (
                f"El servidor recibió tu examen correctamente.\n\n"
                f"TU COMPROBANTE ES:\n{resultado_red.comprobante}\n\n"
                f"Por favor, anotá este código o sacale una foto antes de cerrar."
            )
            messagebox.showinfo("Entrega Exitosa", mensaje_aprobacion)

        else:
            logging.error(f"Rechazo del servidor: {resultado_red.mensaje_error}")
            self.mostrar_estado(f"❌ Error: {resultado_red.mensaje_error}", COLOR_ERROR)
            self.btn_ejecutar_entrega.configure(
                state="normal", text="Reintentar Entrega"
            )

            if resultado_red.bloqueado_por_reentrega:
                messagebox.showwarning(
                    "Reentrega Bloqueada", resultado_red.mensaje_error
                )


if __name__ == "__main__":
    aplicacion_cliente = AppAlumno()
    aplicacion_cliente.mainloop()
