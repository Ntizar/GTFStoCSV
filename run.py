#!/usr/bin/env python3
"""GTFStoCSV — Convierte GTFS a CSV, GeoJSON, SHP y visor HTML.

Uso:
    python run.py ruta/al/gtfs.zip
    python run.py ruta/al/gtfs.zip -o directorio_salida
    python run.py ruta/al/gtfs.zip --no-shp   # Sin SHP
    python run.py ruta/al/gtfs.zip --no-html  # Sin visor HTML
"""

import sys
import os
import argparse

# Añadir directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gtfstocsv.parser import GTFSParser
from gtfstocsv.exporter import (
    export_table_summary, export_all_geojson, export_shp_zip
)
from gtfstocsv.templater import generar_visor


def main():
    parser = argparse.ArgumentParser(
        description="GTFStoCSV — Convierte GTFS a CSV, GeoJSON, SHP y visor HTML con mapa IGN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python run.py data/mi-gtfs.zip
  python run.py data/mi-gtfs.zip -o mis_datos
  python run.py data/mi-gtfs.zip --no-shp
        """
    )
    parser.add_argument("gtfs_zip", help="Ruta al archivo GTFS .zip")
    parser.add_argument("-o", "--output", default="output",
                        help="Directorio de salida (default: output/)")
    parser.add_argument("--no-shp", action="store_true",
                        help="Omitir exportación SHP (shapefile)")
    parser.add_argument("--no-html", action="store_true",
                        help="Omitir generación del visor HTML")
    parser.add_argument("--no-csv", action="store_true",
                        help="Omitir exportación CSV de tablas")
    parser.add_argument("--only-csv", action="store_true",
                        help="Solo exportar CSV (sin GeoJSON, SHP ni HTML)")

    args = parser.parse_args()

    # Validar archivo
    if not os.path.exists(args.gtfs_zip):
        print(f"❌ Archivo no encontrado: {args.gtfs_zip}")
        sys.exit(1)

    if not args.gtfs_zip.lower().endswith('.zip'):
        print(f"⚠️  El archivo no tiene extensión .zip: {args.gtfs_zip}")

    # Parsear
    print(f"\n{'='*60}")
    print(f"  🚍 GTFStoCSV v1.0.0 — Equipo Kaizen (Ineco)")
    print(f"{'='*60}")
    print(f"  📂 Archivo: {args.gtfs_zip}")
    print(f"  📁 Salida:  {args.output}/")
    print()

    print("⏳ Parseando GTFS...")
    try:
        gtfs = GTFSParser(args.gtfs_zip)
        gtfs.parse()
    except Exception as e:
        print(f"❌ Error al parsear GTFS: {e}")
        sys.exit(1)

    print()
    print(gtfs.summary_text())
    print()

    # Crear directorio de salida
    os.makedirs(args.output, exist_ok=True)

    # CSV — Tablas GTFS individuales
    if not args.only_csv and not args.no_csv:
        csv_dir = os.path.join(args.output, "csv")
        print("📥 Exportando tablas CSV...")
        exported = export_table_summary(gtfs, csv_dir)
        print(f"   {len(exported)} tablas exportadas: {', '.join(exported)}")
        print()

    # GeoJSON — Todas las rutas
    if not args.only_csv:
        print("🌐 Exportando GeoJSON...")
        geojson_path = export_all_geojson(gtfs, args.output)
        print()

    # SHP — Shapefiles
    if not args.no_shp and not args.only_csv:
        print("🗺️  Exportando SHP...")
        shp_path = os.path.join(args.output, "todas_las_rutas.shp.zip")
        export_shp_zip(gtfs, shp_path)
        print()

    # Visor HTML
    if not args.no_html and not args.only_csv:
        print("🖥️  Generando visor HTML...")
        html_path = generar_visor(gtfs, args.output)
        print()

    # Resumen final
    print(f"{'='*60}")
    print(f"  ✅ ¡Hecho! Archivos generados en {args.output}/")
    if not args.only_csv:
        if not args.no_html:
            print(f"  🖥️  Visor:    {args.output}/visor.html  (ábrelo con doble clic)")
        print(f"  🌐 GeoJSON: {geojson_path}")
        if not args.no_shp:
            print(f"  🗺️  SHP:     {shp_path}")
    if not args.no_csv or args.only_csv:
        print(f"  📋 CSV:     {args.output}/csv/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()