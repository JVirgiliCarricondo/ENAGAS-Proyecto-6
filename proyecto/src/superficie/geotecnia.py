"""Capa de coste P2: Geotecnia.

Para cada escenario A y B, rasteriza los polígonos geológicos del IGME
sobre la rejilla del DEM de referencia asignando un índice de coste fijo
por litología (columna DLO).

  - Píxeles dentro del AOI sin polígono IGME  → DEFAULT_COST (0.3)
  - Píxeles fuera del AOI (nodata en el DEM)  → NODATA (-9999, transparente)

Salida: data/processed/Capas_Coste/geotecnia_{A,B}.tif  +  .qml de estilos
  - CRS: EPSG:25830, transform/shape igual que dem_aoi_{s}.tif
  - dtype: float32, nodata: -9999.0, compresión: LZW
  - Valores válidos: [0.1, 0.7]
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize


BASE_DIR = Path(__file__).resolve().parents[2]
RECORTE_DIR = BASE_DIR / "data" / "processed" / "Recorte_AOI"
CAPAS_COSTE_DIR = BASE_DIR / "data" / "processed" / "Capas_Coste"

SCENARIOS = ["A", "B"]
NODATA: float = -9999.0
DEFAULT_COST: float = 0.3

# Índice de coste geotécnico por litología (DLO del IGME).
# Cualquier DLO no listado recibe DEFAULT_COST (0.3).
COST_TABLE: dict[str, float] = {
    # Aluviales y fondos de valle — excavación muy fácil
    "Gravas, arenas, limos y arcillas. Aluviales y fondos de valle": 0.1,
    "CANTOS, ARENAS Y LIMOS. CONOS DE DEYECCIÓN": 0.1,
    "Cantos y gravas polimácticas redondeadas. Terrazas": 0.1,
    # Misma entrada con á almacenada como í (U+00ED) por corrupción en el GPKG fuente
    "Cantos y gravas polim\xedcticas redondeadas. Terrazas": 0.1,
    "GRAVAS POLIGENICAS, ARENAS Y LIMOS. TERRAZAS": 0.1,
    # Sedimentos finos / coluviales — fácil
    "Limo-arcillas y arenas con algun canto. Rellenos de Val": 0.2,
    "Limo-arcillas y arenas con algún canto. Rellenos de Val": 0.2,
    "CANTOS, LIMOS Y ARCILLAS. COLUVIAL": 0.2,
    # Arcillas blandas / paleocanales aislados — moderado
    "Arcillas y paleocanales de arenisca. Unidad de Mequinenza-Ballobar": 0.3,
    "Paleocanal individual": 0.3,
    # Arenisca compacta / paleocanales exhumados
    "Paleocanales de arenisca exhumados (ambas unidades)": 0.4,
    "Paleocanales de arenisca exhumados. Unidad de Mequinenza-Ballobar": 0.4,
    "Paleocanales de arenisca exhumados. Unidad de Torrente de Cinca-Alcolea de Cinca": 0.4,
    "Paleocanales amalgamados": 0.4,
    # Conglomerados / mezcla duro-blando
    "Areniscas, conglomerados y arcillas": 0.5,
    "Areniscas, conglomerados y arcillas. Unidad de Torrente de Cinca-Alcolea de Cinca": 0.5,
    "Arcillas rojas, capas de calizas y areniscas": 0.5,
    # Caliza presente — más duro
    "Arcillas, paleocanales de arenisca y capas de calizas": 0.6,
    "Arcillas rojas con niveles edafizados, capas de caliza...": 0.6,
    "Arcillas rojas con niveles edafizados, capas de caliza y paleocanal. de arenisca. Un. de Fayón-Fraga": 0.6,
    # Misma entrada con ó almacenada como ¢ (U+00A2) por corrupción en el GPKG fuente
    "Arcillas rojas con niveles edafizados, capas de caliza y paleocanal. de arenisca. Un. de Fay\xa2n-Fraga": 0.6,
    # Yeso — problemático para infraestructuras (corrosivo, expansivo)
    "Arcillas rojas con yeso nodular y areniscas": 0.7,
    "Arcillas rojas con yeso nodular y areniscas. Unidad de Mequinenza-Ballobar": 0.7,
    "ARCILLAS ROJAS CON NIVELES CENTIMETRICOS DE YESOS Y CALIZAS": 0.7,
    "CANTOS, LIMOS YESIFEROS Y ARCILLAS. FONDOS DE VALLE PLANOS": 0.7,
    "YESOS TABULARES Y NODULARES CON ARCILLAS GRISES": 0.7,
    "YESOS TABULARES Y NODULARES CON ARCILLAS ROJAS Y GRISES": 0.7,
    "YESOS TABULARES Y NODULARES CON MARGAS Y ARCILLAS": 0.7,
    "Yesos masivos. U.BUJARALOZ-SARIÑENA": 0.7,
}

# ColorBrewer RdYlGn invertido: verde (fácil) → rojo oscuro (problemático)
_COLORS: dict[float, str] = {
    0.1: "#1a9641",
    0.2: "#a6d96a",
    0.3: "#ffffbf",
    0.4: "#fdae61",
    0.5: "#f46d43",
    0.6: "#d73027",
    0.7: "#a50026",
}

_LABELS: dict[float, str] = {
    0.1: "0.1 - Aluviales (facil)",
    0.2: "0.2 - Sedimento fino",
    0.3: "0.3 - Arcilla blanda (defecto)",
    0.4: "0.4 - Arenisca compacta",
    0.5: "0.5 - Conglomerado/caliza",
    0.6: "0.6 - Caliza presente",
    0.7: "0.7 - Yeso (problematico)",
}


def _read_reference(dem_path: Path) -> tuple[dict, np.ndarray]:
    """Devuelve (profile, valid_mask); valid_mask=True donde el DEM tiene dato."""
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM de referencia no encontrado: {dem_path}")
    with rasterio.open(dem_path) as src:
        profile = src.profile.copy()
        dem_data = src.read(1)
        if src.nodata is not None:
            nd = float(src.nodata)
            valid_mask = ~np.isnan(dem_data) & (dem_data != nd) if np.isnan(nd) else dem_data != nd
        else:
            valid_mask = np.isfinite(dem_data)
    return profile, valid_mask.astype(bool)


def _assign_costs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Añade columna 'cost' mapeando DLO → índice geotécnico."""
    gdf = gdf.copy()
    gdf["cost"] = gdf["DLO"].map(
        lambda dlo: COST_TABLE.get(str(dlo).strip(), DEFAULT_COST)
    )
    return gdf


