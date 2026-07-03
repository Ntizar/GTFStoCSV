"""gtfstocsv/templater.py — Genera el visor HTML con Kaizen + Leaflet + IGN.

El visor es un HTML autocontenido que:
  - Incluye el Kaizen Design System CSS (inline)
  - Carga Leaflet + IGN WMTS para el mapa
  - Muestra rutas como polylines clickeables
  - Panel de ruta detallado con paradas y horarios
  - Tablas exportables a CSV (cada tabla GTFS)
  - Botones de descarga GeoJSON/SHP por ruta
  - Soporta carga directa de GTFS vía drag & drop

Uso:
    from gtfstocsv.templater import generar_visor
    generar_visor(parser, output_dir="output")
"""

import json
import os
import math


def generar_visor(parser, output_dir: str) -> str:
    """Genera el visor HTML con los datos del parser.

    Args:
        parser: Instancia de GTFSParser ya parseada
        output_dir: Directorio donde generar los archivos

    Returns:
        Ruta al archivo visor.html generado
    """
    os.makedirs(output_dir, exist_ok=True)

    # Generar data.json compacto para el visor
    data = _build_data_json(parser)
    data_path = os.path.join(output_dir, "data.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Generar el HTML
    html = _build_html(parser)
    html_path = os.path.join(output_dir, "visor.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ Visor HTML: {html_path}")
    print(f"  ✅ Datos JSON: {data_path}")
    return html_path


def _build_data_json(parser):
    """Construye el JSON de datos para el visor (estructura optimizada)."""
    data = {
        "meta": {
            "filename": parser.filename,
            "agency": [a.get("agency_name", "") for a in parser.agency] if parser.agency else [],
            "publisher": parser.feed_info[0].get("feed_publisher_name", "") if parser.feed_info else "",
            "version": parser.feed_info[0].get("feed_version", "") if parser.feed_info else "",
        },
        "routes": [],
        "stops": [],
        "shapes": {},
    }

    # Rutas con resumen
    for r in parser.routes:
        rid = r["route_id"]
        trips = parser.trips_by_route.get(rid, [])
        stops = parser.get_route_stops_ordered(rid)
        coords = parser.get_route_shape(rid)
        headsigns = set()
        for t in trips:
            hs = t.get("trip_headsign", "").strip()
            if hs:
                headsigns.add(hs)

        data["routes"].append({
            "id": rid,
            "short_name": r.get("route_short_name", ""),
            "long_name": r.get("route_long_name", ""),
            "type": r.get("route_type", ""),
            "color": r.get("route_color", ""),
            "text_color": r.get("route_text_color", ""),
            "agency_id": r.get("agency_id", ""),
            "num_trips": len(trips),
            "num_stops": len(stops),
            "headsigns": list(headsigns),
            "shape_km": _calc_length(coords),
            "has_shape": len(coords) > 0,
        })

    # Paradas con coordenadas
    for s in parser.stops:
        try:
            lat = float(s.get("stop_lat", 0))
            lon = float(s.get("stop_lon", 0))
        except (ValueError, TypeError):
            continue
        if lat == 0 and lon == 0:
            continue
        data["stops"].append({
            "id": s.get("stop_id", ""),
            "name": s.get("stop_name", ""),
            "lat": lat,
            "lon": lon,
            "code": s.get("stop_code", ""),
        })

    # Shapes (coordenadas compactas)
    for shape_id, coords in parser.shapes_coords.items():
        data["shapes"][shape_id] = [[lat, lng] for lat, lng in coords]

    # Mapa route_id -> shape_id (del primer trip de cada ruta)
    route_shape_map = {}
    for r in parser.routes:
        rid = r["route_id"]
        trips = parser.trips_by_route.get(rid, [])
        for t in trips:
            sid = t.get("shape_id", "")
            if sid and sid in data["shapes"]:
                route_shape_map[rid] = sid
                break

    data["route_shape_map"] = route_shape_map

    return data


def _build_html(parser):
    """Construye el HTML completo del visor."""
    data_summary = parser.summary_text()

    kaizen_css = _get_kaizen_css()
    visor_js = _get_visor_js()

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GTFStoCSV — Visor GTFS</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
<style>
{kaizen_css}
/* Estilos adicionales del visor */
:root {{ --header-h: 60px; --sidebar-w: 380px; }}
body {{ font-family: var(--kz-font); background: var(--kz-gris-50); }}
#header {{ position: fixed; top: 0; left: 0; right: 0; height: var(--header-h);
  background: var(--kz-azul); color: white; z-index: 2000;
  display: flex; align-items: center; padding: 0 20px; gap: 16px; }}
#header h1 {{ font-size: var(--kz-text-lg); font-weight: 600; }}
#header .subtitle {{ font-size: var(--kz-text-sm); opacity: 0.8; }}
#header .kz-badge {{ margin-left: auto; }}
#sidebar {{ position: fixed; top: var(--header-h); left: 0; bottom: 0;
  width: var(--sidebar-w); background: white; border-right: 1px solid var(--kz-gris-300);
  z-index: 1000; overflow-y: auto; display: flex; flex-direction: column; }}
