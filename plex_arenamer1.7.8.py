# Script: autorenamer
# Versión: 1.7.8
# Descripción: ... (igual que antes) ...
#              Modificaciones:
#              - extract_basename ahora elimina el (año) del nombre base final
#                para una comparación de similitud de título más pura. El año
#                se sigue extrayendo por separado para la comparación de años.
# ... (resto de la descripción y uso)
#
import os
import requests
import xml.etree.ElementTree as ET
import json
import re
from colorama import Fore, Style, init
import argparse
import datetime

# Inicializar colorama
init(autoreset=True)

# Version del script
VERSION = "1.7.8"

# Nombre del archivo de configuración JSON
CONFIG_FILE = "config.json"
LOG_FILE = "rename.log"

# Variables de configuración globales (se llenarán desde verify_and_load_config)
PLEX_BASE_URL = ""
PLEX_TOKEN = ""
WORDS_TO_REMOVE = []
SIMILARITY_AUTO = 100
SIMILARITY_ASK = 85
YEAR_DIFF_AUTO = 1

# Banner de inicio
print(f"""
 {Style.RESET_ALL}
 {Fore.LIGHTGREEN_EX}autorenamer v{VERSION}{Style.RESET_ALL}
 {Style.RESET_ALL}
""")

# --- load_config_file, verify_and_load_config, print_debug, plex_request ---
# --- fetch_plex_sections, fetch_plex_movies, get_identifiers, sanitize_filename ---
# --- extract_year_from_filename (importante, esta no cambia), calculate_similarity ---
# --- (Estas funciones permanecen igual que en v1.7.7) ---
def load_config_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"{Fore.LIGHTRED_EX}Archivo de configuración {file_path} no encontrado.{Style.RESET_ALL}")
        return None
    except json.JSONDecodeError:
        print(f"{Fore.LIGHTRED_EX}Error al decodificar el archivo JSON {file_path}. Asegúrate de que es un JSON válido.{Style.RESET_ALL}")
        return None
    except Exception as e:
        print(f"{Fore.LIGHTRED_EX}Error al leer el archivo {file_path}: {e}{Style.RESET_ALL}")
        return None

def verify_and_load_config(config_data, debug_cli_flag): # debug_cli_flag para el mensaje inicial
    global PLEX_BASE_URL, PLEX_TOKEN, WORDS_TO_REMOVE, SIMILARITY_AUTO, SIMILARITY_ASK, YEAR_DIFF_AUTO
    try:
        PLEX_BASE_URL = config_data["PLEX_BASE_URL"]
        PLEX_TOKEN = config_data["PLEX_TOKEN"]
        default_words_to_remove = [
            "720p", "1080p", "2160p", "4k", "480p", "dvd", "xvid", "mp3", "ac3", "6ch", "5.1",
            "bluray", "web-dl", "webrip", "hdtv", "hdrip", "x264", "h264", "x265", "hevc",
            "extended", "uncut", "remastered", "director's cut", "final cut", "multi", "dual"
        ]
        WORDS_TO_REMOVE = config_data.get("WORDS_TO_REMOVE_FROM_FILENAME", default_words_to_remove)
        SIMILARITY_AUTO = int(config_data.get("SIMILARITY_THRESHOLD_AUTO", 100))
        SIMILARITY_ASK = int(config_data.get("SIMILARITY_THRESHOLD_ASK", 85))
        YEAR_DIFF_AUTO = int(config_data.get("YEAR_MATCH_DIFFERENCE_AUTO", 1))

        if not (0 <= SIMILARITY_AUTO <= 100 and 0 <= SIMILARITY_ASK <= 100):
            print(f"{Fore.LIGHTRED_EX}Error: Los umbrales de similitud (SIMILARITY_THRESHOLD_AUTO y SIMILARITY_THRESHOLD_ASK) deben estar entre 0 y 100.{Style.RESET_ALL}")
            return False
        if SIMILARITY_ASK > SIMILARITY_AUTO:
            print(f"{Fore.LIGHTYELLOW_EX}Advertencia: SIMILARITY_THRESHOLD_ASK ({SIMILARITY_ASK}%) es mayor que SIMILARITY_THRESHOLD_AUTO ({SIMILARITY_AUTO}%).{Style.RESET_ALL}")
        if not isinstance(WORDS_TO_REMOVE, list):
            print(f"{Fore.LIGHTRED_EX}Error: WORDS_TO_REMOVE_FROM_FILENAME en config.json debe ser una lista de strings.{Style.RESET_ALL}")
            return False
        if debug_cli_flag:
            print_debug(f"Configuración cargada (relevante para autorenamer):", debug_cli_flag, "verify_and_load_config")
            print_debug(f"  PLEX_BASE_URL: {PLEX_BASE_URL}", debug_cli_flag)
            print_debug(f"  WORDS_TO_REMOVE_FROM_FILENAME: {len(WORDS_TO_REMOVE)} palabras/frases", debug_cli_flag)
            print_debug(f"  SIMILARITY_THRESHOLD_AUTO: {SIMILARITY_AUTO}%", debug_cli_flag)
            print_debug(f"  SIMILARITY_THRESHOLD_ASK: {SIMILARITY_ASK}%", debug_cli_flag)
            print_debug(f"  YEAR_MATCH_DIFFERENCE_AUTO: {YEAR_DIFF_AUTO} año(s)", debug_cli_flag)
        return True
    except KeyError as e:
        print(f"{Fore.LIGHTRED_EX}Falta la variable requerida '{e}' en el archivo de configuración ({CONFIG_FILE}). Saliendo del programa.{Style.RESET_ALL}")
        return False
    except ValueError:
        print(f"{Fore.LIGHTRED_EX}Error: Los valores para SIMILARITY_THRESHOLD_AUTO, SIMILARITY_THRESHOLD_ASK, o YEAR_MATCH_DIFFERENCE_AUTO en config.json deben ser números enteros.{Style.RESET_ALL}")
        return False

