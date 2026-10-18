"""
Módulo de Interfaz Gráfica (GUI) de SEEP (Servidor Docente).
Contiene la clase principal que maneja las pantallas de configuración y el dashboard de monitoreo en vivo.
"""

import logging
import os
import subprocess
import sys
from datetime import datetime
from tkinter import messagebox
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk

import seep_config
from servidor_modulos import api, persistencia

# -----------------------------------------------------------------------------
# CONSTANTES DE CONFIGURACIÓN VISUAL Y LÍMITES
# -----------------------------------------------------------------------------
GEOMETRIA_VENTANA: str = "1000x600"
GEOMETRIA_MODAL_ALERTAS: str = "450x250"
INTERVALO_ACTUALIZACION_MS: int = 3000
RETARDO_BUSQUEDA_MS: int = 300

# Anchos estáticos de columnas (Object Pooling)
ANCHO_COL_LEGAJO: int = 100
ANCHO_COL_APELLIDOS: int = 150
ANCHO_COL_NOMBRES: int = 150
ANCHO_COL_HORA: int = 80
ANCHO_COL_COMPROBANTE: int = 130
ANCHO_COL_ESTADO: int = 60
ANCHO_COL_ACCIONES: int = 100

# -----------------------------------------------------------------------------
# ESTILOS Y FUENTES
# -----------------------------------------------------------------------------
# Paleta de Colores
COLOR_EXITO: str = "green"
COLOR_ERROR: str = "red"
COLOR_ALERTA_IP_DIFIERE: str = "#FF4500"
COLOR_ALERTA_IP_OK: str = "gray"
COLOR_BOTON_PELIGRO: str = "#8B0000"
COLOR_BOTON_PELIGRO_HOVER: str = "#FF0000"
COLOR_HOVER_BOTON_HEADER: Tuple[str, str] = ("gray80", "gray30")

# Fuentes Tipográficas
# NOTA(to-do): Roboto es cambiada silenciosamente por windows, pensar en otra fuente.
FUENTE_TITULO: Tuple[str, int, str] = ("Roboto", 24, "bold")
FUENTE_SUBTITULO: Tuple[str, int, str] = ("Roboto", 18, "bold")
FUENTE_NORMAL_BOLD: Tuple[str, int, str] = ("Roboto", 14, "bold")
FUENTE_NORMAL: Tuple[str, int] = ("Roboto", 12)
FUENTE_MONOSPACE: Tuple[str, int] = ("Consolas", 12)
FUENTE_NUMERO_GRANDE: Tuple[str, int, str] = ("Roboto", 36, "bold")