.sidebar-scroll {{ flex: 1; overflow-y: auto; padding: 12px; }}
#map {{ position: fixed; top: var(--header-h); left: var(--sidebar-w); right: 0; bottom: 0; z-index: 500; }}
.dropzone {{ border: 2px dashed var(--kz-azul-claro); border-radius: var(--kz-radius-lg);
  padding: 20px; text-align: center; margin: 8px 0; cursor: pointer;
  transition: all .2s; background: var(--kz-azul-50); }}
.dropzone:hover {{ border-color: var(--kz-azul); background: var(--kz-azul-100); }}
.dropzone.dragover {{ border-color: var(--kz-azul); background: var(--kz-azul-100); transform: scale(1.01); }}
.dropzone-icon {{ font-size: 2rem; }}
.dropzone-text {{ font-size: var(--kz-text-sm); color: var(--kz-gris-600); }}
#stats-bar {{ display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0; }}
.stat-chip {{ background: var(--kz-azul-50); color: var(--kz-azul); padding: 4px 10px;
  border-radius: 20px; font-size: var(--kz-text-xs); font-weight: 500; }}
.route-item {{ display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-bottom: 1px solid var(--kz-gris-100); cursor: pointer;
  transition: background .15s; border-radius: var(--kz-radius-sm); }}
.route-item:hover {{ background: var(--kz-azul-50); }}
.route-item.active {{ background: var(--kz-azul-100); }}
.route-badge {{ width: 20px; height: 20px; border-radius: 4px; display: flex;
  align-items: center; justify-content: center; font-size: 10px; font-weight: 700;
  color: white; flex-shrink: 0; }}
.route-info {{ flex: 1; min-width: 0; }}
.route-name {{ font-size: var(--kz-text-sm); font-weight: 500; }}
.route-detail {{ font-size: var(--kz-text-xs); color: var(--kz-gris-500); }}
.route-actions {{ display: flex; gap: 4px; }}
.route-actions button {{ background: none; border: 1px solid var(--kz-gris-300);
  border-radius: 4px; padding: 2px 6px; font-size: 11px; cursor: pointer;
  transition: all .15s; }}
.route-actions button:hover {{ background: var(--kz-azul-50); border-color: var(--kz-azul-claro); }}
.section-title {{ font-size: var(--kz-text-sm); font-weight: 600; color: var(--kz-azul);
  padding: 10px 0 6px; border-bottom: 2px solid var(--kz-azul); margin-bottom: 8px;
  display: flex; justify-content: space-between; align-items: center; }}
.section-title .btn-export {{ font-size: var(--kz-text-xs); padding: 2px 8px; }}
.table-wrap {{ overflow-x: auto; max-height: 300px; overflow-y: auto;
  border: 1px solid var(--kz-gris-200); border-radius: var(--kz-radius-md); }}
table.kz-table {{ font-size: var(--kz-text-xs); }}
table.kz-table th {{ position: sticky; top: 0; z-index: 2; }}
table.kz-table td, table.kz-table th {{ padding: 4px 6px; white-space: nowrap; }}

/* Panel de ruta (slide from right) */
#route-panel {{ position: fixed; top: var(--header-h); right: 0; bottom: 0;
  width: 480px; background: white; border-left: 2px solid var(--kz-azul);
  z-index: 1500; transform: translateX(100%); transition: transform .3s ease;
  overflow-y: auto; display: flex; flex-direction: column; }}
#route-panel.open {{ transform: translateX(0); }}
#route-panel .panel-header {{ padding: 16px; border-bottom: 1px solid var(--kz-gris-200);
  display: flex; align-items: center; gap: 12px; }}
#route-panel .panel-header h2 {{ font-size: var(--kz-text-lg); flex: 1; }}
#route-panel .panel-close {{ background: none; border: none; font-size: 1.5rem;
  cursor: pointer; color: var(--kz-gris-500); padding: 4px; line-height: 1; }}
#route-panel .panel-body {{ padding: 16px; flex: 1; overflow-y: auto; }}
.kpi-row {{ display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }}
.kpi-box {{ flex: 1; min-width: 80px; background: var(--kz-gris-50);
  border: 1px solid var(--kz-gris-200); border-radius: var(--kz-radius-md);
  padding: 8px 12px; text-align: center; }}
.kpi-val {{ font-size: var(--kz-text-xl); font-weight: 700; color: var(--kz-azul); }}
.kpi-lbl {{ font-size: var(--kz-text-xs); color: var(--kz-gris-600); }}
.stop-list {{ list-style: none; padding: 0; }}
.stop-list li {{ display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-bottom: 1px solid var(--kz-gris-100);
  font-size: var(--kz-text-sm); }}
.stop-num {{ width: 22px; height: 22px; background: var(--kz-azul-50);
  color: var(--kz-azul); border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: 11px; font-weight: 600; }}
.stop-name {{ flex: 1; }}
.no-data {{ padding: 20px; text-align: center; color: var(--kz-gris-500);
  font-size: var(--kz-text-sm); }}

/* Buscador */
.search-box {{ position: relative; margin: 8px 0; }}
.search-box input {{ width: 100%; padding: 8px 12px; border: 1px solid var(--kz-gris-300);
  border-radius: var(--kz-radius-md); font-size: var(--kz-text-sm); }}
.search-box input:focus {{ outline: none; border-color: var(--kz-azul); }}

