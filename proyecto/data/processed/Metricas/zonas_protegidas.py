"""
Métrica — % de cada ruta solución que pasa por zona protegida (Red Natura 2000).

Para los escenarios A y B y para cada ruta solución (ramal) de
data/processed/Rutas/ruta_{s}_{perfil}.gpkg, mide qué porcentaje de la
LONGITUD de la ruta cae dentro de zona protegida.

Fuente de "protegido": el raster binario de coste
data/processed/Capas_Coste/protegida_{s}.tif (1 = dentro de Red Natura,
0 = fuera), ya alineado a la rejilla común (EPSG:25830). Ver el script que lo
genera en src/superficie/zonas_protegidas.py.

Método (porcentaje por longitud, no por nº de celdas):
  1. Se densifica la línea de la ruta en pasos de media celda (res/2) para no
     saltarse ninguna celda del raster.
  2. Cada sub-segmento se clasifica muestreando el raster en su punto medio:
     valor > 0 -> el segmento va por zona protegida.
  3. pct = (longitud dentro de protegido) / (longitud total) * 100.

Solo imprime por consola (sin ficheros de salida).

Uso (desde proyecto/):
  python data/processed/Metricas/zonas_protegidas.py
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import LineString, MultiLineString

# data/processed/Metricas/zonas_protegidas.py -> parents[1] = data/processed
PROCESSED = Path(__file__).resolve().parents[1]
RUTAS_DIR = PROCESSED / "Rutas"
CAPAS_DIR = PROCESSED / "Capas_Coste"

ESCENARIOS = ["A", "B"]
NODATA = -9999.0


def _iter_segmentos(geom) -> list[tuple[float, float, float, float, float]]:
    """Devuelve los vértices de una geometría (LineString/MultiLineString)
    como lista de líneas, cada una como secuencia de coordenadas."""
    if isinstance(geom, LineString):
        return [list(geom.coords)]
    if isinstance(geom, MultiLineString):
        return [list(part.coords) for part in geom.geoms]
    raise TypeError(f"Geometría no soportada: {geom.geom_type}")


def medir_ruta(linea_coords: list, arr: np.ndarray, transform: rasterio.Affine,
               paso: float) -> tuple[float, float]:
    """Recorre una polilínea muestreando el raster en el punto medio de cada
    sub-segmento de longitud 'paso'. Devuelve (longitud_total, longitud_protegida)."""
    H, W = arr.shape
    total = 0.0
    protegida = 0.0
    inv_a = 1.0 / transform.a
    inv_e = 1.0 / transform.e

    for (x0, y0), (x1, y1) in zip(linea_coords[:-1], linea_coords[1:]):
        seg_len = float(np.hypot(x1 - x0, y1 - y0))
        if seg_len == 0.0:
            continue
        n = max(1, int(np.ceil(seg_len / paso)))
        for k in range(n):
            # punto medio del sub-segmento k
            t = (k + 0.5) / n
            xm = x0 + t * (x1 - x0)
            ym = y0 + t * (y1 - y0)
            col = int((xm - transform.c) * inv_a)
            row = int((ym - transform.f) * inv_e)
            sub_len = seg_len / n
            total += sub_len
            if 0 <= row < H and 0 <= col < W:
                v = arr[row, col]
                if v != NODATA and v > 0:
                    protegida += sub_len
    return total, protegida


def procesar_escenario(s: str) -> None:
    protegida_path = CAPAS_DIR / f"protegida_{s}.tif"
    if not protegida_path.exists():
        raise FileNotFoundError(f"No existe el raster de protegidas: {protegida_path}")

    with rasterio.open(protegida_path) as src:
        arr = src.read(1)
        transform = src.transform
    res = abs(transform.a)
    paso = res / 2.0

    rutas = sorted(RUTAS_DIR.glob(f"ruta_{s}_*.gpkg"))
    if not rutas:
        print(f"[{s}] sin rutas en {RUTAS_DIR}")
        return

    print(f"\n=== Escenario {s}  (raster {protegida_path.name}, celda {res:.0f} m) ===")
    print(f"  {'perfil':12s} {'long_total_km':>14s} {'km_protegida':>13s} {'% protegida':>12s}")
    for ruta_path in rutas:
        # perfil = sufijo tras 'ruta_{s}_'
        perfil = ruta_path.stem[len(f"ruta_{s}_"):]
        gdf = gpd.read_file(ruta_path)
        if gdf.crs is not None and gdf.crs.to_epsg() != 25830:
            gdf = gdf.to_crs(25830)

        total = 0.0
        protegida = 0.0
        for geom in gdf.geometry:
            if geom is None or geom.is_empty:
                continue
            for coords in _iter_segmentos(geom):
                t, p = medir_ruta(coords, arr, transform, paso)
                total += t
                protegida += p

        pct = (100.0 * protegida / total) if total > 0 else 0.0
        print(f"  {perfil:12s} {total / 1000:>14.2f} {protegida / 1000:>13.2f} {pct:>11.1f}%")


def main() -> None:
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("\nMétrica de zonas protegidas completada (A y B).")


if __name__ == "__main__":
    main()
