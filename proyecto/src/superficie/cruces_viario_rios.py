"""
Script 07 - Capa de coste P5: cruces viario + rios -> cruces_{s}.tif.

Funde dos fuentes lineales (osm_aoi_{s}.gpkg + hidrografia_aoi_{s}.gpkg) en un
unico raster de coste de cruce [0, 1] alineado a la rejilla del DEM del AOI.
Guia de capas (5.5) y modelo de coste en modelo_coste.md (6, coste de cruce).

A diferencia de las capas de transito, esta es una capa de COSTE DE CRUCE: el
coste se paga UNA VEZ al atravesar la linea, no por proximidad. Por eso las
lineas se rasterizan a 1 celda de ancho (all_touched=True) y NO se bufferizan.

Patron comun de las capas de coste (hito 2):
  Paso 1 - Leer la rejilla de referencia: copiar SIEMPRE transform/width/height/
           CRS del DEM (dem_aoi_{s}.tif). Nunca calcular la rejilla a mano.
  Paso 2 - Asignar coste por atributo: columna 'cost' segun las tablas de 5.5.
  Paso 3 - Rasterizar sobre la rejilla. Lineas -> all_touched=True.
  Paso 4 - Rellenar fondo: celdas sin linea = 0.0 (sin cruce).
  Paso 5 - Guardar con el mismo profile que el DEM (GTiff, float32,
           nodata=-9999.0, compress=lzw).

Combinacion de las dos fuentes: se rasteriza OSM e hidrografia por separado y
se funden con el MAXIMO por celda. Si una celda es a la vez viario y rio, gana
el cruce mas restrictivo (decision del equipo, coherente con el script 03).

Tabla OSM (columna 'highway'; ferrocarril en columna 'railway'):

  Categoria                         Coste
  path / track / footway            0.2
  service / unclassified            0.3
  residential                       0.4
  tertiary                          0.5
  secondary                         0.6
  primary                           0.7
  trunk / motorway                  0.8
  railway (columna railway no nula) 0.9
  construction                      0.4   (caso especial, ~residential)
  cualquier highway no listado      0.3   (default prudente ~unclassified)

  El ferrocarril vive en la columna 'railway' (valor 'rail'), NO en 'highway'
  (la guia lo lista bajo highway, pero el esquema real lo separa). El peso de
  'construction' (vias en obra: estado temporal, no clase) y el default lo fija
  el agente geografo-SIG: 0.4 y 0.3 respectivamente (calibrables, §10).

Tabla hidrografia (columnas 'text' = nombre del rio, 'length' = metros):

  Criterio                          Coste
  Sin nombre (text nulo/vacio)      0.3   (rambla/val estacional)
  Con nombre y length <= 2000 m     0.5   (rio menor)
  Con nombre y length >  2000 m     0.8   (rio principal)

Columnas descartadas para el coste (utiles solo para metricas/trazabilidad):
  OSM: osm_id, oneway, surface, maxspeed (name puede usarse en metricas).
  HID: gml_id, localId, namespace, beginLifespanVersion, fictitious,
       classificationScheme y todos los campos hydroId|*.

Salida: data/processed/Capas_Coste/cruces_{s}.tif  (uno por escenario).
Rango [0.0, 0.9], fondo 0.0.

Uso:
  python src/superficie/cruces_viario_rios.py
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
COSTE_FONDO = 0.0

# --- Lookup viario (columna 'highway'). Tabla fija, no data-driven. ---
COSTE_HIGHWAY = {
    "path": 0.2,
    "track": 0.2,
    "footway": 0.2,
    "service": 0.3,
    "unclassified": 0.3,
    "residential": 0.4,
    "tertiary": 0.5,
    "secondary": 0.6,
    "primary": 0.7,
    "trunk": 0.8,
    "motorway": 0.8,
    "construction": 0.4,  # via en obra (~residential), dictamen geografo-SIG
}
COSTE_HIGHWAY_DEFECTO = 0.3  # highway no listado (~unclassified), prudente
COSTE_FERROCARRIL = 0.9  # filas con columna 'railway' no nula (p.ej. 'rail')

# --- Criterios hidrografia (columnas 'text' y 'length' en metros). ---
COSTE_RIO_SIN_NOMBRE = 0.3  # rambla / val estacional
COSTE_RIO_MENOR = 0.5  # con nombre y length <= UMBRAL_RIO_M
COSTE_RIO_PRINCIPAL = 0.8  # con nombre y length >  UMBRAL_RIO_M
UMBRAL_RIO_M = 2000.0


def coste_highway(valor) -> float:
    """Coste de cruce de una via segun su categoria 'highway'."""
    clave = str(valor).strip().lower()
    return COSTE_HIGHWAY.get(clave, COSTE_HIGHWAY_DEFECTO)


def coste_rio(nombre, longitud) -> float:
    """Coste de cruce de un curso de agua segun nombre y longitud (m)."""
    tiene_nombre = nombre is not None and str(nombre).strip() != ""
    if not tiene_nombre:
        return COSTE_RIO_SIN_NOMBRE
    try:
        largo = float(longitud)
    except (TypeError, ValueError):
        # Con nombre pero sin longitud fiable: tratar como rio menor.
        return COSTE_RIO_MENOR
    return COSTE_RIO_MENOR if largo <= UMBRAL_RIO_M else COSTE_RIO_PRINCIPAL


def _limpiar_geom(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Reproyecta al CRS comun y descarta geometrias vacias o nulas."""
    if gdf.crs is None:
        raise ValueError("La capa no tiene CRS definido.")
    gdf = gdf.to_crs(CRS_TRABAJO)
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()