/* Accordion */
.accordion {{ border: 1px solid var(--kz-gris-200); border-radius: var(--kz-radius-md);
  margin-bottom: 6px; overflow: hidden; }}
.accordion-header {{ padding: 10px 12px; background: var(--kz-gris-50);
  cursor: pointer; display: flex; justify-content: space-between;
  align-items: center; font-size: var(--kz-text-sm); font-weight: 500;
  transition: background .15s; }}
.accordion-header:hover {{ background: var(--kz-azul-50); }}
.accordion-body {{ padding: 0 12px 12px; display: none; }}
.accordion.open .accordion-body {{ display: block; }}
.accordion.open .accordion-header {{ background: var(--kz-azul-50); color: var(--kz-azul); }}
.accordion-icon {{ transition: transform .2s; }}
.accordion.open .accordion-icon {{ transform: rotate(180deg); }}

/* Toast */
.toast {{ position: fixed; bottom: 20px; right: 20px; z-index: 9999;
  background: var(--kz-azul); color: white; padding: 12px 20px;
  border-radius: var(--kz-radius-md); font-size: var(--kz-text-sm);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15); opacity: 0;
  transform: translateY(20px); transition: all .3s; }}
.toast.show {{ opacity: 1; transform: translateY(0); }}

/* Capas mapa */
.map-layer-toggle {{ position: absolute; top: 10px; right: 10px; z-index: 800;
  background: white; border-radius: var(--kz-radius-md);
  box-shadow: 0 1px 5px rgba(0,0,0,0.15); padding: 4px; }}
.map-layer-toggle button {{ background: none; border: 1px solid var(--kz-gris-200);
  border-radius: 4px; padding: 4px 10px; font-size: 11px; cursor: pointer;
  margin: 2px; transition: all .15s; }}
.map-layer-toggle button.active {{ background: var(--kz-azul); color: white;
  border-color: var(--kz-azul); }}

@media (max-width: 768px) {{
  #sidebar {{ width: 100%; z-index: 1500; }}
  #map {{ left: 0; }}
  #route-panel {{ width: 100%; }}
}}
</style>
</head>
<body>

<!-- HEADER KAIZEN -->
<div id="header">
  <h1>🚍 GTFStoCSV</h1>
  <span class="subtitle">Visor de datos GTFS — Equipo Kaizen</span>
  <span class="kz-badge" id="header-status">Sin datos</span>
</div>

<!-- MAPA -->
<div id="map"></div>

<!-- SIDEBAR -->
<div id="sidebar">
  <div class="sidebar-scroll">

    <!-- Drop Zone -->
    <div class="dropzone" id="dropzone">
      <div class="dropzone-icon">📂</div>
      <div class="dropzone-text"><strong>Arrastra un GTFS .zip</strong><br>o haz clic para seleccionar</div>
      <input type="file" id="file-input" accept=".zip" style="display:none">
    </div>

    <!-- Stats -->
    <div id="stats-bar"></div>

    <!-- Search -->
    <div class="search-box">
      <input type="text" id="search-input" placeholder="🔍 Buscar rutas..." oninput="filterRoutes(this.value)">
    </div>

    <!-- Route List -->
    <div class="section-title">
      <span>📋 Rutas</span>
      <button class="kz-btn kz-btn-sm kz-btn-ghost btn-export" onclick="exportTableCSV(window._routesData, 'rutas')">CSV</button>
    </div>
    <div id="route-list"></div>

    <!-- Tables accordion -->
    <div style="margin-top: 12px;">
      <div class="section-title"><span>📊 Datos GTFS</span></div>
      <div id="tables-accordion"></div>
    </div>

  </div>
</div>

<!-- ROUTE DETAIL PANEL -->
<div id="route-panel">
  <div class="panel-header">
    <h2 id="panel-title">Ruta</h2>
    <button class="panel-close" onclick="closeRoutePanel()">✕</button>
  </div>
  <div class="panel-body" id="panel-body"></div>
</div>

<!-- TOAST -->
<div class="toast" id="toast"></div>

<script>
// ============================================================
// VISOR GTFS — JavaScript
// ============================================================

const COLORS = ['#1A4488','#CB1823','#3463AC','#6B96CF','#2d6a4f','#e67e22','#8e44ad','#16a085','#c0392b','#2980b9'];
const ROUTE_TYPES = {{'0':'🚊 Tranvía','1':'🚇 Metro','2':'🚆 Tren','3':'🚌 Bus','4':'🚍 Ferry','5':'🚃 Tranvía','6':'🚡 Teleférico','7':'🚞 Funicular','11':'🚐 Bus','100':'🚄 Tren','109':'🚄 AVE','200':'🚌 Bus'}};

let map, routeLayers = {{}}, activeRouteId = null, allRoutes = [], allStops = [];
let allShapes = {{}}, routeShapeMap = {{}};
const ignGris = L.tileLayer('https://www.ign.es/wmts/ign-base?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=IGNBase-gris&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&TILEMATRIX={{z}}&TILECOL={{x}}&TILEROW={{y}}&FORMAT=image/jpeg', {{
  attribution: '© IGN — Instituto Geográfico Nacional (CC BY 4.0)', maxZoom: 19
}});
const ignTopo = L.tileLayer('https://www.ign.es/wmts/ign-base?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=IGNBaseTodo&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&TILEMATRIX={{z}}&TILECOL={{x}}&TILEROW={{y}}&FORMAT=image/jpeg', {{
  attribution: '© IGN — Instituto Geográfico Nacional (CC BY 4.0)', maxZoom: 19
}});

