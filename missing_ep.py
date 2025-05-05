#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import os
import sys
from datetime import datetime, timedelta
import urllib3
import re
import argparse
from collections import defaultdict

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description='Busca episodios de TV faltantes en Plex comparando con TheTVDB API v4.')
parser.add_argument('-d', '--debug', action='store_true', help='Activa el modo de depuración.')
args = parser.parse_args()

# --- Configuration Loading ---
CONFIG_FILE_PATH = 'plex.config.json'
CONFIG = {}
try:
    with open(CONFIG_FILE_PATH, 'r') as f: CONFIG = json.load(f)
except FileNotFoundError: print(f"Error: Configuración no encontrada: {CONFIG_FILE_PATH}"); sys.exit(1)
except json.JSONDecodeError: print(f"Error: JSON inválido: {CONFIG_FILE_PATH}"); sys.exit(1)
except Exception as e: print(f"Error leyendo configuración: {e}"); sys.exit(1)

# --- Extract Configuration Variables ---
PLEX_BASE_URL = CONFIG.get("PLEX_BASE_URL")
PLEX_TOKEN = CONFIG.get("PLEX_TOKEN")
THETVDB_APIKEY = CONFIG.get("THETVDB_APIKEY")
IGNORE_LIST = CONFIG.get("IGNORE_LIST", [])
CONFIG_DEBUG = CONFIG.get("DEBUG", False)

# --- Determine Debug Mode ---
DEBUG_MODE = args.debug or CONFIG_DEBUG
if DEBUG_MODE: print("**** MODO DEBUG ACTIVADO ****")

# --- Debug Print Helper ---
def debug_print(message):
    if DEBUG_MODE: print(f"[DEBUG] {message}")

# --- Basic Validation ---
if not all([PLEX_BASE_URL, PLEX_TOKEN, THETVDB_APIKEY]):
    print("Error: Faltan variables requeridas."); sys.exit(1)

# --- Constants ---
TVDB_API_BASE_URL = "https://api4.thetvdb.com/v4"
PLEX_HEADERS = {
    "X-Plex-Token": PLEX_TOKEN, "Accept": "application/json",
    "X-Plex-Client-Identifier": "PythonMissingTVEpisodesScript",
    "X-Plex-Product": "Python Script", "X-Plex-Version": "V1"
}
TVDB_HEADERS = { "Accept": "application/json", "Content-Type": "application/json" }

# --- Ignore Plex Certificate Issues ---
VERIFY_SSL = True
if PLEX_BASE_URL.startswith("https"):
    try: requests.get(PLEX_BASE_URL, timeout=5)
    except requests.exceptions.SSLError:
        print("Advertencia: Problema SSL Plex. Deshabilitando verificación.")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        VERIFY_SSL = False
    except requests.exceptions.RequestException: pass

# --- Helper Function for API Requests ---
def make_request(url, method="GET", headers=None, json_data=None, params=None, stream=False, is_tvdb=False):
    session_verify_ssl = VERIFY_SSL if not is_tvdb else True
    try:
        response = requests.request(method, url, headers=headers, json=json_data, params=params,
                                    verify=session_verify_ssl, timeout=45, stream=stream)
        response.raise_for_status()
        if not stream and 'application/json' in response.headers.get('Content-Type', ''):
            if response.status_code == 204: return None
            return response.json()
        return response
    except requests.exceptions.HTTPError as e:
        print(f"Error HTTP: {e.response.status_code} - {e.response.reason} para {url}")
        # ... (más manejo específico de errores) ...
    except Exception as e: # Catch other request errors
        print(f"Error en petición a {url}: {e}")
    return None

# --- TheTVDB Authentication ---
print("Autenticando con TheTVDB API v4...")
tvdb_auth_data = { "apikey": THETVDB_APIKEY }
tvdb_login_response = make_request(f"{TVDB_API_BASE_URL}/login", method="POST", json_data=tvdb_auth_data, headers=TVDB_HEADERS, is_tvdb=True)
if not tvdb_login_response or "data" not in tvdb_login_response or "token" not in tvdb_login_response.get("data", {}):
    print("Error Crítico: Fallo al obtener token TVDB v4."); sys.exit(1)
TVDB_TOKEN = tvdb_login_response["data"]["token"]
TVDB_HEADERS["Authorization"] = f"Bearer {TVDB_TOKEN}"
TVDB_HEADERS.pop("Content-Type", None)
print("Autenticación con TheTVDB API v4 exitosa.")

# --- Get Plex TV Show Library Keys ---
print("Obteniendo secciones de librería de TV de Plex...")
sections_url = f"{PLEX_BASE_URL}/library/sections"
sections_response = make_request(sections_url, headers=PLEX_HEADERS)

