"""gtfstocsv/parser.py — Parseo completo de archivos GTFS.

Soporta todos los archivos del estándar GTFS:
  agency, routes, trips, stop_times, stops, shapes,
  calendar, calendar_dates, frequencies, transfers, feed_info, attributions

Uso:
    from gtfstocsv.parser import GTFSParser
    parser = GTFSParser("ruta/al/gtfs.zip")
    parser.parse()
    print(parser.routes)   # list[dict]
    print(parser.stops)    # list[dict]
"""

import zipfile
import csv
import io
import os
from collections import defaultdict


ARCHIVOS_GTFS = [
    "agency", "routes", "trips", "stop_times", "stops", "shapes",
    "calendar", "calendar_dates", "frequencies", "transfers",
    "feed_info", "attributions"
]


class GTFSParser:
    """Parsea un archivo GTFS .zip y expone todos sus datos como atributos."""

    def __init__(self, zip_path: str):
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"No se encuentra el archivo: {zip_path}")
        self.zip_path = zip_path
        self.filename = os.path.basename(zip_path)

        # Cada archivo GTFS se almacena como lista de dicts, o lista vacía si no existe
        for archivo in ARCHIVOS_GTFS:
            setattr(self, archivo, [])

        # Índices internos (se construyen con build_indexes())
        self.shapes_coords = {}          # shape_id -> list[(lat, lng)]
        self.trips_by_route = {}         # route_id -> list[dict]
        self.stops_by_id = {}            # stop_id -> dict
        self.routes_by_id = {}           # route_id -> dict
        self.stop_times_by_trip = {}     # trip_id -> list[dict]
        self.calendar_by_service = {}    # service_id -> dict
        self.calendar_dates_by_service = defaultdict(list)

        # Metadatos
        self.stats = {
            "stops": 0, "routes": 0, "trips": 0, "stop_times": 0,
            "shapes": 0, "shape_points": 0
        }

    def parse(self):
        """Descomprime el ZIP y parsea todos los archivos GTFS."""
        with zipfile.ZipFile(self.zip_path, 'r') as z:
            namelist = z.namelist()
            for archivo in ARCHIVOS_GTFS:
                filename = f"{archivo}.txt"
                if filename in namelist:
                    with z.open(filename) as f:
                        text = io.TextIOWrapper(f, encoding='utf-8-sig')
                        reader = csv.DictReader(text)
                        rows = list(reader)
                        setattr(self, archivo, rows)
                        self.stats[archivo if archivo != "stop_times" else "stop_times"] = len(rows)

        self.build_indexes()
        return self

    def build_indexes(self):
        """Construye índices para acceso rápido."""
        # stops por ID
        for stop in self.stops:
            self.stops_by_id[stop["stop_id"]] = stop

        # routes por ID
        for route in self.routes:
            self.routes_by_id[route["route_id"]] = route

        # trips por route_id
        for trip in self.trips:
            rid = trip["route_id"]
            if rid not in self.trips_by_route:
                self.trips_by_route[rid] = []
            self.trips_by_route[rid].append(trip)

        # stop_times por trip_id
        for st in self.stop_times:
            tid = st["trip_id"]
            if tid not in self.stop_times_by_trip:
                self.stop_times_by_trip[tid] = []
            self.stop_times_by_trip[tid].append(st)

        # shapes coordenadas por shape_id
        for shape in self.shapes:
            sid = shape["shape_id"]
            if sid not in self.shapes_coords:
                self.shapes_coords[sid] = []
            self.shapes_coords[sid].append((
                float(shape["shape_pt_lat"]),
                float(shape["shape_pt_lon"])
            ))

        # calendar por service_id
        for cal in self.calendar:
            self.calendar_by_service[cal["service_id"]] = cal

        # calendar_dates agrupados
        for cd in self.calendar_dates:
            self.calendar_dates_by_service[cd["service_id"]].append(cd)

        # stats adicionales
        self.stats["shape_points"] = sum(len(v) for v in self.shapes_coords.values())
        self.stats["shapes"] = len(self.shapes_coords)

    def summary_text(self) -> str:
        """Resumen legible de los datos parseados."""
        s = self.stats
        lines = [
            f"📦 {self.filename}",
            f"   🚏 Paradas:      {len(self.stops):,}",
            f"   🚍 Rutas:        {len(self.routes):,}",
            f"   🎫 Viajes:       {len(self.trips):,}",
            f"   ⏰ Stop Times:   {s['stop_times']:,}",
            f"   📐 Shapes:       {s['shapes']:,} ({s['shape_points']:,} puntos)",
            f"   🗓️  Calendar:     {len(self.calendar)} servicios",
        ]
        if self.agency:
            lines.append(f"   🏢 Agencia(s):   {', '.join(a.get('agency_name', '?') for a in self.agency)}")
        if self.feed_info:
            lines.append(f"   ℹ️  Feed:         {self.feed_info[0].get('feed_publisher_name', '?')}")
        return "\n".join(lines)

    def get_route_shape(self, route_id: str) -> list:
        """Devuelve las coordenadas de la shape asociada a una ruta.
        Usa el primer trip de la ruta para obtener el shape_id."""
        trips = self.trips_by_route.get(route_id, [])
        for trip in trips:
            shape_id = trip.get("shape_id", "")
            if shape_id in self.shapes_coords:
                return self.shapes_coords[shape_id]
        return []

    def get_route_stops_ordered(self, route_id: str) -> list:
        """Devuelve las paradas de una ruta ordenadas por stop_sequence.
        Usa el trip con más paradas para tener la ruta más completa."""
        trips = self.trips_by_route.get(route_id, [])
        best_trip = None
        max_stops = 0
        for trip in trips:
            sts = self.stop_times_by_trip.get(trip["trip_id"], [])
            if len(sts) > max_stops:
                max_stops = len(sts)
                best_trip = sts
        if not best_trip:
            return []
        best_trip.sort(key=lambda x: int(x.get("stop_sequence", 0)))
        result = []
        for st in best_trip:
            stop = self.stops_by_id.get(st["stop_id"])
            if stop:
                result.append({**stop, "departure_time": st.get("departure_time", "")})
        return result
