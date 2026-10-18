"""
Módulo de Interfaz Gráfica (GUI) de SEEP-Servidor Docente.
Contiene la clase principal que maneja las pantallas de configuración y el dashboard.
"""

import logging
import os
from datetime import datetime
from tkinter import messagebox
from typing import Any, Optional, Tuple

import customtkinter as ctk

import seep_config
from servidor_modulos import api, persistencia

# -----------------------------------------------------------------------------
# CONSTANTES DE CONFIGURACIÓN VISUAL Y LÍMITES
# -----------------------------------------------------------------------------
# Geometría ajustada para pantallas de 14" (ThinkPads de los laboratorios)
GEOMETRIA_VENTANA: str = "1000x600"

# Intervalo de actualización de la grilla en milisegundos (3 segundos)
INTERVALO_ACTUALIZACION_MS: int = 3000

# Paleta de Colores
COLOR_EXITO: str = "green"
COLOR_ERROR: str = "red"
COLOR_ALERTA_IP_DIFIERE: str = "#FF4500"
COLOR_ALERTA_IP_OK: str = "gray"
COLOR_BOTON_PELIGRO: str = "#8B0000"
COLOR_BOTON_PELIGRO_HOVER: str = "#FF0000"

# Fuentes Tipográficas
# Roboto no esta por defecto en windows, cambiar por otra mas linda luego
FUENTE_TITULO: Tuple[str, int, str] = ("Roboto", 24, "bold")
FUENTE_SUBTITULO: Tuple[str, int, str] = ("Roboto", 18, "bold")
FUENTE_NORMAL_BOLD: Tuple[str, int, str] = ("Roboto", 14, "bold")
FUENTE_NORMAL: Tuple[str, int] = ("Roboto", 12)
FUENTE_MONOSPACE: Tuple[str, int] = ("Consolas", 12)
FUENTE_NUMERO_GRANDE: Tuple[str, int, str] = ("Roboto", 36, "bold")


