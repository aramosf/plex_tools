# Script: Plex-Renamer
# Versión: 1.7.0
# Descripción: Este script se conecta a un servidor Plex, lista los archivos de películas,
#              compara los nombres de archivo con los títulos de metadatos, y ofrece
#              renombrar los archivos si la similitud es alta. Los archivos cuyo nombre base
#              consista en una sola palabra serán saltados. Los ficheros renombrados se loggean
# Uso:
#     1. Crea un archivo plex.config.json con la configuración de tu servidor Plex. Ejemplo:
#        {
#            "PLEX_BASE_URL": "http://tu-servidor-plex:32400",
#            "PLEX_TOKEN": "tu-token-plex"
#        }
#     2. Ejecuta el script desde la terminal: python tu_script.py
#     3. Para habilitar el modo debug: python tu_script.py -d
#
import os
import requests
import xml.etree.ElementTree as ET
import json
import re
from colorama import Fore, Style, init
import argparse
from difflib import SequenceMatcher
import datetime

# Inicializar colorama
init(autoreset=True)

# Version del script
VERSION = "1.7.0"

# Nombre del archivo de configuración JSON
CONFIG_FILE = "plex.config.json"
LOG_FILE = "rename.log"

# Banner de inicio
print(f"""
 {Style.RESET_ALL}
 {Fore.LIGHTGREEN_EX}Plex-Renamer v{VERSION}{Style.RESET_ALL}
 {Style.RESET_ALL}
""")

def load_config(file_path):
    try:
        with open(file_path, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"{Fore.LIGHTRED_EX}Archivo de configuración {file_path} no encontrado.{Style.RESET_ALL}")
        return None
    except json.JSONDecodeError:
        print(f"{Fore.LIGHTRED_EX}Error al decodificar el archivo JSON {file_path}.{Style.RESET_ALL}")
        return None
    except Exception as e:
        print(f"{Fore.LIGHTRED_EX}Error al leer el archivo {file_path}: {e}{Style.RESET_ALL}")
        return None

def print_debug(message, debug=False, function_name=None):
    if debug:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if function_name:
            print(f"{Fore.LIGHTYELLOW_EX}[DEBUG] {timestamp} - {function_name} - {message}{Style.RESET_ALL}")
        else:
            print(f"{Fore.LIGHTYELLOW_EX}[DEBUG] {timestamp} - {message}{Style.RESET_ALL}")

def plex_request(url, headers, debug=False):
    print_debug(f"Petición HTTP: {url}", debug, "plex_request")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return ET.fromstring(response.content)
    except requests.exceptions.RequestException as e:
        print(f"{Fore.LIGHTRED_EX}Error en petición a Plex API: {e}{Style.RESET_ALL}")
        return None

def fetch_plex_sections(debug=False):
    url = f"{PLEX_BASE_URL}/library/sections"
    headers = {"X-Plex-Token": PLEX_TOKEN}
    return plex_request(url, headers, debug)

def fetch_plex_movies(section_id, debug=False):
    url = f"{PLEX_BASE_URL}/library/sections/{section_id}/all"
    headers = {"X-Plex-Token": PLEX_TOKEN}
    return plex_request(url, headers, debug)

def get_identifiers(metadata_xml):
    for guid in metadata_xml.findall(".//Guid"):
        guid_id = guid.get("id", "")
        if "imdb" in guid_id:
            yield "imdb", guid_id.split("//")[-1]
        elif "tmdb" in guid_id:
            yield "tmdb", guid_id.split("//")[-1]

def sanitize_filename(name):
    return re.sub(r'[:\\/*?"<>|]', '', name)

def extract_year_from_filename(filename):
    """
    Extrae el año (cuatro dígitos entre 1900 y 2200) del nombre del archivo.
    """
    match = re.search(r"(19\d{2}|2[0-1]\d{2}|2200)", filename)
    if match:
        return int(match.group(1))
    return None

