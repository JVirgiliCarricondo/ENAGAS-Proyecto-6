"""
Script 06 - Capa de coste P4: zonas protegidas (Red Natura 2000).

Convierte natura2000_aoi_{s}.gpkg en un raster de coste relativo [0, 1]
alineado a la rejilla del DEM del AOI. Modelo de coste en modelo_coste.md (5.2)
y resumen del reto en CLAUDE.md.

Patron comun de las capas de coste (hito 2):
  Paso 1 - Leer la rejilla de referencia: copiar SIEMPRE transform/width/height/
           CRS del DEM (dem_aoi_{s}.tif). Nunca calcular la rejilla a mano: asi
           es imposible que las capas queden desalineadas.
  Paso 2 - Asignar coste por atributo: columna 'cost' segun la tabla TIPO.
  Paso 3 - Rasterizar sobre la rejilla. Poligonos -> all_touched=False.
  Paso 4 - Rellenar fondo: celdas fuera de poligono = valor de fondo (0.0).
  Paso 5 - Guardar con el mismo profile que el DEM (GTiff, float32,
           nodata=-9999.0, compress=lzw).

Tabla de coste (modelo_coste.md 5.2 / 5.4):

  TIPO  Significado                       Coste  Tratamiento
  A     ZEPA                              0.9    coste alto finito
  B     LIC / ZEC                         0.9    coste alto finito
  C     ZEPA + LIC                        0.9    coste alto finito
  --    fuera de poligono (sin proteccion) 0.0   fondo

Nota: modelo_coste.md define barrera dura (inf) solo para 'zona nucleo
protegida'. Esta capa NO contiene ese campo, asi que todo el interior del
poligono es coste alto finito (0.9), no barrera. Las columnas site_code,
SITE_NAME, AC y HECTAREAS no intervienen en el coste (se reservan para las
metricas del hito 4: nombre del espacio afectado).

Salida: data/processed/Capas_Coste/protegida_{s}.tif  (uno por escenario).

Uso:
  python scripts/06_protegida.py
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize


BASE = Path(__file__).resolve().parents[1] / "data" / "processed"
ENTRADA_DIR = BASE / "Recorte_AOI"
SALIDA_DIR = BASE / "Capas_Coste"

ESCENARIOS = ["A", "B"]

CRS_TRABAJO = "EPSG:25830"
NODATA = -9999.0
COSTE_FONDO = 0.0

# Lookup fijo por categoria (modelo_coste.md 5.2). Tabla, no data-driven.
COSTE_POR_TIPO = {
    "A": 0.9,  # ZEPA
    "B": 0.9,  # LIC / ZEC
    "C": 0.9,  # ZEPA + LIC
}
COSTE_PROTEGIDA_DEFECTO = 0.9  # cualquier TIPO designado no previsto


def coste_por_tipo(tipo) -> float:
    """Devuelve el coste relativo de un poligono Red Natura segun su TIPO."""
    clave = str(tipo).strip().upper()
    return COSTE_POR_TIPO.get(clave, COSTE_PROTEGIDA_DEFECTO)


def procesar_escenario(s: str) -> None:
    """Genera protegida_{s}.tif a partir de natura2000_aoi_{s}.gpkg."""
    dem_path = ENTRADA_DIR / f"dem_aoi_{s}.tif"
    natura_path = ENTRADA_DIR / f"natura2000_aoi_{s}.gpkg"

    if not dem_path.exists():
        raise FileNotFoundError(f"No existe el DEM de referencia: {dem_path}")
    if not natura_path.exists():
        raise FileNotFoundError(f"No existe la capa Red Natura: {natura_path}")

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
        # Sin poligono protegido en el AOI: toda la rejilla es fondo (0.0).
        cost_array = np.full((height, width), COSTE_FONDO, dtype="float32")
        n_poligonos = 0
    else:
        natura["cost"] = natura["TIPO"].map(coste_por_tipo)
        shapes = list(zip(natura.geometry, natura["cost"]))
        cost_array = rasterize(
            shapes,
            out_shape=(height, width),
            transform=transform,
            fill=COSTE_FONDO,  # Paso 4: fondo = sin proteccion
            all_touched=False,  # poligonos: solo celdas cuyo centro cae dentro
            dtype="float32",
        )
        n_poligonos = len(natura)

    # Esta capa no tiene barreras duras (inf); la linea se deja por consistencia
    # con el esquema comun de las capas de coste.
    cost_array[np.isinf(cost_array)] = NODATA

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
    total = cost_array.size
    print(
        f"[{s}] {salida.name}: {width}x{height} celdas | "
        f"{n_poligonos} poligono(s) Red Natura | "
        f"{celdas_protegidas}/{total} celdas protegidas "
        f"({100 * celdas_protegidas / total:.1f}%)"
    )


def main() -> None:
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("Script 06 completado: capa de coste 'protegida' generada (A y B).")


if __name__ == "__main__":
    main()
