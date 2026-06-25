"""
Fase 2 — Ruta con LCP ANISÓTROPO (consideración de Enagás 2026-06-22).

La superficie escalar combinada (Trazados/superficie_{s}.tif) decide DÓNDE hay
coste; la capa de DIRECCIÓN (Capas_Coste/pendiente_direccion_{s}.tif)
decide CÓMO se cruza la pendiente que no se puede evitar: de frente (perpendicular
a las curvas de nivel), nunca en transversal.

Coste de transición p→q (no se puede prehornear en un raster escalar; va aquí):

    coste(p→q) = d · C_celda · (1 + λ · S · sinθ)

  d       = distancia geométrica del paso (1 ortogonal, √2 diagonal)
  C_celda = media del coste escalar de p y q (superficie combinada)
  S       = pendiente normalizada [0,1] = clip(pendiente° / 30°, 0, 1)
  θ       = ángulo entre el paso y la línea de máxima pendiente
            sinθ=0 cruzando de frente (barato) · sinθ=1 transversal (caro)
  λ       = peso de la penalización por transversalidad (configurable)

En llano S≈0 → la dirección no penaliza (correcto). Algoritmo: Dijkstra 8-conexo.

Genera, por escenario, en Capas_Coste/Pendiente/:
  ruta_{s}_anisotropa.gpkg   (la propuesta, con la consideración de Enagás)
  ruta_{s}_isotropa.gpkg     (baseline sin anisotropía, para comparar)

Uso (desde proyecto/):
  python -m src.trazados.ruta_pendiente
  python -m src.trazados.ruta_pendiente --escenario A --lambda 4
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

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
DATA = _ROOT / "data"
CONFIG = DATA / "config"
TRAZADOS = DATA / "processed" / "Trazados"
CAPAS = DATA / "processed" / "Capas_Coste"
PENDIENTE = CAPAS / "Pendiente"   # superficies intermedias por perfil
RUTAS_DIR = DATA / "processed" / "Rutas"  # destino de rutas .gpkg (métricas leen aquí)

_NODATA = -9999.0
_BARRERA_DISCO = 999.0
SLOPE_REF = 30.0  # grados; normaliza S a [0,1] (= barrera dura de pendiente.py)

# Mapeo peso (perfiles.yaml) → fichero de capa escalar en Capas_Coste/.
# Claves NO listadas y con tratamiento especial:
#   'longitud'  → coste base por celda (no es una capa).
#   'traversal' → en MI versión NO es una capa escalar; su peso por perfil escala
#                 λ (fuerza de la penalización anisótropa). Ver run_perfiles().
#   'aspecto'   → capa intermedia, no de coste.
PESO_A_CAPA = {
    "pendiente": "pendiente",
    "protegida": "protegida",
    "cruces": "cruces",
    "expropiacion": "expropiacion",
    "geotecnia": "geotecnia",
}

_VECINOS = [(-1, -1), (-1, 0), (-1, 1), (0, -1),
            (0, 1), (1, -1), (1, 0), (1, 1)]


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


def _cargar_superficie(s: str) -> tuple[np.ndarray, rasterio.Affine, object]:
    """Superficie escalar combinada (nan fuera AOI, inf barrera)."""
    tif = TRAZADOS / f"superficie_{s}.tif"
    if not tif.exists():
        raise FileNotFoundError(
            f"Falta {tif}. Ejecuta primero: python -m src.superficie.combinar --escenario {s}"
        )
    with rasterio.open(tif) as src:
        arr = src.read(1).astype("float64")
        transform, crs = src.transform, src.crs
    arr = np.where(arr == _NODATA, np.nan, arr)
    arr = np.where(arr == _BARRERA_DISCO, np.inf, arr)
    return arr, transform, crs


def _cargar_direccion(s: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Capa de dirección: dz/dx, dz/dy, pendiente normalizada S∈[0,1]."""
    tif = CAPAS / f"pendiente_direccion_{s}.tif"
    if not tif.exists():
        raise FileNotFoundError(
            f"Falta {tif}. Ejecuta primero: python -m src.superficie.gradiente --escenario {s}"
        )
    with rasterio.open(tif) as src:
        gx = src.read(1).astype("float64")
        gy = src.read(2).astype("float64")
        slope = src.read(3).astype("float64")
    for a in (gx, gy, slope):
        a[a == _NODATA] = 0.0
    S = np.clip(slope / SLOPE_REF, 0.0, 1.0)
    return gx, gy, S


