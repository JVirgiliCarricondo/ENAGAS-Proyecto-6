"""
Fase 2 — Ruta con LCP ISÓTROPO por perfil de prioridad.

La superficie escalar ponderada de cada perfil (Σ peso_capa · capa, con el TPI
como descriptor del relieve) decide DÓNDE hay coste. El motor busca el camino de
mínimo coste origen→destino sobre esa superficie.

Coste de transición p→q:

    coste(p→q) = d · C_celda

  d       = distancia geométrica del paso (1 ortogonal, √2 diagonal)
  C_celda = media del coste escalar de p y q (superficie ponderada del perfil)

Algoritmo: Dijkstra 8-conexo. La preferencia por el relieve (seguir divisorias,
evitar valles y fondos de cauce) la aporta la capa TPI dentro de la superficie
escalar; ya no se modela la dirección del gradiente (anisotropía retirada).

Genera, por escenario, una ruta por perfil en Rutas/:
  ruta_{s}_{perfil}.gpkg

Uso (desde proyecto/):
  python -m src.trazados.ruta_pendiente
  python -m src.trazados.ruta_pendiente --escenario A
"""

from __future__ import annotations

import argparse
import heapq
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.transform as rt
import yaml
from shapely.geometry import LineString

try:
    from ..superficie.combinar import combinar_pesos
except ImportError:
    from superficie.combinar import combinar_pesos

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
DATA = _ROOT / "data"
CONFIG = DATA / "config"
TRAZADOS = DATA / "processed" / "Trazados"   # superficies escalares (.tif)
RUTAS_DIR = DATA / "processed" / "Rutas"     # rutas LCP (.gpkg)

_NODATA = -9999.0
_BARRERA_DISCO = 999.0

_VECINOS = [(-1, -1), (-1, 0), (-1, 1), (0, -1),
            (0, 1), (1, -1), (1, 0), (1, 1)]

# Colores RGBA por perfil/tipo para identificar rutas en QGIS (paleta ColorBrewer Set1).
_COLOR_RUTA = {
    "corto":      "31,120,180,255",   # azul
    "equilibrio": "255,127,0,255",    # naranja
    "ambiental":  "51,160,44,255",    # verde
    "pendiente":  "227,26,28,255",    # rojo (perfil 'pendiente', ahora basado en TPI)
}


def _utm_to_rowcol(x: float, y: float, transform: rasterio.Affine) -> tuple[int, int]:
    """Coordenadas UTM (x, y) → (row, col). (idéntico a run_trazados)."""
    col = int(round((x - transform.c) / transform.a))
    row = int(round((y - transform.f) / transform.e))
    return row, col


def _snap_to_valid(row: int, col: int, superficie: np.ndarray, radio: int = 20) -> tuple[int, int]:
    """Mueve (row, col) al vecino válido más cercano si cae en nodata/barrera."""
    H, W = superficie.shape

    def _valida(r: int, c: int) -> bool:
        return 0 <= r < H and 0 <= c < W and np.isfinite(superficie[r, c])

    if _valida(row, col):
        return row, col
    best_dist, best = float("inf"), None
    for dr in range(-radio, radio + 1):
        for dc in range(-radio, radio + 1):
            r, c = row + dr, col + dc
            if _valida(r, c) and dr * dr + dc * dc < best_dist:
                best_dist, best = dr * dr + dc * dc, (r, c)
    if best is None:
        raise ValueError(f"No hay celda válida en radio {radio} alrededor de ({row}, {col})")
    log.info("  snap (%d,%d) → %s [%.1f celdas]", row, col, best, best_dist ** 0.5)
    return best


def dijkstra(
    C: np.ndarray,
    origen: tuple[int, int], destino: tuple[int, int],
) -> list[tuple[int, int]]:
    """LCP 8-conexo isótropo: coste(p→q) = d · media(C_p, C_q)."""
    H, W = C.shape
    transitable = np.isfinite(C)  # nan (fuera) e inf (barrera) → no transitable
    INF = float("inf")
    dist = np.full(H * W, INF)
    prev = np.full(H * W, -1, dtype=np.int64)

    so = origen[0] * W + origen[1]
    sd = destino[0] * W + destino[1]
    dist[so] = 0.0
    pq: list[tuple[float, int]] = [(0.0, so)]

    while pq:
        d_p, p = heapq.heappop(pq)
        if d_p > dist[p]:
            continue
        if p == sd:
            break
        r, c = divmod(p, W)
        cp = C[r, c]
        for dr, dc in _VECINOS:
            rr, cc = r + dr, c + dc
            if not (0 <= rr < H and 0 <= cc < W) or not transitable[rr, cc]:
                continue
            step = dr * dr + dc * dc
            d = 1.0 if step == 1 else np.sqrt(2.0)
            c_cell = 0.5 * (cp + C[rr, cc])

            nd = d_p + d * c_cell
            q = rr * W + cc
            if nd < dist[q]:
                dist[q] = nd
                prev[q] = p
                heapq.heappush(pq, (nd, q))

    if prev[sd] == -1 and sd != so:
        raise RuntimeError("No se encontró ruta origen→destino (¿barreras lo aíslan?)")

    celdas: list[tuple[int, int]] = []
    cur = sd
    while cur != -1:
        celdas.append(divmod(cur, W))
        if cur == so:
            break
        cur = prev[cur]
    celdas.reverse()
    return celdas


