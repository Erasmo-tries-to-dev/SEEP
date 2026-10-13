"""
Punto de entrada principal del Servidor de Entregas SEEP.
"""

import sys
import logging
from servidor_modulos.interfaz import InterfazServidor

# 1. El orquestador principal configura el logging UNA sola vez para todo el sistema
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("seep_servidor.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

if __name__ == "__main__":
    # 2. Arrancamos el sistema sabiendo que cualquier módulo que use logging
    # escribirá automáticamente en 'seep_servidor.log'
    app = InterfazServidor()
    app.mainloop()
