"""Métrica — % de cada ruta solución que pasa por zona protegida (Red Natura 2000).

Para cada ruta (.gpkg de Rutas/) mide qué porcentaje de su LONGITUD discurre
dentro de zona protegida, muestreando el raster binario de coste
Capas_Coste/protegida_{s}.tif (1 = dentro de Red Natura, 0 = fuera), ya alineado
a la rejilla común EPSG:25830. El raster lo genera src/superficie/zonas_protegidas.py.

Porcentaje por LONGITUD (no por nº de celdas): la línea se densifica en pasos de
media celda y cada sub-segmento se clasifica por el valor del raster en su punto
medio.

Interfaz común del módulo de métricas:
    calcular(linea, escenario) -> dict[str, float]

Uso standalone (desde proyecto/):
    python -m src.metricas.zonas_protegidas
    python -m src.metricas.zonas_protegidas --escenario A
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry

CRS_TRABAJO = "EPSG:25830"

BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
CAPAS_DIR = BASE / "Capas_Coste"
RUTAS_DIR = BASE / "Rutas"

ESCENARIOS = ["A", "B"]
PERFILES = ["corto", "equilibrio", "ambiental", "pendiente"]

NODATA = -9999.0


def _coords_de(geom: BaseGeometry) -> list[list]:
    """Vértices de una geometría lineal como lista de polilíneas (lista de coords)."""
    if isinstance(geom, LineString):
        return [list(geom.coords)]
    if isinstance(geom, MultiLineString):
        return [list(part.coords) for part in geom.geoms]
    raise TypeError(f"Geometría no soportada: {geom.geom_type}")


def _medir_polilinea(
    coords: list, arr: np.ndarray, transform: rasterio.Affine, paso: float
) -> tuple[float, float]:
    """Longitud total y longitud protegida de una polilínea, por muestreo del raster.

    Mide POR LONGITUD (no por celdas): cada segmento de la polilínea se parte en
    sub-segmentos de longitud ~``paso``, y cada sub-segmento se clasifica leyendo
    el raster en su punto medio (conversión coordenada→celda con la afín inversa).
    Si esa celda está protegida, la longitud del sub-segmento suma a la parte protegida.

    Args:
        coords: Vértices de la polilínea [(x, y), ...] en EPSG:25830.
        arr: Raster binario de protección (>0 = Red Natura; NODATA = sin dato).
        transform: Transformación afín del raster (para coordenada→celda).
        paso: Longitud objetivo de cada sub-segmento (m); media celda por defecto.

    Returns:
        (longitud_total_m, longitud_protegida_m) de esta polilínea, en metros.
    """
    H, W = arr.shape
    # Inversos de la afín precalculados: coordenada→celda es (coord - origen)/tamaño.
    inv_a = 1.0 / transform.a
    inv_e = 1.0 / transform.e
    total = 0.0
    protegida = 0.0

    for (x0, y0), (x1, y1) in zip(coords[:-1], coords[1:]):
        seg_len = float(np.hypot(x1 - x0, y1 - y0))
        if seg_len == 0.0:
            continue
        # Densificar: partir el segmento en n trozos de longitud ~paso (media celda),
        # para no saltarse ninguna celda que el segmento atraviese.
        n = max(1, int(np.ceil(seg_len / paso)))
        sub_len = seg_len / n
        for k in range(n):
            t = (k + 0.5) / n  # punto medio del sub-segmento k (fracción del segmento)
            xm = x0 + t * (x1 - x0)
            ym = y0 + t * (y1 - y0)
            # Coordenada UTM → índice de celda (col, row) del raster.
            col = int((xm - transform.c) * inv_a)
            row = int((ym - transform.f) * inv_e)
            total += sub_len
            # Celda dentro del raster y con valor de dato positivo → protegida.
            if 0 <= row < H and 0 <= col < W:
                v = arr[row, col]
                if v != NODATA and v > 0:
                    protegida += sub_len
    return total, protegida


def calcular(linea: BaseGeometry, escenario: str) -> dict[str, float]:
    """Porcentaje de la longitud de la ruta dentro de zona protegida.

    Args:
        linea:     geometría de la ruta (LineString/MultiLineString) en EPSG:25830.
        escenario: 'A' o 'B'.

    Returns:
        dict con:
          km_total      longitud total de la ruta (km)
          km_protegida  longitud dentro de Red Natura 2000 (km)
          pct_protegida porcentaje de la longitud dentro de protegido (0-100)

    Raises:
        FileNotFoundError: Si no existe el raster protegida_{s}.tif del escenario.
    """
    s = escenario.upper()
    protegida_path = CAPAS_DIR / f"protegida_{s}.tif"
    if not protegida_path.exists():
        raise FileNotFoundError(
            f"Raster de zonas protegidas no encontrado: {protegida_path}\n"
            f"Ejecuta primero src/superficie/zonas_protegidas.py"
        )

    with rasterio.open(protegida_path) as src:
        arr = src.read(1)
        transform = src.transform
    paso = abs(transform.a) / 2.0  # media celda: no se salta ninguna celda

    total = 0.0
    protegida = 0.0
    if linea is not None and not linea.is_empty:
        for coords in _coords_de(linea):
            t, p = _medir_polilinea(coords, arr, transform, paso)
            total += t
            protegida += p

    pct = (100.0 * protegida / total) if total > 0 else 0.0
    return {
        "km_total": round(total / 1000, 4),
        "km_protegida": round(protegida / 1000, 4),
        "pct_protegida": round(pct, 2),
    }


def _cargar_linea(perfil: str, escenario: str) -> BaseGeometry:
    s = escenario.upper()
    path = RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg"
    if not path.exists():
        raise FileNotFoundError(f"Ruta no encontrada: {path}")
    gdf = gpd.read_file(path)
    if gdf.crs is not None and gdf.crs.to_epsg() != 25830:
        gdf = gdf.to_crs(CRS_TRABAJO)
    return gdf.geometry.iloc[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="% de cada ruta que pasa por zona protegida (Red Natura 2000)."
    )
    parser.add_argument("--escenario", default="ambos",
                        help="id de escenario.yaml (p. ej. A, B o C) o 'ambos' (=A y B)")
    args = parser.parse_args()

    escenarios = ESCENARIOS if args.escenario == "ambos" else [args.escenario.upper()]
    for s in escenarios:
        print(f"\n=== Escenario {s} ===")
        print(f"  {'perfil':12s} {'km_total':>9s} {'km_protegida':>13s} {'% protegida':>12s}")
        for perfil in PERFILES:
            try:
                linea = _cargar_linea(perfil, s)
                m = calcular(linea, s)
                print(
                    f"  {perfil:12s} {m['km_total']:>9.2f} "
                    f"{m['km_protegida']:>13.2f} {m['pct_protegida']:>11.1f}%"
                )
            except FileNotFoundError as e:
                print(f"  {perfil:12s} [OMITIDA] {e}")


if __name__ == "__main__":
    main()
