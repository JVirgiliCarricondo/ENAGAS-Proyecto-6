"""
Script 06 - Capa de coste P4: zonas protegidas (Red Natura 2000).

Convierte natura2000_aoi_{s}.gpkg en un raster BINARIO {0, 1} alineado a la
rejilla del DEM del AOI. Modelo de coste en modelo_coste.md (5.2) y resumen del
reto en CLAUDE.md.

La proteccion es una variable binaria: una celda esta dentro de Red Natura
o no lo esta. La capa NO grada la intensidad de la penalizacion; eso lo hace
el PESO de la capa en la combinacion multicriterio (§8), que es independiente
del resto de capas. Por eso aqui el valor es 1 (dentro) o 0 (fuera), nada
intermedio.

Patron comun de las capas de coste (hito 2):
  Paso 1 - Leer la rejilla de referencia: copiar SIEMPRE transform/width/height/
           CRS del DEM (dem_aoi_{s}.tif). Nunca calcular la rejilla a mano: asi
           es imposible que las capas queden desalineadas.
  Paso 2 - Asignar el valor binario por atributo: columna 'cost' = 1 si la
           geometria es Red Natura (cualquier TIPO).
  Paso 3 - Rasterizar sobre la rejilla. Poligonos -> all_touched=False.
  Paso 4 - Rellenar fondo: celdas fuera de poligono = 0 (sin proteccion).
  Paso 5 - Guardar con el mismo profile que el DEM (GTiff, float32,
           nodata=-9999.0, compress=lzw).

Tabla de valores (binaria, modelo_coste.md 5.2):

  Situacion                          Valor
  Dentro de Red Natura (ZEPA/LIC/ZEC)  1
  Fuera de poligono (sin proteccion)   0

Nota: la capa es transitable (valor finito). No hay barrera dura (inf): la
'zona nucleo protegida' que seria intransitable no viene en estos datos (solo
hay TIPO a nivel de espacio completo) y se trataria, si llegara, como una capa
de barrera aparte. Las columnas site_code, SITE_NAME, AC y HECTAREAS no
intervienen en el valor (se reservan para las metricas del hito 4: nombre del
espacio afectado).

Salida: data/processed/Capas_Coste/protegida_{s}.tif  (uno por escenario).

Uso:
  python src/superficie/zonas_protegidas.py
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask, rasterize


BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
ENTRADA_DIR = BASE / "Recorte_AOI"
SALIDA_DIR = BASE / "Capas_Coste"

ESCENARIOS = ["A", "B"]

CRS_TRABAJO = "EPSG:25830"
NODATA = -9999.0

# Variable binaria: dentro de Red Natura = 1, fuera = 0. La magnitud de la
# penalizacion la decide el peso de la capa en la combinacion (§8), no este
# valor. Por eso TODO TIPO designado (ZEPA/LIC/ZEC) vale 1, sin gradacion.
VALOR_PROTEGIDA = 1.0
VALOR_FONDO = 0.0


def procesar_escenario(s: str) -> None:
    """Genera protegida_{s}.tif a partir de natura2000_aoi_{s}.gpkg."""
    dem_path = ENTRADA_DIR / f"dem_aoi_{s}.tif"
    natura_path = ENTRADA_DIR / f"natura2000_aoi_{s}.gpkg"
    aoi_path = BASE / f"aoi_corredor_{s}.gpkg"

    if not dem_path.exists():
        raise FileNotFoundError(f"No existe el DEM de referencia: {dem_path}")
    if not natura_path.exists():
        raise FileNotFoundError(f"No existe la capa Red Natura: {natura_path}")
    if not aoi_path.exists():
        raise FileNotFoundError(f"No existe el AOI corredor: {aoi_path}")

    # --- Paso 1: rejilla de referencia (copiada del DEM, nunca recalculada) ---
    with rasterio.open(dem_path) as ref:
        transform = ref.transform
        width, height = ref.width, ref.height
        profile = ref.profile.copy()

    # --- Paso 2: asignar coste por atributo (columna 'cost') ---
    natura = gpd.read_file(natura_path)
    if natura.crs is None:
        raise ValueError(f"La capa Red Natura no tiene CRS definido: {natura_path}")
    natura = natura.to_crs(CRS_TRABAJO)
    natura = natura[natura.geometry.notna() & ~natura.geometry.is_empty].copy()

    # --- Paso 3 + 4: rasterizar poligonos (all_touched=False) y rellenar fondo ---
    if natura.empty:
        # Sin poligono protegido en el AOI: toda la rejilla es fondo (0).
        cost_array = np.full((height, width), VALOR_FONDO, dtype="float32")
        n_poligonos = 0
    else:
        # Variable binaria: cualquier geometria Red Natura -> 1, sin gradacion.
        natura["cost"] = VALOR_PROTEGIDA
        shapes = list(zip(natura.geometry, natura["cost"]))
        cost_array = rasterize(
            shapes,
            out_shape=(height, width),
            transform=transform,
            fill=VALOR_FONDO,  # Paso 4: fondo = sin proteccion
            all_touched=False,  # poligonos: solo celdas cuyo centro cae dentro
            dtype="float32",
        )
        n_poligonos = len(natura)

    # --- Paso 4b: recortar al AOI corredor. El raster solo es valido dentro del
    # corredor (mismo poligono que aoi_corredor_{s}.gpkg). Fuera del AOI no hay
    # transito posible: esas celdas son nodata, no fondo 0. Asi la capa tiene la
    # forma del corredor y no el rectangulo completo del bounding box del DEM. ---
    aoi = gpd.read_file(aoi_path)
    if aoi.crs is None:
        raise ValueError(f"El AOI corredor no tiene CRS definido: {aoi_path}")
    aoi = aoi.to_crs(CRS_TRABAJO)
    dentro_aoi = geometry_mask(
        aoi.geometry,
        out_shape=(height, width),
        transform=transform,
        invert=True,  # True = celda dentro del corredor
    )
    cost_array = np.where(dentro_aoi, cost_array, NODATA).astype("float32")

    # --- Paso 5: guardar con el mismo profile que el DEM ---
    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    profile.update(
        driver="GTiff",
        dtype="float32",
        nodata=NODATA,
        count=1,
        compress="lzw",
    )
    salida = SALIDA_DIR / f"protegida_{s}.tif"
    with rasterio.open(salida, "w", **profile) as dst:
        dst.write(cost_array.astype(np.float32), 1)

    celdas_protegidas = int(np.count_nonzero(cost_array > 0))
    celdas_aoi = int(np.count_nonzero(dentro_aoi))
    print(
        f"[{s}] {salida.name}: {width}x{height} celdas | "
        f"{n_poligonos} poligono(s) Red Natura | "
        f"{celdas_aoi} celdas dentro del AOI | "
        f"{celdas_protegidas}/{celdas_aoi} celdas protegidas "
        f"({100 * celdas_protegidas / celdas_aoi:.1f}%)"
    )


def main() -> None:
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("Script 06 completado: capa de coste 'protegida' generada (A y B).")


if __name__ == "__main__":
    main()