def print_debug(message, debug_mode=False, function_name=None):
    if debug_mode:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if function_name: print(f"{Fore.LIGHTYELLOW_EX}[DEBUG] {timestamp} - {function_name} - {message}{Style.RESET_ALL}")
        else: print(f"{Fore.LIGHTYELLOW_EX}[DEBUG] {timestamp} - {message}{Style.RESET_ALL}")

def plex_request(url, headers, debug_mode=False):
    print_debug(f"Petición HTTP: {url}", debug_mode, "plex_request")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response.encoding = response.apparent_encoding if response.apparent_encoding else 'utf-8'
        return ET.fromstring(response.content)
    except requests.exceptions.RequestException as e:
        print(f"{Fore.LIGHTRED_EX}Error en petición a Plex API: {e}{Style.RESET_ALL}")
        return None
    except ET.ParseError as e:
        print(f"{Fore.LIGHTRED_EX}Error al parsear XML de Plex API: {e}{Style.RESET_ALL}")
        print_debug(f"Contenido recibido (primeros 500 chars): {response.text[:500]}", debug_mode, "plex_request")
        return None

def fetch_plex_sections(debug_mode=False):
    url = f"{PLEX_BASE_URL}/library/sections"; headers = {"X-Plex-Token": PLEX_TOKEN}
    return plex_request(url, headers, debug_mode)

def fetch_plex_movies(section_id, debug_mode=False):
    url = f"{PLEX_BASE_URL}/library/sections/{section_id}/all"; headers = {"X-Plex-Token": PLEX_TOKEN}
    return plex_request(url, headers, debug_mode)

def get_identifiers(metadata_xml):
    ids_found = {"imdb": None, "tmdb": None}
    for guid in metadata_xml.findall(".//Guid"):
        guid_id = guid.get("id", "")
        if "imdb" in guid_id:
            match_imdb = re.search(r'(tt\d+)', guid_id);
            if match_imdb: ids_found["imdb"] = match_imdb.group(1)
        elif "tmdb" in guid_id:
            match_tmdb = re.search(r'(\d+)', guid_id);
            if match_tmdb: ids_found["tmdb"] = match_tmdb.group(1)
    return ids_found["imdb"], ids_found["tmdb"]

def sanitize_filename(name):
    name = re.sub(r'[:\\/*?"<>|]', '', name); name = re.sub(r'\s+', ' ', name).strip()
    return name