// Init map
function initMap() {{
  map = L.map('map', {{ center: [40.4168, -3.7038], zoom: 6, preferCanvas: true }});
  ignGris.addTo(map);
  // Layer control
  const layers = {{ 'IGN Gris': ignGris, 'IGN Topográfica': ignTopo }};
  map.on('click', () => closeRoutePanel());
}}

// Toast
let toastTimer;
function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 3000);
}}

// ============================================================
// DROPZONE — Carga de GTFS ZIP
// ============================================================
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');

dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('dragover', (e) => {{ e.preventDefault(); dropzone.classList.add('dragover'); }});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', (e) => {{ e.preventDefault(); dropzone.classList.remove('dragover');
  const file = e.dataTransfer.files[0]; if (file) loadGTFSZip(file); }});
fileInput.addEventListener('change', (e) => {{ if (e.target.files[0]) loadGTFSZip(e.target.files[0]); }});

async function loadGTFSZip(file) {{
  showToast(`📦 Cargando ${{file.name}}...`);
  try {{
    const arrayBuffer = await file.arrayBuffer();
    const zip = await JSZip.loadAsync(arrayBuffer);
    const data = await parseGTFSZip(zip, file.name);
    renderAll(data);
    showToast(`✅ ${{file.name}} — ${{data.routes.length}} rutas, ${{data.stops.length}} paradas`);
  }} catch(e) {{
    showToast('❌ Error al cargar GTFS: ' + e.message);
    console.error(e);
  }}
}}

async function parseGTFSZip(zip, filename) {{
  function csvParse(text) {{
    const lines = text.trim().split('\\n'); if (lines.length < 2) return [];
    const delim = detectDelim(lines[0]);
    const headers = lines[0].split(delim).map(h => h.trim().replace(/^"|"$/g,''));
    const result = [];
    for (let i = 1; i < lines.length; i++) {{
      const vals = parseCSVLine(lines[i], delim);
      if (vals.length !== headers.length) continue;
      const row = {{}};
      for (let j = 0; j < headers.length; j++) row[headers[j]] = vals[j] || '';
      result.push(row);
    }}
    return result;
  }}
  function detectDelim(line) {{
    const c = (line.match(/,/g)||[]).length, t = (line.match(/\\t/g)||[]).length, s = (line.match(/;/g)||[]).length;
    if (t > c && t > s) return '\\t'; if (s > c) return ';'; return ',';
  }}
  function parseCSVLine(line, delim) {{
    const r = []; let c = '', q = false;
    for (let i = 0; i < line.length; i++) {{
      if (line[i] === '"') q = !q;
      else if (line[i] === delim && !q) {{ r.push(c.trim()); c = ''; }}
      else c += line[i];
    }}
    r.push(c.trim()); return r;
  }}

  const routes = await getZipText(zip, 'routes.txt').then(t => t ? csvParse(t) : []);
  const stops = await getZipText(zip, 'stops.txt').then(t => t ? csvParse(t) : []);
  const trips = await getZipText(zip, 'trips.txt').then(t => t ? csvParse(t) : []);
  const stopTimes = await getZipText(zip, 'stop_times.txt').then(t => t ? csvParse(t) : []);
  const shapes = await getZipText(zip, 'shapes.txt').then(t => t ? csvParse(t) : []);
  const agency = await getZipText(zip, 'agency.txt').then(t => t ? csvParse(t) : []);
  const calendar = await getZipText(zip, 'calendar.txt').then(t => t ? csvParse(t) : []);
  const calDates = await getZipText(zip, 'calendar_dates.txt').then(t => t ? csvParse(t) : []);
  const frequencies = await getZipText(zip, 'frequencies.txt').then(t => t ? csvParse(t) : []);
  const transfers = await getZipText(zip, 'transfers.txt').then(t => t ? csvParse(t) : []);
  const feedInfo = await getZipText(zip, 'feed_info.txt').then(t => t ? csvParse(t) : []);

  // Build indexes
  const stopsById = {{}}; stops.forEach(s => stopsById[s.stop_id] = s);
  const tripsByRoute = {{}}; trips.forEach(t => {{
    if (!tripsByRoute[t.route_id]) tripsByRoute[t.route_id] = [];
    tripsByRoute[t.route_id].push(t);
  }});
  const stopTimesByTrip = {{}}; stopTimes.forEach(st => {{
    if (!stopTimesByTrip[st.trip_id]) stopTimesByTrip[st.trip_id] = [];
    stopTimesByTrip[st.trip_id].push(st);
  }});
  const shapesCoords = {{}}; shapes.forEach(s => {{
    if (!shapesCoords[s.shape_id]) shapesCoords[s.shape_id] = [];
    shapesCoords[s.shape_id].push([parseFloat(s.shape_pt_lat), parseFloat(s.shape_pt_lon)]);
  }});
  const routeShapeMap = {{}};
  trips.forEach(t => {{ if (t.shape_id && shapesCoords[t.shape_id] && !routeShapeMap[t.route_id]) routeShapeMap[t.route_id] = t.shape_id; }});

  // Build routes data
  const resultRoutes = routes.map(r => {{
    const rid = r.route_id;
    const trips = tripsByRoute[rid] || [];
    const firstTrip = trips[0];
    const shapeId = routeShapeMap[rid];
    const coords = shapeId ? (shapesCoords[shapeId] || []) : [];
    const headsigns = [...new Set(trips.map(t => t.trip_headsign).filter(Boolean))];
    const stops = getOrderedStops(rid, trips, stopTimesByTrip, stopsById);
    return {{
      id: rid, short_name: r.route_short_name || '', long_name: r.route_long_name || '',
      type: r.route_type || '', color: r.route_color || '', text_color: r.route_text_color || '',
      agency_id: r.agency_id || '', num_trips: trips.length, num_stops: stops.length,
      headsigns, has_shape: coords.length > 0, shape_km: calcLength(coords)
    }};
  }});

  const resultStops = stops.filter(s => {{
    const lat = parseFloat(s.stop_lat), lon = parseFloat(s.stop_lon);
    return !isNaN(lat) && !isNaN(lon) && !(lat === 0 && lon === 0);
  }}).map(s => ({{ id: s.stop_id, name: s.stop_name, lat: parseFloat(s.stop_lat), lon: parseFloat(s.stop_lon), code: s.stop_code || '' }}));

  window._rawData = {{ routes, stops, trips, stopTimes, shapes, agency, calendar, calDates, frequencies, transfers, feedInfo }};

  return {{ meta: {{ filename, agency: agency.map(a => a.agency_name).filter(Boolean) }}, routes: resultRoutes, stops: resultStops, shapes: shapesCoords, route_shape_map: routeShapeMap }};
}}