# <<< --- CORRECCIÓN: Asegurarse de que tv_keys se inicializa ANTES del bloque if/else --- >>>
tv_keys = []

if sections_response and "MediaContainer" in sections_response and "Directory" in sections_response["MediaContainer"]:
    for directory in sections_response["MediaContainer"]["Directory"]:
        if directory.get("type") == "show" and "key" in directory:
            key = directory["key"]; title = directory.get("title", "Sin Título")
            # Quitar el debug print aquí para reducir ruido si no es necesario
            # debug_print(f"Sección TV encontrada: '{title}' (Key: {key})")
            tv_keys.append(key)
else:
    # Este error es crítico, si no podemos obtener secciones, no podemos continuar.
    print("Error Crítico: No se pudieron obtener las secciones de la librería de Plex o la respuesta fue inválida.")
    sys.exit(1) # Salir si no hay secciones

# Ahora tv_keys existe, aunque podría estar vacía si no se encontraron secciones 'show'.
if not tv_keys:
    # Esto es una advertencia, no un error crítico si el servidor respondió pero no había secciones de TV.
    print("Advertencia: No se encontraron secciones de librería de tipo 'show' en Plex.")
    # Podríamos decidir salir aquí también si no hay nada que procesar:
    # sys.exit(0)

# Esta línea ahora es segura porque tv_keys está definida.
print(f"Se encontraron {len(tv_keys)} secciones de TV.") # <-- Línea 108 (aprox)


# --- Get All Rating Keys ---
# ... (resto del código sin cambios desde aquí) ...
print("Recopilando claves de calificación (ratingKeys) de las series...")
all_rating_keys = set()
for key in tv_keys: # Ahora seguro iterar sobre tv_keys
    debug_print(f"Obteniendo series de sección {key}")
    series_list_url = f"{PLEX_BASE_URL}/library/sections/{key}/all"
    series_response = make_request(series_list_url, headers=PLEX_HEADERS)
    if series_response and "MediaContainer" in series_response:
        content_list = series_response["MediaContainer"].get("Metadata") or series_response["MediaContainer"].get("Directory")
        if content_list is not None:
             for series in content_list:
                 title = series.get("title"); rating_key = series.get("ratingKey")
                 if title and rating_key:
                     if title not in IGNORE_LIST: all_rating_keys.add(rating_key)
        else: print(f"Advertencia: Sección {key} sin 'Metadata'/'Directory'.")
    else: print(f"Advertencia: No se obtuvieron series para sección {key}.")
print(f"Se encontraron {len(all_rating_keys)} series únicas (después de ignorar).")

# --- Get All Show Data from Plex ---
print("Recopilando datos detallados de las series desde Plex...")
plex_shows = {}
count = 0
total_keys = len(all_rating_keys)
for rating_key in sorted(list(all_rating_keys)):
    count += 1
    metadata_url = f"{PLEX_BASE_URL}/library/metadata/{rating_key}"
    show_data_response = make_request(metadata_url, headers=PLEX_HEADERS)
    if show_data_response and "MediaContainer" in show_data_response and "Metadata" in show_data_response["MediaContainer"]:
        show_data = show_data_response["MediaContainer"]["Metadata"][0]
        title = show_data.get("title")
        primary_guid = show_data.get("guid")
        if DEBUG_MODE or count % 10 == 0 or count == total_keys:
             print(f"Procesando Plex: [{count}/{total_keys}] {title or 'Título Desconocido'}")

        if not title: print(f"Advertencia: Omitida RK {rating_key} (sin título)."); continue

        tvdb_id = None
        guid_list = show_data.get("Guid", [])
        for guid_entry in guid_list:
            if isinstance(guid_entry, dict) and 'id' in guid_entry:
                guid_str = guid_entry['id']
                match = re.search(r'(?:tvdb|thetvdb)://(\d+)', guid_str)
                if match: tvdb_id = match.group(1); break
        if tvdb_id:
            if tvdb_id not in plex_shows:
                plex_shows[tvdb_id] = {"title": title, "ratingKeys": [], "seasons": {}}
            plex_shows[tvdb_id]["ratingKeys"].append(rating_key)
        else: print(f"Advertencia: No se encontró TVDB ID para '{title}' (RK:{rating_key}, GUID:{primary_guid}). Omitida.")
    else: print(f"Advertencia: No se obtuvieron metadatos para RK {rating_key}.")

