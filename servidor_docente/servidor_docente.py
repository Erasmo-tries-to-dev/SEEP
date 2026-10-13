"""
Punto de entrada principal del Servidor de Entregas SEEP.
"""

from interfaz import InterfazServidor

if __name__ == "__main__":
    app = InterfazServidor()
    app.mainloop()
