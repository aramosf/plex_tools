import csv
import os
import shutil
import sys
import argparse
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

# --- Constantes y Configuración ---
CSV_FILE = "plex_movies_export.csv"

# Códigos de escape ANSI para colores
COLOR_RESET = "\033[0m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_CYAN = "\033[96m"
COLOR_MAGENTA = "\033[95m"
COLOR_BOLD = "\033[1m"

# --- Funciones de Utilidad ---

def prepare_directory(path_str: str) -> Path:
    """Prepara un directorio de destino: lo crea y devuelve su ruta absoluta."""
    if not path_str:
        raise ValueError(f"{COLOR_RED}La ruta del directorio de destino no puede estar vacía.{COLOR_RESET}")
    target_path = Path(path_str)
    try:
        target_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(f"{COLOR_RED}Error al crear directorio '{path_str}': {e}{COLOR_RESET}")
    if not target_path.is_dir():
        raise SystemExit(f"{COLOR_RED}La ruta de destino '{path_str}' no es un directorio.{COLOR_RESET}")
    try:
        return target_path.resolve()
    except OSError as e:
        raise SystemExit(f"{COLOR_RED}Error al resolver ruta de destino '{path_str}': {e}{COLOR_RESET}")

def count_items_in_directory(directory_path: Path) -> int:
    """Cuenta los elementos directamente dentro de un directorio."""
    if not directory_path.is_dir(): return 0
    try:
        return len(list(directory_path.iterdir()))
    except OSError as e:
        print(f"{COLOR_YELLOW}Advertencia: No se pudo contar en '{directory_path}': {e}{COLOR_RESET}", file=sys.stderr)
        return 9999

def get_total_size(path: Path) -> int:
    """Calcula el tamaño total en bytes de un archivo o directorio (recursivamente)."""
    if not path.exists(): return 0
    if path.is_file(): return path.stat().st_size
    total_size = 0
    for entry in path.rglob('*'):
        if entry.is_file():
            try:
                total_size += entry.stat().st_size
            except OSError as e:
                print(f"{COLOR_YELLOW}Advertencia: No se pudo obtener tamaño de '{entry}': {e}{COLOR_RESET}", file=sys.stderr)
    return total_size

def format_bytes(size_bytes: int) -> str:
    """Formatea bytes a una cadena legible (KB, MB, GB, TB)."""
    if size_bytes == 0: return "0 B"
    sizes = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(sizes) - 1:
        size_bytes /= 1024; i += 1
    return f"{size_bytes:.2f} {sizes[i]}"

def extract_year_from_name(name: str) -> Optional[int]:
    """Extrae un año de 4 dígitos entre paréntesis de una cadena."""
    match = re.search(r'\((\d{4})\)', name)
    if match:
        return int(match.group(1))
    return None

# --- Función Principal ---

def main():
    parser = argparse.ArgumentParser(
        description="Mueve películas según nota, género o año (un filtro a la vez). Opera en 'dry-run' por defecto.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # Argumentos para los filtros (mutuamente excluyentes)
    parser.add_argument(
        '-d', '--down', nargs=2, metavar=('<nota>', '<dir>'),
        help="Mueve películas con nota < <nota> al <dir>."
    )
    parser.add_argument(
        '-t', '--top', nargs=2, metavar=('<nota>', '<dir>'),
        help="Mueve películas con nota > <nota> al <dir>."
    )
    parser.add_argument(
        '-g', '--genre', nargs='+', metavar=('<dir>', '<género>'),
        help="Mueve películas que tengan TODOS los géneros especificados (lógica 'Y').\n"
             "Ej: -g /docs Documental 'Película de TV'"
    )
    parser.add_argument(
        '-y', '--year', nargs=2, metavar=('<rango>', '<dir>'),
        help="Mueve películas cuyo año esté en el <rango> (ej: '1920-1940')."
    )
    # Argumentos de configuración del script
    parser.add_argument(
        '-c', '--csv-file', default=CSV_FILE,
        help=f"Archivo CSV a procesar (por defecto: {CSV_FILE})"
    )
    parser.add_argument(
        '-e', '--execute', action='store_true',
        help="Ejecuta realmente las operaciones de movimiento. Por defecto es modo 'dry-run'."
    )
    args = parser.parse_args()

    # --- Validación de Parámetros Mutuamente Excluyentes ---
    active_filters_count = sum([1 for arg in [args.down, args.top, args.genre, args.year] if arg is not None])
    if active_filters_count > 1:
        sys.exit(f"{COLOR_RED}Error: Los filtros de nota (-d, -t), género (-g) y año (-y) son mutuamente excluyentes. Usa solo uno a la vez.{COLOR_RESET}")
    if active_filters_count == 0:
        parser.print_help()
        sys.exit(f"{COLOR_RED}Error: Debes especificar un filtro (-d, -t, -g, o -y).{COLOR_RESET}")

    # --- Procesar el ÚNICO filtro activo ---
    active_filter = {}
    if args.down:
        try:
            active_filter = {'type': 'down', 'threshold': float(args.down[0]), 'dest': prepare_directory(args.down[1])}
        except ValueError: sys.exit(f"{COLOR_RED}Error: La nota '{args.down[0]}' no es un número válido.{COLOR_RESET}")
    elif args.top:
        try:
            active_filter = {'type': 'top', 'threshold': float(args.top[0]), 'dest': prepare_directory(args.top[1])}
        except ValueError: sys.exit(f"{COLOR_RED}Error: La nota '{args.top[0]}' no es un número válido.{COLOR_RESET}")
    elif args.genre:
        if len(args.genre) < 2: sys.exit(f"{COLOR_RED}Error: -g requiere un directorio y al menos un género.{COLOR_RESET}")
        dest_dir = prepare_directory(args.genre[0])
        genre_list = [g.lower() for g in args.genre[1:]]
        active_filter = {'type': 'genre', 'genres': genre_list, 'dest': dest_dir}
    elif args.year:
        try:
            start_str, end_str = args.year[0].split('-')
            start_year, end_year = int(start_str), int(end_str)
            if start_year > end_year: sys.exit(f"{COLOR_RED}Error: El rango de años '{args.year[0]}' es inválido.{COLOR_RESET}")
            active_filter = {'type': 'year', 'start': start_year, 'end': end_year, 'dest': prepare_directory(args.year[1])}
        except (ValueError, IndexError):
            sys.exit(f"{COLOR_RED}Error: El rango de años '{args.year[0]}' debe tener el formato AAAA-AAAA.{COLOR_RESET}")

    csv_path = Path(args.csv_file)
    if not csv_path.is_file():
        sys.exit(f"{COLOR_RED}Error: No se encuentra el archivo CSV '{csv_path}'.{COLOR_RESET}")

    execute_mode = args.execute
    print(f"Modo: {COLOR_BOLD}{'EJECUCIÓN REAL' if execute_mode else 'DRY-RUN (simulación)'}{COLOR_RESET}")
    print(f"Procesando '{csv_path}' con el siguiente filtro:")
    if active_filter['type'] == 'down': print(f"  {COLOR_BLUE}BAJA NOTA < {active_filter['threshold']} -> {active_filter['dest']}{COLOR_RESET}")
    if active_filter['type'] == 'top': print(f"  {COLOR_BLUE}ALTA NOTA > {active_filter['threshold']} -> {active_filter['dest']}{COLOR_RESET}")
    if active_filter['type'] == 'genre': print(f"  {COLOR_MAGENTA}GÉNERO con TODOS [{', '.join(active_filter['genres'])}] -> {active_filter['dest']}{COLOR_RESET}")
    if active_filter['type'] == 'year': print(f"  {COLOR_MAGENTA}AÑO en [{active_filter['start']}-{active_filter['end']}] -> {active_filter['dest']}{COLOR_RESET}")
    print("---")

    # --- Variables para el Resumen ---
    stats = {'processed': 0, 'matched': 0, 'moved': 0, 'skipped': 0, 'failed': 0}
    total_size_to_move = 0
    conflicts = []

    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            required_cols = ["title", "imdb_rating", "file_path", "genres"] 
            if not all(col in reader.fieldnames for col in required_cols):
                sys.exit(f"{COLOR_RED}Error: El CSV debe contener las columnas: {', '.join(required_cols)}{COLOR_RESET}")

            for row_num, row in enumerate(reader, start=2):
                stats['processed'] += 1
                
                full_file_path_str = row.get("file_path", "")
                if not full_file_path_str:
                    print(f"{COLOR_YELLOW}Línea {row_num}: SKIPPED (ruta de archivo vacía){COLOR_RESET}", file=sys.stderr)
                    stats['skipped'] += 1
                    continue
                
                full_file_path = Path(full_file_path_str)
                source_dir = full_file_path.parent
                
                # --- Comprobar si la película coincide con el filtro activo ---
                is_match = False
                move_reason = ""
                
                f_type = active_filter['type']
                if f_type == 'down' or f_type == 'top':
                    try:
                        rating = float(row.get("imdb_rating", "N/A"))
                        if (f_type == 'down' and rating < active_filter['threshold']) or \
                           (f_type == 'top' and rating > active_filter['threshold']):
                            is_match = True
                            move_reason = f"{'BAJA' if f_type == 'down' else 'ALTA'} NOTA"
                    except (ValueError, TypeError): pass
                elif f_type == 'genre':
                    movie_genres = {g.strip().lower() for g in row.get("genres", "").split('#')}
                    # La película debe tener TODOS los géneros especificados (lógica 'Y')
                    if all(g in movie_genres for g in active_filter['genres']):
                        is_match = True
                        move_reason = "GÉNERO"
                elif f_type == 'year':
                    movie_year = extract_year_from_name(source_dir.name)
                    if movie_year and active_filter['start'] <= movie_year <= active_filter['end']:
                        is_match = True
                        move_reason = "AÑO"
                
                if not is_match:
                    continue
                
                stats['matched'] += 1
                source_display_name = f"{row.get('title', 'N/A')} ({row.get('imdb_rating', 'N/A')})"
                current_dest_dir = active_filter['dest']

                # --- VALIDACIONES Y LÓGICA DE MOVIMIENTO ---
                if not source_dir.is_dir():
                    print(f"{COLOR_YELLOW}{source_display_name} [{move_reason}] SKIPPED (origen '{source_dir}' no encontrado){COLOR_RESET}", file=sys.stderr)
                    stats['skipped'] += 1; continue
                
                try:
                    source_dir_abs_str = str(source_dir.resolve()).rstrip(os.sep) + os.sep
                    current_dest_dir_abs_str = str(current_dest_dir.resolve()).rstrip(os.sep) + os.sep
                    if source_dir_abs_str.startswith(current_dest_dir_abs_str):
                        print(f"{COLOR_YELLOW}{source_display_name} [{move_reason}] SKIPPED (ya en destino){COLOR_RESET}", file=sys.stderr)
                        stats['skipped'] += 1; continue
                except OSError as e:
                    print(f"{COLOR_YELLOW}{source_display_name} [{move_reason}] SKIPPED (error al resolver ruta: {e}){COLOR_RESET}", file=sys.stderr)
                    stats['skipped'] += 1; continue
                
                # Decidir si mover directorio o solo archivo
                source_basename = source_dir.name
                num_items = count_items_in_directory(source_dir)
                contains_id = ("imdb" in source_basename.lower() or "tmdb" in source_basename.lower())
                
                if not contains_id or num_items > 3:
                    reasons = []
                    if not contains_id: reasons.append("sin id")
                    if num_items > 3: reasons.append(f">{num_items} archivos")
                    move_log_type = f"FILE_ONLY ({', '.join(reasons)})"
                    move_target, target_name_in_dest = full_file_path, full_file_path.name
                    if not move_target.is_file():
                        print(f"{COLOR_YELLOW}{source_display_name} [{move_reason}] SKIPPED (archivo '{move_target}' no encontrado){COLOR_RESET}", file=sys.stderr)
                        stats['skipped'] += 1; continue
                else:
                    move_log_type = "DIR"
                    move_target, target_name_in_dest = source_dir, source_basename

                target_path_in_dest = current_dest_dir / target_name_in_dest
                
                # --- Ejecutar o Simular el Movimiento ---
                if execute_mode:
                    if target_path_in_dest.exists():
                        print(f"{COLOR_YELLOW}{source_display_name} [{move_reason}] SKIPPED (destino ya existe en '{target_path_in_dest}'){COLOR_RESET}", file=sys.stderr)
                        stats['skipped'] += 1; continue
                    
                    try:
                        shutil.move(str(move_target), str(current_dest_dir))
                        print(f"{COLOR_GREEN}{source_display_name} [{move_reason}] -> {current_dest_dir} OK ({move_log_type}){COLOR_RESET}")
                        stats['moved'] += 1
                    except (shutil.Error, OSError) as e:
                        print(f"{COLOR_RED}{source_display_name} [{move_reason}] FAILED (error al mover: {e}){COLOR_RESET}", file=sys.stderr)
                        stats['failed'] += 1
                else: # Dry-run mode
                    try: display_target = move_target.relative_to(Path.cwd())
                    except ValueError: display_target = move_target
                    
                    print(f"{COLOR_CYAN}{source_display_name} [{move_reason}] -> {current_dest_dir} DRY-RUN ({move_log_type}){COLOR_RESET}")
                    
                    total_size_to_move += get_total_size(move_target)
                    
                    if target_path_in_dest.exists():
                        conflicts.append({'source': str(move_target), 'conflict': str(target_path_in_dest)})

    except FileNotFoundError:
        sys.exit(f"{COLOR_RED}Error: No se pudo abrir el archivo CSV '{csv_path}'.{COLOR_RESET}")
    except Exception as e:
        sys.exit(f"{COLOR_RED}Error inesperado durante el procesamiento: {e}{COLOR_RESET}")

    # --- Resumen Final ---
    print("---")
    print("Proceso completado.")
    print(f"Películas procesadas en CSV: {stats['processed']}")
    print(f"Películas que coinciden con el filtro: {stats['matched']}")

    if not execute_mode:
        print(f"\n{COLOR_BOLD}--- Resumen del Dry-Run ---{COLOR_RESET}")
        print(f"  {COLOR_BLUE}Destino: '{active_filter['dest']}'{COLOR_RESET}")
        print(f"    - Tamaño total a mover: {COLOR_BOLD}{format_bytes(total_size_to_move)}{COLOR_RESET}")
        if conflicts:
            print(f"    - {COLOR_YELLOW}Conflictos detectados: {len(conflicts)}{COLOR_RESET}")
            for c in conflicts:
                print(f"      - Origen '{c['source']}' chocaría con '{c['conflict']}'")
        print(f"\n{COLOR_BOLD}(Para ejecutar realmente las operaciones, usa el parámetro -e){COLOR_RESET}")
    else:
        print(f"Películas {COLOR_GREEN}movidas realmente: {stats['moved']}{COLOR_RESET}")
    
    print(f"Películas {COLOR_YELLOW}saltadas: {stats['skipped']}{COLOR_RESET}")
    print(f"Operaciones {COLOR_RED}fallidas: {stats['failed']}{COLOR_RESET}")
    sys.exit(0)

if __name__ == "__main__":
    main()