def extract_year_from_filename(filename_str): # Renombrado para claridad filename -> filename_str
    # Esta función se usa para obtener el año del NOMBRE DE ARCHIVO ORIGINAL para year_match
    # No debe confundirse con la limpieza de extract_basename
    match = re.search(r"\b(19\d{2}|20\d{2}|21\d{2}|2200)\b", filename_str)
    if match: return int(match.group(1))
    return None

def extract_basename(file_path):
    base_name_ext = os.path.basename(file_path)
    name = os.path.splitext(base_name_ext)[0]

    # 1. Eliminar todo entre corchetes []
    name = re.sub(r'\[.*?\]', '', name)

    # 2. Eliminar palabras específicas de la configuración (WORDS_TO_REMOVE)
    if WORDS_TO_REMOVE:
        for word in WORDS_TO_REMOVE:
            name = re.sub(r'\b' + re.escape(word) + r'\b', '', name, flags=re.IGNORECASE)

    # 3. Manejar paréntesis: temporalmente reemplazar (año) con placeholder, eliminar otros paréntesis.
    years_in_parens_placeholders = {} # Guardará placeholder -> (año original)
    placeholder_base = "___YEAR_PLACEHOLDER___"
    
    def replace_year_in_paren(match_obj):
        nonlocal years_in_parens_placeholders # Python 3
        content_inside_paren = match_obj.group(1)
        # Verificar si el contenido ES SOLO un año
        year_match_inside_paren = re.fullmatch(r'(19\d{2}|20\d{2}|21\d{2}|2200)', content_inside_paren)
        if year_match_inside_paren:
            year_str = year_match_inside_paren.group(1)
            placeholder = f"{placeholder_base}{len(years_in_parens_placeholders)}"
            years_in_parens_placeholders[placeholder] = f"({year_str})" # Guardar el (año) original
            return placeholder # Reemplazar con placeholder
        return match_obj.group(0) # Devolver el paréntesis original y su contenido si no es solo un año

    name = re.sub(r'\((.*?)\)', replace_year_in_paren, name)
    # Ahora, eliminar cualquier paréntesis que no haya sido convertido a placeholder
    name = re.sub(r'\(.*?\)', '', name)

    # 4. Eliminar años de 4 dígitos que NO están (ni estuvieron) entre paréntesis.
    #    (Esta lógica es de v1.7.7)
    name = re.sub(r'(?<!\()\b(19\d{2}|20\d{2}|21\d{2}|2200)\b(?!\))', '', name).strip()
    
    # 5. Restaurar los (años) de los placeholders para una limpieza intermedia.
    #    En este punto, name podría ser "Título ___YEAR_PLACEHOLDER___0"
    for placeholder, original_year_in_paren in years_in_parens_placeholders.items():
        name = name.replace(placeholder, original_year_in_paren)
    #    Ahora name podría ser "Título (1999)"

    # 6. MODIFICACIÓN v1.7.8: Eliminar los patrones (año) del resultado final.
    #    Esto se hace después de que los (años) hayan sido restaurados,
    #    para asegurar que eliminamos específicamente esos.
    name = re.sub(r'\s*\((19\d{2}|20\d{2}|21\d{2}|2200)\)\s*', ' ', name).strip()
    #   \s* -> cero o más espacios
    #   \(   -> paréntesis abierto literal
    #   (AÑO) -> captura el año
    #   \)   -> paréntesis cerrado literal
    #   \s* -> cero o más espacios
    #   Reemplaza con un solo espacio para evitar unir palabras, luego .strip() lo maneja.

    # 7. Limpieza final: reemplazar puntos con espacios, normalizar espacios.
    name = name.replace('.', ' ').strip()
    name = re.sub(r'\s+', ' ', name).strip()

    return name if name else os.path.splitext(base_name_ext)[0]


def calculate_similarity(a, b):
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() * 100

# --- rename_file, log_rename, process_movie, list_movie_files ---
# --- (Estas funciones permanecen igual que en v1.7.7, ya que los cambios ---
# --- principales están en extract_basename y la lógica de comparación usa ---
# --- el resultado de esa función y los umbrales de configuración)      ---