# --- Get Season/Episode Data from Plex ---
print("\nRecopilando datos de temporadas y episodios desde Plex...")
count = 0
total_shows = len(plex_shows)
for tvdb_id, show_info in plex_shows.items():
    count += 1
    if DEBUG_MODE or count % 10 == 0 or count == total_shows:
        print(f"Procesando Episodios Plex: [{count}/{total_shows}] {show_info['title']}")
    show_info["seasons"] = {}
    for rating_key in show_info["ratingKeys"]:
        episodes_url = f"{PLEX_BASE_URL}/library/metadata/{rating_key}/allLeaves"
        episodes_response = make_request(episodes_url, headers=PLEX_HEADERS)
        if episodes_response and "MediaContainer" in episodes_response and "Metadata" in episodes_response["MediaContainer"]:
            for episode in episodes_response["MediaContainer"]["Metadata"]:
                season_num_str = episode.get("parentIndex"); episode_num = episode.get("index")
                episode_title = episode.get("title"); media_type = episode.get("type", "desconocido")
                if media_type == "episode" and season_num_str is not None and episode_num is not None:
                    try:
                        episode_num_int = int(episode_num); season_num_str = str(season_num_str)
                        if season_num_str not in show_info["seasons"]: show_info["seasons"][season_num_str] = []
                        found = any(episode_num_int in ep_dict for ep_dict in show_info["seasons"][season_num_str])
                        if not found: show_info["seasons"][season_num_str].append({episode_num_int: episode_title or "Sin Título"})
                    except (ValueError, TypeError): print(f"Advertencia: Núm. ep/temp inválido '{show_info['title']}' (RK:{rating_key}) S:{season_num_str} E:{episode_num}.")
        else: print(f"Advertencia: No se obtuvieron episodios para '{show_info['title']}' (RK:{rating_key}).")


# --- Compare with TheTVDB API v4 (using /extended) ---
print("\nComparando con TheTVDB API v4 y buscando episodios faltantes...")
missing_episodes_by_show = {}
count = 0
total_shows_to_compare = len(plex_shows)
for tvdb_id, show_info in plex_shows.items():
    count += 1
    show_title = show_info['title']
    print(f"Verificando TVDB v4 (Extended): [{count}/{total_shows_to_compare}] {show_title} (ID: {tvdb_id})")

    all_tvdb_episodes = []
    tvdb_extended_url = f"{TVDB_API_BASE_URL}/series/{tvdb_id}/extended"
    params = {"meta": "episodes"}
    tvdb_response = make_request(tvdb_extended_url, headers=TVDB_HEADERS, params=params, is_tvdb=True)

    if tvdb_response and isinstance(tvdb_response, dict) and "data" in tvdb_response:
        series_data = tvdb_response.get("data")
        if isinstance(series_data, dict) and "episodes" in series_data:
             episode_list = series_data["episodes"]
             if isinstance(episode_list, list):
                 all_tvdb_episodes = episode_list
                 debug_print(f"  Obtenidos {len(all_tvdb_episodes)} episodios desde /extended.")
             else: print(f"Advertencia: TVDB /extended 'episodes' no es lista para '{show_title}'. Datos: {str(episode_list)[:100]}...")
        else: debug_print(f"  TVDB /extended sin clave 'episodes' para '{show_title}'. Asumiendo 0 episodios.")
    else: print(f"Advertencia: No se pudo obtener respuesta válida de TVDB /extended para '{show_title}' (ID:{tvdb_id}).")
    # all_tvdb_episodes permanecerá [] si hubo error

    # Resumen de Episodios (Modo No-Debug)
    if not DEBUG_MODE and all_tvdb_episodes:
        print(f"  Resumen '{show_title}':")
        # ... (código del resumen igual) ...
        plex_seasons_data = show_info.get("seasons", {})
        plex_episode_counts = { s: len(e) for s, e in plex_seasons_data.items() if s != '0' }
        tvdb_episode_counts = defaultdict(int)
        for ep in all_tvdb_episodes:
             if not isinstance(ep, dict): continue
             tvdb_season_num = ep.get("seasonNumber"); tvdb_episode_num = ep.get("number"); aired_str = ep.get("aired")
             if tvdb_season_num is None or tvdb_season_num == 0 or tvdb_episode_num is None: continue
             if not aired_str: continue
             try:
                 aired_date = datetime.strptime(aired_str, "%Y-%m-%d").date()
                 if aired_date >= (datetime.now().date() - timedelta(days=1)): continue
             except ValueError: continue
             season_str = str(tvdb_season_num)
             tvdb_episode_counts[season_str] += 1
        all_season_keys_str = set(plex_episode_counts.keys()) | set(tvdb_episode_counts.keys())
        sorted_season_keys_int = []
        try: sorted_season_keys_int = sorted([int(k) for k in all_season_keys_str])
        except ValueError:
             print(f"    Advertencia: Claves de temporada no numéricas para '{show_title}'. Ordenando texto.")
             sorted_season_keys_str = sorted(list(all_season_keys_str))
             for season_key_str in sorted_season_keys_str:
                 plex_count = plex_episode_counts.get(season_key_str, 0); tvdb_count = tvdb_episode_counts[season_key_str]
                 status = "OK" if plex_count >= tvdb_count else ("FALTAN" if plex_count < tvdb_count else "Solo Plex?")
                 print(f"    Temporada {season_key_str:>2}: Plex ({plex_count:>3}), TVDB ({tvdb_count:>3}) [{status}]")
        for season_num_int in sorted_season_keys_int:
            season_key_str = str(season_num_int)
            plex_count = plex_episode_counts.get(season_key_str, 0); tvdb_count = tvdb_episode_counts[season_key_str]
            status = "OK" if plex_count >= tvdb_count else ("FALTAN" if plex_count < tvdb_count else "Solo Plex?")
            print(f"    Temporada {season_num_int:02d}: Plex ({plex_count:>3}), TVDB ({tvdb_count:>3}) [{status}]")


    # Bucle para encontrar episodios específicamente faltantes
    for tvdb_episode in all_tvdb_episodes:
        if not isinstance(tvdb_episode, dict): continue
        try:
            # ... (lógica interna de comparación igual) ...
            tvdb_season_num = tvdb_episode.get("seasonNumber"); tvdb_episode_num = tvdb_episode.get("number")
            tvdb_episode_name = tvdb_episode.get("name"); aired_str = tvdb_episode.get("aired")
            if tvdb_season_num is None or tvdb_season_num == 0 or tvdb_episode_num is None: continue
            if not aired_str: continue
            try:
                aired_date = datetime.strptime(aired_str, "%Y-%m-%d").date()
                if aired_date >= (datetime.now().date() - timedelta(days=1)): continue
            except ValueError: continue
            tvdb_season_num_str = str(tvdb_season_num)
            plex_episodes_in_season = show_info.get("seasons", {}).get(tvdb_season_num_str, [])
            plex_episode_numbers = set(num for ep_dict in plex_episodes_in_season for num in ep_dict.keys())
            plex_episode_names = set(name for ep_dict in plex_episodes_in_season for name in ep_dict.values())
            try: tvdb_episode_num_int = int(tvdb_episode_num)
            except (ValueError, TypeError): continue
            found_by_number = tvdb_episode_num_int in plex_episode_numbers
            found_by_name = tvdb_episode_name is not None and tvdb_episode_name in plex_episode_names
            is_missing = not found_by_number and not found_by_name
            if is_missing:
                if show_title not in missing_episodes_by_show: missing_episodes_by_show[show_title] = []
                missing_episodes_by_show[show_title].append({
                    "season": tvdb_season_num_str, "episode": str(tvdb_episode_num_int),
                    "name": tvdb_episode_name or "Nombre Desconocido"
                })
        except Exception as e:
            print(f"Error inesperado procesando episodio TVDB '{show_title}': {tvdb_episode}\nError: {e}")
            continue


