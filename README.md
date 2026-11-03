# T&S Tecnología y Servicios

Aplicación Flask existente para la presentación corporativa de T&S y la consulta de mantenimiento por cliente. Los CSV continúan siendo la fuente de datos para dispositivos y cámaras.

Plataforma web para gestionar mantenimiento tecnológico y cámaras de seguridad, con inventarios CSV, accesos por rol y paneles para clientes y administradores.

## Funcionalidades

- Sitio público con inicio, servicios, proyectos, contacto y política de privacidad.
- Panel de mantenimiento con indicadores, filtros, búsqueda, gráficas, edición por rol, alta de dispositivos y exportación CSV.
- Inventario de cámaras con filtros, diagramas y estados.
- Consola administrativa para crear, editar, activar, desactivar y eliminar cuentas; consulta de actividad y gestión de mensajes.
- Protección de rutas por rol desde el servidor, tokens CSRF, sesiones endurecidas y contraseñas almacenadas mediante hash.
- Copias automáticas en `instance/backups/` antes de modificar archivos CSV o cuentas.
- Bloqueo de escritura y control de revisiones para detectar ediciones concurrentes y evitar sobrescribir cambios recientes.

## Requisitos

- Python 3.10 o superior.
- Dependencias indicadas en `requirements.txt`.

## Instalar y ejecutar en Windows

Desde PowerShell, en la carpeta del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

La aplicación estará disponible en `http://127.0.0.1:5000`.

En un entorno de producción, configura una clave secreta persistente y HTTPS antes de iniciar el servidor:

```powershell
$env:TS_SECRET_KEY = "<genera una clave aleatoria larga y privada>"
$env:TS_COOKIE_SECURE = "true"
$env:FLASK_DEBUG = "false"
```

La aplicación genera una clave local persistente en `instance/secret_key` si `TS_SECRET_KEY` no está definida. Esa alternativa es para desarrollo local; no uses el servidor integrado de Flask en producción. Utiliza un servidor WSGI, por ejemplo Gunicorn en Linux.

## Cuentas y primer acceso

Las cuentas heredadas se migran a hashes en `instance/users.json`, que no se versiona. En el primer inicio de sesión, el sistema exige cambiar la contraseña por una de al menos 12 caracteres. Las cuentas nuevas también deben cambiar su contraseña inicial al ingresar. El panel nunca devuelve hashes ni contraseñas.

Si `instance/users.json` se elimina, el sistema vuelve a inicializar las cuentas heredadas y solicita cambiar las contraseñas otra vez. Protege esa carpeta y conserva copias de seguridad.

## Datos y copias

- `1/dispositivos1.csv` y `1/dispositivos2.csv`: inventario de dispositivos de los clientes existentes.
- `1/camaras1.csv` y `1/camaras2.csv`: inventario de cámaras.
- `1/dispositivos3.csv`: se conserva sin alterar; actualmente no está asignado a una ruta de cliente.
- `instance/backups/`: respaldos automáticos de los archivos cambiados y de cuentas.
- `cambios_log.json`: registro de actividad de la aplicación.
- `data.db`: archivo existente conservado; la aplicación actual no lo usa como fuente de los inventarios.

Los cambios CSV se escriben de forma atómica. Si el archivo cambió desde que se cargó en el navegador, el sistema avisa y solicita recargar para evitar perder la edición de otra persona.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

## Notas de despliegue

- GitHub Pages solo publica sitios estáticos; para ejecutar Flask y sus funciones de gestión, despliega la aplicación en un servicio compatible con Python/WSGI.
- No publiques archivos `.env`, `instance/`, CSV de clientes ni respaldos.
- Activa `TS_COOKIE_SECURE=true` únicamente cuando el sitio se sirva mediante HTTPS.
- Los clientes y sus rutas CSV se conservan según la configuración existente; para agregar un nuevo cliente hay que asignar sus archivos reales, no se crean datos ficticios.
