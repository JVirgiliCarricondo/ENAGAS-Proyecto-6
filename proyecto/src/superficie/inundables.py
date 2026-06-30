"""
Script 07 - Capa de coste P6: zonas inundables (peligrosidad fluvial T=100, SNCZI).

Convierte inundables_aoi_{s}.tif (mascara binaria de inundabilidad T=100) en un
raster de coste alineado a la rejilla del DEM del AOI. Modelo de coste en
Modelo_Coste.md (5.3).

La inundabilidad es una variable binaria: una celda esta dentro de la lamina de
inundacion T=100 o no lo esta. El valor "dentro" esta estandarizado al factor
oficial "ZONAS INUNDABLES" (A=14.25 / 38 = 0.375), de modo que la capa comparte
la escala [0,1] con las demas. El PESO de la capa en la combinacion multicriterio
(§8) sigue modulando el enfasis por perfil.

A diferencia de las capas vectoriales (Red Natura, Catastro...), la entrada YA es
un raster, producido por descargar_capas.py (mosaico de los GeoTIFF oficiales del
CNIG -> mascara) + alinear_capas.py: valores 1=inundable / 0=fuera, con
nodata=-9999 fuera del corredor. Por eso aqui solo se remuestrea a la rejilla del
DEM (vecino mas proximo, capa categorica) y se mapean los valores a coste.

Tabla de valores (binaria, estandarizada A_oficial / 38):

  Situacion                              Valor
  Dentro de zona inundable T=100         0.375   (A oficial = 14.25)
  Fuera de zona inundable                0

Sin barrera dura: la inundabilidad encarece el corredor pero no lo bloquea (las
obras admiten cruce de zona inundable con medidas; el peso del perfil decide
cuanto se evita). Los km en zona inundable se reportan como metrica (hito 4).

Salida: data/processed/Capas_Coste/inundable_{s}.tif  (uno por escenario).

Uso:
  python src/superficie/inundables.py
"""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

try:
    from .config import params_inundables as _params_inundables
except ImportError:
    from config import params_inundables as _params_inundables

BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
ENTRADA_DIR = BASE / "Recorte_AOI"
SALIDA_DIR = BASE / "Capas_Coste"

ESCENARIOS = ["A", "B"]

CRS_TRABAJO = "EPSG:25830"
NODATA = -9999.0

# Parámetros cargados de perfiles.yaml (parametros_capas.inundables)
_icfg = _params_inundables()
VALOR_INUNDABLE: float = float(_icfg["valor_inundable"])
VALOR_FONDO: float = float(_icfg["valor_fondo"])


def procesar_escenario(s: str) -> None:
    """Genera inundable_{s}.tif a partir de inundables_aoi_{s}.tif."""
    dem_path = ENTRADA_DIR / f"dem_aoi_{s}.tif"
    inund_path = ENTRADA_DIR / f"inundables_aoi_{s}.tif"

    if not dem_path.exists():
        raise FileNotFoundError(f"No existe el DEM de referencia: {dem_path}")
    if not inund_path.exists():
        raise FileNotFoundError(f"No existe la capa de inundabilidad: {inund_path}")

    # --- Paso 1: rejilla de referencia (copiada del DEM, nunca recalculada) ---
    with rasterio.open(dem_path) as ref:
        transform = ref.transform
        width, height = ref.width, ref.height
        profile = ref.profile.copy()

    # --- Paso 2-3: remuestrear la máscara binaria a la rejilla del DEM ---
    # Capa categórica (0/1) -> vecino más próximo. La entrada ya está en EPSG:25830
    # y prácticamente en la misma rejilla; el reproject garantiza el encaje exacto.
    with rasterio.open(inund_path) as src:
        src_nodata = float(src.nodata) if src.nodata is not None else NODATA
        mask = np.full((height, width), src_nodata, dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=mask,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=CRS_TRABAJO,
            src_nodata=src_nodata,
            dst_nodata=src_nodata,
            resampling=Resampling.nearest,
        )

    # --- Paso 4: mapear a coste ---
    #   nodata (fuera del corredor) -> NODATA
    #   valor > 0.5 (inundable)     -> VALOR_INUNDABLE
    #   resto (fondo, no inundable) -> VALOR_FONDO
    cost_array = np.full((height, width), VALOR_FONDO, dtype="float32")
    es_inundable = (mask > 0.5) & (mask != src_nodata)
    cost_array[es_inundable] = VALOR_INUNDABLE
    cost_array[mask == src_nodata] = NODATA

    # --- Paso 5: guardar con el mismo profile que el DEM ---
    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    profile.update(
        driver="GTiff",
        dtype="float32",
        nodata=NODATA,
        count=1,
        compress="lzw",
    )
    salida = SALIDA_DIR / f"inundable_{s}.tif"
    with rasterio.open(salida, "w", **profile) as dst:
        dst.write(cost_array.astype(np.float32), 1)

    celdas_inund = int(np.count_nonzero(cost_array == VALOR_INUNDABLE))
    validas = int(np.count_nonzero(cost_array != NODATA))
    if validas:
        print(
            f"[{s}] {salida.name}: {width}x{height} celdas | "
            f"{celdas_inund} celda(s) inundable(s) "
            f"({100 * celdas_inund / validas:.1f}% del corredor)"
        )
    else:
        print(f"[{s}] {salida.name}: {width}x{height} celdas | sin celdas válidas")


def main() -> None:
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("Script 07 completado: capa de coste 'inundable' generada (A y B).")


if __name__ == "__main__":
    main()
