#!/usr/bin/env python3
# -*- coding: utf-8 -*- # Especifica la codificación UTF-8 para el archivo

import os
import requests
import xml.etree.ElementTree as ET
import json
import re
import argparse
from colorama import Fore, Style, init
import csv
import datetime
import inspect # Usado en print_debug para obtener el nombre de la función

# Inicializar colorama para salida de texto coloreada en la consola
init(autoreset=True)

# Versión del script
VERSION = "1.2.0" # Mantener la versión por si se usa en otro lugar

# Nombre del archivo de configuración JSON esperado
CONFIG_FILE = "plex.config.json"

# Ya no hay banner aquí

# --- Funciones ---

def load_config(file_path):
    """
    Carga la configuración desde un archivo JSON.

    Args:
        file_path (str): La ruta al archivo de configuración JSON.

    Returns:
        dict: Un diccionario con la configuración cargada, o None si ocurre un error.
    """
    print(f"{Fore.CYAN}Intentando cargar configuración desde: {file_path}{Style.RESET_ALL}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f: # Especificar encoding utf-8
            config = json.load(f)
        print(f"{Fore.GREEN}Archivo de configuración cargado exitosamente.{Style.RESET_ALL}")
        return config
    except FileNotFoundError:
        print(f"{Fore.LIGHTRED_EX}Error: Archivo de configuración '{file_path}' no encontrado.{Style.RESET_ALL}")
        return None
    except json.JSONDecodeError:
        print(f"{Fore.LIGHTRED_EX}Error: El archivo de configuración '{file_path}' no es un JSON válido.{Style.RESET_ALL}")
        return None
    except Exception as e:
        print(f"{Fore.LIGHTRED_EX}Error inesperado al leer el archivo '{file_path}': {e}{Style.RESET_ALL}")
        return None

def print_debug(message, debug=False):
    """
    Imprime mensajes de depuración si el modo debug está activado.

    Args:
        message (str): El mensaje a imprimir.
        debug (bool): Flag para activar/desactivar la impresión de depuración.
    """
    if debug:
        # Obtener el nombre de la función que llamó a print_debug
        function_name = inspect.stack()[1].function
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{Fore.LIGHTYELLOW_EX}[DEBUG] {timestamp} - {function_name} - {message}{Style.RESET_ALL}")

def plex_request(url, headers, debug=False):
    """
    Realiza una petición GET a la API de Plex y parsea la respuesta XML.

    Args:
        url (str): La URL del endpoint de la API de Plex.
        headers (dict): Los encabezados HTTP para la petición (incluyendo X-Plex-Token).
        debug (bool): Flag para activar/desactivar mensajes de depuración.

    Returns:
        xml.etree.ElementTree.Element: El elemento raíz del XML parseado, o None si hay un error.
    """
    print_debug(f"Realizando petición HTTP GET a: {url}", debug)
    try:
        response = requests.get(url, headers=headers, timeout=30) # Añadir timeout
        response.raise_for_status() # Lanza excepción para códigos de error HTTP (4xx o 5xx)
        print_debug(f"Petición exitosa (Código {response.status_code})", debug)
        # Intentar parsear la respuesta como XML
        return ET.fromstring(response.content)
    except requests.exceptions.Timeout:
        print(f"{Fore.LIGHTRED_EX}Error: La petición a Plex API ({url}) superó el tiempo de espera.{Style.RESET_ALL}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"{Fore.LIGHTRED_EX}Error en la petición a Plex API ({url}): {e}{Style.RESET_ALL}")
        return None
    except ET.ParseError as e:
        print(f"{Fore.LIGHTRED_EX}Error al parsear la respuesta XML de Plex ({url}): {e}{Style.RESET_ALL}")
        print_debug(f"Contenido recibido: {response.text[:500]}...", debug) # Mostrar inicio de respuesta si falla el parseo
        return None

def fetch_plex_sections(plex_url, plex_token, debug=False):
    """
    Obtiene la lista de secciones (bibliotecas) del servidor Plex.

    Args:
        plex_url (str): La URL base del servidor Plex.
        plex_token (str): El token de autenticación de Plex.
        debug (bool): Flag para activar/desactivar mensajes de depuración.

    Returns:
        xml.etree.ElementTree.Element: El XML con las secciones, o None si falla.
    """
    url = f"{plex_url}/library/sections"
    headers = {"X-Plex-Token": plex_token, "Accept": "application/xml"} # Pedir XML explícitamente
    print_debug("Obteniendo secciones de la biblioteca", debug)
    return plex_request(url, headers, debug)

def fetch_plex_movies(plex_url, plex_token, section_id, debug=False):
    """
    Obtiene todos los elementos (películas) dentro de una sección específica de Plex.

    Args:
        plex_url (str): La URL base del servidor Plex.
        plex_token (str): El token de autenticación de Plex.
        section_id (str): El ID de la sección de películas.
        debug (bool): Flag para activar/desactivar mensajes de depuración.

    Returns:
        xml.etree.ElementTree.Element: El XML con los metadatos de las películas, o None si falla.
    """
    url = f"{plex_url}/library/sections/{section_id}/all"
    headers = {"X-Plex-Token": plex_token, "Accept": "application/xml"}
    print_debug(f"Obteniendo películas de la sección ID: {section_id}", debug)
    return plex_request(url, headers, debug)

def get_identifiers(metadata_xml):
    """
    Extrae identificadores (IMDb, TMDb) de los elementos <Guid> en el XML de metadatos.

    Args:
        metadata_xml (xml.etree.ElementTree.Element): El XML de metadatos de un item.

    Yields:
        tuple: Un par (tipo_identificador, id_valor) como ('imdb', 'tt1234567').
    """
    if metadata_xml is None:
        return

    # Busca todos los elementos <Guid> dentro del XML proporcionado
    for guid in metadata_xml.findall(".//Guid"):
        guid_id = guid.get("id", "") # Obtiene el valor del atributo 'id', default a "" si no existe
        # Comprueba si el ID corresponde a IMDb
        if "imdb://" in guid_id:
            yield "imdb", guid_id.split("//")[-1] # Devuelve 'imdb' y el ID real
        # Comprueba si el ID corresponde a TMDb
        elif "tmdb://" in guid_id:
            yield "tmdb", guid_id.split("//")[-1] # Devuelve 'tmdb' y el ID real

def get_movie_info(plex_url, plex_token, video_xml, debug=False):
    """
    Obtiene información detallada de una película específica, incluyendo una petición
    adicional para metadatos completos como IDs y rating.

    Args:
        plex_url (str): La URL base del servidor Plex.
        plex_token (str): El token de autenticación de Plex.
        video_xml (xml.etree.ElementTree.Element): El elemento XML <Video> de la película.
        debug (bool): Flag para activar/desactivar mensajes de depuración.

    Returns:
        dict: Un diccionario con la información de la película, o None si falla la obtención de metadatos.
              Campos: 'title', 'file_path', 'file_directory', 'file_size', 'imdb_id', 'imdb_rating'.
    """
    headers = {"X-Plex-Token": plex_token, "Accept": "application/xml"}

    # --- Información básica del elemento <Video> inicial ---
    part_element = video_xml.find(".//Part")
    file_path = part_element.get("file", "N/A") if part_element is not None else "N/A"
    basic_title = video_xml.get('title', 'Título Desconocido')
    print_debug(f"Procesando item básico: {basic_title}", debug)

    # --- Obtener Metadatos Detallados ---
    rating_key = video_xml.get("ratingKey")
    if not rating_key:
        print(f"{Fore.YELLOW}Advertencia: No se encontró 'ratingKey' para el item {basic_title}. Saltando metadatos detallados.{Style.RESET_ALL}")
        return None

    metadata_url = f"{plex_url}/library/metadata/{rating_key}"
    print_debug(f"Obteniendo metadatos detallados desde: {metadata_url}", debug)
    metadata_xml = plex_request(metadata_url, headers, debug)

    if metadata_xml is None:
        print(f"{Fore.YELLOW}Advertencia: No se pudieron obtener metadatos detallados para el item con ratingKey {rating_key} ({basic_title}).{Style.RESET_ALL}")
        return None

    # --- Extraer Información de los Metadatos Detallados ---
    video_metadata_element = metadata_xml.find(".//Video")
    if video_metadata_element is None:
         print(f"{Fore.YELLOW}Advertencia: No se encontró el elemento <Video> en los metadatos detallados para {basic_title}.{Style.RESET_ALL}")
         return None

    title = video_metadata_element.get('title', basic_title)
    imdb_id = "N/A"
    for type, id_val in get_identifiers(metadata_xml):
        if type == "imdb":
            imdb_id = id_val
            break

    imdb_rating = video_metadata_element.get('rating', 'N/A')

    file_size = "N/A"
    if file_path != "N/A" and os.path.exists(file_path):
        try:
            file_size_bytes = os.path.getsize(file_path)
            file_size = file_size_bytes
        except OSError as e:
            print(f"{Fore.YELLOW}Advertencia: No se pudo obtener el tamaño del archivo '{file_path}': {e}{Style.RESET_ALL}")
            file_size = "Error"
    elif file_path != "N/A":
        print(f"{Fore.YELLOW}Advertencia: La ruta del archivo '{file_path}' no existe o no es accesible desde donde se ejecuta el script.{Style.RESET_ALL}")
        file_size = "Inaccesible"

    return {
        "title": title,
        "file_path": file_path,
        "file_directory": os.path.dirname(file_path) if file_path != "N/A" else "N/A",
        "file_size": file_size,
        "imdb_id": imdb_id,
        "imdb_rating": imdb_rating
    }

def export_to_csv(data, filename="plex_movies_export.csv"):
    """
    Exporta la lista de diccionarios de películas a un archivo CSV.
    Todos los campos se escribirán entre comillas dobles.

    Args:
        data (list): Una lista de diccionarios, donde cada diccionario representa una película.
        filename (str): El nombre del archivo CSV a generar.
    """
    if not data:
        print(f"{Fore.YELLOW}No se encontraron datos de películas para exportar.{Style.RESET_ALL}")
        return

    print(f"{Fore.CYAN}Iniciando exportación a CSV: {filename}{Style.RESET_ALL}")
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['title', 'imdb_id', 'imdb_rating', 'file_path', 'file_directory', 'file_size']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for movie in data:
                writer.writerow(movie)
        print(f"{Fore.LIGHTGREEN_EX}Éxito: Datos exportados correctamente a '{filename}'. Se procesaron {len(data)} películas.{Style.RESET_ALL}")
    except IOError as e:
         print(f"{Fore.LIGHTRED_EX}Error de E/S al escribir el archivo CSV '{filename}': {e}{Style.RESET_ALL}")
    except Exception as e:
         print(f"{Fore.LIGHTRED_EX}Error inesperado durante la exportación a CSV: {e}{Style.RESET_ALL}")

def list_movie_files(plex_url, plex_token, debug=False):
    """
    Función principal que orquesta la obtención de datos de películas y su exportación.
    """
    # Mensaje inicial simple sin banner
    print(f"{Fore.LIGHTGREEN_EX}--- PlexExportCSV v{VERSION} ---{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Iniciando proceso para listar películas y exportar a CSV...{Style.RESET_ALL}")

    sections_xml = fetch_plex_sections(plex_url, plex_token, debug)
    if sections_xml is None:
        print(f"{Fore.LIGHTRED_EX}No se pudieron obtener las secciones de Plex. Abortando.{Style.RESET_ALL}")
        return

    all_movie_data = []
    print(f"{Fore.CYAN}Buscando secciones de tipo 'movie'...{Style.RESET_ALL}")
    found_movie_sections = False
    for section in sections_xml.findall(".//Directory"):
        if section.get("type") == "movie":
            found_movie_sections = True
            section_id = section.get("key")
            section_title = section.get("title", f"ID {section_id}")
            print(f"{Fore.BLUE}Procesando sección de películas: '{section_title}' (ID: {section_id}){Style.RESET_ALL}")

            movies_xml = fetch_plex_movies(plex_url, plex_token, section_id, debug)
            if movies_xml is None:
                print(f"{Fore.YELLOW}Advertencia: No se pudieron obtener películas para la sección '{section_title}'. Saltando esta sección.{Style.RESET_ALL}")
                continue

            movie_elements = movies_xml.findall(".//Video")
            total_movies_in_section = len(movie_elements)
            print(f"{Fore.CYAN}Se encontraron {total_movies_in_section} elementos en la sección '{section_title}'. Procesando metadatos...{Style.RESET_ALL}")

            processed_count = 0
            for video_xml in movie_elements:
                processed_count += 1
                if processed_count % 20 == 0 or processed_count == total_movies_in_section:
                     print(f"{Fore.MAGENTA}  Procesando película {processed_count}/{total_movies_in_section}...", end='\r')

                try:
                    movie_info = get_movie_info(plex_url, plex_token, video_xml, debug)
                    if movie_info:
                        all_movie_data.append(movie_info)
                except Exception as e:
                    title_for_error = video_xml.get('title', 'Desconocido')
                    print(f"\n{Fore.LIGHTRED_EX}Error inesperado procesando la película '{title_for_error}': {e}{Style.RESET_ALL}")
                    print_debug(f"XML del item con error: {ET.tostring(video_xml, encoding='unicode')}", debug)

            print(f"\n{Fore.GREEN}Sección '{section_title}' procesada.{Style.RESET_ALL}")

    if not found_movie_sections:
         print(f"{Fore.YELLOW}No se encontraron secciones de tipo 'movie' en tu servidor Plex.{Style.RESET_ALL}")

    export_to_csv(all_movie_data)

def verify_config(config):
    """
    Verifica que las claves esenciales estén presentes en el diccionario de configuración.

    Args:
        config (dict): El diccionario de configuración cargado.

    Returns:
        tuple: Un par (PLEX_BASE_URL, PLEX_TOKEN) si la configuración es válida.
               Lanza SystemExit si falta alguna clave.
    """
    missing_keys = []
    plex_base_url = config.get("PLEX_BASE_URL")
    plex_token = config.get("PLEX_TOKEN")

    if not plex_base_url:
        missing_keys.append("PLEX_BASE_URL")
    if not plex_token:
        missing_keys.append("PLEX_TOKEN")

    if missing_keys:
        print(f"{Fore.LIGHTRED_EX}Error: Faltan las siguientes claves obligatorias en el archivo de configuración ({CONFIG_FILE}): {', '.join(missing_keys)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Asegúrate de que el archivo '{CONFIG_FILE}' existe en el mismo directorio y contiene las claves PLEX_BASE_URL y PLEX_TOKEN con sus valores.{Style.RESET_ALL}")
        exit(1)

    if not plex_base_url.startswith(("http://", "https://")):
         print(f"{Fore.YELLOW}Advertencia: PLEX_BASE_URL ('{plex_base_url}') no parece una URL válida (debería empezar con http:// o https://).{Style.RESET_ALL}")
    if plex_base_url.endswith('/'):
        plex_base_url = plex_base_url[:-1]
        print_debug(f"Se eliminó la barra final de PLEX_BASE_URL. Nuevo valor: {plex_base_url}", True)

    return plex_base_url, plex_token

# --- Punto de Entrada Principal ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        # Se quita la versión del nombre aquí ya que no hay banner, pero se mantiene en la descripción
        description=f"PlexExportCSV: Extrae información de películas (título, ruta, tamaño, IDs, rating) de las bibliotecas tipo 'movie' de un servidor Plex y la guarda en un archivo CSV. Versión {VERSION}",
        epilog="Ejemplo: python script.py -d"
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="Habilita el modo de depuración para mostrar mensajes detallados, incluyendo peticiones HTTP."
    )
    parser.add_argument(
        "-c", "--config",
        default=CONFIG_FILE,
        help=f"Ruta al archivo de configuración JSON (por defecto: {CONFIG_FILE})."
    )

    args = parser.parse_args()
    config_file_path = args.config
    CONFIG = load_config(config_file_path)

    if not CONFIG:
        print(f"{Fore.LIGHTRED_EX}No se pudo cargar la configuración desde '{config_file_path}'. Saliendo del programa.{Style.RESET_ALL}")
        exit(1)

    try:
        PLEX_BASE_URL, PLEX_TOKEN = verify_config(CONFIG)
    except SystemExit:
        exit(1)

    # Llamar a la función principal
    list_movie_files(PLEX_BASE_URL, PLEX_TOKEN, args.debug)

    print(f"\n{Fore.LIGHTGREEN_EX}Proceso completado.{Style.RESET_ALL}")
