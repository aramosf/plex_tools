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
VERSION = "1.6.0" # Añadida extracción de géneros

# Nombre del archivo de configuración JSON esperado
CONFIG_FILE = "config.json"


# --- Funciones ---

def load_config(file_path):
    """
    Carga la configuración desde un archivo JSON.
    """
    print(f"{Fore.CYAN}Intentando cargar configuración desde: {file_path}{Style.RESET_ALL}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
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
    """
    if debug:
        function_name = inspect.stack()[1].function
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{Fore.LIGHTYELLOW_EX}[DEBUG] {timestamp} - {function_name} - {message}{Style.RESET_ALL}")

def plex_request(url, headers, debug=False, item_description="un elemento"):
    """
    Realiza una petición GET a la API de Plex y parsea la respuesta XML.
    """
    print_debug(f"Realizando petición HTTP GET a: {url}", debug)
    try:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        print_debug(f"Petición exitosa (Código {response.status_code})", debug)
        return ET.fromstring(response.content)
    except requests.exceptions.Timeout:
        print(f"{Fore.LIGHTRED_EX}Error: La petición a Plex API para {item_description} ({url}) superó el tiempo de espera.{Style.RESET_ALL}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"{Fore.LIGHTRED_EX}Error en la petición a Plex API para {item_description} ({url}): {e}{Style.RESET_ALL}")
        return None
    except ET.ParseError as e:
        print(f"{Fore.LIGHTRED_EX}Error al parsear la respuesta XML de Plex para {item_description} ({url}): {e}{Style.RESET_ALL}")
        print_debug(f"Contenido recibido (primeros 500 chars): {response.text[:500]}...", debug)
        return None

def fetch_plex_sections(plex_url, plex_token, debug=False):
    url = f"{plex_url}/library/sections"
    headers = {"X-Plex-Token": plex_token, "Accept": "application/xml"}
    print_debug("Obteniendo secciones de la biblioteca", debug)
    return plex_request(url, headers, debug, item_description="las secciones de la biblioteca")

def fetch_section_items(plex_url, plex_token, section_id, debug=False, section_type="items"):
    url = f"{plex_url}/library/sections/{section_id}/all"
    headers = {"X-Plex-Token": plex_token, "Accept": "application/xml"}
    print_debug(f"Obteniendo {section_type} de la sección ID: {section_id}", debug)
    return plex_request(url, headers, debug, item_description=f"elementos de la sección {section_id}")

def get_external_identifiers(metadata_xml):
    ids = {}
    if metadata_xml is None: return ids
    for guid in metadata_xml.findall(".//Guid"):
        guid_id = guid.get("id", "")
        if "imdb://" in guid_id:
            ids["imdb_id"] = guid_id.split("//")[-1]
        elif "tmdb://" in guid_id:
            ids["themoviedb_id"] = guid_id.split("//")[-1]
    return ids

def get_external_ratings(metadata_xml):
    ratings = {}
    if metadata_xml is None: return ratings
    for rating_elem in metadata_xml.findall(".//Rating"):
        image_url = rating_elem.get("image", "")
        value = rating_elem.get("value", "N/A")
        if "imdb://" in image_url:
            ratings["imdb_rating"] = value
        elif "themoviedb://" in image_url:
            ratings["themoviedb_rating"] = value
    if "imdb_rating" not in ratings:
        main_rating = metadata_xml.get('rating')
        if main_rating: ratings["imdb_rating"] = main_rating
    return ratings

def get_genres(metadata_xml):
    """
    Extrae los géneros y los une con un '#'.
    """
    if metadata_xml is None:
        return {"genres": "N/A"}
    
    genre_list = [
        genre.get("tag") for genre in metadata_xml.findall(".//Genre") if genre.get("tag")
    ]
    
    genres_str = "#".join(sorted(genre_list)) if genre_list else "N/A"
    return {"genres": genres_str}

def get_stream_info(media_element):
    """
    Extrae información detallada de los streams (video, audio, etc.) de un elemento Media.
    """
    stream_info = {
        'bitrate': 'N/A',
        'display_resolution': 'N/A',
        'video_dimensions': 'N/A',
        'languages': 'N/A'
    }
    if media_element is None:
        return stream_info

    stream_info['bitrate'] = media_element.get('bitrate', 'N/A')
    languages = set()
    video_stream_found = False

    for stream in media_element.findall(".//Stream"):
        stream_type = stream.get("streamType")
        if stream_type == "1" and not video_stream_found:
            stream_info['display_resolution'] = stream.get('displayTitle', 'N/A')
            width = stream.get('codedWidth', stream.get('width', 'N/A'))
            height = stream.get('codedHeight', stream.get('height', 'N/A'))
            if width != 'N/A' and height != 'N/A':
                stream_info['video_dimensions'] = f"{width}x{height}"
            video_stream_found = True
        elif stream_type in ["2", "3"]:
            lang = stream.get('language')
            if lang and lang.lower() not in ['und', 'zxx', 'qaa']:
                languages.add(lang.strip().capitalize())
            
    if languages:
        stream_info['languages'] = ', '.join(sorted(list(languages)))

    return stream_info

def get_file_info(part_element):
    file_path = part_element.get("file", "N/A") if part_element is not None else "N/A"
    file_size = "N/A"
    if file_path != "N/A":
        try:
            if os.path.exists(file_path): file_size = os.path.getsize(file_path)
            else: file_size = "Inaccesible"
        except OSError: file_size = "Error"
    return file_path, file_size

def get_movie_info(plex_url, plex_token, video_xml, debug=False):
    """
    Obtiene información detallada de una película.
    """
    headers = {"X-Plex-Token": plex_token, "Accept": "application/xml"}
    basic_title = video_xml.get('title', 'Título Desconocido')
    rating_key = video_xml.get("ratingKey")

    print_debug(f"Procesando película: {basic_title} (RatingKey: {rating_key})", debug)
    if not rating_key:
        print(f"{Fore.YELLOW}Advertencia: No se encontró 'ratingKey' para el item {basic_title}.{Style.RESET_ALL}")
        return None

    metadata_url = f"{plex_url}/library/metadata/{rating_key}"
    metadata_xml = plex_request(metadata_url, headers, debug, f"metadatos de la película {basic_title}")
    if metadata_xml is None: return None

    video_metadata_element = metadata_xml.find(".//Video")
    if video_metadata_element is None:
         print(f"{Fore.YELLOW}Advertencia: No se encontró el elemento <Video> en los metadatos detallados para {basic_title}.{Style.RESET_ALL}")
         return None

    title = video_metadata_element.get('title', basic_title)
    ids = get_external_identifiers(metadata_xml)
    ratings = get_external_ratings(metadata_xml)
    genres = get_genres(metadata_xml) # <-- NUEVO
    
    media_element = video_metadata_element.find(".//Media")
    stream_info = get_stream_info(media_element)
    
    part_element = video_metadata_element.find(".//Part")
    file_path, file_size = get_file_info(part_element)

    return {
        "title": title,
        **ids,
        **ratings,
        **genres, # <-- NUEVO
        **stream_info,
        "file_path": file_path,
        "file_directory": os.path.dirname(file_path) if file_path != "N/A" else "N/A",
        "file_size": file_size,
    }

def get_episode_info(plex_url, plex_token, episode_xml, show_info_prefetched, debug=False):
    """
    Obtiene información detallada de un episodio.
    """
    headers = {"X-Plex-Token": plex_token, "Accept": "application/xml"}
    episode_rating_key = episode_xml.get("ratingKey")
    episode_title_basic = episode_xml.get('title', 'Título Episodio Desconocido')
    season_number = episode_xml.get('parentIndex', 'N/A')
    episode_number = episode_xml.get('index', 'N/A')

    print_debug(f"Procesando S{season_number}E{episode_number} - {episode_title_basic}", debug)
    if not episode_rating_key:
        print(f"{Fore.YELLOW}Advertencia: No se encontró 'ratingKey' para {episode_title_basic}.{Style.RESET_ALL}")
        return None

    episode_metadata_url = f"{plex_url}/library/metadata/{episode_rating_key}"
    episode_metadata_xml = plex_request(episode_metadata_url, headers, debug, f"metadatos del episodio {episode_title_basic}")
    if episode_metadata_xml is None: return None

    episode_video_element = episode_metadata_xml.find(".//Video")
    if episode_video_element is None:
        print(f"{Fore.YELLOW}Advertencia: No se encontró el elemento <Video> en los metadatos de {episode_title_basic}.{Style.RESET_ALL}")
        return None

    episode_title = episode_video_element.get('title', episode_title_basic)
    episode_ids = get_external_identifiers(episode_metadata_xml)
    episode_ratings = get_external_ratings(episode_metadata_xml)
    
    media_element = episode_video_element.find(".//Media")
    stream_info = get_stream_info(media_element)
    
    part_element = episode_video_element.find(".//Part")
    file_path, file_size = get_file_info(part_element)

    return {
        **show_info_prefetched,
        "season_number": season_number,
        "episode_number": episode_number,
        "episode_title": episode_title,
        "episode_imdb_id": episode_ids.get("imdb_id", "N/A"),
        "episode_themoviedb_id": episode_ids.get("themoviedb_id", "N/A"),
        "episode_imdb_rating": episode_ratings.get("imdb_rating", "N/A"),
        "episode_themoviedb_rating": episode_ratings.get("themoviedb_rating", "N/A"),
        **stream_info,
        "file_path": file_path,
        "file_directory": os.path.dirname(file_path) if file_path != "N/A" else "N/A",
        "file_size": file_size,
    }

def get_show_details_prefetched(plex_url, plex_token, show_rating_key, show_title_basic, debug=False):
    """
    Obtiene metadatos detallados de un show para ser usados en sus episodios.
    """
    headers = {"X-Plex-Token": plex_token, "Accept": "application/xml"}
    metadata_url = f"{plex_url}/library/metadata/{show_rating_key}"
    metadata_xml = plex_request(metadata_url, headers, debug, f"metadatos del show '{show_title_basic}'")
    if metadata_xml is None: return None

    directory_element = metadata_xml.find(".//Directory")
    if directory_element is None: return None

    show_title = directory_element.get('title', show_title_basic)
    show_ids = get_external_identifiers(metadata_xml)
    show_ratings = get_external_ratings(metadata_xml)
    show_genres = get_genres(metadata_xml)["genres"] # <-- NUEVO

    return {
        "show_title": show_title,
        "show_imdb_id": show_ids.get("imdb_id", "N/A"),
        "show_themoviedb_id": show_ids.get("themoviedb_id", "N/A"),
        "show_imdb_rating": show_ratings.get("imdb_rating", "N/A"),
        "show_themoviedb_rating": show_ratings.get("themoviedb_rating", "N/A"),
        "show_genres": show_genres, # <-- NUEVO
    }

def export_to_csv(data, filename, fieldnames):
    """
    Exporta la lista de diccionarios de elementos a un archivo CSV.
    """
    if not data:
        print(f"{Fore.YELLOW}No se encontraron datos para exportar a '{filename}'.{Style.RESET_ALL}")
        return

    print(f"{Fore.CYAN}Iniciando exportación a CSV: {filename}{Style.RESET_ALL}")
    try:
        output_dir = os.path.dirname(filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print_debug(f"Directorio de salida '{output_dir}' creado.", True)

        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for item in data:
                filtered_item = {key: item.get(key, 'N/A') for key in fieldnames}
                writer.writerow(filtered_item)
        print(f"{Fore.LIGHTGREEN_EX}Éxito: Datos exportados a '{filename}'. Se procesaron {len(data)} elementos.{Style.RESET_ALL}")
    except IOError as e:
         print(f"{Fore.LIGHTRED_EX}Error de E/S al escribir el archivo CSV '{filename}': {e}{Style.RESET_ALL}")
    except Exception as e:
         print(f"{Fore.LIGHTRED_EX}Error inesperado durante la exportación a CSV: {e}{Style.RESET_ALL}")

def process_plex_libraries(plex_url, plex_token, library_types_to_process, output_directory, movie_fields, episode_fields, debug=False):
    """
    Función principal que orquesta la obtención de datos y su exportación.
    """
    print(f"{Fore.LIGHTGREEN_EX}--- PlexExportCSV v{VERSION} ---{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Iniciando proceso para listar bibliotecas y exportar a CSV...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Tipos de biblioteca a procesar: {', '.join(library_types_to_process)}{Style.RESET_ALL}")

    sections_xml = fetch_plex_sections(plex_url, plex_token, debug)
    if sections_xml is None: return

    all_movie_data, all_episode_data = [], []
    found_processed_sections = False

    for section in sections_xml.findall(".//Directory"):
        section_type = section.get("type")
        if section_type not in library_types_to_process: continue

        found_processed_sections = True
        section_id = section.get("key")
        section_title = section.get("title", f"ID {section_id}")
        print(f"\n{Fore.BLUE}Procesando sección '{section_title}' (Tipo: {section_type}){Style.RESET_ALL}")

        items_xml = fetch_section_items(plex_url, plex_token, section_id, debug, section_type)
        if items_xml is None: continue

        if section_type == "movie":
            elements = items_xml.findall(".//Video")
            print(f"{Fore.CYAN}Se encontraron {len(elements)} películas. Procesando metadatos...{Style.RESET_ALL}")
            for i, video_xml in enumerate(elements, 1):
                print(f"{Fore.MAGENTA}  Procesando película {i}/{len(elements)}...", end='\r')
                movie_info = get_movie_info(plex_url, plex_token, video_xml, debug)
                if movie_info: all_movie_data.append(movie_info)
            print(f"\n{Fore.GREEN}Sección '{section_title}' procesada.{Style.RESET_ALL}")

        elif section_type == "show":
            elements = items_xml.findall(".//Directory[@type='show']")
            print(f"{Fore.CYAN}Se encontraron {len(elements)} shows. Procesando metadatos...{Style.RESET_ALL}")
            for i, show_xml in enumerate(elements, 1):
                show_title = show_xml.get('title', 'Show Desconocido')
                show_rating_key = show_xml.get('ratingKey')
                print(f"{Fore.MAGENTA}  Procesando show {i}/{len(elements)}: {show_title}...", end='\r')
                if not show_rating_key: continue

                show_info_prefetched = get_show_details_prefetched(plex_url, plex_token, show_rating_key, show_title, debug)
                if not show_info_prefetched: continue

                seasons_url = f"{plex_url}/library/metadata/{show_rating_key}/children"
                seasons_xml = plex_request(seasons_url, headers={"X-Plex-Token": plex_token, "Accept": "application/xml"}, debug=debug, item_description=f"temporadas de '{show_title}'")
                if seasons_xml is None: continue

                for season_xml in seasons_xml.findall(".//Directory[@type='season']"):
                    season_rating_key = season_xml.get('ratingKey')
                    episodes_url = f"{plex_url}/library/metadata/{season_rating_key}/children"
                    episodes_xml = plex_request(episodes_url, headers={"X-Plex-Token": plex_token, "Accept": "application/xml"}, debug=debug, item_description=f"episodios de la temporada")
                    if episodes_xml is None: continue

                    for episode_xml in episodes_xml.findall(".//Video[@type='episode']"):
                        episode_info = get_episode_info(plex_url, plex_token, episode_xml, show_info_prefetched, debug)
                        if episode_info: all_episode_data.append(episode_info)
            print(f"\n{Fore.GREEN}Sección '{section_title}' procesada.{Style.RESET_ALL}")

    if not found_processed_sections:
         print(f"{Fore.YELLOW}No se encontraron secciones de los tipos especificados en tu servidor Plex.{Style.RESET_ALL}")

    if "movie" in library_types_to_process:
        export_to_csv(all_movie_data, os.path.join(output_directory, "plex_movies_export.csv"), movie_fields)
    if "show" in library_types_to_process:
        export_to_csv(all_episode_data, os.path.join(output_directory, "plex_tv_episodes_export.csv"), episode_fields)

def verify_config(config):
    """
    Verifica que la configuración sea válida. Es obligatorio definir los campos del CSV.
    """
    missing_keys = []
    plex_base_url = config.get("PLEX_BASE_URL")
    plex_token = config.get("PLEX_TOKEN")
    movie_fields = config.get("CSV_MOVIE_FIELDS")
    episode_fields = config.get("CSV_EPISODE_FIELDS")

    if not plex_base_url: missing_keys.append("PLEX_BASE_URL")
    if not plex_token: missing_keys.append("PLEX_TOKEN")
    if not movie_fields: missing_keys.append("CSV_MOVIE_FIELDS")
    if not episode_fields: missing_keys.append("CSV_EPISODE_FIELDS")

    if missing_keys:
        print(f"{Fore.LIGHTRED_EX}Error: Faltan las siguientes claves OBLIGATORIAS en '{CONFIG_FILE}': {', '.join(missing_keys)}{Style.RESET_ALL}")
        exit(1)

    if plex_base_url.endswith('/'):
        plex_base_url = plex_base_url[:-1]
        print_debug(f"Se eliminó la barra final de PLEX_BASE_URL. Nuevo valor: {plex_base_url}", True)

    return plex_base_url, plex_token, movie_fields, episode_fields

# --- Punto de Entrada Principal ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"PlexExportCSV: Extrae información de películas y/o series de un servidor Plex y la guarda en archivos CSV. Versión {VERSION}",
        epilog=f"Ejemplos:\n"
               f"  python {os.path.basename(__file__)} -t movie show  (Exporta ambos tipos)\n"
               f"  python {os.path.basename(__file__)} -t show -o /tmp/exports  (Exporta series a un directorio específico)\n\n"
               f"IMPORTANTE: Debes definir 'CSV_MOVIE_FIELDS' y 'CSV_EPISODE_FIELDS' en tu archivo '{CONFIG_FILE}'.",
        formatter_class=argparse.RawTextHelpFormatter # Para mostrar el epílogo con saltos de línea
    )
    parser.add_argument("-t", "--type", nargs='+', choices=['movie', 'show'], required=True, help="Especifica los tipos de biblioteca a exportar. Opciones: 'movie', 'show'.")
    parser.add_argument("-c", "--config", default=CONFIG_FILE, help=f"Ruta al archivo de configuración JSON (por defecto: {CONFIG_FILE}).")
    parser.add_argument("-o", "--output-dir", default=".", help="Directorio donde se guardarán los archivos CSV (por defecto: el directorio actual).")
    parser.add_argument("-d", "--debug", action="store_true", help="Habilita el modo de depuración para mostrar mensajes detallados.")

    args = parser.parse_args()
    CONFIG = load_config(args.config)
    if not CONFIG: exit(1)

    try:
        PLEX_BASE_URL, PLEX_TOKEN, MOVIE_FIELDS, EPISODE_FIELDS = verify_config(CONFIG)
        process_plex_libraries(PLEX_BASE_URL, PLEX_TOKEN, args.type, args.output_dir, MOVIE_FIELDS, EPISODE_FIELDS, args.debug)
    except SystemExit as e:
        if e.code != 0: print(f"{Fore.LIGHTRED_EX}El programa terminó de forma inesperada.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.LIGHTRED_EX}Ha ocurrido un error inesperado durante la ejecución: {e}{Style.RESET_ALL}")

    print(f"\n{Fore.LIGHTGREEN_EX}Proceso completado.{Style.RESET_ALL}")