class InterfazServidor(ctk.CTk):
    """
    Clase principal de la Interfaz Gráfica de Usuario (GUI) del Servidor Docente.
    Gestiona la configuración inicial, el arranque del sistema y la visualización
    en tiempo real de las entregas recibidas.
    """

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("SEEP - Configuración Inicial")
        self.geometry(GEOMETRIA_VENTANA)

        # Atributos de estado (Type Hinting para evitar globales)
        self.ruta_db: Optional[str] = None
        self.ruta_entregas: Optional[str] = None
        self.ultimo_conteo: int = -1
        self.intervalo_actualizacion: int = INTERVALO_ACTUALIZACION_MS

        # --- ATRIBUTOS PARA BÚSQUEDA Y ORDENAMIENTO ---
        self.filas_cacheadas: list = []
        self.texto_busqueda = ctk.StringVar()
        self.texto_busqueda.trace_add("write", lambda *args: self._refrescar_vista())
        self.columna_orden: int = 3  # Por defecto ordena por la Hora (índice 3)
        self.orden_descendente: bool = True

        self._construir_pantalla_config()
        self._construir_pantalla_dashboard()

    def _construir_pantalla_config(self) -> None:
        """Construye y empaqueta el formulario inicial de configuración del servidor."""
        self.frame_config = ctk.CTkFrame(self)
        self.frame_config.pack(pady=40, padx=40, fill="both", expand=True)

        ctk.CTkLabel(
            self.frame_config,
            text="Configuración de la Sesión",
            font=FUENTE_TITULO,
        ).pack(pady=20)

        ctk.CTkLabel(self.frame_config, text="Módulo a evaluar:").pack(pady=(10, 0))
        self.var_modulo = ctk.StringVar(value="imperativo")
        ctk.CTkOptionMenu(
            self.frame_config,
            values=["imperativo", "objetos", "concurrente"],
            variable=self.var_modulo,
        ).pack(pady=5)

        ctk.CTkLabel(self.frame_config, text="Turno (ej. TA, TB):").pack(pady=(10, 0))
        self.entrada_turno = ctk.CTkEntry(
            self.frame_config, placeholder_text="Ingrese turno..."
        )
        self.entrada_turno.pack(pady=5)

        ctk.CTkLabel(self.frame_config, text="Aula (ej. Lab3):").pack(pady=(10, 0))
        self.entrada_aula = ctk.CTkEntry(
            self.frame_config, placeholder_text="Ingrese aula..."
        )
        self.entrada_aula.pack(pady=5)

        self.lbl_error = ctk.CTkLabel(
            self.frame_config, text="", text_color=COLOR_ERROR
        )
        self.lbl_error.pack(pady=5)

        ctk.CTkButton(
            self.frame_config,
            text="Iniciar Servidor",
            command=self.iniciar_sistema,
            font=FUENTE_NORMAL_BOLD,
        ).pack(pady=20)

    def _construir_pantalla_dashboard(self) -> None:
        """Construye (pero no muestra) la pantalla de la grilla de entregas y el panel superior."""
        self.frame_dashboard = ctk.CTkFrame(self)

        self.lbl_titulo_dash = ctk.CTkLabel(
            self.frame_dashboard,
            text="SERVIDOR ACTIVO",
            font=FUENTE_TITULO,
            text_color=COLOR_EXITO,
        )
        self.lbl_info_dash = ctk.CTkLabel(
            self.frame_dashboard, text="", font=FUENTE_SUBTITULO
        )

        self.lbl_titulo_dash.pack(pady=10)
        self.lbl_info_dash.pack(pady=5)

        # --- PANEL DE ESTADÍSTICAS EN VIVO ---
        self.frame_estadisticas = ctk.CTkFrame(
            self.frame_dashboard, fg_color="transparent"
        )
        self.frame_estadisticas.pack(pady=10, fill="x")

        self.frame_estadisticas.grid_columnconfigure(0, weight=1)
        self.frame_estadisticas.grid_columnconfigure(1, weight=1)

        # Caja de Estadísticas: Entregas
        self.frame_entregas = ctk.CTkFrame(self.frame_estadisticas)
        self.frame_entregas.grid(row=0, column=0, padx=10, sticky="e")
        ctk.CTkLabel(
            self.frame_entregas, text="Entregas Recibidas", font=FUENTE_NORMAL_BOLD
        ).pack(pady=(5, 0), padx=20)
        self.lbl_contador_entregas = ctk.CTkLabel(
            self.frame_entregas,
            text="0",
            font=FUENTE_NUMERO_GRANDE,
            text_color=COLOR_EXITO,
        )
        self.lbl_contador_entregas.pack(pady=(0, 5))

        # Caja de Estadísticas: Alertas
        self.frame_alertas = ctk.CTkFrame(self.frame_estadisticas)
        self.frame_alertas.grid(row=0, column=1, padx=10, sticky="w")
        ctk.CTkLabel(
            self.frame_alertas, text="Alertas de Seguridad", font=FUENTE_NORMAL_BOLD
        ).pack(pady=(5, 0), padx=20)
        self.lbl_contador_alertas = ctk.CTkLabel(
            self.frame_alertas,
            text="0",
            font=FUENTE_NUMERO_GRANDE,
            text_color=COLOR_ALERTA_IP_OK,
        )
        self.lbl_contador_alertas.pack(pady=(0, 5))
        # --------------------------------------------

        # Botón para abrir la carpeta contenedora
        self.btn_abrir_carpeta = ctk.CTkButton(
            self.frame_dashboard,
            text="📁 Abrir Carpeta de Entregas",
            font=FUENTE_NORMAL_BOLD,
            fg_color="transparent",
            border_width=1,
            text_color=("black", "white"),
            command=self.abrir_carpeta_entregas,
        )
        self.btn_abrir_carpeta.pack(pady=(0, 10))

        # --- BARRA DE BÚSQUEDA SUPERIOR ---
        self.frame_controles = ctk.CTkFrame(
            self.frame_dashboard, fg_color="transparent"
        )
        self.frame_controles.pack(fill="x", padx=20, pady=(0, 5))

        self.entrada_busqueda = ctk.CTkEntry(
            self.frame_controles,
            placeholder_text="🔍 Buscar por apellido, nombre o legajo...",
            textvariable=self.texto_busqueda,
            width=350,
        )
        self.entrada_busqueda.pack(side="left")
        # ----------------------------------------

        self.frame_lista = ctk.CTkScrollableFrame(
            self.frame_dashboard,
            label_text="Entregas Recibidas (Actualización en tiempo real)",
        )
        self.frame_lista.pack(pady=10, padx=20, fill="both", expand=True)

    def abrir_carpeta_entregas(self) -> None:
        """Abre la carpeta de entregas en el explorador de archivos del sistema operativo."""
        if not self.ruta_entregas or not os.path.exists(self.ruta_entregas):
            messagebox.showerror("Error", "La carpeta no existe o no se ha creado aún.")
            return

        try:
            if os.name == "nt":  # Windows
                os.startfile(self.ruta_entregas)
            else:  # macOS / Linux
                import subprocess, sys

                comando = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([comando, self.ruta_entregas])
        except Exception as e:
            logging.error(f"No se pudo abrir la carpeta: {e}")
            messagebox.showerror("Error", f"No se pudo abrir la carpeta de destino.")

    def iniciar_sistema(self) -> None:
        """
        Callback del botón Iniciar. Valida los datos, prepara el entorno,
        inicia la base de datos, levanta el servidor web en un hilo secundario
        y realiza la transición visual al dashboard.
        """
        turno = self.entrada_turno.get().strip().upper()
        aula = self.entrada_aula.get().strip().upper()
        modulo = self.var_modulo.get()

        if not turno or not aula:
            self.lbl_error.configure(text="Error: Debe completar el Turno y el Aula.")
            return

        # Inicializamos entorno y BD a través del módulo API
        fecha_hoy = datetime.now().strftime("%Y%m%d")
        nombre_carpeta = f"entregas_{modulo}_{fecha_hoy}_{turno}_{aula}"
        ruta_carpeta = os.path.join(api.obtener_directorio_base(), nombre_carpeta)
        os.makedirs(ruta_carpeta, exist_ok=True)
        self.ruta_db = os.path.join(ruta_carpeta, "seep_registro.db")

        pin_sesion = persistencia.inicializar_base_datos(
            self.ruta_db, modulo, fecha_hoy, turno, aula, api._generar_pin()
        )

        # Arrancamos Flask y Waitress
        app = api.crear_app(modulo, pin_sesion, ruta_carpeta, self.ruta_db)
        ip_local = api.obtener_ip_local()
        api.iniciar_servidor_en_hilo(app, callback_error=self.mostrar_error_critico)

        # Transición de interfaz visual
        self.title(f"SEEP - Panel Docente | Módulo: {modulo.upper()} | Aula: {aula}")
        self.frame_config.pack_forget()
        self.frame_dashboard.pack(pady=20, padx=20, fill="both", expand=True)

        self.lbl_info_dash.configure(text=f"IP: {ip_local}   |   PIN: {pin_sesion}")
        self.ruta_entregas = ruta_carpeta

        self.actualizar_grilla()

    def mostrar_error_critico(self, titulo: str, mensaje: str) -> None:
        """Callback ejecutado desde el hilo de la API si el servidor falla al arrancar."""

        def _mostrar_y_cerrar():
            messagebox.showerror(titulo, mensaje)
            import os

            os._exit(1)

        self.after(0, _mostrar_y_cerrar)

    def habilitar_reentrega_gui(
        self, legajo_alumno: str, nombres: str, apellidos: str
    ) -> None:
        """Actualiza la base de datos para permitir una nueva entrega al alumno seleccionado."""
        if not self.ruta_db:
            return
        try:
            persistencia.habilitar_reentrega(self.ruta_db, legajo_alumno)
            messagebox.showinfo(
                "Reentrega Autorizada",
                f"Se habilitó UNA (1) nueva entrega para:\n{apellidos}, {nombres}\n"
                f"(Legajo/DNI: {legajo_alumno}).\n\nEl alumno ya puede darle a 'Entregar' en su computadora.",
            )
        except Exception as e:
            logging.error(f"Error habilitando reentrega: {e}")
            messagebox.showerror(
                "Error de Base de Datos", f"No se pudo habilitar: {str(e)}"
            )

    def mostrar_modal_alertas(
        self, legajo: str, nombres: str, apellidos: str, alertas: list
    ) -> None:
        """Despliega un modal (CTkToplevel) con los detalles de seguridad de una entrega sospechosa."""
        modal = ctk.CTkToplevel(self)
        modal.title(f"Alertas de Seguridad - {legajo}")
        modal.geometry("450x250")

        # Estas dos líneas obligan a la ventanita a quedarse arriba del panel principal
        modal.attributes("-topmost", True)
        modal.grab_set()

        ctk.CTkLabel(
            modal, text=f"Alumno: {apellidos}, {nombres}", font=FUENTE_SUBTITULO
        ).pack(pady=(20, 10))

        marco_alertas = ctk.CTkFrame(modal)
        marco_alertas.pack(padx=20, pady=10, fill="both", expand=True)

        # Listamos todas las banderas amarillas que se hayan detectado
        for alerta in alertas:
            ctk.CTkLabel(
                marco_alertas,
                text=alerta,
                text_color=COLOR_ALERTA_IP_DIFIERE,
                font=FUENTE_NORMAL_BOLD,
                justify="left",
                wraplength=380,
            ).pack(pady=5, padx=10, anchor="w")

        ctk.CTkButton(modal, text="Cerrar", command=modal.destroy).pack(pady=15)

    def _cambiar_orden(self, col_index: int) -> None:
        """Actualiza el estado de ordenamiento y refresca la vista inmediatamente."""
        if self.columna_orden == col_index:
            # Si hace clic en la misma columna, invierte el orden (Ascendente/Descendente)
            self.orden_descendente = not self.orden_descendente
        else:
            # Si cambia de columna, ordena ascendente por defecto
            self.columna_orden = col_index
            self.orden_descendente = False
        self._refrescar_vista()

    def dibujar_encabezados(self) -> None:
        """Renderiza la primera fila de la grilla con los títulos interactivos."""
        # Tupla: (Texto a mostrar, índice real en la tupla de Base de Datos)
        encabezados = [
            ("Legajo/DNI", 0),
            ("Apellidos", 1),
            ("Nombres", 2),
            ("Hora", 3),
            ("Comprobante", 4),
            ("Estado", 5),
            ("Acciones", -1),  # -1 significa que no se puede ordenar por esta columna
        ]

        for col, (texto, idx_bd) in enumerate(encabezados):
            if idx_bd != -1:
                # Calculamos si lleva flechita de ordenamiento
                flecha = ""
                if self.columna_orden == idx_bd:
                    # Invertimos las flechas para que coincida con la lectura natural
                    flecha = " ▲" if self.orden_descendente else " ▼"

                # Usamos botones transparentes en lugar de Labels para que sean clickeables
                btn = ctk.CTkButton(
                    self.frame_lista,
                    text=texto + flecha,
                    font=FUENTE_NORMAL_BOLD,
                    fg_color="transparent",
                    text_color=("black", "white"),
                    hover_color=("gray80", "gray30"),
                    anchor="w",
                    width=20,
                    command=lambda i=idx_bd: self._cambiar_orden(i),
                )
                btn.grid(row=0, column=col, padx=10, pady=5, sticky="w")
            else:
                ctk.CTkLabel(
                    self.frame_lista, text=texto, font=FUENTE_NORMAL_BOLD
                ).grid(row=0, column=col, padx=10, pady=5, sticky="w")

    def dibujar_fila(self, indice: int, fila: Tuple[Any, ...]) -> None:
        """
        Desempaqueta una tupla de base de datos y dibuja los labels y botones
        correspondientes en una fila específica de la grilla.
        """
        (
            legajo,
            apellidos,
            nombres,
            timestamp,
            comprobante,
            ip_vinculada,
            ip_origen,
            alertas,
        ) = fila

        hora_str = str(timestamp)[11:19]

        celdas = [
            (ctk.CTkLabel(self.frame_lista, text=legajo), 0),
            (ctk.CTkLabel(self.frame_lista, text=apellidos), 1),
            (ctk.CTkLabel(self.frame_lista, text=nombres), 2),
            (ctk.CTkLabel(self.frame_lista, text=hora_str), 3),
            (
                ctk.CTkLabel(self.frame_lista, text=comprobante, font=FUENTE_MONOSPACE),
                4,
            ),
        ]

        for widget, col in celdas:
            widget.grid(row=indice, column=col, padx=10, pady=2, sticky="w")

        # Como la lista 'alertas' ya la calculó el backend, la UI solo decide si pinta verde o naranja
        if alertas:
            btn_estado = ctk.CTkButton(
                self.frame_lista,
                text="⚠️",
                width=40,
                fg_color="transparent",
                text_color=COLOR_ALERTA_IP_DIFIERE,
                font=FUENTE_NORMAL_BOLD,
                hover_color=("gray80", "gray30"),
                command=lambda l=legajo, n=nombres, a=apellidos, w=alertas: self.mostrar_modal_alertas(
                    l, n, a, w
                ),
            )
        else:
            btn_estado = ctk.CTkButton(
                self.frame_lista,
                text="✅",
                width=40,
                fg_color="transparent",
                text_color=COLOR_EXITO,
                font=FUENTE_NORMAL_BOLD,
                hover=False,
            )
        btn_estado.grid(row=indice, column=5, padx=10, pady=2)

        ctk.CTkButton(
            self.frame_lista,
            text="Habilitar",
            width=80,
            fg_color=COLOR_BOTON_PELIGRO,
            hover_color=COLOR_BOTON_PELIGRO_HOVER,
            command=lambda l=legajo, n=nombres, a=apellidos: self.habilitar_reentrega_gui(
                l, n, a
            ),
        ).grid(row=indice, column=6, padx=10, pady=2, sticky="w")

    def _refrescar_vista(self) -> None:
        """
        Motor de renderizado: Filtra, ordena y dibuja la grilla desde la memoria RAM.
        Se ejecuta al recibir exámenes, al tipear en el buscador, o al ordenar columnas.
        """
        # 1. Limpiamos la grilla visual actual
        for widget in self.frame_lista.winfo_children():
            widget.destroy()

        self.dibujar_encabezados()

        # 2. Filtrado en vivo por texto (ignorando mayúsculas/minúsculas)
        query = self.texto_busqueda.get().lower().strip()
        filas_filtradas = []
        for fila in self.filas_cacheadas:
            # Comparamos contra Legajo (0), Apellidos (1) y Nombres (2)
            if (
                query in str(fila[0]).lower()
                or query in str(fila[1]).lower()
                or query in str(fila[2]).lower()
            ):
                filas_filtradas.append(fila)

        # 3. Ordenamiento Dinámico
        def clave_ordenamiento(f):
            if self.columna_orden == 5:
                # 3. CORRECCIÓN DEL ORDENAMIENTO POR ALERTAS:
                # Si la lista de alertas (índice 7) tiene al menos un elemento, retorna True
                # (Al ordenar descendentemente, los True quedan arriba)
                tiene_alertas = len(f[7]) > 0
                return tiene_alertas
            # Para el resto, ordena como string estándar
            return str(f[self.columna_orden]).lower() if f[self.columna_orden] else ""

        try:
            filas_filtradas.sort(key=clave_ordenamiento, reverse=self.orden_descendente)
        except Exception:
            pass  # Si por alguna rareza de datos falla, se omite el ordenamiento pero no explota

        # 4. Dibujar las filas resultantes
        for indice, fila in enumerate(filas_filtradas, start=1):
            self.dibujar_fila(indice, fila)

    def actualizar_grilla(self) -> None:
        """
        Bucle de actualización (Polling). Ahora solo consulta a la base de datos.
        Si hay entregas nuevas, actualiza el caché en memoria, actualiza los contadores,
        y manda a redibujar la grilla.
        """
        if not self.ruta_db:
            return

        try:
            conteo_actual = persistencia.contar_entregas(self.ruta_db)
            if conteo_actual != self.ultimo_conteo:
                self.ultimo_conteo = conteo_actual

                # Cacheamos los registros frescos de la BD
                self.filas_cacheadas = persistencia.listar_entregas_activas(
                    self.ruta_db
                )

                # --- ACTUALIZAR ESTADÍSTICAS EN VIVO ---
                total_entregas = len(self.filas_cacheadas)
                total_alertas = sum(
                    1 for fila in self.filas_cacheadas if len(fila[7]) > 0
                )

                self.lbl_contador_entregas.configure(text=str(total_entregas))

                if total_alertas > 0:
                    self.lbl_contador_alertas.configure(
                        text=str(total_alertas), text_color=COLOR_ALERTA_IP_DIFIERE
                    )
                else:
                    self.lbl_contador_alertas.configure(
                        text="0", text_color=COLOR_ALERTA_IP_OK
                    )

                # Disparamos el motor de renderizado
                self._refrescar_vista()

        except Exception as e:
            logging.error(f"Error actualizando grilla de entregas: {e}")

        # Reprogramar la próxima lectura silenciosa
        self.after(self.intervalo_actualizacion, self.actualizar_grilla)