def rename_file(file_path, new_name, debug_mode=False):
    # (Igual que en v1.7.7)
    new_path = os.path.join(os.path.dirname(file_path), new_name + os.path.splitext(file_path)[1])
    print_debug(f"Intentando renombrar: {file_path} -> {new_path}", debug_mode, "rename_file")
    if file_path == new_path:
        print(f"{Fore.LIGHTYELLOW_EX}El archivo ya tiene el nombre deseado. No se renombra.{Style.RESET_ALL}")
        return False
    if os.path.exists(new_path):
        if file_path.lower() == new_path.lower() and file_path != new_path:
            try:
                temp_name = new_path + ".renaming_temp"
                if os.path.exists(temp_name): os.remove(temp_name)
                os.rename(file_path, temp_name)
                os.rename(temp_name, new_path)
                print_debug(f"Archivo renombrado (solo mayúsculas/minúsculas): {file_path} -> {new_path}", debug_mode, "rename_file")
                print(f"{Fore.LIGHTGREEN_EX}Archivo renombrado a: {new_path}{Style.RESET_ALL}")
                log_rename(file_path, new_path)
                return True
            except Exception as e:
                print(f"{Fore.LIGHTRED_EX}Error al renombrar (solo mayúsculas/minúsculas): {e}{Style.RESET_ALL}")
                if os.path.exists(temp_name) and not os.path.exists(file_path): os.rename(temp_name, file_path)
                return False
        while True:
            overwrite = input(f"{Fore.LIGHTRED_EX}El archivo {new_path} ya existe. ¿Desea sobreescribirlo? (s/n): {Style.RESET_ALL}").strip().lower()
            if overwrite in ['s', 'n']: break
            print(f"{Fore.LIGHTYELLOW_EX}Entrada no válida. Por favor, responda con 's' o 'n'.{Style.RESET_ALL}")
        if overwrite == 'n':
            print(f"{Fore.LIGHTYELLOW_EX}El archivo no será renombrado.{Style.RESET_ALL}")
            return False
    try:
        os.replace(file_path, new_path)
        print_debug(f"Archivo renombrado: {file_path} -> {new_path}", debug_mode, "rename_file")
        print(f"{Fore.LIGHTGREEN_EX}Archivo renombrado a: {new_path}{Style.RESET_ALL}")
        log_rename(file_path, new_path)
        return True
    except Exception as e:
        print(f"{Fore.LIGHTRED_EX}Error al renombrar el archivo: {e}{Style.RESET_ALL}")
        return False

def log_rename(old_path, new_path):
    # (Igual que en v1.7.7)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{now}] Renombrado: {old_path} -> {new_path}\n"
    with open(LOG_FILE, "a", encoding='utf-8') as log_file:
        log_file.write(log_entry)

