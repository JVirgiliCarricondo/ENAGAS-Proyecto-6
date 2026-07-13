"""
Script 06 - Capa de coste P4: zonas protegidas (Red Natura 2000).

Convierte natura2000_aoi_{s}.gpkg en un raster BINARIO {0, 1} alineado a la
rejilla del DEM del AOI. Modelo de coste en modelo_coste.md (5.2) y resumen del
reto en CLAUDE.md.

La proteccion es una variable binaria: una celda esta dentro de Red Natura
o no lo esta. El valor "dentro" esta estandarizado al factor oficial
"RED NATURA 2000" (A=28.5 / 38 = 0.75), de modo que la capa comparte la escala
[0,1] con las demas. El PESO de la capa en la combinacion multicriterio (§8)
sigue modulando el enfasis por perfil. Por eso aqui el valor es 0.75 (dentro)
o 0 (fuera), nada intermedio.

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

Tabla de valores (binaria, estandarizada A_oficial / 38):

  Situacion                            Valor
  Dentro de Red Natura (ZEPA/LIC/ZEC)  0.75   (A oficial = 28.5)
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
from rasterio.features import rasterize

try:
    from .config import params_zonas_protegidas as _params_zonas_protegidas
except ImportError:
    from config import params_zonas_protegidas as _params_zonas_protegidas

BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
ENTRADA_DIR = BASE / "Recorte_AOI"
SALIDA_DIR = BASE / "Capas_Coste"

ESCENARIOS = ["A", "B"]

CRS_TRABAJO = "EPSG:25830"
NODATA = -9999.0

# Parámetros cargados de perfiles.yaml (parametros_capas.zonas_protegidas)
_zcfg = _params_zonas_protegidas()
VALOR_PROTEGIDA: float = float(_zcfg["valor_protegida"])
VALOR_FONDO: float = float(_zcfg["valor_fondo"])


def procesar_escenario(s: str) -> None:
    """Genera protegida_{s}.tif a partir de natura2000_aoi_{s}.gpkg.

    Entradas (data/processed/Recorte_AOI/):
        - dem_aoi_{s}.tif        : rejilla de referencia (define transform/tamaño/CRS).
        - natura2000_aoi_{s}.gpkg: polígonos Red Natura 2000 recortados al AOI.

    Salida (data/processed/Capas_Coste/):
        - protegida_{s}.tif      : coste binario {0, VALOR_PROTEGIDA} en escala [0, 1].

    Args:
        s: Identificador de escenario ('A' o 'B').

    Raises:
        FileNotFoundError: Si falta el DEM o la capa Red Natura.
        ValueError: Si la capa Red Natura no tiene CRS definido.
    """
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
    """Genera protegida_A.tif y protegida_B.tif (capa de zonas protegidas)."""
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("Script 06 completado: capa de coste 'protegida' generada (A y B).")


if __name__ == "__main__":
    main()
