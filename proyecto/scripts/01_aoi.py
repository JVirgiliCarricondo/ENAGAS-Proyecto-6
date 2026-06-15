"""
Script 0 - Creacion del AOI corredor y recorte de rasters.

Este script define el corredor de trabajo del Hito 2: un buffer de 2 km a cada
lado del eje recto entre la planta H2 de Puertollano y el destino al norte de
Puertollano. Ese corredor sera la mascara dura que usaran los scripts
siguientes, de modo que el LCP no pueda salir del area de estudio.
"""

from pathlib import Path
from math import ceil, floor

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely.geometry import LineString, mapping


# CRS geografico de las coordenadas de entrada (latitud/longitud).
CRS_WGS84 = "EPSG:4326"

# CRS proyectado oficial del proyecto. En EPSG:25830 las distancias estan en
# metros, por eso el buffer de 2000 representa exactamente 2 km.
CRS_TRABAJO = "EPSG:25830"

# Coordenadas del trazado en formato (latitud, longitud), tal como se dieron en
# el enunciado del proyecto.
ORIGEN_LATLON = (38.68151749377432, -4.049492223656498)
DESTINO_LATLON = (38.80681007796324, -4.028723916034112)

# Anchura lateral del corredor: 2000 m a cada lado del eje origen-destino.
BUFFER_CORREDOR_M = 2000

# La resolucion no se fuerza artificialmente. Los rasters del corredor heredan
# la resolucion del raster procesado de origen; si el DEM disponible esta a
# 30 m, todo el modelo de coste se construye a 30 m.

# Rutas relativas pensadas para ejecutar el script desde la raiz de "proyecto".
BASE_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BASE_DIR / "data" / "processed"
AOI_PATH = PROCESSED_DIR / "aoi_corredor.gpkg"
RASTERS_AOI_DIR = PROCESSED_DIR / "rasters_AOI"


def obtener_rejilla_corredor(
    aoi: gpd.GeoDataFrame,
    resolucion_x: float,
    resolucion_y: float,
) -> tuple[rasterio.Affine, int, int]:
    """Calcula una rejilla que cubre el AOI usando la resolucion del raster base."""
    minx, miny, maxx, maxy = aoi.total_bounds

    # Alinear los limites a multiplos de la resolucion del raster evita
    # desplazamientos de celda y conserva la escala real del dato fuente.
    left = floor(minx / resolucion_x) * resolucion_x
    bottom = floor(miny / resolucion_y) * resolucion_y
    right = ceil(maxx / resolucion_x) * resolucion_x
    top = ceil(maxy / resolucion_y) * resolucion_y

    width = int(round((right - left) / resolucion_x))
    height = int(round((top - bottom) / resolucion_y))
    transform = from_origin(left, top, resolucion_x, resolucion_y)
    return transform, width, height


def transformar_latlon_a_utm(latlon: tuple[float, float]) -> tuple[float, float]:
    """Transforma un punto WGS84 (lat, lon) al CRS de trabajo EPSG:25830."""
    lat, lon = latlon

    # always_xy=True fuerza el orden lon, lat en la entrada y x, y en la salida,
    # evitando ambiguedades entre librerias GIS.
    transformer = Transformer.from_crs(CRS_WGS84, CRS_TRABAJO, always_xy=True)
    x, y = transformer.transform(lon, lat)
    return x, y


def crear_corredor() -> gpd.GeoDataFrame:
    """Crea un GeoDataFrame con el eje recto y su buffer de 2 km."""
    origen_xy = transformar_latlon_a_utm(ORIGEN_LATLON)
    destino_xy = transformar_latlon_a_utm(DESTINO_LATLON)

    # El eje es la linea directa entre origen y destino; el buffer alrededor de
    # esta linea define la franja de analisis permitida para todas las rutas.
    eje = LineString([origen_xy, destino_xy])
    corredor = eje.buffer(BUFFER_CORREDOR_M)

    return gpd.GeoDataFrame(
        {
            "nombre": ["corredor_h2_puertollano"],
            "buffer_m": [BUFFER_CORREDOR_M],
            "origen": ["Planta H2 Puertollano"],
            "destino": ["Norte de Puertollano"],
            "geometry": [corredor],
        },
        crs=CRS_TRABAJO,
    )


