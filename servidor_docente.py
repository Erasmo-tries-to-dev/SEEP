"""
Punto de entrada principal del Servidor de Entregas SEEP.
"""

import sys
import logging
import socket
import tkinter as tk
from tkinter import messagebox

import seep_config
from servidor_modulos.interfaz import InterfazServidor

# Inicialización temprana del logger: SOLO por consola.
# El archivo de log se configurará dinámicamente al crear la sesión.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)


def verificar_puerto_libre(puerto: int) -> bool:
    """
    Intenta conectarse al puerto para ver si ya hay un servidor escuchando.

    Args:
        puerto (int): Número de puerto a verificar.

    Returns:
        bool: True si el puerto está libre, False si está ocupado.

    Notes:
        NOTA: Esto es un parche temporal debido a que interfaz.py parece no escuchar
        la excepción de puerto ocupado. Permite verificar la disponibilidad antes de
        iniciar la interfaz y mostrar un mensaje de error amigable.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_prueba:
        socket_prueba.settimeout(0.5)
        try:
            socket_prueba.connect(("127.0.0.1", puerto))
            return False
        except (ConnectionRefusedError, TimeoutError, socket.timeout, OSError):
            return True


if __name__ == "__main__":
    if not verificar_puerto_libre(seep_config.PUERTO_API):
        ventana_raiz = tk.Tk()
        ventana_raiz.withdraw()
        messagebox.showerror(
            "❌ ERROR CRÍTICO - Puerto Ocupado",
            f"El puerto {seep_config.PUERTO_API} ya está en uso.\n\n"
            "Esto ocurre porque ya hay otra ventana de SEEP abierta.\n"
            "Cierre el otro servidor docente y vuelva a intentar.",
        )
        ventana_raiz.destroy()
        sys.exit(1)

    aplicacion = InterfazServidor()
    aplicacion.mainloop()