function getZipText(zip, name) {{ return zip.file(name) ? zip.file(name).async('string').catch(() => '') : Promise.resolve(''); }}

function getOrderedStops(routeId, trips, stopTimesByTrip, stopsById) {{
  let bestTrip = null, maxStops = 0;
  trips.forEach(t => {{
    const sts = stopTimesByTrip[t.trip_id] || [];
    if (sts.length > maxStops) {{ maxStops = sts.length; bestTrip = sts; }}
  }});
  if (!bestTrip) return [];
  bestTrip.sort((a,b) => parseInt(a.stop_sequence||0) - parseInt(b.stop_sequence||0));
  return bestTrip.map(st => ({{ ...(stopsById[st.stop_id] || {{}}), departure_time: st.departure_time }})).filter(s => s.stop_id);
}}

function calcLength(coords) {{
  if (coords.length < 2) return 0;
  let total = 0; const R = 6371;
  for (let i = 1; i < coords.length; i++) {{
    const [lat1, lon1] = coords[i-1], [lat2, lon2] = coords[i];
    const dlat = (lat2-lat1)*Math.PI/180, dlon = (lon2-lon1)*Math.PI/180;
    const a = Math.sin(dlat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dlon/2)**2;
    total += R * 2 * Math.asin(Math.sqrt(a));
  }}
  return Math.round(total*100)/100;
}}

// ============================================================
// RENDER
// ============================================================
function renderAll(data) {{
  allRoutes = data.routes;
  allStops = data.stops;
  allShapes = data.shapes;
  routeShapeMap = data.route_shape_map;
  window._routesData = allRoutes;

  // Update header
  const agency = data.meta.agency.length ? data.meta.agency.join(', ') : data.meta.filename;
  document.getElementById('header-status').textContent = `${{allRoutes.length}} rutas | ${{allStops.length}} paradas`;

  // Stats
  const types = new Set(allRoutes.map(r => r.type).filter(Boolean));
  const hasShape = allRoutes.filter(r => r.has_shape).length;
  document.getElementById('stats-bar').innerHTML =
    `<span class="stat-chip">🚏 ${{allStops.length}} paradas</span>` +
    `<span class="stat-chip">🚍 ${{allRoutes.length}} rutas</span>` +
    `<span class="stat-chip">📐 ${{hasShape}} con trazado</span>` +
    `<span class="stat-chip">🏢 ${{agency}}</span>`;

  // Fit map to first route with shape, or Spain
  const firstWithShape = allRoutes.find(r => r.has_shape);
  if (firstWithShape) {{
    const coords = allShapes[routeShapeMap[firstWithShape.id]];
    if (coords) map.fitBounds(coords, {{ padding: [30,30] }});
  }}

  renderRoutes(allRoutes);
  renderStopsOnMap(allStops);
  renderTablesAccordion();
}}

function renderRoutes(routes) {{
  const container = document.getElementById('route-list');
  container.innerHTML = routes.map(r => {{
    const color = r.color ? `#${{r.color}}` : COLORS[routes.indexOf(r) % COLORS.length];
    const textColor = r.text_color ? `#${{r.text_color}}` : '#fff';
    const typeLabel = ROUTE_TYPES[r.type] || `🚍 Tipo ${{r.type}}`;
    return `<div class="route-item" data-id="${{r.id}}" onclick="openRoute('${{r.id}}')">
      <div class="route-badge" style="background:${{color}};color:${{textColor}}">${{r.short_name || '?'}}</div>
      <div class="route-info">
        <div class="route-name">${{r.long_name || r.short_name || 'Ruta ' + r.id}}</div>
        <div class="route-detail">${{typeLabel}} · ${{r.num_trips}} viajes · ${{r.num_stops}} paradas${{r.shape_km ? ' · '+r.shape_km+' km' : ''}}</div>
      </div>
      <div class="route-actions">
        <button title="GeoJSON" onclick="event.stopPropagation();downloadRouteGeoJSON('${{r.id}}')">🌐</button>
        <button title="CSV Horarios" onclick="event.stopPropagation();downloadRouteCSV('${{r.id}}')">📋</button>
      </div>
    </div>`;
  }}).join('');
}}

