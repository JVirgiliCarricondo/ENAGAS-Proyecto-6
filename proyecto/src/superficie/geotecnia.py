"""Capa de coste P2: Geotecnia.

Para cada escenario A y B, rasteriza los polígonos geológicos del IGME
sobre la rejilla del DEM de referencia asignando un índice de coste fijo
por litología (columna DLO).

  - Píxeles dentro del AOI sin polígono IGME  → DEFAULT_COST (0.15)
  - Píxeles fuera del AOI (nodata en el DEM)  → NODATA (-9999, transparente)

Salida: data/processed/Capas_Coste/geotecnia_{A,B}.tif  +  .qml de estilos
  - CRS: EPSG:25830, transform/shape igual que dem_aoi_{s}.tif
  - dtype: float32, nodata: -9999.0, compresión: LZW
  - Valores válidos: [0.05, 1.0] (estandarizado A_oficial / 38; ver perfiles.yaml)
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

try:
    from .config import params_geotecnia as _params_geotecnia
except ImportError:
    from config import params_geotecnia as _params_geotecnia

BASE_DIR = Path(__file__).resolve().parents[2]
RECORTE_DIR = BASE_DIR / "data" / "processed" / "Recorte_AOI"
CAPAS_COSTE_DIR = BASE_DIR / "data" / "processed" / "Capas_Coste"

SCENARIOS = ["A", "B"]
NODATA: float = -9999.0

# Parámetros cargados de perfiles.yaml (parametros_capas.geotecnia)
_gcfg = _params_geotecnia()
COST_TABLE: dict[str, float] = {str(k): float(v) for k, v in _gcfg["tabla_costes"].items()}
DEFAULT_COST: float = float(_gcfg["default_cost"])

# ColorBrewer RdYlGn invertido: verde (fácil) → rojo oscuro (problemático)
# Valores estandarizados A_oficial / 38 (ver perfiles.yaml, parametros_capas.geotecnia).
_COLORS: dict[float, str] = {
    0.05: "#1a9641",
    0.10: "#a6d96a",
    0.15: "#ffffbf",
    0.22: "#fdae61",
    0.28: "#f46d43",
    0.34: "#d73027",
    1.00: "#a50026",
}

_LABELS: dict[float, str] = {
    0.05: "0.05 - Aluviales (facil)",
    0.10: "0.10 - Sedimento fino",
    0.15: "0.15 - Arcilla blanda (defecto)",
    0.22: "0.22 - Arenisca compacta",
    0.28: "0.28 - Conglomerado",
    0.34: "0.34 - Caliza (roca dura, A=13)",
    1.00: "1.00 - Yeso (inestable/expansivo, A=38)",
}


def _read_reference(dem_path: Path) -> tuple[dict, np.ndarray]:
    """Lee la rejilla de referencia del DEM y su máscara de celdas con dato.

    El DEM alineado define la rejilla común (transform, tamaño, CRS EPSG:25830)
    a la que se rasteriza esta capa. La máscara de validez marca dónde el DEM
    tiene dato real (dentro del AOI); las celdas nodata quedan fuera del AOI.

    Args:
        dem_path: Ruta al DEM alineado dem_aoi_{s}.tif.

    Returns:
        Tupla (profile, valid_mask) donde ``valid_mask`` es True donde el DEM
        tiene dato (dentro del AOI) y False donde es nodata (fuera del AOI).

    Raises:
        FileNotFoundError: Si no existe el DEM de referencia.
    """
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM de referencia no encontrado: {dem_path}")
    with rasterio.open(dem_path) as src:
        profile = src.profile.copy()
        dem_data = src.read(1)
        if src.nodata is not None:
            nd = float(src.nodata)
            # El nodata puede ser NaN (comparación especial) o un valor centinela
            # normal (p.ej. -9999): se distinguen ambos casos para la máscara.
            valid_mask = ~np.isnan(dem_data) & (dem_data != nd) if np.isnan(nd) else dem_data != nd
        else:
            # Sin nodata declarado: se considera válido todo lo finito.
            valid_mask = np.isfinite(dem_data)
    return profile, valid_mask.astype(bool)


def _assign_costs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Añade columna 'cost' mapeando DLO → índice geotécnico.

    La columna DLO del IGME identifica la litología. Cada valor se traduce a su
    índice de coste con ``COST_TABLE``; los códigos no presentes en la tabla
    reciben ``DEFAULT_COST``.

    Args:
        gdf: Polígonos geológicos IGME con la columna 'DLO'.

    Returns:
        Copia del GeoDataFrame con una nueva columna 'cost' (float en [0, 1]).
    """
    gdf = gdf.copy()
    gdf["cost"] = gdf["DLO"].map(
        lambda dlo: COST_TABLE.get(str(dlo).strip(), DEFAULT_COST)
    )
    return gdf


