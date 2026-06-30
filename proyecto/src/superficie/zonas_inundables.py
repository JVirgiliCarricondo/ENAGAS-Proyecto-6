"""
Script 06b - Capa de coste P4b: zonas inundables (SNCZI, MITECO).

Convierte inundable_aoi_{s}.gpkg en un raster BINARIO {0, 0.375} alineado a la
rejilla del DEM del AOI. Modelo de coste en modelo_coste.md (5.2-bis) y resumen
del reto en CLAUDE.md.

La inundabilidad es una variable binaria: una celda esta dentro de alguna
lamina de inundacion SNCZI (T10, T100 o T500, union de las tres) o no lo esta.
El valor "dentro" esta estandarizado al factor oficial "Zonas inundables"
(A=14.25 / 38 = 0.375), de modo que la capa comparte la escala [0,1] con las
demas. El PESO de la capa en la combinacion multicriterio (Modelo_Coste.md §8)
sigue modulando el enfasis por perfil. No se distingue por periodo de retorno
porque la tabla oficial Enagas solo da un factor para este condicionante.

Patron comun de las capas de coste (hito 2), identico a zonas_protegidas.py:
  Paso 1 - Leer la rejilla de referencia: copiar SIEMPRE transform/width/height/
           CRS del DEM (dem_aoi_{s}.tif). Nunca calcular la rejilla a mano: asi
           es imposible que las capas queden desalineadas.
  Paso 2 - Asignar el valor binario por atributo: columna 'cost' = 1 si la
           geometria es lamina de inundacion (cualquier periodo de retorno).
  Paso 3 - Rasterizar sobre la rejilla. Poligonos -> all_touched=False.
  Paso 4 - Rellenar fondo: celdas fuera de poligono = 0 (sin riesgo).
  Paso 5 - Guardar con el mismo profile que el DEM (GTiff, float32,
           nodata=-9999.0, compress=lzw).

Tabla de valores (binaria, estandarizada A_oficial / 38):

  Situacion                                  Valor
  Dentro de lamina de inundacion (T10/T100/T500)  0.375   (A oficial = 14.25)
  Fuera de poligono (sin riesgo conocido)          0

Nota: la capa es transitable (valor finito). No hay barrera dura (inf): una
llanura de inundacion no impide tecnicamente el trazado, solo lo penaliza.

Salida: data/processed/Capas_Coste/inundable_{s}.tif  (uno por escenario).

Uso:
  python src/superficie/zonas_inundables.py
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

try:
    from .config import params_zonas_inundables as _params_zonas_inundables
except ImportError:
    from config import params_zonas_inundables as _params_zonas_inundables

BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
ENTRADA_DIR = BASE / "Recorte_AOI"
SALIDA_DIR = BASE / "Capas_Coste"

ESCENARIOS = ["A", "B"]

CRS_TRABAJO = "EPSG:25830"
NODATA = -9999.0

# Parámetros cargados de perfiles.yaml (parametros_capas.zonas_inundables)
_icfg = _params_zonas_inundables()
VALOR_INUNDABLE: float = float(_icfg["valor_inundable"])
VALOR_FONDO: float = float(_icfg["valor_fondo"])


def procesar_escenario(s: str) -> None:
    """Genera inundable_{s}.tif a partir de inundable_aoi_{s}.gpkg."""
    dem_path = ENTRADA_DIR / f"dem_aoi_{s}.tif"
    inund_path = ENTRADA_DIR / f"inundable_aoi_{s}.gpkg"

    if not dem_path.exists():
        raise FileNotFoundError(f"No existe el DEM de referencia: {dem_path}")
    if not inund_path.exists():
        raise FileNotFoundError(f"No existe la capa de zonas inundables: {inund_path}")

    # --- Paso 1: rejilla de referencia (copiada del DEM, nunca recalculada) ---
    with rasterio.open(dem_path) as ref:
        transform = ref.transform
        width, height = ref.width, ref.height
        profile = ref.profile.copy()

    # --- Paso 2: asignar coste por atributo (columna 'cost') ---
    inundable = gpd.read_file(inund_path)
    if inundable.crs is None:
        raise ValueError(f"La capa de zonas inundables no tiene CRS definido: {inund_path}")
    inundable = inundable.to_crs(CRS_TRABAJO)
    inundable = inundable[inundable.geometry.notna() & ~inundable.geometry.is_empty].copy()

    # --- Paso 3 + 4: rasterizar poligonos (all_touched=False) y rellenar fondo ---
    if inundable.empty:
        # Sin lamina de inundacion en el AOI: toda la rejilla es fondo (0).
        cost_array = np.full((height, width), VALOR_FONDO, dtype="float32")
        n_poligonos = 0
    else:
        # Variable binaria: cualquier lamina de inundacion -> valor unico, sin gradacion.
        inundable["cost"] = VALOR_INUNDABLE
        shapes = list(zip(inundable.geometry, inundable["cost"]))
        cost_array = rasterize(
            shapes,
            out_shape=(height, width),
            transform=transform,
            fill=VALOR_FONDO,  # Paso 4: fondo = sin riesgo conocido
            all_touched=False,  # poligonos: solo celdas cuyo centro cae dentro
            dtype="float32",
        )
        n_poligonos = len(inundable)

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

    celdas_inundables = int(np.count_nonzero(cost_array > 0))
    total = cost_array.size
    print(
        f"[{s}] {salida.name}: {width}x{height} celdas | "
        f"{n_poligonos} poligono(s) zona inundable | "
        f"{celdas_inundables}/{total} celdas inundables "
        f"({100 * celdas_inundables / total:.1f}%)"
    )


def main() -> None:
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("Script 06b completado: capa de coste 'inundable' generada (A y B).")


if __name__ == "__main__":
    main()
