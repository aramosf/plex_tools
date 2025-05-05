#!/bin/bash

# Nombre del archivo CSV (puedes cambiarlo si es necesario)
CSV_FILE="plex_movies_export.csv"

# --- Función de Ayuda ---
usage() {
  echo "Uso: $0 <nota_maxima> <directorio_destino>"
  echo
  echo "Argumentos:"
  echo "  <nota_maxima>        : La nota máxima de IMDb (inclusive). Las películas"
  echo "                         con nota estrictamente *inferior* a este valor serán movidas."
  echo "                         Ejemplo: 3.0"
  echo "  <directorio_destino> : La ruta completa al directorio donde se moverán"
  echo "                         las carpetas de las películas con baja nota."
  echo
  echo "Descripción:"
  echo "  Este script lee el archivo '$CSV_FILE', busca películas con una nota de IMDb"
  echo "  inferior a <nota_maxima>, y mueve sus directorios correspondientes"
  echo "  (indicados en la columna 'file_directory') al <directorio_destino>."
  echo "  Se realizan comprobaciones para evitar la pérdida de datos:"
  echo "    - Verifica que el directorio de origen exista antes de moverlo."
  echo "    - Verifica que no exista ya un directorio con el mismo nombre en el destino."
  echo "    - Crea el directorio de destino si no existe."
  echo "    - Requiere que la nota máxima sea un número válido."
  exit 1
}

# --- Validación de Argumentos ---
if [ "$#" -ne 2 ]; then
  echo "Error: Número incorrecto de argumentos." >&2
  usage
fi

threshold="$1"
dest_dir="$2"

# Validar que la nota sea un número (simple validación, awk hará la comparación numérica)
if ! [[ "$threshold" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "Error: La nota máxima '$threshold' no parece ser un número válido (ej: 3.0, 4, 5.5)." >&2
    usage
fi

# Validar que el archivo CSV exista
if [ ! -f "$CSV_FILE" ]; then
    echo "Error: No se encuentra el archivo CSV '$CSV_FILE'." >&2
    exit 1
fi

# --- Preparación del Directorio Destino ---
# Crear el directorio destino si no existe (-p crea directorios padres si es necesario)
echo "INFO: Asegurando que el directorio destino '$dest_dir' exista..."
mkdir -p "$dest_dir"
if [ $? -ne 0 ]; then
    echo "Error: No se pudo crear el directorio destino '$dest_dir'." >&2
    exit 1
fi
# Asegurarse de que sea un directorio
if [ ! -d "$dest_dir" ]; then
    echo "Error: La ruta destino '$dest_dir' existe pero no es un directorio." >&2
    exit 1
fi
echo "INFO: El directorio destino '$dest_dir' está listo."

# --- Procesamiento del CSV y Mover Archivos ---
echo "INFO: Procesando '$CSV_FILE' para mover películas con nota < $threshold a '$dest_dir'..."

# Usamos awk para filtrar las líneas correctas y extraer el directorio
# -v pasa variables de bash a awk
# FPAT maneja campos con comas dentro de comillas
# NR > 1 salta la cabecera
# Comparamos la nota (columna 3) con el umbral
# Imprimimos la ruta del directorio (columna 5) sin comillas
awk -v threshold="$threshold" \
    'BEGIN{ FPAT = "([^,]+)|(\"[^\"]+\")"; OFS="," }
     NR > 1 {
        rating = $3;
        gsub(/"/, "", rating); # Quitar comillas de la nota

        source_dir_raw = $5;
        gsub(/^"|"$/, "", source_dir_raw); # Quitar comillas del path si las tiene

        # Comprobar si es numérico y menor que el umbral
        if (rating != "N/A" && rating + 0 == rating && rating < threshold) {
            print source_dir_raw # Imprimir solo la ruta del directorio a mover
        }
     }' "$CSV_FILE" | \
while IFS= read -r source_dir; do
    # IFS= read -r previene que se interpreten backslashes y se coman espacios al inicio/final

    if [ -z "$source_dir" ]; then
        # Saltar líneas vacías si las hubiera por alguna razón
        continue
    fi

    echo "---" # Separador visual para cada película
    echo "INFO: Candidata encontrada: Película con directorio '$source_dir'"

    # Comprobación 1: ¿Existe el directorio de origen?
    if [ ! -d "$source_dir" ]; then
        echo "AVISO: El directorio de origen '$source_dir' no existe o no es un directorio. Saltando." >&2
        continue
    fi

    # Obtener el nombre base del directorio (ej: "Abuelos (2019) {imdb-tt8092586}")
    source_basename=$(basename "$source_dir")
    if [ -z "$source_basename" ]; then
        echo "ERROR: No se pudo obtener el nombre base del directorio '$source_dir'. Saltando." >&2
        continue
    fi

    # Construir la ruta completa de destino
    target_path="$dest_dir/$source_basename"

    # Comprobación 2: ¿Existe ya algo con ese nombre en el destino? (Evitar sobrescritura)
    if [ -e "$target_path" ]; then # -e comprueba existencia de archivo o directorio
        echo "AVISO: Ya existe '$target_path' en el destino. No se moverá '$source_dir' para evitar sobrescritura. Saltando." >&2
        continue
    fi

    # ¡Todo listo para mover!
    echo "ACCIÓN: Moviendo '$source_dir' a '$dest_dir/'..."
    # Usamos -v para que mv muestre lo que está haciendo
    mv -v "$source_dir" "$dest_dir/"

    if [ $? -ne 0 ]; then
        echo "ERROR: Falló el intento de mover '$source_dir'. Comprueba permisos o si el directorio está en uso." >&2
        # Continuamos con el siguiente, pero informamos del error
    else
        echo "ÉXITO: Directorio '$source_dir' movido correctamente."
    fi

done

echo "---"
echo "INFO: Proceso completado."
exit 0

