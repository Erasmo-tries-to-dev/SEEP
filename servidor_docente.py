"""
Punto de entrada principal del Servidor de Entregas SEEP.
"""

import sys
import logging
from servidor_modulos.interfaz import InterfazServidor


import socket
from tkinter import messagebox
import tkinter as tk
import seep_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("seep_servidor.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


# NOTA: Esto es un parche temporal debido a que interfaz.py parece no escuchar la excepcion de puerto ocupado, o bien esta nunca de lanza, hay que averiguar porque ocurre esto.
# No es lo ideal, pero permite verificar si el puerto esta ocupado antes de iniciar la interfaz y mostrar un mensaje de error.
def verificar_puerto_libre(puerto: int) -> bool:
    """Intenta conectarse al puerto para ver si ya hay un servidor escuchando."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", puerto))
            return False
        except (ConnectionRefusedError, TimeoutError, socket.timeout, OSError):
            return True


if __name__ == "__main__":
    if not verificar_puerto_libre(seep_config.PUERTO_API):
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "❌ ERROR CRÍTICO - Puerto Ocupado",
            f"El puerto {seep_config.PUERTO_API} ya está en uso.\n\n"
            "Esto ocurre porque ya hay otra ventana de SEEP abierta.\n"
            "Cierre el otro servidor docente y vuelva a intentar.",
        )
        root.destroy()
        exit(1)
    app = InterfazServidor()
    app.mainloop()