def dijkstra_anisotropo(
    C: np.ndarray, gx: np.ndarray, gy: np.ndarray, S: np.ndarray,
    origen: tuple[int, int], destino: tuple[int, int], lam: float,
) -> list[tuple[int, int]]:
    """LCP 8-conexo con coste de transición anisótropo. lam=0 → isótropo puro."""
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

            factor = 1.0
            if lam > 0.0:
                # paso en (Este, Norte): E=dc, N=-dr
                uE, uN = dc / d, -dr / d
                # gradiente de ascenso medio en (Este, Norte): E=gx, N=-gy
                GE = 0.5 * (gx[r, c] + gx[rr, cc])
                GN = -0.5 * (gy[r, c] + gy[rr, cc])
                gmag = np.hypot(GE, GN)
                if gmag > 1e-12:
                    sinth = abs(uE * (GN / gmag) - uN * (GE / gmag))
                    S_edge = 0.5 * (S[r, c] + S[rr, cc])
                    factor = 1.0 + lam * S_edge * sinth

            nd = d_p + d * c_cell * factor
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


def exposicion_transversal(
    celdas: list[tuple[int, int]], gx: np.ndarray, gy: np.ndarray, S: np.ndarray,
) -> float:
    """Media de S·sinθ a lo largo de la ruta (exposición a cruce transversal).

    0 = siempre de frente a la ladera; alto = mucho recorrido transversal en pendiente.
    """
    vals = []
    for (r0, c0), (r1, c1) in zip(celdas[:-1], celdas[1:]):
        dr, dc = r1 - r0, c1 - c0
        d = np.hypot(dr, dc)
        if d == 0:
            continue
        uE, uN = dc / d, -dr / d
        GE = 0.5 * (gx[r0, c0] + gx[r1, c1])
        GN = -0.5 * (gy[r0, c0] + gy[r1, c1])
        gmag = np.hypot(GE, GN)
        sinth = abs(uE * (GN / gmag) - uN * (GE / gmag)) if gmag > 1e-12 else 0.0
        vals.append(0.5 * (S[r0, c0] + S[r1, c1]) * sinth)
    return float(np.mean(vals)) if vals else 0.0