def extract_basename(file_path):
    base_name = os.path.basename(file_path)
    base_name = os.path.splitext(base_name)[0]
    match = re.search(r'^(.*?)([\(\[])', base_name)
    if match:
        base_name = match.group(1).strip()
    return base_name

def calculate_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio() * 100

def rename_file(file_path, new_name, debug=False):
    new_path = os.path.join(os.path.dirname(file_path), new_name + os.path.splitext(file_path)[1])
    print_debug(f"Intentando renombrar: {file_path} -> {new_path}", debug, "rename_file")
    if os.path.exists(new_path):
        while True:
            overwrite = input(f"{Fore.LIGHTRED_EX}El archivo {new_path} ya existe. ¿Desea sobreescribirlo? (s/n): {Style.RESET_ALL}").strip().lower()
            if overwrite in ['s', 'n']:
                break
            print(f"{Fore.LIGHTYELLOW_EX}Entrada no válida. Por favor, responda con 's' o 'n'.{Style.RESET_ALL}")
        if overwrite == 'n':
            print(f"{Fore.LIGHTYELLOW_EX}El archivo no será renombrado.{Style.RESET_ALL}")
            return False
    os.replace(file_path, new_path)
    print_debug(f"Archivo renombrado: {file_path} -> {new_path}", debug, "rename_file")
    print(f"{Fore.LIGHTGREEN_EX}Archivo renombrado a: {new_path}{Style.RESET_ALL}")
    log_rename(file_path, new_path)
    return True

def log_rename(old_path, new_path):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{now}] Renombrado: {old_path} -> {new_path}\n"
    with open(LOG_FILE, "a") as log_file:
        log_file.write(log_entry)

def process_movie(video, headers, debug=False):
    part_element = video.find(".//Part")
    file_path = part_element.get("file", "N/A") if part_element is not None else "N/A"

    if "imdb-" in file_path or "tmdb-" in file_path:
        return file_path, "N/A", "N/A", "N/A", True, "N/A"

    rating_key = video.get("ratingKey")
    metadata_url = f"{PLEX_BASE_URL}/library/metadata/{rating_key}"
    print_debug(f"Petición HTTP: {metadata_url}", debug, "process_movie")
    metadata_xml = plex_request(metadata_url, headers, debug)
    if metadata_xml is None:
        return file_path, "ERROR", "ERROR", "ERROR", False, "ERROR"

    imdb_id = "N/A"
    for type, id in get_identifiers(metadata_xml):
        if type == "imdb":
            imdb_id = id
            break
    
    title = metadata_xml.find(".//Video").get('title', 'Desconocido')
    year = metadata_xml.find(".//Video").get('year', 'Desconocido')
    
    base_name = extract_basename(file_path)
    
    if len(base_name.split()) <=1:
        return file_path, imdb_id, title, year, True, "SKIP"
    
    similarity = calculate_similarity(base_name.lower(), title.lower())
    
    return file_path, imdb_id, title, year, False, similarity