def _rasterize_geology(
    gdf: gpd.GeoDataFrame, profile: dict, valid_mask: np.ndarray
) -> np.ndarray:
    """Rasteriza los polígonos IGME sobre la rejilla del DEM.

    Convierte los polígonos vectoriales de litología en un raster de coste
    alineado a la rejilla común. La composición de valores es en capas:
    primero nodata en todo, luego DEFAULT_COST dentro del AOI, y por último el
    coste litológico donde hay polígono IGME.

    Args:
        gdf: Polígonos IGME con columna 'cost' (ver ``_assign_costs``).
        profile: Profile del DEM de referencia (aporta transform/width/height).
        valid_mask: True dentro del AOI (celdas con dato en el DEM).

    Returns:
        Array float32 con el coste geotécnico por celda; NODATA fuera del AOI.
    """
    height: int = profile["height"]
    width: int = profile["width"]
    transform = profile["transform"]

    # Base: nodata en todo el array; DEFAULT_COST donde el DEM es válido (AOI).
    # Así las celdas del AOI sin polígono IGME reciben el coste por defecto.
    result = np.full((height, width), NODATA, dtype="float32")
    result[valid_mask] = DEFAULT_COST

    valid_geoms = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if valid_geoms.empty:
        return result

    # Cada polígono se "quema" con su valor de coste (pares geometría, valor).
    shapes = list(zip(valid_geoms.geometry, valid_geoms["cost"].astype(float)))

    # rasterize convierte los polígonos a rejilla. fill=-1.0 es un centinela que
    # marca "ningún polígono IGME cubre esta celda" (distinto de un coste real).
    # all_touched=False: solo se pinta la celda si su CENTRO cae dentro del
    # polígono (evita engordar artificialmente las coberturas).
    rasterized = rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=-1.0,
        dtype="float32",
        all_touched=False,
    )

    # Sobreescribir con el coste IGME solo donde hay polígono (>= 0, no el
    # centinela -1) Y la celda está dentro del AOI. Fuera de eso queda el
    # DEFAULT_COST (AOI sin polígono) o el NODATA (fuera del AOI).
    igme_covered = rasterized >= 0.0
    result[valid_mask & igme_covered] = rasterized[valid_mask & igme_covered]

    return result


def _write_qml(tif_path: Path) -> None:
    """Escribe un .qml (estilo QGIS) junto al TIF para colorear la capa.

    Genera una leyenda de rampa DISCRETA (una clase por litología). Como la
    rampa es discreta, el límite superior de cada clase se fija en el punto
    medio hasta el siguiente valor de coste, de modo que la imprecisión float32
    no haga caer un valor en la clase equivocada.

    Args:
        tif_path: Ruta del GeoTIFF de coste; el .qml se escribe con el mismo
            nombre y extensión .qml.
    """
    costs = sorted(_COLORS)
    items_lines = []
    for i, v in enumerate(costs):
        # Escala no uniforme: el límite superior de cada clase DISCRETA es el
        # punto medio hasta la siguiente; la última llega al máximo (1.0).
        upper = round((v + costs[i + 1]) / 2, 3) if i < len(costs) - 1 else 1.0
        items_lines.append(
            f'          <item value="{upper:.3f}" label="{_LABELS[v]}" '
            f'color="{_COLORS[v]}" alpha="255"/>'
        )
    items_xml = "\n".join(items_lines)

    qml = f"""\
<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer type="singlebandpseudocolor" band="1"
        classificationMin="0.05" classificationMax="1.0"
        opacity="1" alphaBand="-1" nodataColor="">
      <rasterTransparency/>
      <minMaxOrigin>
        <limits>MinMax</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <rastershader>
        <colorrampshader minimumValue="0.05" maximumValue="1.0"
            colorRampType="DISCRETE" classificationMode="1"
            clip="0" labelPrecision="1">
{items_xml}
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0" gamma="1"/>
    <huesaturation saturation="0" grayscaleMode="0" colorizeOn="0"
      colorizeRed="255" colorizeGreen="128" colorizeBlue="128"
      colorizeStrength="100" invertColors="0"/>
    <rasterresampler maxOversampling="2"/>
    <resamplingStage>resamplingFilter</resamplingStage>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
"""
    qml_path = tif_path.with_suffix(".qml")
    qml_path.write_text(qml, encoding="utf-8")
    print(f"  QML: {qml_path.name}")


