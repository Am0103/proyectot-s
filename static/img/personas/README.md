# Fotos de Personas

Esta carpeta contiene las fotos de empleados, clientes y personas relacionadas con el proyecto T&S.

## Estructura recomendada:
- `empleados/`: Fotos del equipo de trabajo
- `clientes/`: Fotos de clientes o representantes
- `otros/`: Otras fotos relevantes

## Formatos soportados:
- JPG
- PNG
- GIF

## Nombres de archivos:
Usar nombres descriptivos como:
- `juan_perez_tecnico.jpg`
- `cliente_empresa_xyz.png`

## Uso en la aplicación:
Las fotos pueden ser referenciadas desde los templates usando:
```
{{ url_for('static', filename='img/personas/empleados/juan_perez.jpg') }}
```