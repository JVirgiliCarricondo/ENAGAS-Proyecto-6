"""Capa de coste de expropiación parcelaria.

Genera expropiacion_{s}.tif a partir de catastro_aoi_{s}.gpkg rasterizado
sobre la rejilla de referencia dem_aoi_{s}.tif. Coste basado en el campo TIPO
de las parcelas catastrales según la tabla de lookup definida en modelo_coste.md.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import mapping

try:
    from .config import params_expropiacion as _params_expropiacion
except ImportError:
    from config import params_expropiacion as _params_expropiacion

log = logging.getLogger(__name__)

# ── Rutas ────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
DATA = _ROOT / "data"
RECORTE = DATA / "processed" / "Recorte_AOI"
CAPAS_COSTE = DATA / "processed" / "Capas_Coste"

# ── Parámetros cargados de perfiles.yaml (parametros_capas.expropiacion) ─────
_ecfg = _params_expropiacion()
TIPO_COST: dict[str, float] = {str(k): float(v) for k, v in _ecfg["tipos"].items()}
TIPO_DEFAULT: float = float(_ecfg["default_cost"])
FONDO_COST: float = float(_ecfg["fondo_cost"])
AREA_PERIURBANO_M2: float = float(_ecfg["area_periurbano_m2"])
COST_PERIURBANO: float = float(_ecfg["cost_periurbano"])

NODATA = -9999.0

# ── Paleta QGIS (color hex, etiqueta, alpha) ─────────────────────────────────
# Se genera un .qml junto al .tif para que QGIS aplique los colores al instante.
# Los breakpoints usan puntos medios entre valores de coste consecutivos para
# evitar que la imprecisión float32 haga caer un valor en el bin equivocado.
#   Valores reales:   0.05   0.20   0.40   0.50   0.90
#   Breakpoints:         0.125  0.30  0.45   0.70   0.95
_QGIS_PALETTE: list[tuple[float, str, str, int]] = [
    (0.125, "#4CAF50", "Dominio público (D)",        255),
    (0.30,  "#FFEB3B", "Rústico / sin parcela (R)",  255),
    (0.45,  "#FF9800", "Sin clasificar (X)",         255),
    (0.70,  "#E65100", "Periurbano (R &lt; 500 m²)", 255),
    (0.95,  "#C62828", "Urbano (U)",                 255),
]


def _write_qml(tif_path: Path) -> Path:
    # singlebandpseudocolor DISCRETE: cada item cubre valores <= su breakpoint.
    # Los breakpoints son puntos medios entre costes consecutivos, por lo que
    # la imprecisión float32 (p.ej. 0.20000000298) siempre cae en el bin correcto.
    items = "\n".join(
        f'          <item value="{v}" color="{c}" label="{l}" alpha="{a}"/>'
        for v, c, l, a in _QGIS_PALETTE
    )
    vmin = 0.0
    vmax = _QGIS_PALETTE[-1][0]  # 0.95
    qml = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer opacity="1" alphaBand="-1" band="1" type="singlebandpseudocolor"
      classificationMin="{vmin}" classificationMax="{vmax}" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="DISCRETE" clip="0"
          minimumValue="{vmin}" maximumValue="{vmax}"
          classificationMode="1" labelPrecision="2">
{items}
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>"""
    qml_path = tif_path.with_suffix(".qml")
    qml_path.write_text(qml, encoding="utf-8")
    return qml_path