function renderStopsOnMap(stops) {{
  const icon = L.divIcon({{
    html: '<div style="width:8px;height:8px;background:#1A4488;border:2px solid #fff;border-radius:50%;box-shadow:0 1px 3px rgba(0,0,0,0.3)"></div>',
    iconSize: [8,8], iconAnchor: [4,4], className: ''
  }});
  const markers = L.layerGroup(stops.map(s =>
    L.marker([s.lat, s.lon], {{ icon }}).bindPopup(`<b>${{s.name}}</b><br><small>ID: ${{s.id}}</small>`)
  ));
  markers.addTo(map);
}}

function renderTablesAccordion() {{
  const container = document.getElementById('tables-accordion');
  const tables = ['agency','routes','trips','stop_times','stops','shapes','calendar','calendar_dates','frequencies','transfers','feed_info','attributions'];
  const labels = {{ agency:'🏢 Agencia', routes:'📋 Rutas', trips:'🎫 Viajes', stop_times:'⏰ Stop Times', stops:'🚏 Paradas', shapes:'📐 Shapes', calendar:'🗓️ Calendar', calendar_dates:'📅 Calendar Dates', frequencies:'🔄 Frecuencias', transfers:'🔀 Transferencias', feed_info:'ℹ️ Feed Info', attributions:'© Atribuciones' }};
  const raw = window._rawData || {{}};
  let html = '';
  tables.forEach(t => {{
    const data = raw[t];
    if (!data || !data.length) return;
    const keys = Object.keys(data[0]);
    let rows = data.slice(0, 50).map(row =>
      '<tr>' + keys.map(k => `<td>${{(row[k]||'').toString().substring(0,50)}}</td>`).join('') + '</tr>'
    ).join('');
    const total = data.length;
    html += `<div class="accordion">
      <div class="accordion-header" onclick="this.parentElement.classList.toggle('open')">
        <span>${{labels[t] || t}} (${{total}})</span>
        <span class="accordion-icon">▼</span>
      </div>
      <div class="accordion-body">
        <button class="kz-btn kz-btn-sm kz-btn-ghost" onclick="exportTableCSV(window._rawData['${{t}}'], '${{t}}')" style="margin:8px 0">📥 Exportar CSV</button>
        <div class="table-wrap">
          <table class="kz-table">
            <thead><tr>${{keys.map(k => '<th>'+k+'</th>').join('')}}</tr></thead>
            <tbody>${{rows}}</tbody>
          </table>
          ${{total > 50 ? '<div style="padding:8px;text-align:center;color:var(--kz-gris-500);font-size:var(--kz-text-xs)">Mostrando 50 de '+total+' filas. Exporta CSV para ver todas.</div>' : ''}}
        </div>
      </div>
    </div>`;
  }});
  container.innerHTML = html || '<div class="no-data">Carga un GTFS para ver los datos</div>';
}}

// ============================================================
// FILTER
// ============================================================
function filterRoutes(query) {{
  const q = query.toLowerCase();
  document.querySelectorAll('.route-item').forEach(item => {{
    const match = item.textContent.toLowerCase().includes(q);
    item.style.display = match ? '' : 'none';
  }});
}}

