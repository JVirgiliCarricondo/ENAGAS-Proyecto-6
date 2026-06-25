"""Métrica de Persona 1 — longitud y coste relativo de una ruta.

Calcula, para una ruta ya generada (LineString sobre la rejilla común):

  · longitud_km     — longitud total de la geometría, en kilómetros.
  · coste_relativo  — índice ADIMENSIONAL [0, 1] del coste de tránsito de la
                      ruta, NUNCA en €. Se obtiene muestreando la superficie de
                      coste a lo largo del trazado y normalizando contra el
                      rango válido de esa misma superficie.

Entradas (según el reparto del equipo, Persona 1):
  · geometría de la ruta  → data/processed/Rutas/ruta_{s}_{perfil}.gpkg
  · superficie de coste   → data/processed/Trazados/superficie_{s}.tif

La superficie de referencia es SIEMPRE la de pesos iguales del escenario
(superficie_{s}.tif), NO la del perfil. Esto garantiza que el coste_relativo
sea comparable entre rutas: todas se miden sobre la misma escala neutral.
El índice [0, 1] indica la posición del coste medio del trazado dentro del
rango válido de esa superficie (0 = terreno más barato; 1 = más caro).

Convenios heredados del pipeline (Modelo_Coste.md §9):
  · CRS común EPSG:25830 (metros) → la longitud sale directa de la geometría.
  · nodata fuera del AOI = -9999.0 ; barrera dura = 999.0 (se excluyen del rango).

Uso (desde proyecto/):
  python -m src.metricas.longitud                      # escenarios A y B, todos los perfiles
  python -m src.metricas.longitud --escenario A
  python -m src.metricas.longitud --escenario B --perfil equilibrio
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import LineString

# ── Rutas del proyecto (mismo patrón que src/superficie/config.py) ────────────
_ROOT = Path(__file__).resolve().parents[2]
DATA = _ROOT / "data" / "processed"
RUTAS = DATA / "Rutas"
TRAZADOS = DATA / "Trazados"

# Convenios de codificación de las superficies de coste (Modelo_Coste.md §9).
_NODATA = -9999.0
_BARRERA_DISCO = 999.0

# Perfiles de prioridad disponibles (data/config/perfiles.yaml).
PERFILES = ["corto", "ambiental", "pendiente", "equilibrio"]


# ── Carga de entradas ─────────────────────────────────────────────────────────
def cargar_ruta(path: str | Path) -> LineString:
    """Lee el .gpkg de la ruta y devuelve su geometría como LineString."""
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise ValueError(f"La ruta {path} no contiene geometrías.")
    geom = gdf.geometry.iloc[0]
    if geom.geom_type != "LineString":
        raise ValueError(f"Se esperaba LineString, no {geom.geom_type} ({path}).")
    return geom


# ── Métrica 1: longitud ───────────────────────────────────────────────────────
def longitud_km(geom: LineString) -> float:
    """Longitud total de la ruta en kilómetros.

    La geometría está en EPSG:25830 (metros), así que la longitud del polígono
    de la línea ya está en metros; basta con dividir entre 1000.
    """
    return geom.length / 1000.0


# ── Muestreo de la superficie a lo largo de la ruta ──────────────────────────
def _muestrear_coste(
    geom: LineString, superficie_path: str | Path, paso_m: float | None = None
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Muestrea la superficie de coste a lo largo de la ruta.

    Densifica la línea cada `paso_m` (por defecto media celda) y lee el coste de
    la superficie en cada punto. Devuelve:
      costes    — coste de tránsito en cada punto muestreado (sin nodata/barrera),
      pasos_m   — longitud (m) del segmento asociado a cada punto interior,
      c_min,c_max — rango VÁLIDO de la superficie (para normalizar a [0, 1]).
    """
    with rasterio.open(superficie_path) as src:
        arr = src.read(1).astype("float64")
        transform = src.transform
        nodata = src.nodata if src.nodata is not None else _NODATA
        res = abs(src.res[0])

        if paso_m is None:
            paso_m = res / 2.0  # Nyquist sobre la rejilla: media celda

        # Puntos equiespaciados a lo largo de la línea (incluye inicio y fin).
        n = max(2, int(np.ceil(geom.length / paso_m)) + 1)
        dists = np.linspace(0.0, geom.length, n)
        puntos = [geom.interpolate(d) for d in dists]
        xs = np.array([p.x for p in puntos])
        ys = np.array([p.y for p in puntos])

        rows, cols = rasterio.transform.rowcol(transform, xs, ys)
        rows = np.clip(np.asarray(rows), 0, arr.shape[0] - 1)
        cols = np.clip(np.asarray(cols), 0, arr.shape[1] - 1)
        costes = arr[rows, cols]

    # Rango válido de la superficie (excluye nodata y barrera dura).
    valido = arr[(arr != nodata) & (arr != _BARRERA_DISCO) & np.isfinite(arr)]
    c_min, c_max = float(valido.min()), float(valido.max())

    # Si algún punto cayó en nodata/barrera (no debería: la ruta vive en el AOI),
    # se sustituye por el coste válido más cercano para no romper la media.
    invalida = (costes == nodata) | (costes == _BARRERA_DISCO) | ~np.isfinite(costes)
    if invalida.any():
        costes = costes.copy()
        costes[invalida] = np.interp(
            np.flatnonzero(invalida),
            np.flatnonzero(~invalida),
            costes[~invalida],
        )

    # Longitud del segmento representado por cada punto (trapecio sobre la línea).
    pasos = np.diff(dists)
    return costes, pasos, c_min, c_max


