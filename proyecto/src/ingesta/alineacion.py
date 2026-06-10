"""Alineación de capas a un CRS y una rejilla comunes.

Esqueleto de partida — completar en el Sprint 2. Apoyarse en `rasterio` (warp/reproject)
y `geopandas`/`rasterio.features` (rasterización de vectores).

El corazón del reto: "alinear antes de combinar". Toda capa, antes de convertirse en coste,
debe estar recortada al AOI, reproyectada a EPSG:25830 y remuestreada/rasterizada a la
MISMA rejilla (misma resolución y mismo origen de celda) que las demás.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Rejilla:
    """Definición de la rejilla común de trabajo."""
    crs: str            # p.ej. "EPSG:25830"
    resolucion_m: float
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def shape(self) -> tuple[int, int]:
        """(filas, columnas) de la rejilla. TODO(S2): derivar de extent y resolución."""
        raise NotImplementedError("Calcular dimensiones de la rejilla — Sprint 2")


def rejilla_desde_escenario(escenario_path: str | Path) -> Rejilla:
    """Construye la rejilla común a partir de data/config/escenario.yaml.

    TODO(S2): leer crs_trabajo, resolucion_m y aoi; validar que el AOI es coherente.
    """
    raise NotImplementedError("Leer escenario y construir rejilla — Sprint 2")


def alinear_raster(src_path: str | Path, rejilla: Rejilla, resampling: str = "bilinear"):
    """Reproyecta y remuestrea un raster (p.ej. el DEM) a la rejilla común.

    TODO(S2): rasterio.warp.reproject hacia rejilla.crs / rejilla.shape / transform.
    Devuelve un array 2D alineado (y, opcionalmente, lo escribe en data/processed/).
    """
    raise NotImplementedError("Reproyectar + remuestrear a la rejilla común — Sprint 2")


def rasterizar_vector(gdf, rejilla: Rejilla, columna: str | None = None):
    """Rasteriza una capa vectorial (Red Natura 2000, CLC, OSM) sobre la rejilla común.

    TODO(S2): reproyectar el GeoDataFrame a rejilla.crs y usar rasterio.features.rasterize
    para quemar geometrías (o el valor de `columna`) en un array de la forma rejilla.shape.
    """
    raise NotImplementedError("Rasterizar vector a la rejilla común — Sprint 2")