def _save_raster(path: Path, data: np.ndarray, profile: dict) -> None:
    """Escribe el raster de coste como GeoTIFF float32 comprimido LZW."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out_profile = profile.copy()
    out_profile.update(
        {
            "driver": "GTiff",
            "count": 1,
            "dtype": "float32",
            "nodata": NODATA,
            "compress": "lzw",
        }
    )
    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(data.astype("float32"), 1)


def _validate_output(path: Path, ref_profile: dict) -> None:
    """Comprueba que el raster de salida mantiene el contrato de alineación."""
    with rasterio.open(path) as dst:
        if dst.crs.to_epsg() != 25830:
            raise RuntimeError(f"CRS incorrecto en {path}: {dst.crs}")
        if dst.transform != ref_profile["transform"]:
            raise RuntimeError(f"Transform no coincide con el DEM en {path}")
        if dst.width != ref_profile["width"] or dst.height != ref_profile["height"]:
            raise RuntimeError(f"Shape no coincide con el DEM en {path}")
        if dst.dtypes[0] != "float32":
            raise RuntimeError(f"dtype incorrecto en {path}: {dst.dtypes[0]}")
        if dst.nodata != NODATA:
            raise RuntimeError(f"nodata incorrecto en {path}: {dst.nodata}")


def process_scenario(scenario: str) -> None:
    """Genera la capa de coste geotécnico para un escenario (A o B).

    Entradas (data/processed/Recorte_AOI/):
        - dem_aoi_{s}.tif  : rejilla de referencia (define transform/tamaño/CRS).
        - igme_aoi_{s}.gpkg: polígonos geológicos IGME (columna DLO) del AOI.

    Salida (data/processed/Capas_Coste/):
        - geotecnia_{s}.tif: coste litológico por celda en [0.05, 1.0] (+ su .qml).
                             NODATA (-9999) fuera del AOI.

    Args:
        scenario: Identificador de escenario ('A' o 'B').

    Raises:
        FileNotFoundError: Si falta el DEM o el GPKG del IGME.
        ValueError: Si la capa IGME no contiene la columna 'DLO'.
    """
    dem_path = RECORTE_DIR / f"dem_aoi_{scenario}.tif"
    igme_path = RECORTE_DIR / f"igme_aoi_{scenario}.gpkg"
    output_path = CAPAS_COSTE_DIR / f"geotecnia_{scenario}.tif"

    if not dem_path.exists():
        raise FileNotFoundError(f"DEM no encontrado: {dem_path}")
    if not igme_path.exists():
        raise FileNotFoundError(f"GPKG IGME no encontrado: {igme_path}")

    print(f"[{scenario}] Rejilla de referencia: {dem_path.name}")
    profile, valid_mask = _read_reference(dem_path)
    print(f"  Píxeles válidos en DEM: {valid_mask.sum()} / {valid_mask.size}")

    print(f"[{scenario}] Capa IGME: {igme_path.name}")
    gdf = gpd.read_file(igme_path)

    if "DLO" not in gdf.columns:
        raise ValueError(f"La capa IGME no contiene la columna 'DLO': {igme_path}")

    unmapped = set(gdf["DLO"].dropna().unique()) - set(COST_TABLE.keys())
    if unmapped:
        print(f"  DLO no mapeados (DEFAULT_COST={DEFAULT_COST}):")
        for dlo in sorted(unmapped):
            print(f"    · {dlo!r}")

    gdf = _assign_costs(gdf)

    print(f"[{scenario}] Rasterizando {len(gdf)} polígonos...")
    data = _rasterize_geology(gdf, profile, valid_mask)

    valid_data = data[data != NODATA]
    print(f"  Valores: min={valid_data.min():.2f} max={valid_data.max():.2f} "
          f"(nodata={np.sum(data == NODATA)} celdas)")

    print(f"[{scenario}] Guardando: {output_path.name}")
    _save_raster(output_path, data, profile)
    _write_qml(output_path)
    _validate_output(output_path, profile)
    print(f"[{scenario}] OK")


def main() -> None:
    """Genera geotecnia_A.tif y geotecnia_B.tif con sus estilos .qml."""
    CAPAS_COSTE_DIR.mkdir(parents=True, exist_ok=True)
    for scenario in SCENARIOS:
        process_scenario(scenario)
    print("Capa de coste geotécnico generada para los escenarios A y B.")


if __name__ == "__main__":
    main()