// ============================================================
// ROUTE PANEL
// ============================================================
async function openRoute(routeId) {{
  activeRouteId = routeId;
  document.querySelectorAll('.route-item').forEach(el => el.classList.toggle('active', el.dataset.id === routeId));

  const route = allRoutes.find(r => r.id === routeId);
  if (!route) return;

  const raw = window._rawData;
  const trips = raw.trips.filter(t => t.route_id === routeId);
  const stops = getOrderedStops(routeId, trips, groupBy(raw.stopTimes, 'trip_id'), groupBy(raw.stops, 'stop_id'));
  const shapeId = routeShapeMap[routeId];
  const coords = shapeId ? (allShapes[shapeId] || []) : [];

  const color = route.color ? `#${{route.color}}` : '#1A4488';
  const textColor = route.text_color ? `#${{route.text_color}}` : '#fff';

  // Highlight on map
  if (highlightLayer) map.removeLayer(highlightLayer);
  if (coords.length > 0) {{
    highlightLayer = L.polyline(coords, {{ color, weight: 6, opacity: 1 }}).addTo(map);
    map.fitBounds(highlightLayer.getBounds(), {{ padding: [50,50] }});
  }}

  const headsigns = route.headsigns || [];
  const headsignHtml = headsigns.length
    ? `<div style="margin-bottom:12px;display:flex;gap:4px;flex-wrap:wrap">${{headsigns.map(h =>
      `<span class="kz-badge kz-badge-success">${{h}}</span>`).join('')}}</div>`
    : '';

  const stopsHtml = stops.length
    ? `<ol class="stop-list">${{stops.map((s,i) =>
      `<li><span class="stop-num">${{i+1}}</span><span class="stop-name">${{s.stop_name || s.stop_id}}</span><small style="color:var(--kz-gris-500)">${{s.departure_time || ''}}</small></li>`
    ).join('')}}</ol>`
    : '<div class="no-data">No hay paradas ordenadas</div>';

  document.getElementById('panel-title').innerHTML =
    `<span class="route-badge" style="background:${{color}};color:${{textColor}};width:28px;height:28px;border-radius:4px;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:13px">${{route.short_name || '?'}}</span> ${{route.long_name || route.short_name || 'Ruta ' + route.id}}`;

  document.getElementById('panel-body').innerHTML =
    `<div class="kpi-row">
      <div class="kpi-box"><div class="kpi-val">${{route.num_trips}}</div><div class="kpi-lbl">Viajes</div></div>
      <div class="kpi-box"><div class="kpi-val">${{route.num_stops}}</div><div class="kpi-lbl">Paradas</div></div>
      <div class="kpi-box"><div class="kpi-val">${{route.shape_km || 0}} km</div><div class="kpi-lbl">Longitud</div></div>
      <div class="kpi-box"><div class="kpi-val">${{headsigns.length}}</div><div class="kpi-lbl">Direcciones</div></div>
    </div>
    ${{headsignHtml}}
    <h4 style="font-size:var(--kz-text-sm);color:var(--kz-azul);margin-bottom:8px">🚏 Paradas ordenadas</h4>
    ${{stopsHtml}}
    <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="kz-btn kz-btn-primary kz-btn-sm" onclick="downloadRouteGeoJSON('${{routeId}}')">🌐 GeoJSON</button>
      <button class="kz-btn kz-btn-secondary kz-btn-sm" onclick="downloadRouteCSV('${{routeId}}')">📋 CSV Horarios</button>
    </div>`;

  document.getElementById('route-panel').classList.add('open');
}}

let highlightLayer = null;

function closeRoutePanel() {{
  document.getElementById('route-panel').classList.remove('open');
  if (highlightLayer) {{ map.removeLayer(highlightLayer); highlightLayer = null; }}
  document.querySelectorAll('.route-item').forEach(el => el.classList.remove('active'));
}}