# --- Imprimir Lista Detallada de Faltantes ---
if missing_episodes_by_show:
    print("\n--- Lista Detallada de Episodios Faltantes ---")
    # ... (código igual) ...
    for show_title in sorted(missing_episodes_by_show.keys()):
        print(f"\n{show_title}:")
        missing_list = missing_episodes_by_show[show_title]
        try: missing_list.sort(key=lambda x: (int(x['season']), int(x['episode'])))
        except ValueError: missing_list.sort(key=lambda x: (x['season'], x['episode']))
        for episode in missing_list:
            try:
                s_num = int(episode['season']); e_num = int(episode['episode'])
                print(f"  S{s_num:02d}E{e_num:02d} - {episode['name']}")
            except (ValueError, TypeError): print(f"  Season {episode['season']} Episode {episode['episode']} - {episode['name']} (Error formato)")

else:
     print("\n--- ¡No se encontraron episodios faltantes! ---")


# --- Resumen Final de Episodios Faltantes por Temporada ---
if missing_episodes_by_show:
    print("\n--- Resumen de Episodios Faltantes por Temporada ---")
    missing_counts = defaultdict(lambda: defaultdict(int))
    for show_title, missing_list in missing_episodes_by_show.items():
        for episode in missing_list:
            season = episode['season']
            missing_counts[show_title][season] += 1
    for show_title in sorted(missing_counts.keys()):
        print(f"\n{show_title}:")
        seasons_sorted = []
        try: seasons_sorted = sorted(missing_counts[show_title].keys(), key=int)
        except ValueError:
            print("  Advertencia: Claves de temporada no numéricas. Ordenando texto.")
            seasons_sorted = sorted(missing_counts[show_title].keys())
        for season in seasons_sorted:
            count = missing_counts[show_title][season]
            try: season_formatted = f"Temporada {int(season):02d}"
            except ValueError: season_formatted = f"Temporada {season}"
            print(f"  {season_formatted}: {count} episodio{'s' if count > 1 else ''} faltante{'s' if count > 1 else ''}")


print("\n--- Proceso Completado ---")
