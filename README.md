# GTFStoCSV 🚍 → 📋 → 🗺️

**Convierte cualquier archivo GTFS en tablas CSV, GeoJSON, Shapefiles y un visor HTML interactivo con mapa del IGN.**

Herramienta local, 100% Python, sin servidores, sin bases de datos. Diseño corporativo Equipo Kaizen (Ineco).

---

## ⚡ Uso Rápido

```bash
# 1. Clonar o copiar
git clone <repo> && cd GTFStoCSV

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar con cualquier GTFS
python run.py data/mi-gtfs.zip

# 4. Abrir el visor
open output/visor.html   # o doble clic
```

---

## 📦 ¿Qué Genera?

Al ejecutar `python run.py ruta/al/gtfs.zip` obtienes esto en `output/`:

```
output/
├── visor.html              # 🖥️ Visor interactivo con mapa IGN (doble clic)
├── data.json               # 📊 Datos en JSON para el visor
├── todas_las_rutas.geojson # 🌐 Todas las rutas en un GeoJSON
├── todas_las_rutas.shp.zip # 🗺️ Shapefiles para GIS (QGIS, ArcGIS)
└── csv/                    # 📋 Tablas GTFS individuales exportables
    ├── agency.csv
    ├── routes.csv
    ├── trips.csv
    ├── stops.csv
    ├── stop_times.csv
    ├── shapes.csv
    ├── calendar.csv
    ├── calendar_dates.csv
    ├── frequencies.csv
    ├── transfers.csv
    └── feed_info.csv
```

---

## 🖥️ Visor HTML (Sin servidor)

El visor se abre con **doble clic** — no necesita Python, ni Node, ni Docker.

### Funcionalidades

| Función | Cómo |
|---------|------|
| 🗺️ **Mapa IGN** | Capa gris y topográfica del Instituto Geográfico Nacional |
| 🚏 **Rutas clickeables** | Clic en polyline → panel detalle con paradas |
| 📋 **Tablas GTFS** | Acordeones con todas las tablas, 50 primeras filas |
| 📥 **Exportar CSV** | Cada tabla GTFS tiene botón de descarga |
| 🌐 **GeoJSON por ruta** | Descarga individual de cada línea en formato GIS |
| 📋 **CSV Horarios** | Stop times de una ruta específica |
| 🔍 **Búsqueda** | Filtra rutas por nombre en tiempo real |
| 📂 **Drag & drop** | Arrastra otro GTFS .zip directamente al visor |

### Mapa IGN

Usa el servicio WMTS del Instituto Geográfico Nacional:
- **IGNBase-gris** (por defecto) — mapa topográfico en gris, ideal para datos
- **IGNBaseTodo** — mapa topográfico a color
- Licencia **CC BY 4.0** — solo requiere atribución

---

## 🚀 Opciones CLI

```bash
# Directorio de salida personalizado
python run.py data/gtfs.zip -o mis_datos/

# Solo CSV (sin GeoJSON, SHP ni visor)
python run.py data/gtfs.zip --only-csv

# Sin Shapefiles (más rápido, no necesita pyshp)
python run.py data/gtfs.zip --no-shp

# Sin visor HTML
python run.py data/gtfs.zip --no-html

# Ayuda completa
python run.py --help
```

---

## 📋 Formatos de Exportación

### CSV
Cada archivo GTFS se exporta como CSV independiente en `output/csv/`. UTF-8 con BOM para que Excel abra bien los acentos. Compatible con cualquier hoja de cálculo o herramienta de datos.

### GeoJSON
Todas las rutas como **FeatureCollection** en `output/todas_las_rutas.geojson`. Cada ruta incluye:
- `LineString` con las coordenadas del trazado
- Propiedades: nombre, número de viajes, paradas, headsigns, longitud en km
- Array de paradas con coordenadas

Además, desde el visor HTML puedes descargar cada ruta individualmente.

### SHP (Shapefile ZIP)
Requiere `pyshp` (`pip install pyshp`). Genera un ZIP con:
- `.shp` — geometrías (Polyline)
- `.shx` — índice
- `.dbf` — atributos (route_id, short_name, num_trips, etc.)
- `.prj` — proyección WGS84 (EPSG:4326)

Listo para arrastrar a QGIS, ArcGIS, o cualquier GIS.

---

## 🏗️ Estructura del Proyecto

```
GTFStoCSV/
├── run.py                 # 🚀 Entry point — python run.py <gtfs.zip>
├── requirements.txt       # 📦 Dependencias (solo pyshp)
├── README.md              # 📖 Esta guía
├── MAINTENANCE.md         # 🔧 Cómo mantener y modificar el código
├── gtfstocsv/             # 🧠 Módulo principal
│   ├── __init__.py        #   Versión
│   ├── parser.py          #   Parseo GTFS → Python
│   ├── exporter.py        #   Exportación CSV / GeoJSON / SHP
│   └── templater.py       #   Generación visor HTML
├── output/                # 📁 Directorio de salida (se genera solo)
└── data/                  # 📁 Pon aquí tus GTFS .zip
```

---

## 📦 Dependencias

| Librería | ¿Para qué? | ¿Obligatoria? |
|----------|-----------|---------------|
| `pyshp`  | Exportar SHP (shapefiles) | ❌ Opcional — solo si quieres SHP |
| Python 3 stdlib | zipfile, csv, json, math, os | ✅ Ya viene con Python |

```bash
# Mínimo (para CSV + GeoJSON + visor)
# No necesitas instalar nada

# Con SHP
pip install -r requirements.txt
```

---

## 🗂️ ¿Dónde Consigo GTFS?

- **NAP España** (Punto de Acceso Nacional de Transporte): [transportes.gob.es](https://transportes.gob.es/)
- **OpenData EMT Madrid**: [opendata.emtmadrid.es](https://opendata.emtmadrid.es/)
- **TransitFeeds** (archivo): [transitfeeds.com](https://transitfeeds.com/)
- **Mobility Database**: [mobilitydatabase.org](https://mobilitydatabase.org/)
- **GTFS de ejemplo**: La carpeta `data/` puede contener GTFS de demostración

---

## 🎨 Diseño Kaizen

El visor HTML utiliza el **Kaizen Design System v4.0** del Equipo Kaizen (Ineco):

- **Colores oficiales:** Azul #1A4488, Rojo #CB1823
- **Estilo:** Flat corporativo, sin sombras, sin gradientes complejos
- **Tipografía:** Inter (sistema)
- **Componentes:** Sidebar, tabs, badges, tablas, botones, acordeones

---

## ❤️ Hecho por

**David Antizar** — Equipo Kaizen, Ineco

---

## 📄 Licencia

MIT — úsalo, modifícalo, compártelo. Si haces algo chulo, cuéntanoslo :)