def list_movie_files(debug=False):
    print(f"{Fore.LIGHTGREEN_EX}Iniciando proceso para listar archivos de películas, sus nombres, IDs de IMDB, y comparación de títulos...{Style.RESET_ALL}")
    sections = fetch_plex_sections(debug)
    if sections is None:
        return
    headers = {"X-Plex-Token": PLEX_TOKEN}

    for section in sections.findall(".//Directory"):
        if section.get("type") == "movie":
            section_id = section.get("key")
            movies = fetch_plex_movies(section_id, debug)
            if movies is None:
                return
            
            total_movies = len(list(movies.findall(".//Video")))

            print(f"{Fore.LIGHTBLUE_EX}Procesando sección: {section.get('title')} - {total_movies} películas encontradas{Style.RESET_ALL}")

            for i, video in enumerate(movies.findall(".//Video"), start=1):
                 try:
                    file_path, imdb_id, title, year, skip, similarity  = process_movie(video, headers, debug)
                    
                    if skip and similarity == "SKIP":
                         print(f"{Fore.LIGHTYELLOW_EX}{'-' * 40}{Style.RESET_ALL}")
                         print(f"{Fore.LIGHTYELLOW_EX}Saltando archivo: {file_path} (Nombre base es una sola palabra){Style.RESET_ALL}")
                         continue
                    
                    if skip:
                        continue

                    print(f"{Fore.LIGHTYELLOW_EX}{'-' * 40}{Style.RESET_ALL}")
                    print(f"{Fore.LIGHTCYAN_EX}Archivo: {file_path} | IMDB ID: {imdb_id} | Título: {title} ({year}){Style.RESET_ALL}")
                    print(f"{Fore.LIGHTGREEN_EX}Porcentaje de similitud con nombre del fichero: {similarity:.2f}%{Style.RESET_ALL}")

                    filename_year = extract_year_from_filename(os.path.basename(file_path))
                    metadata_year = int(year) if year != 'Desconocido' else None

                    year_match = False
                    if filename_year and metadata_year:
                        year_diff = abs(filename_year - metadata_year)
                        year_match = year_diff <= 2
                    
                    if similarity > 85:
                        new_name = sanitize_filename(f"{title} ({year}) {{imdb-{imdb_id}}}")
                        print(f"{Fore.LIGHTGREEN_EX}Propuesta de nuevo nombre: {new_name}{Style.RESET_ALL}")
                        if (
                            similarity == 100 and
                            len(title.split()) >= 2 and
                            year_match and
                            similarity >= 85
                        ):
                            print(f"{Fore.LIGHTRED_EX}Coincidencia del 100% (con año coincidente y título de 2+ palabras). Renombrando automáticamente.{Style.RESET_ALL}")
                            rename_file(file_path, new_name, debug)
                        else:

                           while True:
                               confirm = input(f"{Fore.LIGHTCYAN_EX}¿Desea renombrar este archivo? (s/n): {Style.RESET_ALL}").strip().lower()
                               if confirm in ['s', 'n']:
                                   break
                               print(f"{Fore.LIGHTYELLOW_EX}Entrada no válida. Por favor, responda con 's' o 'n'.{Style.RESET_ALL}")
                           
                           if confirm == 's':
                                rename_file(file_path, new_name, debug)
                           else:
                               print(f"{Fore.LIGHTYELLOW_EX}Archivo no renombrado.{Style.RESET_ALL}")


                 except Exception as e:
                    print(f"{Fore.LIGHTRED_EX}Error procesando película: {e}{Style.RESET_ALL}")

def verify_config(config):
    try:
        PLEX_BASE_URL = config["PLEX_BASE_URL"]
        PLEX_TOKEN = config["PLEX_TOKEN"]
        return PLEX_BASE_URL, PLEX_TOKEN
    except KeyError as e:
        print(f"{Fore.LIGHTRED_EX}Falta la variable '{e}' en el archivo de configuración. Saliendo del programa.{Style.RESET_ALL}")
        exit()

if __name__ == "__main__":
    # Argument Parser
    parser = argparse.ArgumentParser(description="Lista archivos de películas en Plex con sus nombres, IDs de IMDB, y comparación de títulos.")
    parser.add_argument("-d", "--debug", action="store_true", help="Habilita el modo debug para mostrar peticiones HTTP.")
    args = parser.parse_args()
    
    # Cargar la configuración después de parsear los argumentos
    CONFIG = load_config(CONFIG_FILE)
    
    # Verificar que la configuración se haya cargado correctamente
    if not CONFIG:
      print(f"{Fore.LIGHTRED_EX}No se pudo cargar la configuración. Saliendo del programa.{Style.RESET_ALL}")
      exit()
    
     # Obtener variables de configuración
    PLEX_BASE_URL, PLEX_TOKEN = verify_config(CONFIG)
    
    list_movie_files(args.debug)
