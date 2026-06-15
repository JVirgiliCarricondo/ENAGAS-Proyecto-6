"""
Script 2 - Rasterizacion de capas vectoriales de coste.

Convierte las capas vectoriales ya procesadas a la misma rejilla raster del DEM
del corredor: EPSG:25830, misma resolucion, misma extension y mismo origen de
celda. Cada raster resultante representa un indice relativo de coste 0-1, nunca
euros.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask, rasterize


BASE_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BASE_DIR / "data" / "processed"
VECTORES_DIR = PROCESSED_DIR / "Recorte_AOI"
RASTERS_AOI_DIR = PROCESSED_DIR / "rasters_AOI"

AOI_PATH = PROCESSED_DIR / "aoi_corredor.gpkg"
DEM_CORREDOR_PATH = RASTERS_AOI_DIR / "dem_aoi_corredor.tif"

CATastro_PATH = VECTORES_DIR / "catastro_aoi.gpkg"
NATURA_PATH = VECTORES_DIR / "natura2000_aoi.gpkg"
OSM_PATH = VECTORES_DIR / "osm_aoi.gpkg"
HIDRO_PATH = VECTORES_DIR / "hidrografia_aoi.gpkg"

SALIDA_SUELO = RASTERS_AOI_DIR / "coste_suelo.tif"
SALIDA_PROTEGIDA = RASTERS_AOI_DIR / "coste_protegida.tif"
SALIDA_OSM = RASTERS_AOI_DIR / "coste_osm.tif"
SALIDA_HIDRO = RASTERS_AOI_DIR / "coste_hidrografia.tif"
SALIDA_CRUCES = RASTERS_AOI_DIR / "coste_cruces.tif"

CRS_TRABAJO = "EPSG:25830"
NODATA_COSTE = -9999.0


def leer_rejilla_referencia() -> tuple[dict, np.ndarray]:
    """Lee el perfil del DEM corredor y crea la mascara booleana de trabajo."""
    if not DEM_CORREDOR_PATH.exists():
        raise FileNotFoundError(
            "No se encontro el DEM del corredor. Ejecuta primero scripts/01_aoi.py."
        )
    if not AOI_PATH.exists():
        raise FileNotFoundError(
            "No se encontro el AOI corredor. Ejecuta primero scripts/01_aoi.py."
        )

    with rasterio.open(DEM_CORREDOR_PATH) as src:
        perfil = src.profile.copy()
        dem = src.read(1)
        if src.nodata is None:
            dem_valido = np.isfinite(dem)
        else:
            dem_valido = dem != src.nodata

    aoi = gpd.read_file(AOI_PATH, layer="aoi_corredor").to_crs(CRS_TRABAJO)

    # True significa celda dentro del corredor. La combinamos con la mascara del
    # DEM para que ningun raster de coste sea valido donde no hay pendiente.
    dentro_aoi = geometry_mask(
        aoi.geometry,
        out_shape=(perfil["height"], perfil["width"]),
        transform=perfil["transform"],
        invert=True,
    )
    mascara_trabajo = dentro_aoi & dem_valido
    return perfil, mascara_trabajo


def leer_vector(path: Path) -> gpd.GeoDataFrame:
    """Carga una capa vectorial y garantiza CRS EPSG:25830."""
    if not path.exists():
        raise FileNotFoundError(f"No existe la capa vectorial esperada: {path}")

    gdf = gpd.read_file(path)
    if gdf.empty:
        return gdf.set_crs(CRS_TRABAJO, allow_override=True)
    if gdf.crs is None:
        raise ValueError(f"La capa no tiene CRS definido: {path}")
    return gdf.to_crs(CRS_TRABAJO)


def preparar_raster_base(dentro_aoi: np.ndarray, valor_base: float = 0.0) -> np.ndarray:
    """Crea un raster float32 con nodata fuera del corredor."""
    raster = np.full(dentro_aoi.shape, NODATA_COSTE, dtype="float32")
    raster[dentro_aoi] = valor_base
    return raster


def clasificar_coste_suelo(fila) -> float:
    """Asigna coste relativo de suelo a cada parcela catastral."""
    tipo = str(fila.get("TIPO", "")).strip().upper()

    # Catastro suele codificar urbano como U y rustico como R. En esta AOI
    # tambien aparece X, que tratamos como baldío/desconocido de bajo coste.
    if tipo in {"U", "URBANO", "URBAN"}:
        return 1.0
    if tipo in {"I", "IND", "INDUSTRIAL"}:
        return 0.9
    if tipo in {"R", "RUSTICO", "RUSTICA", "AGRICOLA", "AGRARIO"}:
        return 0.4
    if tipo in {"X", "BALDIO", "SIN_USO", "DESCONOCIDO", ""}:
        return 0.1

    # Ante codigos no previstos, usamos el coste mas bajo de suelo alterable
    # para no penalizar indebidamente zonas sin clasificacion clara.
    return 0.1


def rasterizar_suelo(perfil: dict, dentro_aoi: np.ndarray) -> np.ndarray:
    """Rasteriza Catastro a coste de suelo: urbano, industrial, agricola o baldio."""
    catastro = leer_vector(CATastro_PATH)
    raster = preparar_raster_base(dentro_aoi, valor_base=0.1)

    if catastro.empty:
        return raster

    catastro = catastro[catastro.geometry.notna() & ~catastro.geometry.is_empty].copy()
    shapes = [
        (geom, clasificar_coste_suelo(fila))
        for fila, geom in zip(catastro.to_dict("records"), catastro.geometry)
    ]

    valores = rasterize(
        shapes,
        out_shape=(perfil["height"], perfil["width"]),
        transform=perfil["transform"],
        fill=0.1,
        dtype="float32",
        all_touched=True,
    )
    raster[dentro_aoi] = valores[dentro_aoi]
    return raster


def rasterizar_protegida(perfil: dict, dentro_aoi: np.ndarray) -> np.ndarray:
    """Rasteriza Red Natura 2000: dentro=0.9 y fuera=0.0."""
    natura = leer_vector(NATURA_PATH)
    raster = preparar_raster_base(dentro_aoi, valor_base=0.0)

    if natura.empty:
        return raster

    natura = natura[natura.geometry.notna() & ~natura.geometry.is_empty]
    shapes = [(geom, 0.9) for geom in natura.geometry]
    valores = rasterize(
        shapes,
        out_shape=(perfil["height"], perfil["width"]),
        transform=perfil["transform"],
        fill=0.0,
        dtype="float32",
        all_touched=True,
    )
    raster[dentro_aoi] = valores[dentro_aoi]
    return raster


def filtrar_osm_cruces(osm: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Selecciona carreteras y ferrocarril de la capa OSM disponible."""
    if osm.empty or "fclass" not in osm.columns:
        return osm

    clases_cruce = {
        "motorway",
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "unclassified",
        "residential",
        "service",
        "track",
        "track_grade1",
        "track_grade2",
        "track_grade3",
        "track_grade4",
        "track_grade5",
        "rail",
        "railway",
    }
    return osm[osm["fclass"].astype(str).str.lower().isin(clases_cruce)].copy()


