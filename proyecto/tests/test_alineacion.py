"""Pruebas de la alineación de rasters — el componente más crítico del reto.

Esqueleto de partida. Priorizar aquí: si las capas no comparten CRS y rejilla, toda
superficie de coste posterior es engañosa. Activar (quitar skip) en el Sprint 2.
"""

import pytest

from src.ingesta.alineacion import Rejilla


@pytest.mark.skip(reason="Implementar en Sprint 2")
def test_capas_alineadas_comparten_shape():
    # Dos capas distintas, tras alinearse a la misma rejilla, deben tener la MISMA forma.
    rejilla = Rejilla(crs="EPSG:25830", resolucion_m=30, xmin=0, ymin=0, xmax=3000, ymax=3000)
    # dem = alinear_raster("data/raw/DEM.tif", rejilla)
    # clc = rasterizar_vector(gdf_clc, rejilla, columna="clase")
    # assert dem.shape == clc.shape == rejilla.shape
    assert rejilla.crs == "EPSG:25830"


@pytest.mark.skip(reason="Implementar en Sprint 2")
def test_rejilla_resolucion_consistente():
    # La rejilla a 30 m sobre un AOI de 3000 m debe dar 100 celdas por lado.
    rejilla = Rejilla(crs="EPSG:25830", resolucion_m=30, xmin=0, ymin=0, xmax=3000, ymax=3000)
    assert rejilla.shape == (100, 100)