def process_movie(video, headers, debug_mode=False):
    # (Igual que en v1.7.7)
    part_element = video.find(".//Part")
    file_path = part_element.get("file", "N/A") if part_element is not None else "N/A"
    original_filename_base = os.path.basename(file_path)
    tmdb_id_explicit_match = re.search(r'(?:tmdbid\s*=\s*|tmdb-)(\d+)', original_filename_base, re.IGNORECASE)
    tmdb_presence_match = None
    if not tmdb_id_explicit_match:
        tmdb_presence_match = re.search(r'tmdbid|tmdb-', original_filename_base, re.IGNORECASE)
    proceed_with_tmdb_logic = False
    tmdb_id_extracted_from_filename = None
    if tmdb_id_explicit_match:
        tmdb_id_extracted_from_filename = tmdb_id_explicit_match.group(1)
        proceed_with_tmdb_logic = True
        print_debug(f"TMDB ID explícito ({tmdb_id_extracted_from_filename}) encontrado en nombre: {original_filename_base}. Renombrado directo.", debug_mode, "process_movie")
    elif tmdb_presence_match:
        proceed_with_tmdb_logic = True
        print_debug(f"Presencia de 'tmdbid' o 'tmdb-' detectada (sin ID numérico explícito en nombre): {original_filename_base}. Se usará Plex meta para ID. Renombrado directo.", debug_mode, "process_movie")
    if proceed_with_tmdb_logic:
        rating_key = video.get("ratingKey")
        metadata_url = f"{PLEX_BASE_URL}/library/metadata/{rating_key}"
        metadata_xml = plex_request(metadata_url, headers, debug_mode)
        if metadata_xml is None:
            return file_path, None, None, None, None, extract_basename(file_path), True, "METADATA_ERROR_TMDB_DIRECT"
        plex_imdb_id, plex_tmdb_id_from_meta = get_identifiers(metadata_xml)
        title = metadata_xml.find(".//Video").get('title', 'Desconocido')
        year = metadata_xml.find(".//Video").get('year', 'Desconocido')
        final_tmdb_id_for_object = tmdb_id_extracted_from_filename if tmdb_id_extracted_from_filename else plex_tmdb_id_from_meta
        has_valid_plex_imdb = plex_imdb_id and plex_imdb_id.lower() not in ["na", "n/a"]
        has_valid_final_tmdb = final_tmdb_id_for_object and final_tmdb_id_for_object.lower() not in ["na", "n/a"]
        if not has_valid_plex_imdb and not has_valid_final_tmdb:
            print_debug(f"TMDB logic: No se pudo asegurar un ID válido para {original_filename_base}. IMDb Plex: {plex_imdb_id}, TMDB Final: {final_tmdb_id_for_object}", debug_mode, "process_movie")
            return file_path, plex_imdb_id, final_tmdb_id_for_object, title, year, extract_basename(file_path), True, "NO_ID_FOR_TMDB_DIRECT_RENAME"
        return file_path, plex_imdb_id, final_tmdb_id_for_object, title, year, extract_basename(file_path), False, "TMDB_DIRECT_RENAME"
    base_name_from_file = extract_basename(file_path) # Esta es la línea clave que se beneficia del cambio
    filename_lower = original_filename_base.lower()
    if re.search(r"\{imdb-tt\d+\}", filename_lower) or re.search(r"\{tmdb-\d+\}", filename_lower):
        print_debug(f"Archivo ya parece tener un ID en formato estándar {{id-xxxx}}: {file_path}", debug_mode, "process_movie")
        return file_path, None, None, None, None, base_name_from_file, True, "ALREADY_FORMATTED_ID_TAG"
    rating_key = video.get("ratingKey")
    metadata_url = f"{PLEX_BASE_URL}/library/metadata/{rating_key}"
    print_debug(f"Petición HTTP para metadatos (flujo normal): {metadata_url}", debug_mode, "process_movie")
    metadata_xml = plex_request(metadata_url, headers, debug_mode)
    if metadata_xml is None:
        return file_path, None, None, None, None, base_name_from_file, True, "METADATA_ERROR"
    imdb_id, tmdb_id = get_identifiers(metadata_xml)
    has_valid_imdb = imdb_id and imdb_id.lower() not in ["na", "n/a"]
    has_valid_tmdb = tmdb_id and tmdb_id.lower() not in ["na", "n/a"]
    if not has_valid_imdb and not has_valid_tmdb:
        print_debug(f"No se encontró ID de IMDb ni TMDB válido en los metadatos para: {file_path}. IMDb: {imdb_id}, TMDB: {tmdb_id}", debug_mode, "process_movie")
        return file_path, imdb_id, tmdb_id, None, None, base_name_from_file, True, "NO_ID_FOUND"
    title = metadata_xml.find(".//Video").get('title', 'Desconocido')
    year = metadata_xml.find(".//Video").get('year', 'Desconocido')
    similarity = calculate_similarity(base_name_from_file.lower(), title.lower()) # Ahora la similitud debería ser mayor
    return file_path, imdb_id, tmdb_id, title, year, base_name_from_file, False, similarity

