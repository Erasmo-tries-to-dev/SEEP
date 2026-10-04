import os
import time
import hashlib
import csv
import base64
import requests
from datetime import datetime

# --- CONFIGURACIÓN DE LA NUBE ---
# Debe coincidir exactamente con la URL de tu servidor en Render
URL_NUBE = "https://seep-buffer.onrender.com"

# Variables globales para el contexto de la sesión
MODULO_ACTIVO = ""
CARPETA_ENTREGAS = ""


def limpiar_cadena(texto):
    """
    Sanitiza una cadena de texto eliminando caracteres inválidos
    para garantizar compatibilidad con el sistema de archivos de Windows.
    """
    if not texto:
        return "Desconocido"
    texto = texto.replace(" ", "_").replace("/", "-")
    for caracter_invalido in ["<", ">", ":", '"', "\\", "|", "?", "*"]:
        texto = texto.replace(caracter_invalido, "")
    return texto.strip()


def calcular_hash_bytes(contenido_bytes):
    """
    Calcula el hash SHA-256 directamente desde los bytes decodificados del archivo.
    Esto mantiene la función anti-plagio sin necesidad de leer el archivo del disco.
    """
    sha256_hash = hashlib.sha256()
    sha256_hash.update(contenido_bytes)
    return sha256_hash.hexdigest()


def registrar_en_csv(datos_fila):
    """
    Guarda los datos de la entrega en un archivo CSV.
    Ya no necesita Lock porque el procesamiento es secuencial.
    """
    nombre_archivo_csv = f"registro_entregas_{MODULO_ACTIVO}.csv"
    archivo_existe = os.path.isfile(nombre_archivo_csv)

    with open(nombre_archivo_csv, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")

        if not archivo_existe:
            writer.writerow(
                [
                    "Hora",
                    "Módulo",
                    "Legajo/DNI",
                    "Apellidos",
                    "Nombres",
                    "Hash SHA-256",
                    "Nombre de Archivo Original",
                    "Archivo Guardado Como",
                ]
            )

        writer.writerow(datos_fila)


def configurar_modulo():
    """
    Presenta un menú interactivo en consola para que el docente seleccione el módulo a evaluar.
    """
    print("=" * 60)
    print(" SELECCIONE EL MÓDULO A EVALUAR ")
    print("=" * 60)
    print(" 1. Imperativo (.pas)")
    print(" 2. Objetos (.zip)")
    print(" 3. Concurrente (Archivo sin extensión de R-Info)")
    print("=" * 60)

    while True:
        opcion = input("Ingrese la opción (1, 2 o 3): ").strip()
        if opcion == "1":
            return "imperativo", "entregas_imperativo"
        elif opcion == "2":
            return "objetos", "entregas_objetos"
        elif opcion == "3":
            return "concurrente", "entregas_concurrente"
        else:
            print("Opción inválida. Ingrese 1, 2 o 3.")


def iniciar_sesion_nube():
    """
    Contacta al servidor puente para crear un buzón temporal y obtener el PIN.
    """
    print("Conectando con la nube para abrir el buzón...")
    try:
        respuesta = requests.post(f"{URL_NUBE}/crear_buzon", timeout=10)
        respuesta.raise_for_status()
        return respuesta.json()["pin"]
    except Exception as e:
        print(f"❌ Error al conectar con el servidor: {e}")
        print("Asegúrese de tener conexión a Internet y que el servidor esté activo.")
        exit(1)


def cerrar_sesion_nube(pin):
    """
    Avisa al servidor que el examen terminó para liberar su memoria RAM.
    """
    print("\nCerrando buzón en la nube y limpiando memoria...")
    try:
        requests.delete(f"{URL_NUBE}/cerrar_buzon/{pin}", timeout=5)
        print("✅ Buzón cerrado exitosamente.")
    except:
        pass  # Si falla al cerrar no es crítico para nosotros


def consumir_entregas(pin):
    """
    Bucle infinito que consulta la nube cada 5 segundos buscando parciales nuevos.
    Descarga, guarda, registra y confirma la recepción (ACK).
    """
    while True:
        try:
            respuesta = requests.get(f"{URL_NUBE}/descargar/{pin}", timeout=10)

            if respuesta.status_code == 200:
                entregas = respuesta.json()

                for entrega in entregas:
                    apellidos_seguro = limpiar_cadena(entrega.get("apellidos"))
                    nombres_seguro = limpiar_cadena(entrega.get("nombres"))
                    id_seguro = limpiar_cadena(entrega.get("legajo"))
                    nombre_original = entrega.get("nombre_archivo")
                    id_entrega_nube = entrega.get("id_entrega")

                    # Extraer extensión original para mantener el formato
                    _, ext = os.path.splitext(nombre_original)

                    # Decodificar el archivo que viajó como texto Base64
                    contenido_bytes = base64.b64decode(entrega.get("contenido_b64"))

                    # Calcular Hash anti-plagio
                    hash_archivo = calcular_hash_bytes(contenido_bytes)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    hora_legible = datetime.now().strftime("%H:%M:%S")

                    nombre_final = f"{apellidos_seguro}_{nombres_seguro}_{id_seguro}_{timestamp}{ext}"
                    ruta_guardado = os.path.join(CARPETA_ENTREGAS, nombre_final)

                    # Guardar archivo físico en el disco del docente
                    with open(ruta_guardado, "wb") as f:
                        f.write(contenido_bytes)

                    # Registrar en CSV
                    datos_auditoria = [
                        hora_legible,
                        MODULO_ACTIVO,
                        id_seguro,
                        apellidos_seguro,
                        nombres_seguro,
                        hash_archivo,
                        nombre_original,
                        nombre_final,
                    ]
                    registrar_en_csv(datos_auditoria)

                    print(
                        f"[+] Descargado: {apellidos_seguro} {nombres_seguro} | DNI/Legajo: {id_seguro} | a las {hora_legible}"
                    )

                    # Enviar ACK al servidor para que borre el archivo de la nube
                    requests.post(
                        f"{URL_NUBE}/confirmar_recepcion/{pin}/{id_entrega_nube}",
                        timeout=5,
                    )

        except requests.exceptions.RequestException:
            # Silenciamos errores temporales de red para que el bucle no se corte si el internet parpadea
            pass

        # Pausa de 5 segundos antes de volver a preguntar (Evita saturar Render y te protege del rate-limit)
        time.sleep(5)


if __name__ == "__main__":
    MODULO_ACTIVO, CARPETA_ENTREGAS = configurar_modulo()

    os.makedirs(CARPETA_ENTREGAS, exist_ok=True)
    os.system("cls" if os.name == "nt" else "clear")

    PIN_ACTUAL = iniciar_sesion_nube()

    print("=" * 60)
    print(f" CLIENTE DOCENTE (SEEP) - MÓDULO {MODULO_ACTIVO.upper()} ")
    print("=" * 60)
    print(f" PIN PARA ALUMNOS: {PIN_ACTUAL}")
    print(f" LOS PARCIALES SE GUARDARÁN EN: ./{CARPETA_ENTREGAS}/")
    print(f" LOS LOGS SE GUARDARÁN EN: ./registro_entregas_{MODULO_ACTIVO}.csv")
    print("=" * 60)
    print(
        "Sincronizando con la nube. Esperando exámenes... (Presione Ctrl+C para finalizar)\n"
    )

    try:
        consumir_entregas(PIN_ACTUAL)
    except KeyboardInterrupt:
        # Esto captura cuando el docente aprieta Ctrl+C para cerrar el programa
        cerrar_sesion_nube(PIN_ACTUAL)
        print("\nPrograma finalizado correctamente.")