def _exportar(celdas, transform, crs, tipo: str, lam: float, path: Path,
              expos: float) -> LineString:
    linea = LineString([rt.xy(transform, r, c, offset="center") for r, c in celdas])
    gdf = gpd.GeoDataFrame(
        {"tipo": [tipo], "lambda": [lam], "n_celdas": [len(celdas)],
         "longitud_m": [round(linea.length, 1)],
         "exposicion_transversal": [round(expos, 4)]},
        geometry=[linea], crs=crs,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GPKG")
    return linea


def _superficie_perfil(
    s: str, pesos: dict[str, float]
) -> tuple[np.ndarray, rasterio.Affine, object]:
    """Superficie escalar PONDERADA por los pesos de un perfil (perfiles.yaml).

    coste = peso_longitud (base por celda) + Σ peso_capa · capa
    Sigue el convenio de combinar.py: -9999 → nan (celda impasable: fuera de AOI
    o barrera dura). Una celda es impasable si cualquier capa usada lo es.
    """
    base = float(pesos.get("longitud", 1.0))

    transform = crs = None
    acc = None
    for key, w in pesos.items():
        cap = PESO_A_CAPA.get(key)
        if cap is None:
            continue  # 'longitud' u otra clave sin capa raster
        path = CAPAS / f"{cap}_{s}.tif"
        if not path.exists():
            log.warning("[%s] capa ausente para peso '%s': %s", s, key, path.name)
            continue
        with rasterio.open(path) as src:
            arr = src.read(1).astype("float64")
            if transform is None:
                transform, crs = src.transform, src.crs
                acc = np.full(arr.shape, base, dtype="float64")
        arr = np.where(arr == _NODATA, np.nan, arr)
        acc = acc + float(w) * arr  # nan se propaga → celda impasable

    if acc is None:
        raise RuntimeError(f"[{s}] perfil sin capas ponderables: {pesos}")
    return acc, transform, crs


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


def run_perfiles(s: str, lam: float) -> None:
    """Rehace las rutas por perfil (perfiles.yaml) con el motor anisótropo."""
    cfg = yaml.safe_load((CONFIG / "escenario.yaml").read_text(encoding="utf-8"))
    esc = cfg[f"escenario_{s}"]
    origen_utm = (esc["origen"]["x"], esc["origen"]["y"])
    destino_utm = (esc["destino"]["x"], esc["destino"]["y"])

    perfiles = yaml.safe_load((CONFIG / "perfiles.yaml").read_text(encoding="utf-8"))["perfiles"]
    gx, gy, S = _cargar_direccion(s)

    print(f"\n=== Escenario {s}: rutas por perfil (lam_base={lam}) ===")
    for perfil in perfiles:
        pid, pesos = perfil["id"], perfil["pesos"]
        # El peso 'traversal' del perfil escala λ (fuerza del cruce perpendicular).
        lam_p = lam * float(pesos.get("traversal", 0.0))
        C, transform, crs = _superficie_perfil(s, pesos)
        _guardar_superficie(C, transform, crs, PENDIENTE / f"superficie_{s}_{pid}.tif")
        origen = _snap_to_valid(*_utm_to_rowcol(*origen_utm, transform), C)
        destino = _snap_to_valid(*_utm_to_rowcol(*destino_utm, transform), C)
        celdas = dijkstra_anisotropo(C, gx, gy, S, origen, destino, lam_p)
        expos = exposicion_transversal(celdas, gx, gy, S)
        RUTAS_DIR.mkdir(parents=True, exist_ok=True)
        out = RUTAS_DIR / f"ruta_{s}_{pid}.gpkg"
        linea = _exportar(celdas, transform, crs, pid, lam_p, out, expos)
        print(f"  {pid:11s}: {out.name:24s} longitud={linea.length:7.0f} m  "
              f"lam={lam_p:.2f}  exposicion_transversal={expos:.4f}")


def run_escenario(s: str, lam: float) -> None:
    cfg = yaml.safe_load((CONFIG / "escenario.yaml").read_text(encoding="utf-8"))
    esc = cfg[f"escenario_{s}"]
    origen_utm = (esc["origen"]["x"], esc["origen"]["y"])
    destino_utm = (esc["destino"]["x"], esc["destino"]["y"])

    C, transform, crs = _cargar_superficie(s)
    gx, gy, S = _cargar_direccion(s)

    origen = _snap_to_valid(*_utm_to_rowcol(*origen_utm, transform), C)
    destino = _snap_to_valid(*_utm_to_rowcol(*destino_utm, transform), C)
    log.info("[%s] origen=%s destino=%s", s, origen, destino)

    print(f"\n=== Escenario {s} (lam={lam}) ===")
    for tipo, lval in [("isotropa", 0.0), ("anisotropa", lam)]:
        celdas = dijkstra_anisotropo(C, gx, gy, S, origen, destino, lval)
        expos = exposicion_transversal(celdas, gx, gy, S)
        out = PENDIENTE / f"ruta_{s}_{tipo}.gpkg"
        linea = _exportar(celdas, transform, crs, tipo, lval, out, expos)
        print(f"  {tipo:11s}: {out.name}  longitud={linea.length:7.0f} m  "
              f"exposición_transversal={expos:.4f}")


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Ruta con LCP anisótropo (dirección de pendiente).")
    parser.add_argument("--escenario", choices=["A", "B", "ambos"], default="ambos")
    parser.add_argument("--lambda", dest="lam", type=float, default=4.0,
                        help="peso de penalización por transversalidad (def: 4.0)")
    parser.add_argument("--modo", choices=["perfiles", "demo"], default="perfiles",
                        help="'perfiles' = 4 rutas de perfiles.yaml; 'demo' = iso vs aniso (pesos iguales)")
    args = parser.parse_args()

    escenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario]
    for s in escenarios:
        if args.modo == "perfiles":
            run_perfiles(s, args.lam)
        else:
            run_escenario(s, args.lam)
    print(f"\nRutas guardadas en: {RUTAS_DIR}")


if __name__ == "__main__":
    main()