def guardar_corredor(aoi: gpd.GeoDataFrame) -> None:
    """Guarda el corredor en GeoPackage para poder abrirlo directamente en QGIS."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # driver="GPKG" escribe un GeoPackage estandar; layer permite identificar
    # claramente la capa cuando se abra el archivo en QGIS.
    aoi.to_file(AOI_PATH, layer="aoi_corredor", driver="GPKG")
    print(f"AOI corredor guardado en: {AOI_PATH}")


def listar_rasters_procesados() -> list[Path]:
    """Localiza rasters .tif procesados que aun no sean salidas de este script."""
    rasters = []

    # Se buscan todos los GeoTIFF dentro de data/processed para cumplir el
    # requisito de recortar los rasters procesados antes de usarlos.
    for raster_path in PROCESSED_DIR.rglob("*.tif"):
        nombres_padres = {parent.name.lower() for parent in raster_path.parents}
        if "rasters_aoi" in nombres_padres or "rasters_corredor" in nombres_padres:
            continue
        if raster_path.name.endswith("_corredor.tif"):
            continue
        if raster_path.name.startswith(("coste_", "superficie_coste_")):
            continue
        rasters.append(raster_path)

    return sorted(rasters)


def elegir_remuestreo(src: rasterio.DatasetReader) -> Resampling:
    """Selecciona un remuestreo prudente segun el tipo de dato del raster."""
    dtype = np.dtype(src.dtypes[0])

    # Los rasters continuos, como un DEM, se remuestrean con bilinear para
    # suavizar valores. Los enteros/categoricos usan nearest para no inventar
    # clases nuevas.
    if np.issubdtype(dtype, np.floating):
        return Resampling.bilinear
    return Resampling.nearest


def recortar_raster_al_corredor(raster_path: Path, aoi: gpd.GeoDataFrame) -> Path:
    """Recorta y enmascara un raster al AOI corredor conservando su resolucion."""
    RASTERS_AOI_DIR.mkdir(parents=True, exist_ok=True)

    # El nombre de salida incorpora la ruta relativa para evitar colisiones si
    # existen dos rasters con el mismo nombre en subcarpetas distintas.
    nombre_relativo = raster_path.relative_to(PROCESSED_DIR).with_suffix("")
    nombre_seguro = "_".join(nombre_relativo.parts)
    salida = RASTERS_AOI_DIR / f"{nombre_seguro}_corredor.tif"
    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError(f"El raster no tiene CRS definido: {raster_path}")

        nodata = src.nodata if src.nodata is not None else -9999
        remuestreo = elegir_remuestreo(src)
        resolucion_x = abs(src.res[0])
        resolucion_y = abs(src.res[1])
        transform_objetivo, width, height = obtener_rejilla_corredor(
            aoi,
            resolucion_x,
            resolucion_y,
        )

        # Se reproyecta o recorta a la rejilla del corredor sin inventar una
        # resolucion mas fina que la del raster de origen.
        data_objetivo = np.full(
            (src.count, height, width),
            nodata,
            dtype=src.dtypes[0],
        )

        for banda in range(1, src.count + 1):
            reproject(
                source=rasterio.band(src, banda),
                destination=data_objetivo[banda - 1],
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=src.nodata,
                dst_transform=transform_objetivo,
                dst_crs=CRS_TRABAJO,
                dst_nodata=nodata,
                resampling=remuestreo,
            )

        # La extension de salida es rectangular, pero el corredor real tiene
        # forma de capsula. Esta mascara deja como nodata cualquier celda fuera
        # del corredor para que las etapas de coste no la usen.
        mascara_fuera_aoi = geometry_mask(
            [mapping(geom) for geom in aoi.geometry],
            out_shape=(height, width),
            transform=transform_objetivo,
            invert=False,
        )
        data_objetivo[:, mascara_fuera_aoi] = nodata

        perfil = src.profile.copy()
        perfil.update(
            {
                "crs": CRS_TRABAJO,
                "height": height,
                "width": width,
                "transform": transform_objetivo,
                "driver": "GTiff",
                "compress": "deflate",
                "nodata": nodata,
            }
        )

        with rasterio.open(salida, "w", **perfil) as dst:
            dst.write(data_objetivo)

    print(f"Raster recortado: {raster_path} -> {salida}")
    return salida


def main() -> None:
    """Ejecuta el flujo completo del Script 0."""
    aoi = crear_corredor()
    guardar_corredor(aoi)

    rasters = listar_rasters_procesados()
    if not rasters:
        print("No se encontraron rasters .tif en data/processed para recortar.")
        return

    for raster_path in rasters:
        recortar_raster_al_corredor(raster_path, aoi)

    print("Script 0 completado: AOI creado y rasters procesados recortados.")


if __name__ == "__main__":
    main()
