# CONTRIBUTING — GTFStoCSV

Guía para mantener, modificar y extender esta herramienta.
Piensa que no hay nadie del equipo Kaizen disponible — todo tiene que estar claro.

---

## 📋 Índice

1. [Arquitectura general](#1-arquitectura-general)
2. [Cómo añadir una nueva exportación](#2-cómo-añadir-una-nueva-exportación)
3. [Cómo modificar el visor HTML](#3-cómo-modificar-el-visor-html)
4. [Cómo añadir soporte para un nuevo campo GTFS](#4-cómo-añadir-soporte-para-un-nuevo-campo-gtfs)
5. [Cómo funciona el pipeline de datos](#5-cómo-funciona-el-pipeline-de-datos)
6. [Estilo de código](#6-estilo-de-código)
7. [Testing](#7-testing)
8. [Errores comunes](#8-errores-comunes)
9. [Referencia GTFS](#9-referencia-gtfs)

---

## 1. Arquitectura general

```
GTFS ZIP (.zip)
     │
     ▼
┌─────────────────┐
│  parser.py      │ ← Lee ZIP, parsea CSV, construye índices
│  parse_gtfs()   │ → Devuelve dict con TODOS los datos
└────────┬────────┘
         │
         ├──────────────────────┐
         ▼                      ▼
┌─────────────────┐   ┌─────────────────┐
│  exporter.py    │   │  templater.py   │
│  export_all()   │   │ generate_visor()│
│                 │   │                 │
│ → CSV files     │   │ → visor.html    │
│ → GeoJSON files │   │   (standalone)  │
│ → SHP files     │   └─────────────────┘
└─────────────────┘
```

**Regla de oro:** Cada módulo hace UNA cosa y la hace bien.
- `parser.py` solo lee datos
- `exporter.py` solo escribe archivos
- `templater.py` solo genera HTML

### Flujo de datos

1. `parser.parse_gtfs(zip_path)` devuelve un dict con:
   - Tablas: `routes`, `stops`, `trips`, `stop_times`,...
   - Índices: `indexes.trips_by_route`, `indexes.shapes_by_id`,...
   - Estadísticas: `stats.routes_count`, `stats.has_shapes`,...

2. `exporter.export_all(data, dir)` usa ese dict y escribe archivos

3. `templater.generate_visor(data, dir)` serializa el dict a JSON,
   lo embebe en el HTML y genera el visor

**No hay base de datos. No hay servidor. No hay caché.**
Todo vive en RAM durante la ejecución. El HTML generado es autocontenido.

---

## 2. Cómo añadir una nueva exportación

Ejemplo: añadir exportación a **GPX** (formato GPS Exchange).

### Paso 1: Añadir función en `exporter.py`

```python
def export_route_gpx(data: dict, route_id: str, output_path: str) -> str:
    """
    Exporta una ruta a GPX (formato GPS Exchange).
    """
    routes = {r["route_id"]: r for r in data.get("routes", [])}
    route = routes.get(route_id)
    if not route:
        raise ValueError(f"Ruta '{route_id}' no encontrada")

    shape_id = data["indexes"].get("route_shape", {}).get(route_id)
    coords = data["indexes"].get("shapes_by_id", {}).get(shape_id, [])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    gpx = '<?xml version="1.0" encoding="UTF-8"?>\\n'
    gpx += '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">\\n'
    gpx += f'  <trk><name>{route.get("route_short_name", route_id)}</name><trkseg>\\n'
    for lat, lon in coords:
        gpx += f'    <trkpt lat="{lat}" lon="{lon}"></trkpt>\\n'
    gpx += '  </trkseg></trk></gpx>'

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(gpx)
    return output_path
```

### Paso 2: Conectar en `export_all()`

```python
def export_all(data: dict, output_dir: str) -> dict:
    # ... código existente ...
    
    # GPX por ruta
    gpx_dir = os.path.join(output_dir, "gpx")
    os.makedirs(gpx_dir, exist_ok=True)
    result["routes_gpx"] = []
    for route in data.get("routes", []):
        rid = route["route_id"]
        if rid not in data["indexes"].get("route_shape", {}):
            continue
        path = os.path.join(gpx_dir, f"ruta_{rid}.gpx")
        export_route_gpx(data, rid, path)
        result["routes_gpx"].append({"route_id": rid, "path": path})
    
    return result
```

### Paso 3: Añadir flag CLI en `run.py`

```python
parser.add_argument("--export-gpx", action="store_true", help="Exportar rutas a GPX")

# En main():
if args.export_gpx or args.export_all:
    from gtfstocsv.exporter import export_all_routes_gpx
    gpx_dir = os.path.join(export_dir, "gpx")
    gpxs = export_all_routes_gpx(data, gpx_dir)
    print(f"   ✅ GPX: {len(gpxs)} archivos en {gpx_dir}/")
```

### Paso 4: Añadir botón en el visor HTML (`templater.py`)

Busca la sección "export-btn-group" o la toolbar de GeoJSON y añade:

```javascript
function exportRouteGPX(routeId) {
    // Lógica para generar GPX desde los datos embebidos
    const data = window.GTFS_DATA;
    // ... construir GPX ...
    const blob = new Blob([gpx], { type: 'application/gpx+xml' });
    saveAs(blob, `ruta_${routeId}.gpx`);
}
```

---

## 3. Cómo modificar el visor HTML

El visor HTML se genera en `templater.py` dentro de la función `_build_html()`.

### ¿Dónde está cada cosa?

| Sección | Localización en `_build_html()` |
|---------|-------------------------------|
| CSS Kaizen | Variable `_MINIMAL_KAIZEN_CSS` |
| Header (logo, botones) | `<header class="kz-header">` |
| Banner azul | `<div class="kz-banner">` |
| Sidebar stats | Tras `<aside class="kz-sidebar">` |
| Lista de rutas | `renderRouteList()` en JS |
| Mapa Leaflet | `initMap()` y `drawRoutes()` en JS |
| Tablas de datos | Secciones `kz-section` con IDs |
| Botones exportación | Toolbars con clase `kz-toolbar` |
| Datos embebidos | `window.GTFS_DATA = {...}` en `<script>` |

### Cómo modificar el diseño

Los colores y estilos están en la variable `_MINIMAL_KAIZEN_CSS` al inicio de `templater.py`.

**Colores oficiales Kaizen:**
- Azul: `#1A4488`
- Rojo: `#CB1823`
- Azul medio: `#3463AC`
- Azul claro: `#6B96CF`

**NO uses** gradientes complejos, sombras, bordes gruesos ni colores fuera de la paleta.
El estilo es **flat**, limpio, corporativo.

### Cómo añadir una tabla nueva

1. Busca la sección de tablas en `_build_html()` (después de `<!-- TABLAS (scrollable) -->`)
2. Añade un nuevo bloque siguiendo el patrón:

```html
<div class="kz-section" id="mi-tabla-table">
  <div class="kz-section-title">📊 Mi Tabla <span>...</span></div>
  <div class="kz-toolbar">
    <span class="kz-toolbar-label">Exportar:</span>
    <button class="kz-btn kz-btn-primary kz-btn-sm" onclick="exportTableCSV('mi_tabla')">📥 CSV</button>
  </div>
  <div class="table-wrapper">
    <table class="kz-table"><thead><tr id="miTablaHeader"></tr></thead><tbody id="miTablaBody"></tbody></table>
  </div>
</div>
```

3. Añade la referencia en el sidebar:
```html
<div class="kz-sidebar-item" onclick="scrollToTable('mi-tabla-table')">📊 Mi Tabla (N)</div>
```

4. Añade la función de render en JavaScript:
```javascript
renderMiTabla(); // Y añadir al init()
```

### Cómo cambiar el mapa base

En `initMap()`, dentro de `window.baseLayers`, puedes añadir o quitar capas:

```javascript
'gris': L.tileLayer('https://www.ign.es/wmts/ign-base?...', {...}),
'topo': L.tileLayer('https://www.ign.es/wmts/ign-base?...', {...}),
'orto': L.tileLayer('https://www.ign.es/wmts/ign-base?...', {...}),
'carto': L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/...', {...}),
```

**Importante:** Las tiles del IGN requieren `FORMAT=image/jpeg` en la URL. Sin esto, devuelven error 400.

---

## 4. Cómo añadir soporte para un nuevo campo GTFS

El estándar GTFS permite campos extendidos (por ejemplo, `route_brand`, `stop_timezone`, etc.).

### Si el campo ya existe en el archivo pero no se muestra:

Solo tienes que añadirlo al visor en `templater.py`. Las tablas se renderizan automáticamente con `Object.keys(data[0])` — es decir, **se muestran todos los campos que tenga cada fila**. No necesitas hacer nada en el parser.

### Si quieres normalizar un campo (como se hace con `route_color`):

Añade una línea en la función de parseo correspondiente en `parser.py`:

```python
def _parse_routes(rows):
    for r in rows:
        # ... código existente ...
        # Añadir: normalizar un nuevo campo
        r["route_brand_clean"] = r.get("route_brand", "").strip().upper()
    return rows
```

### Si quieres añadir un índice nuevo:

En `_build_indexes()`:

```python
# Ejemplo: paradas por zona
stops_by_zone = defaultdict(list)
for s in data.get("stops", []):
    zone = s.get("zone_id", "sin-zona")
    stops_by_zone[zone].append(s["stop_id"])
indexes["stops_by_zone"] = dict(stops_by_zone)
```

### Si quieres parsear un archivo GTFS opcional que no está contemplado:

1. Añade el nombre del archivo en `parse_gtfs()`:
```python
data["nuevo_archivo"] = _read_csv_from_zip(z, "nuevo_archivo.txt")
```

2. Añade su contador en `stats`:
```python
"nuevo_archivo_count": len(data["nuevo_archivo"]),
```

---

## 5. Cómo funciona el pipeline de datos

```
ZIP → _read_csv_from_zip() → _parse_csv() → list[dict]
                                                    │
                              ┌─────────────────────┤
                              ▼                     ▼
                      _parse_stops()         _parse_routes()
                      _parse_trips()         _parse_shapes()
                      _parse_stop_times()
                              │                     │
                              ▼                     ▼
                      Tablas limpias         Tablas limpias
                              │                     │
                              └─────┬──────────────┘
                                    ▼
                            _build_indexes()
                                    │
                                    ▼
                            Dict final con:
                            - Tablas (listas de dicts)
                            - Índices (dicts de relaciones)
                            - Stats (dict de resumen)
```

### CSV auto-detección de delimiter

El parser detecta automáticamente si el CSV usa `,`, `\\t` (tab) o `;`.
Esto es importante porque algunos GTFS de España usan tabuladores.

```python
def _detect_delimiter(header_line):
    comma = header_line.count(",")
    tab = header_line.count("\\t")
    semi = header_line.count(";")
    if tab > comma and tab > semi: return "\\t"
    if semi > comma: return ";"
    return ","
```

### Encoding

El parser prueba: `utf-8-sig` → `utf-8` → `latin-1` → `cp1252`.
Si todo falla, usa `utf-8` con reemplazo de caracteres.

---

## 6. Estilo de código

### Python

- Python 3.10+ (sin dependencias externas para el core)
- Nombres de funciones: `snake_case`
- Nombres de clases: `PascalCase`
- 4 espacios de indentación
- Docstrings en todas las funciones públicas
- Type hints donde sea legible
- Módulos de menos de 200 líneas (si se pasa, refactorizar)
- NO usar `eval()`, `exec()` ni `__import__` dinámico

### HTML/JavaScript (dentro de templater.py)

- El HTML se genera como un string Python multilínea (f-string)
- **Escapar variables**: usar `html.escape()` o `json.dumps()` para datos
- El JavaScript usa ES6+ (arrow functions, template literals)
- NO usar jQuery
- NO usar bibliotecas JS externas excepto Leaflet y FileSaver (vía CDN)
- Las funciones JS usan `camelCase`

### Estructura de ficheros

```
gtfstocsv/
├── __init__.py     → Versión + nada más
├── parser.py       → Solo parseo (máx 300 líneas)
├── exporter.py     → Solo exportación (máx 300 líneas)
└── templater.py    → Solo generación HTML (máx 600 líneas)
```

---

## 7. Testing

No hay tests automatizados (por ahora). Para probar cambios:

### Parseo
```bash
python -m gtfstocsv.parser data/mi-gtfs.zip
# Debe mostrar estadísticas sin errores
```

### Exportación
```bash
python -m gtfstocsv.exporter data/mi-gtfs.zip output_test/
# Debe generar archivos CSV, GeoJSON, SHP en output_test/
```

### Visor HTML
```bash
python -m gtfstocsv.templater data/mi-gtfs.zip output_test/
# Abrir output_test/visor.html en navegador
# Comprobar: mapa cargado, rutas visibles, tablas renderizadas,
#            botones de exportación funcionan
```

### Regresión
Siempre probar con al menos 2 GTFS diferentes (uno pequeño y uno grande).

---

## 8. Errores comunes

### "El mapa no se ve"

1. ¿Tienes conexión a Internet? (Leaflet y los tiles IGN requieren CDN)
2. Abre la consola del navegador (F12) y mira si hay errores
3. El mapa necesita que `window.GTFS_DATA` tenga datos
4. `initMap()` debe llamarse después de que el DOM cargue

### "No se ven rutas en el mapa"

Causas posibles:
1. El GTFS no tiene `shapes.txt` → no hay trazados que dibujar
2. `route_shape` no se construyó → los trips no tienen `shape_id`
3. Las coordenadas están mal → revisar `_parse_shapes()`

### "Los CSV se descargan con caracteres raros"

El encoding es UTF-8 BOM (`\\uFEFF`). Asegúrate de que el navegador está en UTF-8.
Si abres con Excel: usar "Datos → Desde Texto/CSV" y elegir UTF-8.

### "El archivo ZIP no se abre"

```python
# Probar manualmente
import zipfile
with zipfile.ZipFile("archivo.zip") as z:
    print(z.namelist())  # ¿Están los archivos en la raíz?
```

### "No funciona con doble clic en el HTML"

El visor HTML necesita Internet para cargar Leaflet y las tiles IGN desde CDN.
Para uso sin conexión, servir localmente:
```bash
cd output/ && python3 -m http.server 8080
# Abrir http://localhost:8080/visor.html
```

---

## 9. Referencia GTFS

### Especificación oficial

https://gtfs.org/documentation/schedule/reference/

### Archivos del estándar

| Archivo | ¿Requerido? | Descripción |
|---------|-------------|-------------|
| `agency.txt` | ✅ | Agencias de transporte |
| `routes.txt` | ✅ | Rutas/líneas |
| `trips.txt` | ✅ | Viajes/servicios |
| `stop_times.txt` | ✅ | Horarios por parada |
| `stops.txt` | ✅ | Paradas con coordenadas |
| `calendar.txt` | ⚠️ Condicional | Calendarios (si no hay calendar_dates) |
| `calendar_dates.txt` | Opcional | Excepciones |
| `shapes.txt` | Opcional | Trazados geográficos |
| `frequencies.txt` | Opcional | Frecuencias |
| `transfers.txt` | Opcional | Transbordos |
| `feed_info.txt` | Opcional | Metadatos |
| `attributions.txt` | Opcional | Atribuciones |
| `translations.txt` | Opcional | Traducciones |
| `pathways.txt` | Opcional | Accesibilidad |
| `levels.txt` | Opcional | Niveles |

### Convenciones de parseo en este proyecto

- **route_color**: se normaliza a HEX con `#` (ej: `"1A4488"` → `"#1A4488"`)
- **stop_lat/stop_lon**: se convierten a float
- **stop_sequence**: se convierte a int
- **shape_pt_lat/shape_pt_lon**: se convierten a float
- **shape_pt_sequence**: se convierte a int
- **route_type**: se convierte a int
- **IDs**: todos a string (algunos GTFS usan IDs numéricos)
- **Campos vacíos**: se mantienen como string vacío `""`

---

*Hecho con ❤️ por David Antizar — Equipo Kaizen, Ineco*
*Si algo no está claro, abre un issue en github.com/Ntizar/GTFStoCSV*