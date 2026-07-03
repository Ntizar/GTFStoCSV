"""gtfstocsv/exporter.py — Exportación a CSV, GeoJSON y SHP.

CSV: cualquier tabla GTFS individual (stops, routes, trips, stop_times...)
GeoJSON: líneas completas como FeatureCollection (con shapes + propiedades)
SHP: shapefile ZIP (requiere pyshp)

Uso:
    from gtfstocsv.exporter import export_csv, export_geojson, export_shp_zip

    # CSV de todas las rutas
    export_csv(parser.routes, "output/routes.csv")

    # GeoJSON de una ruta
    export_geojson(parser, "R001", "output/linea_101.geojson")

    # SHP de todas las rutas
    export_shp_zip(parser, "output/shapes_all.shp.zip")
"""

import csv
import json
import os
import io
import zipfile


def export_csv(data: list[dict], output_path: str):
    """Exporta una lista de diccionarios GTFS a CSV.

    Args:
        data: Lista de diccionarios (ej: parser.routes, parser.stops)
        output_path: Ruta del archivo CSV a escribir
    """
    if not data:
        raise ValueError("No hay datos para exportar")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fieldnames = list(data[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"  ✅ CSV exportado: {output_path} ({len(data):,} filas)")


def export_geojson_feature(parser, route_id: str) -> dict:
    """Genera un Feature GeoJSON para una ruta específica."""
    route = parser.routes_by_id.get(route_id)
    if not route:
        return None

    coords = parser.get_route_shape(route_id)
    trips = parser.trips_by_route.get(route_id, [])
    stops = parser.get_route_stops_ordered(route_id)

    geometry = None
    if coords:
        geometry = {
            "type": "LineString",
            "coordinates": [[lng, lat] for lat, lng in coords]
        }

    # Contar direcciones/headsigns únicos
    headsigns = set()
    for t in trips:
        hs = t.get("trip_headsign", "").strip()
        if hs:
            headsigns.add(hs)

    properties = {
        "route_id": route.get("route_id", ""),
        "route_short_name": route.get("route_short_name", ""),
        "route_long_name": route.get("route_long_name", ""),
        "route_type": route.get("route_type", ""),
        "route_color": route.get("route_color", ""),
        "route_text_color": route.get("route_text_color", ""),
        "agency_id": route.get("agency_id", ""),
        "num_trips": len(trips),
        "num_stops": len(stops),
        "headsigns": list(headsigns),
        "shape_km": _calc_shape_length(coords),
        "source_gtfs": parser.filename,
    }

    # Paradas como array de propiedades
    if stops:
        properties["stops"] = [
            {
                "stop_id": s.get("stop_id", ""),
                "stop_name": s.get("stop_name", ""),
                "stop_lat": s.get("stop_lat", ""),
                "stop_lon": s.get("stop_lon", ""),
            }
            for s in stops
        ]

    feature = {
        "type": "Feature",
        "properties": properties,
    }
    if geometry:
        feature["geometry"] = geometry

    return feature


def export_geojson(parser, route_id: str, output_path: str):
    """Exporta una ruta como archivo GeoJSON Feature."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    feature = export_geojson_feature(parser, route_id)
    if not feature:
        raise ValueError(f"Ruta {route_id} no encontrada")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(feature, f, ensure_ascii=False, indent=2)
    print(f"  ✅ GeoJSON exportado: {output_path}")


def export_all_geojson(parser, output_dir: str) -> str:
    """Exporta TODAS las rutas como un único FeatureCollection GeoJSON.

    Returns:
        Ruta al archivo generado.
    """
    os.makedirs(output_dir, exist_ok=True)
    features = []
    for route in parser.routes:
        feat = export_geojson_feature(parser, route["route_id"])
        if feat:
            features.append(feat)

    fc = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": f"GTFStoCSV — {parser.filename}",
            "total_routes": len(features),
            "total_stops": len(parser.stops)
        }
    }

    output_path = os.path.join(output_dir, "todas_las_rutas.geojson")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)
    print(f"  ✅ GeoJSON (todas rutas): {output_path} ({len(features)} rutas)")
    return output_path


def export_shp_zip(parser, output_path: str):
    """Exporta TODAS las rutas como un ZIP con shapefiles.

    Requiere pyshp (pip install pyshp).
    Genera: .shp, .shx, .dbf, .prj, .cpg dentro del ZIP.
    Por ruta, genera una polyline.

    Returns:
        Ruta al archivo .shp.zip generado, o None si no hay pyshp.
    """
    try:
        import shapefile
    except ImportError:
        print("  ⚠️  pyshp no instalado. Omitiendo SHP. pip install pyshp")
        return None

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Crear un shapefile temporal en memoria
    tmp_dir = output_path.replace(".shp.zip", "") + "_shp_temp"
    os.makedirs(tmp_dir, exist_ok=True)
    shp_path = os.path.join(tmp_dir, "rutas")

    w = shapefile.Writer(shp_path, shapeType=shapefile.POLYLINE)
    w.field("route_id", "C", 50)
    w.field("short_name", "C", 50)
    w.field("long_name", "C", 100)
    w.field("route_type", "C", 10)
    w.field("num_trips", "N", 10)
    w.field("num_stops", "N", 10)
    w.field("color", "C", 10)

    for route in parser.routes:
        coords = parser.get_route_shape(route["route_id"])
        if not coords:
            continue
        trips = parser.trips_by_route.get(route["route_id"], [])
        stops = parser.get_route_stops_ordered(route["route_id"])
        w.line([[[lng, lat] for lat, lng in coords]])
        w.record(
            route_id=route.get("route_id", ""),
            short_name=route.get("route_short_name", ""),
            long_name=route.get("route_long_name", ""),
            route_type=route.get("route_type", ""),
            num_trips=len(trips),
            num_stops=len(stops),
            color=route.get("route_color", ""),
        )

    w.close()

    # Crear .prj (EPSG:4326 WGS84)
    prj_content = (
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID'
        '["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],'
        'UNIT["Degree",0.017453292519943295]]'
    )
    with open(shp_path + ".prj", "w") as f:
        f.write(prj_content)

    # Comprimir todo en ZIP
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
        for ext in [".shp", ".shx", ".dbf", ".prj"]:
            fpath = shp_path + ext
            if os.path.exists(fpath):
                z.write(fpath, f"rutas{ext}")

    # Limpiar temporales
    for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
        fpath = shp_path + ext
        if os.path.exists(fpath):
            os.remove(fpath)
    os.rmdir(tmp_dir)

    print(f"  ✅ SHP exportado: {output_path}")
    return output_path


def _calc_shape_length(coords: list) -> float:
    """Calcula la longitud aproximada de una shape en kilómetros (Haversine)."""
    if len(coords) < 2:
        return 0.0
    import math
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


def export_table_summary(parser, output_dir: str):
    """Exporta TODAS las tablas GTFS como CSV individual en un directorio."""
    os.makedirs(output_dir, exist_ok=True)
    from gtfstocsv.parser import ARCHIVOS_GTFS
    exported = []
    for archivo in ARCHIVOS_GTFS:
        data = getattr(parser, archivo, [])
        if data:
            path = os.path.join(output_dir, f"{archivo}.csv")
            export_csv(data, path)
            exported.append(archivo)
    return exported