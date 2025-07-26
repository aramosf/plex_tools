import os
import json
import re
import argparse
import shutil
from pathlib import Path
from collections import defaultdict

# Inicializar colorama
try:
    import colorama
    from colorama import Fore, Style, Back
    colorama.init(autoreset=True)
except ImportError:
    class DummyColorama:
        def __getattr__(self, name): return ""
    Fore = Style = Back = DummyColorama()

CONFIG_FILE = 'config.json'

def cargar_configuracion():
    """Carga la configuración desde el archivo JSON."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            config['patrones_regex'] = [re.compile(p, re.IGNORECASE) for p in config['patrones_nombre']]
            return config
    except FileNotFoundError:
        print(f"{Fore.RED}Error: No se encontró el archivo de configuración '{CONFIG_FILE}'.")
        return None
    except json.JSONDecodeError:
        print(f"{Fore.RED}Error: El archivo de configuración '{CONFIG_FILE}' no es un JSON válido.")
        return None

def sanitize_filename(name):
    """
    Limpia un nombre para que sea seguro, protegiendo las etiquetas de ID.
    """
    id_tag = ''
    title_part = name
    
    # 1. Buscar y aislar la etiqueta de ID para protegerla
    id_match = re.search(r'(\{((imdb-tt|tmdb-)\d+)\})', name, re.IGNORECASE)
    if id_match:
        id_tag = id_match.group(1)
        title_part = name.replace(id_tag, '')

    # 2. Sanear solo la parte del título
    # LÍNEA MODIFICADA: Se añaden ",!¡?¿" a la lista de caracteres permitidos.
    sanitized_title = re.sub(r'[^\w\s.\-()\[\]{},!¡?¿]', '-', title_part)
    sanitized_title = re.sub(r'[\s-]+', ' ', sanitized_title).strip()
    
    # 3. Reconstruir el nombre
    final_name = f"{sanitized_title} {id_tag}".strip() if sanitized_title and id_tag else sanitized_title + id_tag

    # 4. Asegurarse de que no empiece con un punto
    if final_name.startswith('.'):
        final_name = final_name.lstrip('.').strip()

    return final_name

def get_base_movie_name(stem):
    """Elimina los indicadores comunes de partes múltiples de un nombre de archivo."""
    part_regex = re.compile(r'[\s._-](part|cd|disc|pt)\d+$', re.IGNORECASE)
    base_name = part_regex.sub('', stem)
    return base_name.strip()

def es_pelicula_procesable(path, config):
    """Verifica si un archivo es una película que cumple los criterios para ser organizada."""
    if not path.is_file() or path.suffix.lower() not in config['extensiones_video']:
        return False
    for patron in config['patrones_regex']:
        if patron.search(path.name):
            return True
    return False

def procesar_directorio(directorio_base, config, execute_mode, archivos_procesados):
    """Recorre un directorio, identifica películas y archivos, y los organiza de forma segura."""
    print(f"\n--- {Style.BRIGHT}Procesando: {Fore.CYAN}{directorio_base}{Style.RESET_ALL} ---")
    if not os.path.isdir(directorio_base):
        print(f"{Fore.YELLOW}AVISO: El directorio '{directorio_base}' no existe. Omitiendo.")
        return

    for path in list(Path(directorio_base).rglob('*')):
        if not path.is_file(): continue

        if path.suffix.lower() in config['archivos_a_eliminar_extensiones']:
            archivos_procesados.add(path)
            print(f"{Fore.RED}{Style.BRIGHT}[ELIMINAR ARCHIVO]{Style.RESET_ALL} {Fore.CYAN}{path}{Style.RESET_ALL}")
            if execute_mode:
                try: path.unlink(); print(f"{Fore.RED}  -> ELIMINADO.")
                except OSError as e: print(f"{Fore.RED}  -> ERROR al eliminar: {e}")
            else:
                print(f"{Fore.YELLOW}  -> SIMULADO.")
            continue

        if es_pelicula_procesable(path, config):
            archivos_procesados.add(path)
            
            base_name = get_base_movie_name(path.stem)
            sanitized_name = sanitize_filename(base_name)
            ideal_parent_dir = Path(directorio_base) / sanitized_name
            
            if path.parent.resolve() == ideal_parent_dir.resolve():
                continue

            print(f"{Fore.GREEN}{Style.BRIGHT}[ORGANIZAR/CORREGIR]{Style.RESET_ALL} {Fore.CYAN}{path.name}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}  [MOVER ARCHIVO]{Style.RESET_ALL} de {Fore.CYAN}{path.parent}{Style.RESET_ALL}")
            print(f"                 a {Fore.CYAN}{ideal_parent_dir}{Style.RESET_ALL}")

            if execute_mode:
                try:
                    ideal_parent_dir.mkdir(exist_ok=True)
                    shutil.move(str(path), str(ideal_parent_dir))
                    print(f"{Fore.GREEN}    -> MOVIDO.")
                except Exception as e:
                    print(f"{Fore.RED}    -> ERROR al mover: {e}")
            else:
                if not ideal_parent_dir.exists():
                    print(f"{Fore.GREEN}  [CREAR DIR]{Style.RESET_ALL} {Fore.CYAN}{ideal_parent_dir}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}    -> SIMULADO.")

def limpiar_directorios_vacios(directorio, execute_mode):
    """Elimina directorios vacíos de abajo hacia arriba."""
    print(f"\n--- {Style.BRIGHT}Buscando directorios vacíos en: {Fore.CYAN}{directorio}{Style.RESET_ALL} ---")
    for dirpath, _, _ in os.walk(directorio, topdown=False):
        if os.path.realpath(dirpath) == os.path.realpath(directorio): continue
        try:
            if not os.listdir(dirpath):
                print(f"{Fore.RED}{Style.BRIGHT}[ELIMINAR DIR VACÍO]{Style.RESET_ALL} {Fore.CYAN}{dirpath}{Style.RESET_ALL}")
                if execute_mode:
                    try: os.rmdir(dirpath); print(f"{Fore.RED}  -> BORRADO.")
                    except OSError as e: print(f"{Fore.RED}  -> ERROR al borrar: {e}")
                else:
                    print(f"{Fore.YELLOW}  -> SIMULADO.")
        except FileNotFoundError:
            continue

def generar_reporte_sobrantes(directorios, archivos_procesados):
    """Genera un reporte de archivos que no fueron procesados."""
    print(f"\n\n{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}--- REPORTE DE ARCHIVOS NO PROCESADOS ---{Style.RESET_ALL}")
    
    sobrantes_por_extension = defaultdict(list)
    for directorio in directorios:
        if not Path(directorio).is_dir(): continue
        for path in Path(directorio).rglob('*'):
            if path.is_file() and path.exists() and path not in archivos_procesados:
                sobrantes_por_extension[path.suffix.lower()].append(str(path))

    if not sobrantes_por_extension:
        print(f"\n{Fore.GREEN}¡Excelente! No se encontraron archivos sobrantes.")
        return
    
    print(f"{Fore.YELLOW}Estos archivos no se movieron ni eliminaron (no coinciden con patrones de película ni de basura).")
    for extension, archivos in sorted(sobrantes_por_extension.items()):
        ext_name = extension if extension else '[Sin extensión]'
        print(f"\n--- {Style.BRIGHT}Extensión: {Fore.YELLOW}{ext_name}{Style.RESET_ALL} ({len(archivos)} archivos) ---")
        for archivo in archivos:
            print(f"  - {Fore.CYAN}{archivo}{Style.RESET_ALL}")

def main():
    """Función principal del script."""
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
        description="Organiza archivos de películas, corrigiendo anidamientos y limpiando archivos innecesarios.\n"
                    "Por defecto, solo simula los cambios (modo dry-run).")
    parser.add_argument('-e', '--execute', action='store_true', help='EJECUTA los cambios en el disco.')
    parser.add_argument('--no-report', action='store_true', help='No muestra el reporte final de archivos sobrantes.')
    args = parser.parse_args()

    config = cargar_configuracion()
    if not config: return

    header_color = Back.RED if args.execute else Back.YELLOW
    text_color = Fore.WHITE if args.execute else Fore.BLACK
    mode_text = " MODO EJECUCIÓN: ¡SE REALIZARÁN CAMBIOS REALES! " if args.execute else " MODO DRY-RUN (POR DEFECTO): NO SE REALIZARÁN CAMBIOS. "
    print(f"{header_color}{text_color}{Style.BRIGHT}{mode_text.center(70, '*')}{Style.RESET_ALL}")
    
    archivos_procesados = set()
    
    for dir_fuente in config['directorios_fuente']:
        procesar_directorio(dir_fuente, config, args.execute, archivos_procesados)
        limpiar_directorios_vacios(dir_fuente, args.execute)

    if not args.no_report:
        generar_reporte_sobrantes(config['directorios_fuente'], archivos_procesados)

    print(f"\n--- {Style.BRIGHT}Proceso finalizado.{Style.RESET_ALL} ---")
    if not args.execute:
        print(f"{Fore.YELLOW}Recuerda: Estás en modo dry-run. Para aplicar los cambios, ejecuta de nuevo con '-e' o '--execute'.")

if __name__ == "__main__":
    main()
