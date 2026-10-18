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
GEOMETRIA_VENTANA: str = "1000x600"
INTERVALO_ACTUALIZACION_MS: int = 3000

# Paleta de Colores
COLOR_EXITO: str = "green"
COLOR_ERROR: str = "red"
COLOR_ALERTA_IP_DIFIERE: str = "#FF4500"
COLOR_ALERTA_IP_OK: str = "gray"
COLOR_BOTON_PELIGRO: str = "#8B0000"
COLOR_BOTON_PELIGRO_HOVER: str = "#FF0000"

# Fuentes Tipográficas
FUENTE_TITULO: Tuple[str, int, str] = ("Roboto", 24, "bold")
FUENTE_SUBTITULO: Tuple[str, int, str] = ("Roboto", 18, "bold")
FUENTE_NORMAL_BOLD: Tuple[str, int, str] = ("Roboto", 14, "bold")
FUENTE_NORMAL: Tuple[str, int] = ("Roboto", 12)
FUENTE_MONOSPACE: Tuple[str, int] = ("Consolas", 12)
FUENTE_NUMERO_GRANDE: Tuple[str, int, str] = ("Roboto", 36, "bold")


class InterfazServidor(ctk.CTk):
    """
    Clase principal de la Interfaz Gráfica de Usuario (GUI) del Servidor Docente.
    """

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("SEEP - Configuración Inicial")
        self.geometry(GEOMETRIA_VENTANA)

        # Atributos de estado y rutas
        self.ruta_db: Optional[str] = None
        self.ruta_entregas: Optional[str] = None
        self.ultimo_conteo: int = -1
        self.intervalo_actualizacion: int = INTERVALO_ACTUALIZACION_MS
        self._temporizador_busqueda: Optional[str] = None

        # --- OPTIMIZACIONES: ESTRUCTURAS DE CACHÉ Y POOLING ---
        self.filas_cacheadas: list = []
        self._pool_filas: list = []  # Almacena los widgets instanciados de la grilla
        self._botones_encabezado: dict = {}  # Almacena los botones de los títulos
        self._ultima_firma_vista: Optional[tuple] = (
            None  # Firma de estado para omitir renders
        )

        self.texto_busqueda = ctk.StringVar()
        self.texto_busqueda.trace_add("write", lambda *args: self._programar_busqueda())

        self.columna_orden: int = 3
        self.orden_descendente: bool = True

        self._construir_pantalla_config()
        self._construir_pantalla_dashboard()

    def _construir_pantalla_config(self) -> None:
        """Construye y empaqueta el formulario inicial de configuración del servidor."""
        self.frame_config = ctk.CTkFrame(self)
        self.frame_config.pack(pady=40, padx=40, fill="both", expand=True)

        ctk.CTkLabel(
            self.frame_config, text="Configuración de la Sesión", font=FUENTE_TITULO
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
        """Construye la pantalla principal del servidor docente."""
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

        # Panel Estadístico
        self.frame_estadisticas = ctk.CTkFrame(
            self.frame_dashboard, fg_color="transparent"
        )
        self.frame_estadisticas.pack(pady=10, fill="x")
        self.frame_estadisticas.grid_columnconfigure(0, weight=1)
        self.frame_estadisticas.grid_columnconfigure(1, weight=1)

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

        # Botones de Acción
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

        self.btn_exportar_csv = ctk.CTkButton(
            self.frame_dashboard,
            text="📊 Exportar a CSV",
            font=FUENTE_NORMAL_BOLD,
            fg_color="transparent",
            border_width=1,
            text_color=("black", "white"),
            command=self.exportar_csv_gui,
        )
        self.btn_exportar_csv.pack(pady=(0, 10))

        # Barra de Búsqueda
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

        # Marco de encabezados fijos
        self.frame_encabezados = ctk.CTkFrame(self.frame_dashboard)
        self.frame_encabezados.pack(fill="x", padx=20, pady=(10, 0))

        # Marco scrollable de lista
        self.frame_lista = ctk.CTkScrollableFrame(self.frame_dashboard)
        self.frame_lista.pack(pady=(0, 10), padx=20, fill="both", expand=True)

        self.dibujar_encabezados()

    def _programar_busqueda(self) -> None:
        """Debouncing de búsqueda."""
        if self._temporizador_busqueda is not None:
            self.after_cancel(self._temporizador_busqueda)
        self._temporizador_busqueda = self.after(300, self._refrescar_vista)

    def _cambiar_orden(self, col_index: int) -> None:
        """Invierte o cambia la columna de orden y refresca."""
        if self.columna_orden == col_index:
            self.orden_descendente = not self.orden_descendente
        else:
            self.columna_orden = col_index
            self.orden_descendente = False

        self.dibujar_encabezados()
        self._refrescar_vista()

    def dibujar_encabezados(self) -> None:
        """
        OPTIMIZACIÓN: Encabezados estáticos y centrados.
        """
        encabezados = [
            ("Legajo/DNI", 0, 100),
            ("Apellidos", 1, 150),
            ("Nombres", 2, 150),
            ("Hora", 3, 80),
            ("Comprobante", 4, 130),  # Aumentado a 130 para que entre cómodo
            ("Estado", 5, 60),
            ("Acciones", -1, 100),
        ]

        # 3. EL TRUCO DEL CENTRADO: Resortes invisibles a los costados
        self.frame_encabezados.grid_columnconfigure(0, weight=1)
        self.frame_encabezados.grid_columnconfigure(len(encabezados) + 1, weight=1)
        self.frame_lista.grid_columnconfigure(0, weight=1)
        self.frame_lista.grid_columnconfigure(len(encabezados) + 1, weight=1)

        # Si ya se crearon los botones, solo actualizamos las flechas
        if self._botones_encabezado:
            for col, (texto, idx_bd, _) in enumerate(encabezados):
                if idx_bd != -1:
                    # 2. ESPACIOS FANTASMAS: Mantiene el ancho constante si no tiene flecha
                    flecha = (
                        " ▲"
                        if (self.columna_orden == idx_bd and self.orden_descendente)
                        else " ▼" if (self.columna_orden == idx_bd) else "   "
                    )
                    self._botones_encabezado[idx_bd].configure(text=texto + flecha)
            return

        # Si no existen, los instanciamos por primera vez
        for col, (texto, idx_bd, ancho) in enumerate(encabezados):
            # Desplazamos las columnas reales 1 lugar a la derecha para dejar la col 0 como resorte
            col_real = col + 1

            # Bloqueamos el ancho de cada columna para que nunca más "salten" al clickear
            self.frame_encabezados.grid_columnconfigure(
                col_real, minsize=ancho, weight=0
            )
            self.frame_lista.grid_columnconfigure(col_real, minsize=ancho, weight=0)

            if idx_bd != -1:
                flecha = (
                    " ▲"
                    if (self.columna_orden == idx_bd and self.orden_descendente)
                    else " ▼" if (self.columna_orden == idx_bd) else "   "
                )
                btn = ctk.CTkButton(
                    self.frame_encabezados,
                    text=texto + flecha,
                    font=FUENTE_NORMAL_BOLD,
                    fg_color="transparent",
                    text_color=("black", "white"),
                    hover_color=("gray80", "gray30"),
                    anchor="w",
                    width=ancho,
                    command=lambda i=idx_bd: self._cambiar_orden(i),
                )
                btn.grid(row=0, column=col_real, padx=10, pady=5, sticky="w")
                self._botones_encabezado[idx_bd] = btn
            else:
                ctk.CTkLabel(
                    self.frame_encabezados,
                    text=texto,
                    font=FUENTE_NORMAL_BOLD,
                    width=ancho,
                    anchor="w",
                ).grid(row=0, column=col_real, padx=10, pady=5, sticky="w")

    def _configurar_fila_en_pool(self, indice: int, fila: tuple) -> None:
        """
        OPTIMIZACIÓN: Object Pooling y anulación de efectos indeseados de hover.
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
            _,
        ) = fila
        hora_str = str(timestamp)[11:19]
        tiene_alertas = len(alertas) > 0

        if indice < len(self._pool_filas):
            w = self._pool_filas[indice]
            w["legajo"].configure(text=legajo)
            w["apellidos"].configure(text=apellidos)
            w["nombres"].configure(text=nombres)
            w["hora"].configure(text=hora_str)
            w["comprobante"].configure(text=comprobante)

            if tiene_alertas:
                # 1. HOVER APAGADO para el reciclaje
                w["estado"].configure(
                    text="⚠️",
                    text_color=COLOR_ALERTA_IP_DIFIERE,
                    hover=False,
                    command=lambda l=legajo, n=nombres, a=apellidos, w_al=alertas: self.mostrar_modal_alertas(
                        l, n, a, w_al
                    ),
                )
            else:
                w["estado"].configure(
                    text="✅", text_color=COLOR_EXITO, hover=False, command=None
                )

            w["accion"].configure(
                command=lambda l=legajo, n=nombres, a=apellidos: self.habilitar_reentrega_gui(
                    l, n, a
                )
            )

            for widget in w.values():
                widget.grid()

        else:
            w = {}
            # Notar que usamos column=1, 2, 3... por culpa del resorte en column=0
            w["legajo"] = ctk.CTkLabel(
                self.frame_lista, text=legajo, width=100, anchor="w"
            )
            w["legajo"].grid(row=indice, column=1, padx=10, pady=2, sticky="w")

            w["apellidos"] = ctk.CTkLabel(
                self.frame_lista, text=apellidos, width=150, anchor="w"
            )
            w["apellidos"].grid(row=indice, column=2, padx=10, pady=2, sticky="w")

            w["nombres"] = ctk.CTkLabel(
                self.frame_lista, text=nombres, width=150, anchor="w"
            )
            w["nombres"].grid(row=indice, column=3, padx=10, pady=2, sticky="w")

            w["hora"] = ctk.CTkLabel(
                self.frame_lista, text=hora_str, width=80, anchor="w"
            )
            w["hora"].grid(row=indice, column=4, padx=10, pady=2, sticky="w")

            w["comprobante"] = ctk.CTkLabel(
                self.frame_lista,
                text=comprobante,
                font=FUENTE_MONOSPACE,
                width=130,
                anchor="w",
            )
            w["comprobante"].grid(row=indice, column=5, padx=10, pady=2, sticky="w")

            if tiene_alertas:
                # 1. HOVER APAGADO para la creación limpia
                w["estado"] = ctk.CTkButton(
                    self.frame_lista,
                    text="⚠️",
                    width=60,
                    fg_color="transparent",
                    text_color=COLOR_ALERTA_IP_DIFIERE,
                    font=FUENTE_NORMAL_BOLD,
                    hover=False,
                    command=lambda l=legajo, n=nombres, a=apellidos, w_al=alertas: self.mostrar_modal_alertas(
                        l, n, a, w_al
                    ),
                )
            else:
                w["estado"] = ctk.CTkButton(
                    self.frame_lista,
                    text="✅",
                    width=60,
                    fg_color="transparent",
                    text_color=COLOR_EXITO,
                    font=FUENTE_NORMAL_BOLD,
                    hover=False,
                )
            w["estado"].grid(row=indice, column=6, padx=10, pady=2, sticky="w")

            w["accion"] = ctk.CTkButton(
                self.frame_lista,
                text="Habilitar",
                width=100,
                fg_color=COLOR_BOTON_PELIGRO,
                hover_color=COLOR_BOTON_PELIGRO_HOVER,
                command=lambda l=legajo, n=nombres, a=apellidos: self.habilitar_reentrega_gui(
                    l, n, a
                ),
            )
            w["accion"].grid(row=indice, column=7, padx=10, pady=2, sticky="w")

            self._pool_filas.append(w)

    def _refrescar_vista(self, forzar: bool = False) -> None:
        """
        Motor de renderizado hiper-optimizado.
        Filtra rápido y reutiliza widgets. Solo procesa si hubo cambios de estado.
        """
        query = self.texto_busqueda.get().lower().strip()

        # OPTIMIZACIÓN: Short-circuiting. Si nada cambió y no estamos forzando, abortar.
        firma_actual = (
            self.ultimo_conteo,
            query,
            self.columna_orden,
            self.orden_descendente,
        )
        if not forzar and firma_actual == self._ultima_firma_vista:
            return
        self._ultima_firma_vista = firma_actual

        # 1. Filtrado rápido (utiliza la cadena precalculada almacenada en el índice 8)
        if query:
            filas_filtradas = [f for f in self.filas_cacheadas if query in f[8]]
        else:
            filas_filtradas = self.filas_cacheadas[:]

        # 2. Ordenamiento en memoria
        def clave_ordenamiento(f):
            if self.columna_orden == 5:
                return len(f[7]) > 0
            return str(f[self.columna_orden]).lower() if f[self.columna_orden] else ""

        try:
            filas_filtradas.sort(key=clave_ordenamiento, reverse=self.orden_descendente)
        except Exception:
            pass

        # 3. Object Pooling: Configurar filas visibles
        total_filtradas = len(filas_filtradas)
        for indice, fila in enumerate(filas_filtradas):
            self._configurar_fila_en_pool(indice, fila)

        # 4. Object Pooling: Ocultar los widgets sobrantes sin destruirlos
        for i in range(total_filtradas, len(self._pool_filas)):
            for widget in self._pool_filas[i].values():
                widget.grid_remove()

    def actualizar_grilla(self) -> None:
        """Bucle de actualización. Descarga datos, pre-calcula campos y actualiza métricas en 1 sola pasada."""
        if not self.ruta_db:
            return

        try:
            conteo_actual = persistencia.contar_entregas(self.ruta_db)
            if conteo_actual != self.ultimo_conteo:
                self.ultimo_conteo = conteo_actual
                filas_crudas = persistencia.listar_entregas_activas(self.ruta_db)

                # OPTIMIZACIÓN: Datos preprocesados y Estadísticas en 1 sola pasada
                total_alertas = 0
                self.filas_cacheadas = []

                for fila in filas_crudas:
                    # fila = (legajo, apellidos, nombres, timestamp, comprobante, ip_vinc, ip_orig, alertas)
                    if len(fila[7]) > 0:
                        total_alertas += 1

                    # Pre-calculamos el texto en minúsculas para que el filtro sea instantáneo
                    texto_busqueda_precalc = f"{fila[0]} {fila[1]} {fila[2]}".lower()

                    # Agregamos el texto precalculado a la tupla (posición 8)
                    self.filas_cacheadas.append((*fila, texto_busqueda_precalc))

                # Actualizamos los labels estadísticos
                self.lbl_contador_entregas.configure(
                    text=str(len(self.filas_cacheadas))
                )
                if total_alertas > 0:
                    self.lbl_contador_alertas.configure(
                        text=str(total_alertas), text_color=COLOR_ALERTA_IP_DIFIERE
                    )
                else:
                    self.lbl_contador_alertas.configure(
                        text="0", text_color=COLOR_ALERTA_IP_OK
                    )

                # Disparamos el motor de renderizado forzando el dibujado
                self._refrescar_vista(forzar=True)

        except Exception as e:
            logging.error(f"Error actualizando grilla de entregas: {e}")

        # Reprogramar la próxima lectura
        self.after(self.intervalo_actualizacion, self.actualizar_grilla)

    # -------------------------------------------------------------------------
    # FUNCIONES DE ARRANQUE Y SISTEMA
    # -------------------------------------------------------------------------

    def iniciar_sistema(self) -> None:
        """Inicia servidor y bases de datos, cambia interfaz a dashboard."""
        turno = self.entrada_turno.get().strip().upper()
        aula = self.entrada_aula.get().strip().upper()
        modulo = self.var_modulo.get()

        if not turno or not aula:
            self.lbl_error.configure(text="Error: Debe completar el Turno y el Aula.")
            return

        fecha_hoy = datetime.now().strftime("%Y%m%d")
        nombre_carpeta = f"entregas_{modulo}_{fecha_hoy}_{turno}_{aula}"
        ruta_carpeta = os.path.join(api.obtener_directorio_base(), nombre_carpeta)
        os.makedirs(ruta_carpeta, exist_ok=True)
        self.ruta_db = os.path.join(ruta_carpeta, "seep_registro.db")

        pin_sesion = persistencia.inicializar_base_datos(
            self.ruta_db, modulo, fecha_hoy, turno, aula, api._generar_pin()
        )

        app = api.crear_app(modulo, pin_sesion, ruta_carpeta, self.ruta_db)
        ip_local = api.obtener_ip_local()
        api.iniciar_servidor_en_hilo(app, callback_error=self.mostrar_error_critico)

        self.title(f"SEEP - Panel Docente | Módulo: {modulo.upper()} | Aula: {aula}")
        self.frame_config.pack_forget()
        self.frame_dashboard.pack(pady=20, padx=20, fill="both", expand=True)

        self.lbl_info_dash.configure(text=f"IP: {ip_local}   |   PIN: {pin_sesion}")
        self.ruta_entregas = ruta_carpeta

        self.actualizar_grilla()

    def mostrar_error_critico(self, titulo: str, mensaje: str) -> None:
        def _mostrar_y_cerrar():
            messagebox.showerror(titulo, mensaje)
            import os

            os._exit(1)

        self.after(0, _mostrar_y_cerrar)

    def abrir_carpeta_entregas(self) -> None:
        if not self.ruta_entregas or not os.path.exists(self.ruta_entregas):
            messagebox.showerror("Error", "La carpeta no existe o no se ha creado aún.")
            return
        try:
            if os.name == "nt":
                os.startfile(self.ruta_entregas)
            else:
                import subprocess, sys

                comando = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([comando, self.ruta_entregas])
        except Exception as e:
            logging.error(f"No se pudo abrir la carpeta: {e}")
            messagebox.showerror("Error", f"No se pudo abrir la carpeta de destino.")

    def exportar_csv_gui(self) -> None:
        if not self.ruta_entregas or not self.ruta_db:
            messagebox.showerror("Error", "El servidor no está iniciado.")
            return
        try:
            ruta_csv = os.path.join(self.ruta_entregas, "asistencia_parcial.csv")
            persistencia.exportar_asistencia_csv(self.ruta_db, ruta_csv)
            messagebox.showinfo(
                "Éxito", f"Reporte exportado correctamente en:\n{ruta_csv}"
            )
        except Exception as e:
            logging.error(f"Error al exportar CSV: {e}")
            messagebox.showerror("Error", f"No se pudo generar el CSV:\n{e}")

    def habilitar_reentrega_gui(
        self, legajo_alumno: str, nombres: str, apellidos: str
    ) -> None:
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
        modal = ctk.CTkToplevel(self)
        modal.title(f"Alertas de Seguridad - {legajo}")
        modal.geometry("450x250")
        modal.attributes("-topmost", True)
        modal.grab_set()

        ctk.CTkLabel(
            modal, text=f"Alumno: {apellidos}, {nombres}", font=FUENTE_SUBTITULO
        ).pack(pady=(20, 10))

        marco_alertas = ctk.CTkFrame(modal)
        marco_alertas.pack(padx=20, pady=10, fill="both", expand=True)

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