# ── Métrica 2: coste relativo ─────────────────────────────────────────────────
def coste_total_indice(geom: LineString, superficie_path: str | Path) -> float:
    """Coste de tránsito ACUMULADO a lo largo de la ruta (índice·km).

    Integral ∫ C(s) ds del coste de la superficie sobre el trazado, con C en
    índice adimensional y s en km. Es la magnitud que minimiza el LCP; se expone
    para trazabilidad, pero NO es comparable entre perfiles sin normalizar.
    """
    costes, pasos, _, _ = _muestrear_coste(geom, superficie_path)
    # Trapecio: cada segmento usa la media del coste de sus dos extremos.
    coste_seg = 0.5 * (costes[:-1] + costes[1:])
    return float(np.sum(coste_seg * pasos) / 1000.0)


def coste_medio(geom: LineString, superficie_path: str | Path) -> float:
    """Coste de tránsito MEDIO por metro recorrido (índice adimensional crudo)."""
    costes, pasos, _, _ = _muestrear_coste(geom, superficie_path)
    coste_seg = 0.5 * (costes[:-1] + costes[1:])
    total = float(np.sum(coste_seg * pasos))
    return total / geom.length if geom.length > 0 else 0.0


def coste_relativo(geom: LineString, superficie_path: str | Path) -> float:
    """Índice de coste relativo de la ruta en [0, 1] (NUNCA €).

    Normaliza el coste medio del trazado contra el rango válido [c_min, c_max]
    de la superficie sobre la que se generó:

        coste_relativo = (coste_medio − c_min) / (c_max − c_min)

    0 → la ruta se mantuvo en el terreno más barato de su superficie;
    1 → la ruta recorrió únicamente el terreno más caro.

    Referencia: superficie_{s}.tif (pesos iguales). Todas las rutas del mismo
    escenario se normalizan contra el mismo rango, por lo que los valores son
    directamente comparables entre perfiles.
    """
    costes, pasos, c_min, c_max = _muestrear_coste(geom, superficie_path)
    coste_seg = 0.5 * (costes[:-1] + costes[1:])
    medio = float(np.sum(coste_seg * pasos)) / geom.length if geom.length > 0 else 0.0
    if c_max <= c_min:
        return 0.0
    return float(np.clip((medio - c_min) / (c_max - c_min), 0.0, 1.0))


# ── Orquestación por escenario + perfil ───────────────────────────────────────
def _resolver_paths(s: str, perfil: str) -> tuple[Path, Path]:
    ruta = RUTAS / f"ruta_{s}_{perfil}.gpkg"
    superficie = TRAZADOS / f"superficie_{s}.tif"   # superficie común del escenario
    if not ruta.exists():
        raise FileNotFoundError(f"Falta la ruta: {ruta}")
    if not superficie.exists():
        raise FileNotFoundError(f"Falta la superficie: {superficie}")
    return ruta, superficie


def metricas_longitud(s: str, perfil: str) -> dict:
    """Devuelve {perfil, longitud_km, coste_relativo, ...} para un escenario+perfil.

    Salida pensada para que la consuma el orquestador (src/metricas/calculo.py)
    y alimente la tabla comparativa (src/comparacion/).
    """
    ruta_path, superficie_path = _resolver_paths(s, perfil)
    geom = cargar_ruta(ruta_path)
    return {
        "escenario": s,
        "perfil": perfil,
        "longitud_km": round(longitud_km(geom), 3),
        "coste_relativo": round(coste_relativo(geom, superficie_path), 3),
        # Magnitudes crudas (trazabilidad; no entran en la tabla final):
        "coste_medio": round(coste_medio(geom, superficie_path), 4),
        "coste_total_indice": round(coste_total_indice(geom, superficie_path), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Longitud y coste relativo de las rutas (Persona 1)."
    )
    parser.add_argument("--escenario", choices=["A", "B", "ambos"], default="ambos")
    parser.add_argument(
        "--perfil", choices=PERFILES + ["todos"], default="todos",
        help="perfil de prioridad (def: todos)",
    )
    args = parser.parse_args()

    escenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario]
    perfiles = PERFILES if args.perfil == "todos" else [args.perfil]

    for s in escenarios:
        print(f"\n=== Escenario {s} ===")
        print(f"{'perfil':12s} {'longitud_km':>12s} {'coste_relativo':>15s} {'coste_medio':>12s}")
        for perfil in perfiles:
            try:
                m = metricas_longitud(s, perfil)
            except FileNotFoundError as e:
                print(f"{perfil:12s}  (omitido: {e})")
                continue
            print(f"{m['perfil']:12s} {m['longitud_km']:12.3f} "
                  f"{m['coste_relativo']:15.3f} {m['coste_medio']:12.4f}")


if __name__ == "__main__":
    main()