def rasterizar_osm(path: Path, transform, width: int, height: int) -> np.ndarray:
    """Rasteriza el viario OSM (+ ferrocarril) a coste de cruce."""
    osm = _limpiar_geom(gpd.read_file(path))
    if osm.empty:
        return np.full((height, width), COSTE_FONDO, dtype="float32")

    tiene_railway = "railway" in osm.columns
    valores = []
    for fila in osm.itertuples(index=False):
        # El ferrocarril (columna 'railway' no nula) manda sobre 'highway'.
        rail = getattr(fila, "railway", None) if tiene_railway else None
        if rail is not None and str(rail).strip() != "":
            valores.append(COSTE_FERROCARRIL)
        else:
            valores.append(coste_highway(getattr(fila, "highway", None)))

    shapes = list(zip(osm.geometry, valores))
    return rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=COSTE_FONDO,
        all_touched=True,  # lineas de 1 celda de ancho: el cruce se activa al tocar
        dtype="float32",
    )


def rasterizar_hidro(path: Path, transform, width: int, height: int) -> np.ndarray:
    """Rasteriza la hidrografia IGN a coste de cruce."""
    hid = _limpiar_geom(gpd.read_file(path))
    if hid.empty:
        return np.full((height, width), COSTE_FONDO, dtype="float32")

    col_text = "text" if "text" in hid.columns else None
    col_len = "length" if "length" in hid.columns else None
    valores = [
        coste_rio(
            getattr(fila, col_text, None) if col_text else None,
            getattr(fila, col_len, None) if col_len else None,
        )
        for fila in hid.itertuples(index=False)
    ]

    shapes = list(zip(hid.geometry, valores))
    return rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=COSTE_FONDO,
        all_touched=True,
        dtype="float32",
    )


def procesar_escenario(s: str) -> None:
    """Genera cruces_{s}.tif fundiendo OSM e hidrografia (maximo por celda)."""
    dem_path = ENTRADA_DIR / f"dem_aoi_{s}.tif"
    osm_path = ENTRADA_DIR / f"osm_aoi_{s}.gpkg"
    hidro_path = ENTRADA_DIR / f"hidrografia_aoi_{s}.gpkg"
    aoi_path = BASE / f"aoi_corredor_{s}.gpkg"

    for p in (dem_path, osm_path, hidro_path, aoi_path):
        if not p.exists():
            raise FileNotFoundError(f"No existe la entrada esperada: {p}")

    # --- Paso 1: rejilla de referencia (copiada del DEM, nunca recalculada) ---
    with rasterio.open(dem_path) as ref:
        transform = ref.transform
        width, height = ref.width, ref.height
        profile = ref.profile.copy()

    # --- Pasos 2-4: coste por atributo, rasterizado y fondo, por fuente ---
    coste_osm = rasterizar_osm(osm_path, transform, width, height)
    coste_hidro = rasterizar_hidro(hidro_path, transform, width, height)

    # Fusion: el cruce mas restrictivo gana en cada celda.
    cost_array = np.maximum(coste_osm, coste_hidro).astype("float32")

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
    salida = SALIDA_DIR / f"cruces_{s}.tif"
    with rasterio.open(salida, "w", **profile) as dst:
        dst.write(cost_array, 1)

    celdas_cruce = int(np.count_nonzero(cost_array > 0))
    celdas_aoi = int(np.count_nonzero(dentro_aoi))
    valores_unicos = sorted(
        {round(v, 2) for v in np.unique(cost_array).tolist() if v != NODATA}
    )
    print(
        f"[{s}] {salida.name}: {width}x{height} celdas | "
        f"{celdas_aoi} celdas dentro del AOI | "
        f"{celdas_cruce}/{celdas_aoi} celdas con cruce "
        f"({100 * celdas_cruce / celdas_aoi:.1f}%) | valores={valores_unicos}"
    )


def main() -> None:
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("Script 07 completado: capa de coste 'cruces' generada (A y B).")


if __name__ == "__main__":
    main()