def rasterizar_buffer_lineas(
    path: Path,
    perfil: dict,
    dentro_aoi: np.ndarray,
    buffer_m: float,
    coste: float,
    filtrar_osm: bool = False,
) -> np.ndarray:
    """Rasteriza lineas aplicando un buffer previo en metros."""
    lineas = leer_vector(path)
    raster = preparar_raster_base(dentro_aoi, valor_base=0.0)

    if filtrar_osm:
        lineas = filtrar_osm_cruces(lineas)
    if lineas.empty:
        return raster

    lineas = lineas[lineas.geometry.notna() & ~lineas.geometry.is_empty].copy()

    # Al estar en EPSG:25830, el buffer se expresa en metros: 50 m para
    # carreteras/ferrocarril y 30 m para rios.
    geometrias_buffer = lineas.geometry.buffer(buffer_m)
    shapes = [(geom, coste) for geom in geometrias_buffer if geom is not None and not geom.is_empty]

    if not shapes:
        return raster

    valores = rasterize(
        shapes,
        out_shape=(perfil["height"], perfil["width"]),
        transform=perfil["transform"],
        fill=0.0,
        dtype="float32",
        all_touched=True,
    )
    raster[dentro_aoi] = valores[dentro_aoi]
    return raster


def guardar_raster(path: Path, datos: np.ndarray, perfil_ref: dict) -> None:
    """Guarda un raster de coste con la misma rejilla que el DEM corredor."""
    path.parent.mkdir(parents=True, exist_ok=True)

    perfil = perfil_ref.copy()
    perfil.update(
        {
            "driver": "GTiff",
            "count": 1,
            "dtype": "float32",
            "nodata": NODATA_COSTE,
            "compress": "deflate",
        }
    )

    with rasterio.open(path, "w", **perfil) as dst:
        dst.write(datos.astype("float32"), 1)

    print(f"Raster guardado: {path}")


def main() -> None:
    """Ejecuta el rasterizado de todas las capas de coste vectoriales."""
    perfil, dentro_aoi = leer_rejilla_referencia()

    coste_suelo = rasterizar_suelo(perfil, dentro_aoi)
    coste_protegida = rasterizar_protegida(perfil, dentro_aoi)
    coste_osm = rasterizar_buffer_lineas(
        OSM_PATH,
        perfil,
        dentro_aoi,
        buffer_m=50,
        coste=1.0,
        filtrar_osm=True,
    )
    coste_hidro = rasterizar_buffer_lineas(
        HIDRO_PATH,
        perfil,
        dentro_aoi,
        buffer_m=30,
        coste=0.8,
        filtrar_osm=False,
    )

    # Para el Script 3 se usa un unico factor "cruces"; tomar el maximo conserva
    # el coste mas restrictivo entre infraestructuras lineales y rios.
    coste_cruces = preparar_raster_base(dentro_aoi, valor_base=0.0)
    celdas_validas = dentro_aoi
    coste_cruces[celdas_validas] = np.maximum(
        coste_osm[celdas_validas],
        coste_hidro[celdas_validas],
    )

    guardar_raster(SALIDA_SUELO, coste_suelo, perfil)
    guardar_raster(SALIDA_PROTEGIDA, coste_protegida, perfil)
    guardar_raster(SALIDA_OSM, coste_osm, perfil)
    guardar_raster(SALIDA_HIDRO, coste_hidro, perfil)
    guardar_raster(SALIDA_CRUCES, coste_cruces, perfil)

    print("Script 2 completado: capas vectoriales rasterizadas a la rejilla del DEM.")


if __name__ == "__main__":
    main()
