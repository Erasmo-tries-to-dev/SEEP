"""
Módulo de Interfaz Gráfica (GUI) de SEEP.
Contiene la clase principal que maneja las pantallas de configuración y el dashboard.
"""

import os
import logging
from datetime import datetime
from tkinter import messagebox
import customtkinter as ctk

import seep_config
import persistencia
import api


class InterfazServidor(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("SEEP - Configuración Inicial")
        self.geometry("700x500")

        # Atributos de estado (Reemplazan al diccionario 'estado' y evitan globales)
        self.ruta_db = None
        self.ultimo_conteo = -1
        self.intervalo_actualizacion = 3000

        self._construir_pantalla_config()
        self._construir_pantalla_dashboard()

    def _construir_pantalla_config(self):
        self.frame_config = ctk.CTkFrame(self)
        self.frame_config.pack(pady=40, padx=40, fill="both", expand=True)

        ctk.CTkLabel(
            self.frame_config,
            text="Configuración de la Sesión",
            font=("Roboto", 24, "bold"),
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

        self.lbl_error = ctk.CTkLabel(self.frame_config, text="", text_color="red")
        self.lbl_error.pack(pady=5)

        ctk.CTkButton(
            self.frame_config,
            text="Iniciar Servidor",
            command=self.iniciar_sistema,
            font=("Roboto", 14, "bold"),
        ).pack(pady=20)

    def _construir_pantalla_dashboard(self):
        self.frame_dashboard = ctk.CTkFrame(self)

        self.lbl_titulo_dash = ctk.CTkLabel(
            self.frame_dashboard,
            text="SERVIDOR ACTIVO",
            font=("Roboto", 24, "bold"),
            text_color="green",
        )
        self.lbl_info_dash = ctk.CTkLabel(
            self.frame_dashboard, text="", font=("Roboto", 18, "bold")
        )
        self.lbl_ruta_dash = ctk.CTkLabel(
            self.frame_dashboard, text="", font=("Roboto", 12)
        )

        self.lbl_titulo_dash.pack(pady=10)
        self.lbl_info_dash.pack(pady=5)
        self.lbl_ruta_dash.pack(pady=(0, 10))

        self.frame_lista = ctk.CTkScrollableFrame(
            self.frame_dashboard,
            label_text="Entregas Recibidas (Actualización en tiempo real)",
        )
        self.frame_lista.pack(pady=10, padx=20, fill="both", expand=True)

    def iniciar_sistema(self):
        turno = self.entrada_turno.get().strip().upper()
        aula = self.entrada_aula.get().strip().upper()
        modulo = self.var_modulo.get()

        if not turno or not aula:
            self.lbl_error.configure(text="Error: Debe completar el Turno y el Aula.")
            return

        # Inicializamos entorno y BD a través del módulo api
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

        # Transición de interfaz
        self.title(f"SEEP - Panel Docente | Módulo: {modulo.upper()} | Aula: {aula}")
        self.frame_config.pack_forget()
        self.frame_dashboard.pack(pady=20, padx=20, fill="both", expand=True)

        self.lbl_info_dash.configure(text=f"IP: {ip_local}   |   PIN: {pin_sesion}")
        self.lbl_ruta_dash.configure(text=f"Guardando en: {ruta_carpeta}")

        self.actualizar_grilla()

    def mostrar_error_critico(self, titulo, mensaje):
        """Callback llamado desde api.py si el servidor falla al arrancar."""
        messagebox.showerror(titulo, mensaje)

    def habilitar_reentrega_gui(self, legajo_alumno, nombres, apellidos):
        if not self.ruta_db:
            return
        try:
            persistencia.habilitar_reentrega(self.ruta_db, legajo_alumno)
            messagebox.showinfo(
                "Reentrega Autorizada",
                f"Se habilitó UNA (1) nueva entrega para:\n{apellidos}, {nombres}\n(Legajo/DNI: {legajo_alumno}).\n\nEl alumno ya puede darle a 'Entregar' en su computadora.",
            )
        except Exception as e:
            logging.error(f"Error habilitando reentrega: {e}")
            messagebox.showerror(
                "Error de Base de Datos", f"No se pudo habilitar: {str(e)}"
            )

    def dibujar_encabezados(self):
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
            ctk.CTkLabel(
                self.frame_lista, text=texto, font=("Roboto", 14, "bold")
            ).grid(row=0, column=col, padx=10, pady=5, sticky="w")

    def dibujar_fila(self, indice, fila):
        legajo, apellidos, nombres, timestamp, comprobante, ip_vinculada, ip_origen = (
            fila
        )
        hora_str = str(timestamp)[11:19]
        ip_difiere = ip_vinculada != ip_origen
        alerta_ip = "⚠️ Difiere" if ip_difiere else "OK"
        color_ip = "orange" if ip_difiere else "gray"

        celdas = [
            (ctk.CTkLabel(self.frame_lista, text=legajo), 0),
            (ctk.CTkLabel(self.frame_lista, text=apellidos), 1),
            (ctk.CTkLabel(self.frame_lista, text=nombres), 2),
            (ctk.CTkLabel(self.frame_lista, text=hora_str), 3),
            (
                ctk.CTkLabel(self.frame_lista, text=comprobante, font=("Consolas", 12)),
                4,
            ),
            (ctk.CTkLabel(self.frame_lista, text=alerta_ip, text_color=color_ip), 5),
        ]
        for widget, col in celdas:
            widget.grid(row=indice, column=col, padx=10, pady=2, sticky="w")

        ctk.CTkButton(
            self.frame_lista,
            text="Habilitar",
            width=80,
            fg_color="#8B0000",
            hover_color="#FF0000",
            command=lambda l=legajo, n=nombres, a=apellidos: self.habilitar_reentrega_gui(
                l, n, a
            ),
        ).grid(row=indice, column=6, padx=10, pady=2, sticky="w")

    def actualizar_grilla(self):
        if not self.ruta_db:
            return
        try:
            conteo_actual = persistencia.contar_entregas(self.ruta_db)
            if conteo_actual != self.ultimo_conteo:
                self.ultimo_conteo = conteo_actual
                for widget in self.frame_lista.winfo_children():
                    widget.destroy()
                self.dibujar_encabezados()

                filas = persistencia.listar_entregas_activas(self.ruta_db)
                for indice, fila in enumerate(filas, start=1):
                    self.dibujar_fila(indice, fila)
        except Exception as e:
            logging.error(f"Error actualizando grilla: {e}")

        self.after(self.intervalo_actualizacion, self.actualizar_grilla)
