import csv

# Columnas que quieres conservar y sus nombres finales
COLUMNAS = [
    "TIPO", "PISO", "NOMBRE_UBICACION", "LAZO", "DIRECCION",
    "SERIAL", "FECHA_MANTO", "ESTADO", "OBSERVACION"
]

# Mapeo para limpiar encabezados (quita espacios y caracteres raros)
def limpiar_encabezado(h):
    h = h.strip().replace("�", "N").replace("  ", " ").replace("_", "")
    h = h.replace("NOMBRE UBICACION", "NOMBRE_UBICACION")
    return h.upper().replace(" ", "_")

with open("dispositivos1.csv", encoding="utf-8") as fin, \
     open("dispositivos1_limpio.csv", "w", newline='', encoding="utf-8") as fout:
    reader = csv.DictReader(fin, delimiter=";")
    # Normaliza encabezados
    encabezados = [limpiar_encabezado(h) for h in reader.fieldnames]
    # Crea mapeo de columnas originales a las que quieres
    mapeo = {}
    for col in COLUMNAS:
        for h in encabezados:
            if col in h:
                mapeo[col] = h
                break
    writer = csv.DictWriter(fout, fieldnames=COLUMNAS)
    writer.writeheader()
    for row in reader:
        nueva = {col: row.get(mapeo[col], "").strip() for col in COLUMNAS}
        writer.writerow(nueva)

print("¡Archivo limpio creado como dispositivos1_limpio.csv!")