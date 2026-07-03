# 🔧 GTFStoCSV — Documento de Mantenimiento

**Para que cualquier persona del equipo (o un agente IA) pueda entender, modificar y arreglar la herramienta.**

---

## 📋 Índice

1. [Arquitectura General](#1-arquitectura-general)
2. [Árbol de Archivos](#2-árbol-de-archivos)
3. [Módulo parser.py](#3-módulo-parserpy)
4. [Módulo exporter.py](#4-módulo-exporterpy)
5. [Módulo templater.py](#5-módulo-templaterpy)
6. [Entry Point run.py](#6-entry-point-runpy)
7. [El Visor HTML](#7-el-visor-html)
8. [Errores Comunes](#8-errores-comunes)
9. [Añadir una Nueva Funcionalidad](#9-añadir-una-nueva-funcionalidad)
10. [Reglas de Estilo y Convenciones](#10-reglas-de-estilo-y-convenciones)
11. [Checklist de Debug Rápido](#11-checklist-de-debug-rápido)

---

## 1. Arquitectura General

```
GTFS.zip ──► parser.py ──► dicts de datos ──► exporter.py ──► CSV / GeoJSON / SHP
                                                └──► templater.py ──► visor.html + data.json
```

**Flujo de datos:**

1. `parser.py` descomprime el ZIP, lee cada `.txt` como CSV, y los guarda en listas de diccionarios.
2. Construye índices (stops_by_id, trips_by_route, shapes_coords...) para acceso rápido.
3. `exporter.py` toma esos datos y escribe archivos en disco.
4. `templater.py` empaqueta los datos en `data.json` y genera un `visor.html` autocontenido.

**Principio de diseño:** Cada módulo hace una cosa. parser NO escribe archivos. exporter NO parsea. templater NO exporta CSVs.

---

## 2. Árbol de Archivos

```
GTFStoCSV/
├── run.py                 # Entry point CLI — llama a parser → exporter → templater
├── requirements.txt       # pyshp (opcional)
├── README.md              # Documentación de uso
├── MAINTENANCE.md         # ← Este documento
├── gtfstocsv/
│   ├── __init__.py        # Solo __version__
│   ├── parser.py          # ~250 líneas — parseo GTFS
│   ├── exporter.py        # ~300 líneas — exportación a formatos
│   └── templater.py       # ~900 líneas — generación visor HTML
├── output/                # Se genera solo al ejecutar
└── data/                  # Pon aquí los GTFS .zip
```

### ¿Qué hace cada archivo?

| Archivo | Responsabilidad | Complejidad |
|---------|----------------|-------------|
| `run.py` | CLI, orquestación | 🟢 Fácil |
| `parser.py` | Parseo GTFS + índices | 🟡 Media |
| `exporter.py` | Escribir CSVs, GeoJSON, SHP | 🟡 Media |
| `templater.py` | Generar HTML + data.json | 🔴 Alta |
| `visor.html` (generado) | Visor interactivo en navegador | 🔴 Alta (JS) |

---

## 3. Módulo `parser.py`

### Clase principal: `GTFSParser`

```python
parser = GTFSParser("ruta/gtfs.zip")
parser.parse()

# Datos disponibles (listas de dicts)
parser.agency         # agencias
parser.routes         # rutas
parser.trips          # viajes (cada viaje = un recorrido)
parser.stop_times     # horarios por parada (el archivo más grande)
parser.stops          # paradas con coordenadas
parser.shapes         # puntos de trazado de rutas
parser.calendar       # calendarios semanales
parser.calendar_dates # excepciones de calendario
parser.frequencies    # frecuencias por tramo horario
parser.transfers      # transbordos entre paradas
parser.feed_info      # metadatos del feed

# Índices (diccionarios)
parser.stops_by_id            # stop_id → dict
parser.routes_by_id           # route_id → dict
parser.trips_by_route         # route_id → list[dict]
parser.stop_times_by_trip     # trip_id → list[dict]
parser.shapes_coords          # shape_id → list[(lat, lng)]
parser.calendar_by_service    # service_id → dict
parser.calendar_dates_by_service  # service_id → list[dict]

# Métodos útiles
parser.summary_text()                       # resumen legible
parser.get_route_shape(route_id)            # list[(lat, lng)]
parser.get_route_stops_ordered(route_id)    # list[dict] paradas ordenadas
```

### Para añadir un nuevo archivo GTFS

Si aparece un nuevo archivo opcional en el estándar GTFS (ej: `rideshare.txt`):

1. Añadir `"rideshare"` a `ARCHIVOS_GTFS` (lista global)
2. El parser lo leerá automáticamente → `parser.rideshare`
3. Si necesitas un índice, añádelo en `build_indexes()`

### Pitfalls conocidos

- **CSV delimiter:** Algunos GTFS usan tabulador (`\t`) o punto y coma (`;`). `csv.DictReader` de Python lo detecta automáticamente porque lee el header primero, pero hay que asegurarse de que el archivo se abre con `utf-8-sig` (BOM).
- **Archivos enormes:** `stop_times.txt` puede tener millones de líneas. Se carga completo en RAM. Para GTFS de país entero (>500 MB), considerar chunking.
- **Coordenadas 0,0:** Algunas paradas tienen lat=0, lon=0 (datos incorrectos). El visor HTML las filtra automáticamente.
- **calendar_dates sin calendar:** Algunos feeds (ej: EMT Fuenlabrada) no tienen `calendar.txt`, solo `calendar_dates.txt`. El parser lo maneja — `parser.calendar` será `[]` pero `parser.calendar_dates` tendrá datos.

---

## 4. Módulo `exporter.py`

### Funciones disponibles

```python
# CSV de cualquier tabla
export_csv(data: list[dict], output_path: str) -> None

# GeoJSON de una ruta (Feature individual)
export_geojson(parser, route_id, output_path) -> None

# GeoJSON de todas las rutas (FeatureCollection)
export_all_geojson(parser, output_dir) -> str  # devuelve ruta

# SHP de todas las rutas (ZIP con .shp/.shx/.dbf/.prj)
export_shp_zip(parser, output_path) -> str | None

# Feature GeoJSON para una ruta (útil para composición)
export_geojson_feature(parser, route_id) -> dict

# Todas las tablas GTFS como CSV individual
export_table_summary(parser, output_dir) -> list[str]
```

### Para añadir un nuevo formato de exportación

1. Crea una función en `exporter.py` que reciba `parser` y `output_path`
2. Si necesita una librería externa, añádela a `requirements.txt`
3. Llama a la función desde `run.py`

### Exportación SHP

SHP usa `pyshp` (shapefile). Detalles técnicos:
- Tipo: `POLYLINE` (cada ruta es una polyline)
- Atributos: route_id, short_name, long_name, route_type, num_trips, num_stops, color
- Proyección: WGS84 (EPSG:4326) — el `.prj` se genera con el string WKT correcto
- Se comprime todo en ZIP porque SHP son múltiples archivos

Si `pyshp` no está instalado, la función devuelve `None` sin error.

---

## 5. Módulo `templater.py`

### Estructura

```python
generar_visor(parser, output_dir) -> str  # devuelve ruta al HTML
```

Internamente llama a:
- `_build_data_json(parser)` → construye `data.json` optimizado para el visor
- `_build_html(parser)` → genera el HTML completo (~500 líneas de HTML + CSS + JS)
- `_get_kaizen_css()` → lee `kaizen.css` del disco o devuelve fallback

### data.json — Estructura

```json
{
  "meta": {
    "filename": "emt-madrid.zip",
    "agency": ["EMT Madrid"],
    "publisher": "EMT Madrid",
    "version": "2026-07"
  },
  "routes": [
    {
      "id": "101",
      "short_name": "101",
      "long_name": "Plaza de Castilla - Avenida de la Ilustración",
      "type": "3",
      "color": "1A4488",
      "text_color": "FFFFFF",
      "num_trips": 24,
      "num_stops": 15,
      "headsigns": ["Plaza de Castilla", "Avda. Ilustración"],
      "shape_km": 12.5,
      "has_shape": true
    }
  ],
  "stops": [
    {
      "id": "1234",
      "name": "Plaza de Castilla",
      "lat": 40.4667,
      "lon": -3.6891,
      "code": "1234"
    }
  ],
  "shapes": {
    "shape_001": [[40.4667, -3.6891], [40.4670, -3.6895], ...]
  },
  "route_shape_map": {
    "101": "shape_001"
  }
}
```

### Para modificar el visor HTML

El HTML se genera como un string gigante en `_build_html()`. Para cambios:

1. **CSS:** Modifica la variable `kaizen_css` al inicio de `_build_html()`, o mejor, modifica `_get_kaizen_css()` que lee el `kaizen.css` real.
2. **JavaScript:** El visor JS está dentro del HTML generado. Búscalo por los comentarios `// VISOR GTFS — JavaScript`.
3. **Estructura HTML:** La plantilla usa f-strings de Python. Ten cuidado con las llaves `{}` — en f-strings se escapan como `{{}}`.

### Reglas de escaping en templater.py

⚠️ **CRÍTICO:** El HTML se genera con f-strings de Python. Las llaves literales en JavaScript/CSS deben escaparse como `{{` y `}}`.

```python
# MAL — Python interpreta {} como placeholder
f"map.fitBounds({coords})"

# BIEN — llaves escapadas
f"map.fitBounds({{coords}})"
```

### Para cambiar el mapa base

El mapa usa IGN WMTS. Para cambiar a OpenStreetMap u otro:

```python
# En _build_html(), busca ignGris e ignTopo
# Cambia la URL del tile layer
const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors'
});
```

### Para añadir una capa al mapa (ej: GBFS bicis)

1. Añade un toggle button en el HTML
2. Añade JS para cargar y mostrar la capa
3. Conecta el toggle con la capa

---

## 6. Entry Point `run.py`

```bash
python run.py data/gtfs.zip -o output/ --no-shp
```

### Flujo interno

```
1. Parsear argumentos (argparse)
2. Validar que el ZIP existe
3. GTFSParser(zip).parse()
4. Mostrar resumen en terminal
5. export_table_summary()   → CSV
6. export_all_geojson()     → GeoJSON
7. export_shp_zip()         → SHP (si no --no-shp)
8. generar_visor()          → HTML + data.json
9. Mostrar resumen final
```

### Para añadir una opción CLI

1. Añade el argumento en `argparse`
2. Añade la lógica condicional en el flujo principal
3. Añade el flag en el resumen final

---

## 7. El Visor HTML

El visor es un HTML **autocontenido** que funciona sin servidor. Aquí está cómo funciona el JavaScript:

### Archivos que carga

| Recurso | CDN | Propósito |
|---------|-----|-----------|
| Leaflet CSS | unpkg | Estilos del mapa |
| Leaflet JS | unpkg | Biblioteca de mapas |
| JSZip | cdnjs | Descompresión ZIP en navegador |

### Estado global

```javascript
let map;                      // Instancia de Leaflet
let allRoutes = [];           // Rutas del GTFS
let allStops = [];            // Paradas con coordenadas
let allShapes = {};           // shape_id → [[lat,lng], ...]
let routeShapeMap = {};       // route_id → shape_id
let highlightLayer = null;    // Polyline resaltada
let activeRouteId = null;     // Ruta activa en panel
window._rawData = {};         // Datos crudos (todas las tablas GTFS)
window._routesData = [];      // Rutas procesadas (para export CSV)
```

### Funciones principales

| Función | Trigger | Qué hace |
|---------|---------|----------|
| `initMap()` | Al cargar | Crea mapa Leaflet con IGN |
| `loadGTFSZip(file)` | Dropzone | Descomprime ZIP, parsea, renderiza |
| `parseGTFSZip(zip)` | loadGTFSZip | Parsea todos los .txt del ZIP |
| `renderAll(data)` | Tras parseo | Renderiza rutas, paradas, tablas |
| `openRoute(routeId)` | Click ruta | Abre panel detalle + highlight en mapa |
| `closeRoutePanel()` | Click mapa/cerrar | Cierra panel + limpia highlight |
| `filterRoutes(query)` | Input búsqueda | Filtra lista de rutas |
| `exportTableCSV(data, name)` | Botón CSV | Descarga tabla como CSV |
| `downloadRouteGeoJSON(id)` | Botón 🌐 | Descarga ruta como GeoJSON |
| `downloadRouteCSV(id)` | Botón 📋 | Descarga horarios como CSV |
| `showToast(msg)` | Varios | Notificación toast |

### Carga de datos: orden de prioridad

1. **data.json** (pre-generado por Python) — se carga al iniciar vía `fetch('data.json')`
2. **Drag & drop** — el usuario arrastra un ZIP y se parsea en el navegador (con JSZip)

---

## 8. Errores Comunes

### 🔴 "No module named 'shapefile'"

```bash
pip install pyshp
# O usa --no-shp para omitir SHP
```

### 🔴 El visor.html no carga el mapa

**Causa:** El visor necesita conexión a internet para cargar Leaflet y JSZip de las CDNs.

**Solución:** Abre el visor con conexión a internet. O descarga las librerías localmente y cambia los `<script src>` a rutas locales.

### 🔴 "data.json not found"

El visor busca `data.json` en el mismo directorio. Si abres `visor.html` desde otro sitio o renombras archivos, no lo encuentra. **Solución:** Abre `visor.html` desde `output/`.

### 🔴 El GTFS no se parsea bien

**Síntoma:** Paradas sin nombre, rutas sin color, "0 paradas" en todas las rutas.

**Posibles causas:**
1. **Delimitador raro:** Algunos GTFS usan `;` o `\t`. Python `csv.DictReader` lo detecta automáticamente.
2. **Encoding:** El parser usa `utf-8-sig` (BOM). Si el archivo está en Windows-1252, se leerán caracteres raros pero los datos se mantienen.
3. **Archivos obligatorios ausentes:** Un GTFS válido necesita al menos `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`. Si falta alguno, el parser no falla pero los datos estarán incompletos.

### 🔴 El HTML generado no muestra los datos

**Causa:** El visor intenta cargar `data.json` con `fetch('data.json')`. Si abres el HTML con `file://` y hay políticas CORS estrictas, puede fallar.

**Solución:** Usar el flag `--no-html` y servir con `python -m http.server` (solo en casos extremos, normalmente funciona bien con `file://`).

---

## 9. Añadir una Nueva Funcionalidad

### Ejemplo: Añadir exportación a Excel (.xlsx)

**Paso 1:** Añadir dependencia
```bash
# requirements.txt
openpyxl>=3.1.0
```

**Paso 2:** Crear función en `exporter.py`
```python
def export_excel(parser, output_path: str):
    import openpyxl
    wb = openpyxl.Workbook()
    for archivo in ARCHIVOS_GTFS:
        data = getattr(parser, archivo, [])
        if not data:
            continue
        ws = wb.create_sheet(title=archivo)
        if data:
            headers = list(data[0].keys())
            ws.append(headers)
            for row in data:
                ws.append([row.get(h, "") for h in headers])
    wb.save(output_path)
```

**Paso 3:** Añadir a `run.py`
```python
# Después de export_table_summary
if not args.only_csv:
    export_excel(parser, os.path.join(args.output, "gtfs_completo.xlsx"))
```

### Ejemplo: Mostrar paradas cercanas en el mapa

**Paso 1:** Añadir un input de coordenadas en el HTML
**Paso 2:** Añadir función Haversine en JS
**Paso 3:** Filtrar y mostrar paradas dentro del radio

---

## 10. Reglas de Estilo y Convenciones

### Python

- **Nombres:** `snake_case` para variables y funciones, `CamelCase` para clases
- **Docstrings:** Siempre en cada función pública (triple comillas)
- **Errores:** Usar excepciones específicas (`FileNotFoundError`, `ValueError`)
- **Print vs log:** Usar `print()` con emojis para feedback visual en CLI

### HTML/CSS

- El CSS se genera inline en el HTML (no hay archivo separado)
- Los estilos del visor usan **variables Kaizen** (`--kz-*`)
- El Kaizen CSS (completo) se incluye inline al inicio
- JavaScript al final del `<body>`

### Convenciones del visor JS

- Variables globales declaradas con `let` (no `var`)
- Funciones anidadas cuando tienen sentido de contexto
- Preferir `async/await` sobre promesas encadenadas
- Emojis para feedback visual (✅, ❌, ⚠️, ℹ️)

---

## 11. Checklist de Debug Rápido

Cuando algo no funciona, sigue esta checklist:

- [ ] ¿El GTFS ZIP no está corrupto? → `unzip -t archivo.zip`
- [ ] ¿Python 3.8+? → `python3 --version`
- [ ] ¿pyshp instalado? (solo si usas SHP) → `pip list | grep pyshp`
- [ ] ¿El visor tiene conexión a internet? (Leaflet CDN)
- [ ] ¿Abriste `output/visor.html` (no el de la raíz)?
- [ ] ¿El `data.json` se generó? → `ls -la output/data.json`
- [ ] ¿El GTFS tiene shapes? → Busca `shapes.txt` dentro del ZIP
- [ ] ¿Las paradas tienen coordenadas válidas? → Revisa primeras filas de stops.txt
- [ ] ¿El mapa muestra algo? → Prueba con otro GTFS conocido

### 🐛 Bugs conocidos

| Bug | Estado | Workaround |
|-----|--------|------------|
| GTFS con `\t` en vez de `,` | Ya resuelto en parser.py | — |
| Paradas con lat=0, lon=0 | Filtradas en data.json | — |
| Visor no funciona sin internet | No resuelto (usa CDNs) | Descargar Leaflet/JSZip local |
| GTFS >500MB en visor drag&drop | Lento en navegador | Usar parseo Python |

---

## 📎 Referencias

- **Estándar GTFS:** [gtfs.org](https://gtfs.org/)
- **IGN WMTS:** [scne.es](https://www.scne.es/)
- **Leaflet:** [leafletjs.com](https://leafletjs.com/)
- **JSZip:** [stuk.github.io/jszip](https://stuk.github.io/jszip/)
- **pyshp:** [pypi.org/project/pyshp](https://pypi.org/project/pyshp/)
- **Kaizen Design System:** `github.com/Ntizar/kaizen-design-system`

---

*Documento generado el 2026-07-03. Mantenido por el Equipo Kaizen — Ineco.*