def _rasterize_geology(
    gdf: gpd.GeoDataFrame, profile: dict, valid_mask: np.ndarray
) -> np.ndarray:
    """Rasteriza polígonos IGME sobre la rejilla del DEM."""
    height: int = profile["height"]
    width: int = profile["width"]
    transform = profile["transform"]

    # Nodata en todo el array; DEFAULT_COST donde el DEM es válido (dentro del AOI)
    result = np.full((height, width), NODATA, dtype="float32")
    result[valid_mask] = DEFAULT_COST

    valid_geoms = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if valid_geoms.empty:
        return result

    shapes = list(zip(valid_geoms.geometry, valid_geoms["cost"].astype(float)))

    # fill=-1.0 como centinela: "ningún polígono IGME cubre esta celda"
    rasterized = rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=-1.0,
        dtype="float32",
        all_touched=False,
    )

    # Aplicar coste IGME solo donde el DEM es válido y hay polígono
    igme_covered = rasterized >= 0.0
    result[valid_mask & igme_covered] = rasterized[valid_mask & igme_covered]

    return result


def _write_qml(tif_path: Path) -> None:
    """Escribe un fichero .qml junto al TIF para que QGIS cargue los colores automáticamente."""
    costs = sorted(_COLORS)
    items_lines = []
    for i, v in enumerate(costs):
        upper = round(v + 0.05, 2) if i < len(costs) - 1 else 0.70
        items_lines.append(
            f'          <item value="{upper:.2f}" label="{_LABELS[v]}" '
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
        classificationMin="0.1" classificationMax="0.7"
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
        <colorrampshader minimumValue="0.1" maximumValue="0.7"
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
    """Genera la capa de coste geotécnico para un escenario (A o B)."""
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
