"""Genera una ruta LCP por perfil y la exporta a data/processed/Rutas/.

Uso:
    python -m src.trazados.run_trazados --escenario A
    python -m src.trazados.run_trazados --escenario B
    python -m src.trazados.run_trazados --escenario ambos

Para cada perfil definido en data/config/perfiles.yaml genera:
    Rutas/ruta_{escenario}_{perfil}.gpkg
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import yaml
from shapely.geometry import LineString

from src.trazados.lcp import Ruta, camino_minimo_coste

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
DATA = _ROOT / "data"
CONFIG = DATA / "config"
TRAZADOS = DATA / "processed" / "Trazados"
RUTAS = DATA / "processed" / "Rutas"

ESCENARIO_YAML = CONFIG / "escenario.yaml"
PERFILES_YAML = CONFIG / "perfiles.yaml"

_NODATA = -9999.0
_BARRERA_DISCO = 999.0


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _utm_to_rowcol(
    x: float, y: float, transform: rasterio.transform.Affine
) -> tuple[int, int]:
    """Coordenadas UTM (x, y) → (row, col) en la rejilla del raster."""
    col = int(round((x - transform.c) / transform.a))
    row = int(round((y - transform.f) / transform.e))
    return row, col


def _snap_to_valid(
    row: int,
    col: int,
    superficie: np.ndarray,
    radio: int = 20,
) -> tuple[int, int]:
    """Mueve (row, col) al vecino válido más cercano si cae en nodata/barrera.

    Busca en espiral cuadrada hasta radio celdas. Lanza ValueError si no encuentra.
    """
    height, width = superficie.shape

    def _valida(r: int, c: int) -> bool:
        if not (0 <= r < height and 0 <= c < width):
            return False
        v = superficie[r, c]
        return not (np.isnan(v) or np.isinf(v))

    if _valida(row, col):
        return row, col

    best_dist, best = float("inf"), None
    for dr in range(-radio, radio + 1):
        for dc in range(-radio, radio + 1):
            r, c = row + dr, col + dc
            if _valida(r, c):
                dist = dr * dr + dc * dc
                if dist < best_dist:
                    best_dist, best = dist, (r, c)

    if best is None:
        raise ValueError(
            f"No hay celda válida en radio {radio} alrededor de ({row}, {col})"
        )
    log.info("  snap (%d, %d) → (%d, %d)  [distancia %.1f celdas]",
             row, col, best[0], best[1], best_dist ** 0.5)
    return best


def _superficie_para_perfil(
    escenario: str,
    pesos: dict[str, float],
) -> tuple[np.ndarray, rasterio.transform.Affine, str]:
    """Devuelve (array_coste, transform, crs_wkt) para un perfil dado.

    Placeholder: carga la superficie de pesos iguales ya generada en Trazados/.
    TODO(S4): sustituir por combinar.run(escenario, pesos=pesos) cuando combinar
              acepte un dict de pesos por capa.
    """
    tif = TRAZADOS / f"superficie_{escenario.upper()}.tif"
    if not tif.exists():
        raise FileNotFoundError(
            f"Superficie no encontrada: {tif}\n"
            f"Ejecuta primero: python -m src.superficie.combinar --escenario {escenario}"
        )
    with rasterio.open(tif) as src:
        arr = src.read(1).astype("float64")
        transform = src.transform
        crs_wkt = src.crs.wkt

    # Restaurar semántica interna: valores de disco → nan / inf
    arr = np.where(arr == _NODATA, np.nan, arr)
    arr = np.where(arr == _BARRERA_DISCO, np.inf, arr)
    return arr, transform, crs_wkt


def _guardar_gpkg(
    ruta: Ruta,
    transform: rasterio.transform.Affine,
    crs_wkt: str,
    path: Path,
) -> None:
    """Exporta una Ruta a GeoPackage con sus atributos."""
    linea: LineString = ruta.como_linea(transform)
    gdf = gpd.GeoDataFrame(
        {
            "perfil": [ruta.perfil],
            "coste_relativo": [round(ruta.coste_relativo, 6)],
            "n_celdas": [len(ruta.celdas)],
            "longitud_m": [round(linea.length, 1)],
        },
        geometry=[linea],
        crs=crs_wkt,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GPKG")


# ── Lógica principal ──────────────────────────────────────────────────────────


def run_escenario(escenario: str) -> list[Path]:
    """Genera una ruta LCP por perfil para el escenario indicado.

    Devuelve la lista de GPKGs escritos.
    """
    s = escenario.upper()
    cfg_esc = _load_yaml(ESCENARIO_YAML)
    cfg_per = _load_yaml(PERFILES_YAML)

    esc = cfg_esc[f"escenario_{s}"]
    origen_utm = (esc["origen"]["x"], esc["origen"]["y"])
    destino_utm = (esc["destino"]["x"], esc["destino"]["y"])

    salidas: list[Path] = []

    for perfil in cfg_per["perfiles"]:
        pid: str = perfil["id"]
        pesos: dict[str, float] = perfil["pesos"]
        log.info("[%s/%s] superficie con pesos=%s …", s, pid, pesos)

        superficie, transform, crs_wkt = _superficie_para_perfil(s, pesos)

        origen_rc = _snap_to_valid(*_utm_to_rowcol(*origen_utm, transform), superficie)
        destino_rc = _snap_to_valid(*_utm_to_rowcol(*destino_utm, transform), superficie)
        log.info("[%s/%s] origen=%s  destino=%s", s, pid, origen_rc, destino_rc)

        ruta = camino_minimo_coste(superficie, origen_rc, destino_rc, pid)

        out_path = RUTAS / f"ruta_{s}_{pid}.gpkg"
        _guardar_gpkg(ruta, transform, crs_wkt, out_path)
        log.info(
            "[%s/%s] guardado: %s  coste=%.6f  longitud=%.0f m",
            s, pid, out_path.name, ruta.coste_relativo,
            gpd.read_file(out_path).geometry.iloc[0].length,
        )
        salidas.append(out_path)

    return salidas


# ── Verificación ──────────────────────────────────────────────────────────────


def _verify(paths: list[Path]) -> None:
    for p in paths:
        gdf = gpd.read_file(p)
        row = gdf.iloc[0]
        print(f"  {p.name}")
        print(f"    perfil    : {row['perfil']}")
        print(f"    longitud  : {row['longitud_m']:.1f} m")
        print(f"    coste     : {row['coste_relativo']:.6f}")
        print(f"    vértices  : {len(row.geometry.coords)}")
        print(f"    CRS       : EPSG:{gdf.crs.to_epsg()}")


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Motor LCP: genera una ruta por perfil.")
    parser.add_argument(
        "--escenario", choices=["A", "B", "ambos"], default="ambos",
    )
    args = parser.parse_args()

    scenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario]
    for sc in scenarios:
        print(f"\n{'='*60}\n  Escenario {sc}\n{'='*60}")
        try:
            out = run_escenario(sc)
            print(f"\n  Verificación ({len(out)} rutas):")
            _verify(out)
        except FileNotFoundError as e:
            print(f"  [ERROR] {e}")
        except NotImplementedError as e:
            print(f"  [PENDIENTE] {e}")