// ============================================================
// EXPORTS
// ============================================================
function downloadBlob(content, filename, type) {{
  const blob = new Blob([content], {{ type }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}}

function exportTableCSV(data, name) {{
  if (!data || !data.length) return showToast('⚠️ No hay datos para exportar');
  const keys = Object.keys(data[0]);
  const csv = '\\uFEFF' + keys.join(',') + '\\n' +
    data.map(row => keys.map(k => {{
      const v = (row[k] || '').toString();
      return v.includes(',') || v.includes('"') ? '"' + v.replace(/"/g,'""') + '"' : v;
    }}).join(',')).join('\\n');
  downloadBlob(csv, `${{name}}.csv`, 'text/csv;charset=utf-8');
  showToast(`✅ ${{name}}.csv descargado`);
}}

function downloadRouteGeoJSON(routeId) {{
  const route = allRoutes.find(r => r.id === routeId);
  if (!route) return;
  const shapeId = routeShapeMap[routeId];
  const coords = shapeId ? (allShapes[shapeId] || []) : [];
  const raw = window._rawData;
  const trips = raw.trips.filter(t => t.route_id === routeId);
  const stops = getOrderedStops(routeId, trips, groupBy(raw.stopTimes, 'trip_id'), groupBy(raw.stops, 'stop_id'));

  const feature = {{
    type: 'Feature',
    geometry: coords.length ? {{ type: 'LineString', coordinates: coords.map(c => [c[1], c[0]]) }} : null,
    properties: {{
      route_id: route.id, short_name: route.short_name, long_name: route.long_name,
      route_type: route.type, color: route.color, num_trips: route.num_trips,
      num_stops: route.num_stops, headsigns: route.headsigns, shape_km: route.shape_km,
      stops: stops.map(s => ({{ stop_id: s.stop_id, stop_name: s.stop_name }}))
    }}
  }};
  const gj = JSON.stringify(feature, null, 2);
  const name = (route.short_name || route.id).replace(/[^a-zA-Z0-9]/g, '_');
  downloadBlob(gj, `ruta_${{name}}.geojson`, 'application/geo+json');
  showToast(`✅ ruta_${{name}}.geojson descargado`);
}}

function downloadRouteCSV(routeId) {{
  const raw = window._rawData;
  const trips = raw.trips.filter(t => t.route_id === routeId);
  const stopTimes = raw.stopTimes.filter(st => trips.some(t => t.trip_id === st.trip_id));
  const stopsMap = groupBy(raw.stops, 'stop_id');
  const enriched = stopTimes.map(st => ({{
    trip_id: st.trip_id,
    stop_id: st.stop_id,
    stop_name: (stopsMap[st.stop_id]||{{}}).stop_name || '',
    arrival_time: st.arrival_time || '',
    departure_time: st.departure_time || '',
    stop_sequence: st.stop_sequence || '',
    pickup_type: st.pickup_type || '',
    drop_off_type: st.drop_off_type || '',
  }}));
  exportTableCSV(enriched, `horarios_${{routeId}}`);
}}

// ============================================================
// UTILS
// ============================================================
function groupBy(arr, key) {{
  const map = {{}};
  (arr || []).forEach(item => {{ map[item[key]] = item; }});
  return map;
}}

// ============================================================
// INIT
// ============================================================
initMap();

// Try to load data.json (pre-generated by Python)
(async function() {{
  try {{
    const resp = await fetch('data.json');
    if (resp.ok) {{
      const data = await resp.json();
      console.log('📦 Datos pre-cargados:', data.meta.filename);
      // Convert raw data format to match parseGTFSZip output
      window._rawData = {{}};
      renderAll(data);
    }}
  }} catch(e) {{
    console.log('ℹ️ No hay data.json pre-cargado');
  }}
}})();
</script>
</body>
</html>'''

    return html


def _calc_length(coords):
    """Calcula longitud de shape en km usando Haversine."""
    if len(coords) < 2:
        return 0.0
    R = 6371
    total = 0.0
    for i in range(len(coords) - 1):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[i + 1]
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
            math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        total += R * c
    return round(total, 2)


def _get_kaizen_css() -> str:
    """Devuelve el CSS del Kaizen Design System v4.0 inline."""
    css_path = os.path.join(os.path.dirname(__file__), "..", "kaizen.css")
    alt_path = "/root/workspace/kaizen-design-system/kaizen.css"

    for path in [css_path, alt_path]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

    # Fallback: CSS mínimo con variables Kaizen
    return """
:root {
  --kz-azul: #1A4488; --kz-rojo: #CB1823;
  --kz-azul-medio: #3463AC; --kz-azul-claro: #6B96CF;
  --kz-azul-900: #0f2d5a; --kz-azul-800: #1A4488;
  --kz-azul-700: #22569e; --kz-azul-600: #3463AC;
  --kz-azul-500: #4a7fc0; --kz-azul-400: #6B96CF;
  --kz-azul-300: #8fb3de; --kz-azul-200: #b8d1ec;
  --kz-azul-100: #dce9f6; --kz-azul-50: #eef4fb;
  --kz-rojo-600: #a31420; --kz-rojo-500: #CB1823;
  --kz-rojo-400: #d9404d; --kz-rojo-300: #e8707a;
  --kz-rojo-200: #f4aab0; --kz-rojo-100: #fbd5d8;
  --kz-rojo-50: #fdf2f3;
  --kz-negro: #1a1a2e; --kz-gris-900: #333; --kz-gris-800: #4a4a5a;
  --kz-gris-700: #666; --kz-gris-600: #808080; --kz-gris-500: #999;
  --kz-gris-400: #b3b3b3; --kz-gris-300: #ccc; --kz-gris-200: #e0e0e0;
  --kz-gris-100: #f0f0f0; --kz-gris-50: #f8f8f8; --kz-blanco: #fff;
  --kz-font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --kz-font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --kz-text-xs: 0.75rem; --kz-text-sm: 0.8125rem; --kz-text-base: 0.9375rem;
  --kz-text-md: 1rem; --kz-text-lg: 1.125rem; --kz-text-xl: 1.375rem; --kz-text-2xl: 1.75rem;
  --kz-gap-xs: 4px; --kz-gap-sm: 8px; --kz-gap-md: 16px; --kz-gap-lg: 24px; --kz-gap-xl: 32px;
  --kz-radius-sm: 4px; --kz-radius-md: 6px; --kz-radius-lg: 8px;
  --kz-transition: 150ms ease; --kz-sidebar-width: 380px; --kz-header-height: 60px;
}
*,*::before,*::after{box-sizing:border-box;margin:0}
body{font-family:var(--kz-font);color:var(--kz-negro);background:var(--kz-gris-50);line-height:1.5}
.kz-badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:var(--kz-text-xs);font-weight:500;background:var(--kz-azul-50);color:var(--kz-azul)}
.kz-badge-success{background:#e8f5e9;color:#2e7d32}
.kz-btn{display:inline-flex;align-items:center;justify-content:center;padding:6px 14px;border:none;border-radius:var(--kz-radius-md);font-size:var(--kz-text-sm);cursor:pointer;transition:var(--kz-transition);text-decoration:none;gap:4px}
.kz-btn-primary{background:var(--kz-azul);color:#fff}
.kz-btn-primary:hover{background:var(--kz-azul-700)}
.kz-btn-secondary{background:var(--kz-gris-100);color:var(--kz-negro)}
.kz-btn-secondary:hover{background:var(--kz-gris-200)}
.kz-btn-ghost{background:transparent;color:var(--kz-azul)}
.kz-btn-ghost:hover{background:var(--kz-azul-50)}
.kz-btn-sm{padding:4px 10px;font-size:var(--kz-text-xs)}
table.kz-table{width:100%;border-collapse:collapse}
table.kz-table th{background:var(--kz-azul);color:#fff;padding:6px 10px;font-size:var(--kz-text-xs);font-weight:600;text-align:left}
table.kz-table td{padding:4px 10px;border-bottom:1px solid var(--kz-gris-100);font-size:var(--kz-text-sm)}
table.kz-table tr:hover td{background:var(--kz-azul-50)}
"""


def _get_visor_js() -> str:
    """Devuelve el JavaScript del visor (ya inline en el HTML)."""
    return ""  # El JS está embebido directamente en el HTML