def _write_route_qml(path: Path, tipo: str) -> None:
    """Estilo QGIS para una ruta: línea de color fijo según el perfil."""
    color = _COLOR_RUTA.get(tipo, "128,128,128,255")
    qml = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <renderer-v2 type="singleSymbol" forcerasterrender="0" enableorderby="0" symbollevels="0">
    <symbols>
      <symbol type="line" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleLine" enabled="1" pass="0" locked="0">
          <prop k="line_color" v="{color}"/>
          <prop k="line_style" v="solid"/>
          <prop k="line_width" v="0.5"/>
          <prop k="line_width_unit" v="MM"/>
          <prop k="capstyle" v="round"/>
          <prop k="joinstyle" v="round"/>
          <prop k="offset" v="0"/>
          <prop k="offset_unit" v="MM"/>
        </layer>
      </symbol>
    </symbols>
    <rotation/>
    <sizescale/>
  </renderer-v2>
</qgis>"""
    path.with_suffix(".qml").write_text(qml, encoding="utf-8")


def _exportar(celdas, transform, crs, tipo: str, path: Path) -> LineString:
    linea = LineString([rt.xy(transform, r, c, offset="center") for r, c in celdas])
    gdf = gpd.GeoDataFrame(
        {"tipo": [tipo], "n_celdas": [len(celdas)],
         "longitud_m": [round(linea.length, 1)]},
        geometry=[linea], crs=crs,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GPKG")
    _write_route_qml(path, tipo)
    return linea


def _write_qml(tif_path: Path, vmin: float, vmax: float) -> None:
    """Leyenda verde→amarillo→rojo para QGIS (mismo esquema que combinar.py / main)."""
    mid = (vmin + vmax) / 2
    qml = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer opacity="1" alphaBand="-1" band="1" type="singlebandpseudocolor"
      classificationMin="{vmin:.4f}" classificationMax="{vmax:.4f}" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0"
          minimumValue="{vmin:.4f}" maximumValue="{vmax:.4f}"
          classificationMode="1" labelPrecision="3">
          <item value="{vmin:.4f}" color="#1a9850" label="Coste bajo"  alpha="255"/>
          <item value="{mid:.4f}" color="#ffffbf" label="Coste medio" alpha="255"/>
          <item value="{vmax:.4f}" color="#d73027" label="Coste alto"  alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>"""
    tif_path.with_suffix(".qml").write_text(qml, encoding="utf-8")


def _guardar_superficie(C: np.ndarray, transform, crs, path: Path) -> None:
    """Guarda la superficie escalar de un perfil + su leyenda de color (.qml).

    nan→-9999, inf→999 (convenio de combinar.py).
    """
    out = np.where(np.isposinf(C), _BARRERA_DISCO, C)
    out = np.where(np.isnan(out), _NODATA, out).astype("float32")
    profile = dict(driver="GTiff", dtype="float32", count=1,
                   height=C.shape[0], width=C.shape[1],
                   transform=transform, crs=crs, nodata=_NODATA, compress="lzw")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(out, 1)

    valido = out[(out != _NODATA) & (out != _BARRERA_DISCO)]
    if valido.size:
        _write_qml(path, float(valido.min()), float(valido.max()))


def run_perfiles(s: str, perfiles_override: list[dict] | None = None) -> None:
    """Genera una ruta LCP isótropa por perfil de prioridad.

    Args:
        s: Identificador de escenario (p. ej. 'A').
        perfiles_override: Lista de perfiles con claves 'id' y 'pesos'. Si es
            None, se leen desde data/config/perfiles.yaml.
    """
    cfg = yaml.safe_load((CONFIG / "escenario.yaml").read_text(encoding="utf-8"))
    esc = cfg[f"escenario_{s}"]
    origen_utm = (esc["origen"]["x"], esc["origen"]["y"])
    destino_utm = (esc["destino"]["x"], esc["destino"]["y"])

    if perfiles_override is not None:
        perfiles = perfiles_override
    else:
        perfiles = yaml.safe_load((CONFIG / "perfiles.yaml").read_text(encoding="utf-8"))["perfiles"]

    print(f"\n=== Escenario {s}: rutas por perfil ===")
    for perfil in perfiles:
        pid, pesos = perfil["id"], perfil["pesos"]
        C, transform, crs = combinar_pesos(s, pesos)
        _guardar_superficie(C, transform, crs, TRAZADOS / f"superficie_{s}_{pid}.tif")
        origen = _snap_to_valid(*_utm_to_rowcol(*origen_utm, transform), C)
        destino = _snap_to_valid(*_utm_to_rowcol(*destino_utm, transform), C)
        celdas = dijkstra(C, origen, destino)
        RUTAS_DIR.mkdir(parents=True, exist_ok=True)
        out = RUTAS_DIR / f"ruta_{s}_{pid}.gpkg"
        linea = _exportar(celdas, transform, crs, pid, out)
        print(f"  {pid:11s}: {out.name:24s} longitud={linea.length:7.0f} m")


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Ruta con LCP isótropo por perfil de prioridad.")
    parser.add_argument("--escenario", choices=["A", "B", "ambos"], default="ambos")
    args = parser.parse_args()

    escenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario]
    for s in escenarios:
        run_perfiles(s)
    print(f"\nRutas guardadas en: {RUTAS_DIR}")


if __name__ == "__main__":
    main()