def _assign_cost(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Añade columna 'cost' según TIPO y refinamiento de área."""
    gdf = gdf.copy()
    gdf["cost"] = gdf["TIPO"].map(TIPO_COST).fillna(TIPO_DEFAULT).astype("float32")
    # refinamiento opcional: parcelas rústicas muy pequeñas = periurbano
    mask_periurban = (gdf["TIPO"] == "R") & (gdf.geometry.area < AREA_PERIURBANO_M2)
    gdf.loc[mask_periurban, "cost"] = COST_PERIURBANO
    return gdf


def run(scenario: str) -> Path:
    s = scenario.upper()

    dem_path = RECORTE / f"dem_aoi_{s}.tif"
    cat_path = RECORTE / f"catastro_aoi_{s}.gpkg"
    out_path = CAPAS_COSTE / f"expropiacion_{s}.tif"

    if not dem_path.exists():
        raise FileNotFoundError(f"Rejilla de referencia no encontrada: {dem_path}")
    if not cat_path.exists():
        raise FileNotFoundError(f"Catastro recortado no encontrado: {cat_path}")

    CAPAS_COSTE.mkdir(parents=True, exist_ok=True)

    # ── Paso 1: leer rejilla de referencia ───────────────────────────────────
    with rasterio.open(dem_path) as src:
        transform = src.transform
        width = src.width
        height = src.height
        crs = src.crs
        profile = src.profile.copy()
        dem_arr = src.read(1)
        dem_nodata = src.nodata
        # máscara de celdas fuera del AOI orientado (nodata en el DEM)
        outside_aoi = (dem_arr == dem_nodata) if dem_nodata is not None else np.zeros((height, width), dtype=bool)

    log.info("[expropiacion_%s] rejilla: %d×%d  CRS: %s", s, height, width, crs)

    # ── Paso 2: leer catastro y asignar coste ────────────────────────────────
    gdf = gpd.read_file(cat_path)
    # Defensa: .area y la rasterización asumen coordenadas en EPSG:25830 (metros).
    # La ingesta ya lo entrega así, pero reproyectamos por si la entrada no viene
    # alineada (coherente con cruces/zonas protegidas, que también lo hacen).
    if gdf.crs is not None and gdf.crs.to_epsg() != 25830:
        log.info("[expropiacion_%s] reproyectando catastro %s → EPSG:25830", s, gdf.crs)
        gdf = gdf.to_crs(epsg=25830)
    log.info("[expropiacion_%s] %d parcelas leídas desde %s", s, len(gdf), cat_path.name)

    if gdf.empty:
        log.warning("[expropiacion_%s] catastro vacío → raster de fondo (%.2f)", s, FONDO_COST)
        arr = np.full((height, width), FONDO_COST, dtype="float32")
    else:
        gdf = _assign_cost(gdf)

        # ── Paso 3: rasterizar ───────────────────────────────────────────────
        shapes = (
            (mapping(geom), cost)
            for geom, cost in zip(gdf.geometry, gdf["cost"])
            if geom is not None and not geom.is_empty
        )
        arr = rasterize(
            shapes=shapes,
            out_shape=(height, width),
            transform=transform,
            fill=0.0,       # 0 = sin parcela (se rellenará en paso 4)
            dtype="float32",
            all_touched=False,
        )

        # ── Paso 4: rellenar fondo ───────────────────────────────────────────
        arr = np.where(arr == 0.0, FONDO_COST, arr)

    # celdas fuera del AOI orientado → nodata (transparente en QGIS)
    arr = np.where(outside_aoi, NODATA, arr)

    # ── Paso 5: guardar ──────────────────────────────────────────────────────
    profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        nodata=NODATA,
        compress="lzw",
        tiled=False,
    )
    # eliminar claves de tiling que son inválidas en modo strip
    for key in ("blockxsize", "blockysize"):
        profile.pop(key, None)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr, 1)

    qml_path = _write_qml(out_path)
    log.info("[expropiacion_%s] guardado: %s", s, out_path)
    log.info("[expropiacion_%s] leyenda QGIS: %s", s, qml_path)
    log.info(
        "[expropiacion_%s] rango de valores: [%.2f, %.2f]",
        s, float(arr.min()), float(arr.max()),
    )
    return out_path


def _verify(path: Path) -> None:
    with rasterio.open(path) as src:
        arr = src.read(1)
        print(f"  CRS      : {src.crs}")
        print(f"  Transform: {src.transform}")
        print(f"  Shape    : {src.height}×{src.width}")
        print(f"  dtype    : {arr.dtype}")
        print(f"  nodata   : {src.nodata}")
        print(f"  min/max  : {arr.min():.4f} / {arr.max():.4f}")
        unique = np.unique(arr)
        print(f"  valores únicos ({len(unique)}): {unique[:12]}{'...' if len(unique) > 12 else ''}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Capa de coste de expropiación")
    parser.add_argument(
        "--escenario",
        choices=["A", "B", "ambos"],
        default="ambos",
        help="Escenario a procesar (por defecto: ambos)",
    )
    args = parser.parse_args()

    scenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario]
    for sc in scenarios:
        print(f"\n{'='*60}")
        print(f"  Escenario {sc}")
        print(f"{'='*60}")
        try:
            out = run(sc)
            print(f"\n  Verificación del contrato de salida:")
            _verify(out)
        except FileNotFoundError as e:
            print(f"  [ERROR] {e}")
