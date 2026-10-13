"""
Punto de entrada principal del Servidor de Entregas SEEP.
"""

from servidor_modulos.interfaz import InterfazServidor

if __name__ == "__main__":
    app = InterfazServidor()
    app.mainloop()
