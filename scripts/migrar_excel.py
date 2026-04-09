import pandas as pd
from sqlalchemy import create_engine

CSV_PATH = "dispositivos1.csv"
DB_PATH = "data.db"

# Leer CSV
df = pd.read_csv(CSV_PATH, sep=';', encoding='latin1', header=None)

# Nombres de columnas
df.columns = [
    "id","PISO","TIPO","LAZO","NOMBRE_UBICACION","DIRECCION",
    "SERIAL","FECHA_MANTO","ESTADO","OBSERVACION"
]

# Si ESTADO está vacío, lo ponemos en "Pendiente"
df['ESTADO'] = df['ESTADO'].fillna('Pendiente')
df['OBSERVACION'] = df['OBSERVACION'].fillna('')

# Crear base de datos SQLite
engine = create_engine(f"sqlite:///{DB_PATH}")
df.to_sql("dispositivos", engine, index=False, if_exists="replace")

print("✅ Base de datos creada: data.db")