class InterfazServidor(ctk.CTk):
    """
    Clase principal de la Interfaz Gráfica de Usuario (GUI) del Servidor Docente.
    Gestiona el ciclo de vida de la ventana, la interacción del usuario y la actualización
    en tiempo real de los datos del repositorio subyacente.
    """

    def __init__(self) -> None:
        """
        Inicializa la ventana principal, configura el tema visual y prepara
        las estructuras de caché para el motor de renderizado.
        """
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("SEEP - Configuración Inicial")
        self.geometry(GEOMETRIA_VENTANA)

        # Atributos de estado y rutas del servidor activo
        self.ruta_db: Optional[str] = None
        self.ruta_entregas: Optional[str] = None
        self.ultimo_conteo: int = -1
        self.intervalo_actualizacion: int = INTERVALO_ACTUALIZACION_MS
        self._temporizador_busqueda: Optional[str] = None

        # --- OPTIMIZACIONES: ESTRUCTURAS DE CACHÉ Y POOLING ---
        self.filas_cacheadas: List[Tuple[Any, ...]] = []
        self._pool_filas: List[Dict[str, ctk.CTkBaseClass]] = []
        self._botones_encabezado: Dict[int, ctk.CTkButton] = {}
        self._ultima_firma_vista: Optional[tuple] = None

        self.texto_busqueda = ctk.StringVar()
        self.texto_busqueda.trace_add("write", lambda *args: self._programar_busqueda())

        self.columna_orden: int = 3
        self.orden_descendente: bool = True

        self._construir_pantalla_config()
        self._construir_pantalla_dashboard()

    # -----------------------------------------------------------------------------
    # CONSTRUCCIÓN DE COMPONENTES VISUALES
    # -----------------------------------------------------------------------------
    def _construir_pantalla_config(self) -> None:
        """
        Construye y empaqueta el formulario inicial de configuración de la sesión docente.
        """
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
        """
        Construye la pantalla principal del panel docente, incluyendo métricas,
        controles de exportación y la tabla de monitoreo en vivo.
        """
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

        self.frame_encabezados = ctk.CTkFrame(self.frame_dashboard)
        self.frame_encabezados.pack(fill="x", padx=20, pady=(10, 0))

        self.frame_lista = ctk.CTkScrollableFrame(self.frame_dashboard)
        self.frame_lista.pack(pady=(0, 10), padx=20, fill="both", expand=True)

        self.dibujar_encabezados()

    # -----------------------------------------------------------------------------
    # MOTOR DE RENDERIZADO DE LA GRILLA (OBJECT POOLING)
    # -----------------------------------------------------------------------------
    def _programar_busqueda(self) -> None:
        """Aplica un retraso (debouncing) para evitar renderizados excesivos al tipear rápido."""
        if self._temporizador_busqueda is not None:
            self.after_cancel(self._temporizador_busqueda)
        self._temporizador_busqueda = self.after(
            RETARDO_BUSQUEDA_MS, self._refrescar_vista
        )

    def _cambiar_orden(self, indice_columna: int) -> None:
        """
        Invierte el orden de la columna actual o cambia la columna de ordenamiento y refresca la vista.

        Args:
            indice_columna (int): Índice de la columna seleccionada para ordenar.
        """
        if self.columna_orden == indice_columna:
            self.orden_descendente = not self.orden_descendente
        else:
            self.columna_orden = indice_columna
            self.orden_descendente = False

        self.dibujar_encabezados()
        self._refrescar_vista()

    def dibujar_encabezados(self) -> None:
        """
        Dibuja de forma estática los encabezados de las columnas de la tabla.
        Asigna resortes (weights) invisibles en los extremos para centrar el contenido.
        """
        encabezados_configurados = [
            ("Legajo/DNI", 0, ANCHO_COL_LEGAJO),
            ("Apellidos", 1, ANCHO_COL_APELLIDOS),
            ("Nombres", 2, ANCHO_COL_NOMBRES),
            ("Hora", 3, ANCHO_COL_HORA),
            ("Comprobante", 4, ANCHO_COL_COMPROBANTE),
            ("Estado", 5, ANCHO_COL_ESTADO),
            ("Acciones", -1, ANCHO_COL_ACCIONES),
        ]

        self.frame_encabezados.grid_columnconfigure(0, weight=1)
        self.frame_encabezados.grid_columnconfigure(
            len(encabezados_configurados) + 1, weight=1
        )
        self.frame_lista.grid_columnconfigure(0, weight=1)
        self.frame_lista.grid_columnconfigure(
            len(encabezados_configurados) + 1, weight=1
        )

        if self._botones_encabezado:
            for _, (texto_encabezado, indice_bd, _) in enumerate(
                encabezados_configurados
            ):
                if indice_bd != -1:
                    indicador_flecha = (
                        " ▲"
                        if (self.columna_orden == indice_bd and self.orden_descendente)
                        else " ▼" if (self.columna_orden == indice_bd) else "   "
                    )
                    self._botones_encabezado[indice_bd].configure(
                        text=texto_encabezado + indicador_flecha
                    )
            return

        for indice_columna, (
            texto_encabezado,
            indice_bd,
            ancho_configurado,
        ) in enumerate(encabezados_configurados):
            columna_visual_real = indice_columna + 1

            self.frame_encabezados.grid_columnconfigure(
                columna_visual_real, minsize=ancho_configurado, weight=0
            )
            self.frame_lista.grid_columnconfigure(
                columna_visual_real, minsize=ancho_configurado, weight=0
            )

            if indice_bd != -1:
                indicador_flecha = (
                    " ▲"
                    if (self.columna_orden == indice_bd and self.orden_descendente)
                    else " ▼" if (self.columna_orden == indice_bd) else "   "
                )
                boton_encabezado = ctk.CTkButton(
                    self.frame_encabezados,
                    text=texto_encabezado + indicador_flecha,
                    font=FUENTE_NORMAL_BOLD,
                    fg_color="transparent",
                    text_color=("black", "white"),
                    hover_color=COLOR_HOVER_BOTON_HEADER,
                    anchor="w",
                    width=ancho_configurado,
                    command=lambda i=indice_bd: self._cambiar_orden(i),
                )
                boton_encabezado.grid(
                    row=0, column=columna_visual_real, padx=10, pady=5, sticky="w"
                )
                self._botones_encabezado[indice_bd] = boton_encabezado
            else:
                ctk.CTkLabel(
                    self.frame_encabezados,
                    text=texto_encabezado,
                    font=FUENTE_NORMAL_BOLD,
                    width=ancho_configurado,
                    anchor="w",
                ).grid(row=0, column=columna_visual_real, padx=10, pady=5, sticky="w")

    def _configurar_fila_en_pool(self, indice_visual: int, datos_fila: tuple) -> None:
        """
        Asigna datos a una fila existente en la caché visual (Object Pooling) o instancia
        nuevos widgets si la caché es insuficiente. Evita destruir y recrear componentes en Tkinter.

        Args:
            indice_visual (int): Índice correspondiente a la posición de la fila en la pantalla.
            datos_fila (tuple): Información procesada del alumno y su examen.
        """
        (
            legajo,
            apellidos,
            nombres,
            marca_temporal,
            comprobante,
            ip_vinculada,
            ip_origen,
            alertas_detectadas,
            _,
        ) = datos_fila
        hora_formateada = str(marca_temporal)[11:19]
        existen_alertas = len(alertas_detectadas) > 0

        if indice_visual < len(self._pool_filas):
            widget_cache = self._pool_filas[indice_visual]
            widget_cache["legajo"].configure(text=legajo)
            widget_cache["apellidos"].configure(text=apellidos)
            widget_cache["nombres"].configure(text=nombres)
            widget_cache["hora"].configure(text=hora_formateada)
            widget_cache["comprobante"].configure(text=comprobante)

            if existen_alertas:
                widget_cache["estado"].configure(
                    text="⚠️",
                    text_color=COLOR_ALERTA_IP_DIFIERE,
                    hover=False,
                    command=lambda l=legajo, n=nombres, a=apellidos, w_al=alertas_detectadas: self.mostrar_modal_alertas(
                        l, n, a, w_al
                    ),
                )
            else:
                widget_cache["estado"].configure(
                    text="✅", text_color=COLOR_EXITO, hover=False, command=None
                )

            widget_cache["accion"].configure(
                command=lambda l=legajo, n=nombres, a=apellidos: self.habilitar_reentrega_gui(
                    l, n, a
                )
            )

            for componente in widget_cache.values():
                componente.grid()

        else:
            nuevo_widget_cache = {}

            nuevo_widget_cache["legajo"] = ctk.CTkLabel(
                self.frame_lista, text=legajo, width=ANCHO_COL_LEGAJO, anchor="w"
            )
            nuevo_widget_cache["legajo"].grid(
                row=indice_visual, column=1, padx=10, pady=2, sticky="w"
            )

            nuevo_widget_cache["apellidos"] = ctk.CTkLabel(
                self.frame_lista, text=apellidos, width=ANCHO_COL_APELLIDOS, anchor="w"
            )
            nuevo_widget_cache["apellidos"].grid(
                row=indice_visual, column=2, padx=10, pady=2, sticky="w"
            )

            nuevo_widget_cache["nombres"] = ctk.CTkLabel(
                self.frame_lista, text=nombres, width=ANCHO_COL_NOMBRES, anchor="w"
            )
            nuevo_widget_cache["nombres"].grid(
                row=indice_visual, column=3, padx=10, pady=2, sticky="w"
            )

            nuevo_widget_cache["hora"] = ctk.CTkLabel(
                self.frame_lista, text=hora_formateada, width=ANCHO_COL_HORA, anchor="w"
            )
            nuevo_widget_cache["hora"].grid(
                row=indice_visual, column=4, padx=10, pady=2, sticky="w"
            )

            nuevo_widget_cache["comprobante"] = ctk.CTkLabel(
                self.frame_lista,
                text=comprobante,
                font=FUENTE_MONOSPACE,
                width=ANCHO_COL_COMPROBANTE,
                anchor="w",
            )
            nuevo_widget_cache["comprobante"].grid(
                row=indice_visual, column=5, padx=10, pady=2, sticky="w"
            )

            if existen_alertas:
                nuevo_widget_cache["estado"] = ctk.CTkButton(
                    self.frame_lista,
                    text="⚠️",
                    width=ANCHO_COL_ESTADO,
                    fg_color="transparent",
                    text_color=COLOR_ALERTA_IP_DIFIERE,
                    font=FUENTE_NORMAL_BOLD,
                    hover=False,
                    command=lambda l=legajo, n=nombres, a=apellidos, w_al=alertas_detectadas: self.mostrar_modal_alertas(
                        l, n, a, w_al
                    ),
                )
            else:
                nuevo_widget_cache["estado"] = ctk.CTkButton(
                    self.frame_lista,
                    text="✅",
                    width=ANCHO_COL_ESTADO,
                    fg_color="transparent",
                    text_color=COLOR_EXITO,
                    font=FUENTE_NORMAL_BOLD,
                    hover=False,
                )
            nuevo_widget_cache["estado"].grid(
                row=indice_visual, column=6, padx=10, pady=2, sticky="w"
            )

            nuevo_widget_cache["accion"] = ctk.CTkButton(
                self.frame_lista,
                text="Habilitar",
                width=ANCHO_COL_ACCIONES,
                fg_color=COLOR_BOTON_PELIGRO,
                hover_color=COLOR_BOTON_PELIGRO_HOVER,
                command=lambda l=legajo, n=nombres, a=apellidos: self.habilitar_reentrega_gui(
                    l, n, a
                ),
            )
            nuevo_widget_cache["accion"].grid(
                row=indice_visual, column=7, padx=10, pady=2, sticky="w"
            )

            self._pool_filas.append(nuevo_widget_cache)

    def _refrescar_vista(self, forzar_renderizado: bool = False) -> None:
        """
        Motor de renderizado y filtrado dinámico. Procesa búsquedas y ordenamientos en memoria,
        y asigna los resultados al pool de widgets. Implementa short-circuiting si no hay cambios reales.

        Args:
            forzar_renderizado (bool): Bandera para omitir la validación de caché.
        """
        cadena_busqueda = self.texto_busqueda.get().lower().strip()

        firma_estado_actual = (
            self.ultimo_conteo,
            cadena_busqueda,
            self.columna_orden,
            self.orden_descendente,
        )
        if not forzar_renderizado and firma_estado_actual == self._ultima_firma_vista:
            return
        self._ultima_firma_vista = firma_estado_actual

        if cadena_busqueda:
            filas_filtradas = [
                fila_data
                for fila_data in self.filas_cacheadas
                if cadena_busqueda in fila_data[8]
            ]
        else:
            filas_filtradas = self.filas_cacheadas[:]

        def funcion_clave_ordenamiento(fila_data: tuple) -> Any:
            if self.columna_orden == 5:
                return len(fila_data[7]) > 0
            return (
                str(fila_data[self.columna_orden]).lower()
                if fila_data[self.columna_orden]
                else ""
            )

        try:
            filas_filtradas.sort(
                key=funcion_clave_ordenamiento, reverse=self.orden_descendente
            )
        except Exception:
            pass

        cantidad_filas_filtradas = len(filas_filtradas)
        for indice_visual, datos_fila in enumerate(filas_filtradas):
            self._configurar_fila_en_pool(indice_visual, datos_fila)

        for i in range(cantidad_filas_filtradas, len(self._pool_filas)):
            for componente_visual in self._pool_filas[i].values():
                componente_visual.grid_remove()

    def actualizar_grilla(self) -> None:
        """
        Bucle perpetuo asíncrono. Consulta a la base de datos si ocurrieron cambios, y de ser así,
        actualiza la caché interna de filas y dispara un renderizado visual forzado.
        """
        if not self.ruta_db:
            return

        try:
            conteo_actual_db = persistencia.contar_entregas(self.ruta_db)
            if conteo_actual_db != self.ultimo_conteo:
                self.ultimo_conteo = conteo_actual_db
                registros_crudos = persistencia.listar_entregas_activas(self.ruta_db)

                total_alertas_calculadas = 0
                self.filas_cacheadas = []

                for registro_fila in registros_crudos:
                    if len(registro_fila[7]) > 0:
                        total_alertas_calculadas += 1

                    texto_precalculado_busqueda = f"{registro_fila[0]} {registro_fila[1]} {registro_fila[2]}".lower()

                    self.filas_cacheadas.append(
                        (*registro_fila, texto_precalculado_busqueda)
                    )

                self.lbl_contador_entregas.configure(
                    text=str(len(self.filas_cacheadas))
                )

                if total_alertas_calculadas > 0:
                    self.lbl_contador_alertas.configure(
                        text=str(total_alertas_calculadas),
                        text_color=COLOR_ALERTA_IP_DIFIERE,
                    )
                else:
                    self.lbl_contador_alertas.configure(
                        text="0", text_color=COLOR_ALERTA_IP_OK
                    )

                self._refrescar_vista(forzar_renderizado=True)

        except Exception as excepcion_bd:
            logging.error(f"Error actualizando grilla de entregas: {excepcion_bd}")

        self.after(self.intervalo_actualizacion, self.actualizar_grilla)

    # -----------------------------------------------------------------------------
    # EVENTOS Y CONTROLADORES DE SISTEMA
    # -----------------------------------------------------------------------------
    def iniciar_sistema(self) -> None:
        """
        Punto de entrada de arranque. Valida el formulario, crea los directorios,
        prepara la base de datos y delega la inicialización de red a la API.
        """
        turno_ingresado = self.entrada_turno.get().strip().upper()
        aula_ingresada = self.entrada_aula.get().strip().upper()
        modulo_seleccionado = self.var_modulo.get()

        if not turno_ingresado or not aula_ingresada:
            self.lbl_error.configure(text="Error: Debe completar el Turno y el Aula.")
            return

        fecha_hoy = datetime.now().strftime("%Y%m%d")
        nombre_carpeta_sesion = f"entregas_{modulo_seleccionado}_{fecha_hoy}_{turno_ingresado}_{aula_ingresada}"
        ruta_directorio_entregas = os.path.join(
            api.obtener_directorio_base(), nombre_carpeta_sesion
        )

        os.makedirs(ruta_directorio_entregas, exist_ok=True)
        self.ruta_db = os.path.join(ruta_directorio_entregas, "seep_registro.db")

        pin_sesion = persistencia.inicializar_base_datos(
            self.ruta_db,
            modulo_seleccionado,
            fecha_hoy,
            turno_ingresado,
            aula_ingresada,
            api._generar_pin(),
        )

        aplicacion_flask = api.crear_app(
            modulo_seleccionado, pin_sesion, ruta_directorio_entregas, self.ruta_db
        )

        _, ips_locales_detectadas = api.iniciar_servidor_en_hilo(
            aplicacion_flask, callback_error=self.mostrar_error_critico
        )

        self.title(
            f"SEEP - Panel Docente | Módulo: {modulo_seleccionado.upper()} | Aula: {aula_ingresada}"
        )
        self.frame_config.pack_forget()
        self.frame_dashboard.pack(pady=20, padx=20, fill="both", expand=True)

        texto_ips = " | ".join(ips_locales_detectadas)
        self.lbl_info_dash.configure(text=f"IPs: {texto_ips}   |   PIN: {pin_sesion}")

        self.ruta_entregas = ruta_directorio_entregas
        self.actualizar_grilla()

    def mostrar_error_critico(self, titulo_error: str, mensaje_error: str) -> None:
        """
        Lanza un cuadro de diálogo modal por encima de la interfaz deteniendo el flujo y forzando
        el cierre incondicional de la aplicación. Se utiliza ante fallas irrecuperables de la API web.

        Args:
            titulo_error (str): Título de la ventana emergente.
            mensaje_error (str): Descripción detallada del fallo para el docente.
        """

        def _mostrar_y_cerrar_aplicacion() -> None:
            messagebox.showerror(titulo_error, mensaje_error)
            os._exit(1)

        self.after(0, _mostrar_y_cerrar_aplicacion)

    def abrir_carpeta_entregas(self) -> None:
        """
        Invoca al sistema operativo anfitrión para abrir la ubicación física
        donde se están almacenando los exámenes recibidos.
        """
        if not self.ruta_entregas or not os.path.exists(self.ruta_entregas):
            messagebox.showerror("Error", "La carpeta no existe o no se ha creado aún.")
            return

        try:
            if os.name == "nt":
                os.startfile(self.ruta_entregas)
            else:
                comando_apertura = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([comando_apertura, self.ruta_entregas])
        except Exception as excepcion_os:
            logging.error(f"No se pudo abrir la carpeta: {excepcion_os}")
            messagebox.showerror("Error", "No se pudo abrir la carpeta de destino.")

    def exportar_csv_gui(self) -> None:
        """
        Manejador de evento para exportar el historial de auditoría de la base de datos
        a un formato legible y compatible con sistemas administrativos.
        """
        if not self.ruta_entregas or not self.ruta_db:
            messagebox.showerror("Error", "El servidor no está iniciado.")
            return

        try:
            ruta_destino_csv = os.path.join(
                self.ruta_entregas, "asistencia_parcial.csv"
            )
            persistencia.exportar_asistencia_csv(self.ruta_db, ruta_destino_csv)
            messagebox.showinfo(
                "Éxito", f"Reporte exportado correctamente en:\n{ruta_destino_csv}"
            )
        except Exception as excepcion_exportacion:
            logging.error(f"Error al exportar CSV: {excepcion_exportacion}")
            messagebox.showerror(
                "Error", f"No se pudo generar el CSV:\n{excepcion_exportacion}"
            )

    def habilitar_reentrega_gui(
        self, legajo_alumno: str, nombres_alumno: str, apellidos_alumno: str
    ) -> None:
        """
        Intermediario de seguridad. Exige la confirmación implícita de la base de datos
        antes de notificar al docente que una anulación fue exitosa.

        Args:
            legajo_alumno (str): Identificador único del alumno objetivo.
            nombres_alumno (str): Nombres provistos en el registro inicial.
            apellidos_alumno (str): Apellidos provistos en el registro inicial.
        """
        if not self.ruta_db:
            return

        try:
            persistencia.habilitar_reentrega(self.ruta_db, legajo_alumno)
            mensaje_exito = (
                f"Se habilitó UNA (1) nueva entrega para:\n{apellidos_alumno}, {nombres_alumno}\n"
                f"(Legajo/DNI: {legajo_alumno}).\n\nEl alumno ya puede darle a 'Entregar' en su computadora."
            )
            messagebox.showinfo("Reentrega Autorizada", mensaje_exito)
        except Exception as excepcion_bd:
            logging.error(f"Error habilitando reentrega: {excepcion_bd}")
            messagebox.showerror(
                "Error de Base de Datos", f"No se pudo habilitar: {str(excepcion_bd)}"
            )

    def mostrar_modal_alertas(
        self,
        legajo_alumno: str,
        nombres_alumno: str,
        apellidos_alumno: str,
        alertas_detectadas: List[str],
    ) -> None:
        """
        Genera y presenta una ventana secundaria detallando los motivos de advertencia
        de seguridad detectados por el motor de reglas.

        Args:
            legajo_alumno (str): Legajo evaluado.
            nombres_alumno (str): Nombre del alumno observado.
            apellidos_alumno (str): Apellidos del alumno observado.
            alertas_detectadas (List[str]): Cadenas explicativas provenientes de `persistencia.py`.
        """
        ventana_modal = ctk.CTkToplevel(self)
        ventana_modal.title(f"Alertas de Seguridad - {legajo_alumno}")
        ventana_modal.geometry(GEOMETRIA_MODAL_ALERTAS)
        ventana_modal.attributes("-topmost", True)
        ventana_modal.grab_set()

        etiqueta_identificacion = f"Alumno: {apellidos_alumno}, {nombres_alumno}"
        ctk.CTkLabel(
            ventana_modal, text=etiqueta_identificacion, font=FUENTE_SUBTITULO
        ).pack(pady=(20, 10))

        marco_contenedor_alertas = ctk.CTkFrame(ventana_modal)
        marco_contenedor_alertas.pack(padx=20, pady=10, fill="both", expand=True)

        for texto_alerta in alertas_detectadas:
            ctk.CTkLabel(
                marco_contenedor_alertas,
                text=texto_alerta,
                text_color=COLOR_ALERTA_IP_DIFIERE,
                font=FUENTE_NORMAL_BOLD,
                justify="left",
                wraplength=380,
            ).pack(pady=5, padx=10, anchor="w")

        ctk.CTkButton(ventana_modal, text="Cerrar", command=ventana_modal.destroy).pack(
            pady=15
        )
