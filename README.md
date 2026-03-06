# Proyecto T&S

Aplicacion web en Flask para una landing corporativa y un sistema de gestion de mantenimiento por cliente con control de roles.

## Caracteristicas principales
- Landing page con secciones de inicio, servicios, proyectos, contacto y privacidad.
- Sistema de login por cliente con roles `viewer` y `editor`.
- Panel administrativo para gestion de usuarios, logs y mensajes de contacto.
- Lectura y edicion de dispositivos desde archivos CSV por cliente.
- Registro de cambios y actividad del sistema.

## Tecnologias
- Python
- Flask
- HTML, CSS, JavaScript
- CSV (fuente de datos)

## Estructura
- `app.py`: aplicacion principal Flask y rutas.
- `templates/`: vistas Jinja2 (landing y sistema).
- `static/`: estilos, scripts e imagenes.
- `1/`: archivos CSV de dispositivos por cliente.

## Ejecutar en local
1. Crear y activar entorno virtual (si no existe).
2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Ejecutar:
   ```bash
   python app.py
   ```
4. Abrir:
   - `http://127.0.0.1:5000`
   - `http://127.0.0.1:5000/sistema/login`

## Credenciales de prueba
- Admin: `admin / admin123`
- Bulevar editor: `bulevar / admin`
- Bulevar viewer: `bulevar_view / view123`
- Eden editor: `eden / admin`
- Eden viewer: `eden_view / view123`

## Nota
Este proyecto usa Flask en modo desarrollo (`debug=True`) para pruebas locales.