def list_movie_files(debug_mode=False):
    # (Igual que en v1.7.7)
    print(f"{Fore.LIGHTGREEN_EX}Iniciando proceso para listar archivos de películas, sus nombres, IDs y comparación de títulos...{Style.RESET_ALL}")
    sections = fetch_plex_sections(debug_mode)
    if sections is None: return
    headers = {"X-Plex-Token": PLEX_TOKEN}
    for section in sections.findall(".//Directory"):
        if section.get("type") == "movie":
            section_id = section.get("key")
            section_title = section.get('title', 'Desconocida')
            print_debug(f"Accediendo a la sección de películas '{section_title}' (ID: {section_id})", debug_mode, "list_movie_files")
            movies = fetch_plex_movies(section_id, debug_mode)
            if movies is None:
                print(f"{Fore.LIGHTRED_EX}No se pudieron obtener películas para la sección {section_title}.{Style.RESET_ALL}")
                continue
            movie_videos = list(movies.findall(".//Video"))
            total_movies = len(movie_videos)
            print(f"{Fore.LIGHTBLUE_EX}Procesando sección: {section_title} - {total_movies} películas encontradas{Style.RESET_ALL}")
            for i, video_item in enumerate(movie_videos, start=1):
                try:
                    file_path, imdb_id, tmdb_id, title, year, base_name_from_file, skip_processing, status_or_similarity = process_movie(video_item, headers, debug_mode)
                    print(f"{Fore.LIGHTYELLOW_EX}{'-' * 40}{Style.RESET_ALL}")
                    if skip_processing:
                        if status_or_similarity == "ALREADY_FORMATTED_ID_TAG":
                            print(f"{Fore.LIGHTYELLOW_EX}Saltando (ya etiquetado con ID en formato estándar): {os.path.basename(file_path)}{Style.RESET_ALL}")
                        elif status_or_similarity in ["METADATA_ERROR", "METADATA_ERROR_TMDB_DIRECT"]:
                             print(f"{Fore.LIGHTRED_EX}Error obteniendo metadatos para: {os.path.basename(file_path)}{Style.RESET_ALL}")
                        elif status_or_similarity == "NO_ID_FOUND":
                            print(f"{Fore.LIGHTYELLOW_EX}Saltando (sin ID de IMDb/TMDB en metadatos Plex): {os.path.basename(file_path)}{Style.RESET_ALL}")
                        elif status_or_similarity == "NO_ID_FOR_TMDB_DIRECT_RENAME":
                            print(f"{Fore.LIGHTYELLOW_EX}Saltando (TMDB detectado en nombre pero sin ID final usable de Plex): {os.path.basename(file_path)}{Style.RESET_ALL}")
                        continue
                    is_tmdb_direct_rename = (status_or_similarity == "TMDB_DIRECT_RENAME")
                    similarity_value = 0 if is_tmdb_direct_rename else float(status_or_similarity)
                    print(f"{Fore.LIGHTCYAN_EX}[{i}/{total_movies}] Archivo: {os.path.basename(file_path)}{Style.RESET_ALL}")
                    if not is_tmdb_direct_rename:
                        print(f"    {Fore.LIGHTCYAN_EX}Ruta: {file_path}{Style.RESET_ALL}")
                        print(f"    {Fore.LIGHTMAGENTA_EX}Base actual limpia: '{base_name_from_file}'{Style.RESET_ALL}") # Debería reflejar el cambio
                    id_display = f"IMDb: {imdb_id}" if imdb_id and imdb_id.lower() not in ["na", "n/a"] else "IMDb: N/A"
                    id_display += f" / TMDB: {tmdb_id}" if tmdb_id and tmdb_id.lower() not in ["na", "n/a"] else " / TMDB: N/A"
                    print(f"    {Fore.LIGHTCYAN_EX}Plex Meta: '{title}' ({year}) | {id_display}{Style.RESET_ALL}")
                    if not is_tmdb_direct_rename:
                        print(f"{Fore.LIGHTGREEN_EX}    Similitud con nombre base: {similarity_value:.2f}%{Style.RESET_ALL}") # Esperamos que sea más alta ahora
                    # La extracción del año del nombre del archivo para year_match sigue usando el nombre original
                    filename_year_val = extract_year_from_filename(os.path.basename(file_path))
                    metadata_year_val = int(year) if year and year.isdigit() else None
                    year_match = False
                    if filename_year_val and metadata_year_val:
                        year_diff = abs(filename_year_val - metadata_year_val)
                        year_match = year_diff <= YEAR_DIFF_AUTO
                        print_debug(f"Año archivo: {filename_year_val}, Año meta: {metadata_year_val}, Coinciden (diff<={YEAR_DIFF_AUTO}): {year_match} (dif: {year_diff})", debug_mode, "list_movie_files")
                    id_for_filename_tag = ""
                    if imdb_id and imdb_id.lower() not in ["na", "n/a"]: id_for_filename_tag = f"{{imdb-{imdb_id}}}"
                    elif tmdb_id and tmdb_id.lower() not in ["na", "n/a"]: id_for_filename_tag = f"{{tmdb-{tmdb_id}}}"
                    if not id_for_filename_tag:
                        print(f"{Fore.LIGHTYELLOW_EX}    No se pudo determinar un ID válido para el tag del nombre. No se propone renombrar.{Style.RESET_ALL}")
                        continue
                    new_name_base = f"{title} ({year}) {id_for_filename_tag}".strip()
                    new_name_sanitized = sanitize_filename(new_name_base)
                    print(f"{Fore.LIGHTGREEN_EX}    Propuesta de nuevo nombre: {new_name_sanitized}{Style.RESET_ALL}")
                    auto_rename_triggered = False
                    if is_tmdb_direct_rename:
                        auto_rename_triggered = True
                        print(f"{Fore.LIGHTRED_EX}    Nombre de archivo original contiene TMDB ID/tag. Renombrando automáticamente.{Style.RESET_ALL}")
                    elif similarity_value >= SIMILARITY_AUTO and year_match: # Comparación de título puro ahora
                        if len(title.split()) >= 2: auto_rename_triggered = True
                        elif len(title.split()) == 1 and len(base_name_from_file.split()) == 1: # base_name_from_file ahora es título puro
                             auto_rename_triggered = True
                    if auto_rename_triggered:
                        if not is_tmdb_direct_rename:
                             print(f"{Fore.LIGHTRED_EX}    Similitud >= {SIMILARITY_AUTO}% (con año coincidente). Renombrando automáticamente.{Style.RESET_ALL}")
                        rename_file(file_path, new_name_sanitized, debug_mode)
                    elif similarity_value > SIMILARITY_ASK and not is_tmdb_direct_rename :
                       while True:
                           confirm = input(f"{Fore.LIGHTCYAN_EX}    ¿Desea renombrar este archivo? (s/n): {Style.RESET_ALL}").strip().lower()
                           if confirm in ['s', 'n']: break
                           print(f"{Fore.LIGHTYELLOW_EX}    Entrada no válida. Por favor, responda con 's' o 'n'.{Style.RESET_ALL}")
                       if confirm == 's': rename_file(file_path, new_name_sanitized, debug_mode)
                       else: print(f"{Fore.LIGHTYELLOW_EX}    Archivo no renombrado por el usuario.{Style.RESET_ALL}")
                    elif not is_tmdb_direct_rename:
                        print(f"{Fore.LIGHTYELLOW_EX}    Similitud ({similarity_value:.2f}%) no alcanza el umbral de {SIMILARITY_ASK}%. No se propone renombrar.{Style.RESET_ALL}")
                except Exception as e:
                    file_id_for_error = os.path.basename(file_path) if 'file_path' in locals() and file_path else f"elemento {i}"
                    print(f"{Fore.LIGHTRED_EX}Error inesperado procesando {file_id_for_error}: {e}{Style.RESET_ALL}")
                    import traceback
                    print_debug(f"Traceback: {traceback.format_exc()}", debug_mode, "list_movie_files")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Renombra archivos de películas en Plex basándose en metadatos y similitud.")
    parser.add_argument("-d", "--debug", action="store_true", help="Habilita el modo debug para mostrar información detallada.")
    args = parser.parse_args()
    
    config_data_loaded = load_config_file(CONFIG_FILE)
    if not config_data_loaded:
      print(f"{Fore.LIGHTRED_EX}No se pudo cargar la configuración de '{CONFIG_FILE}'. Saliendo del programa.{Style.RESET_ALL}")
      exit(1)
    
    if not verify_and_load_config(config_data_loaded, args.debug):
        exit(1)
    
    list_movie_files(args.debug)
