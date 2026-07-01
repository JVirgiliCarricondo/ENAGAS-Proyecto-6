"""Contrato de la rejilla común: anclaje a malla global y reproducibilidad.

El núcleo del reto es que las capas de distintos AOIs/escenarios sean
comparables celda a celda. Esto exige que la rejilla común esté anclada a una
malla universal (múltiplos exactos de `res`) y no a los bounds concretos del
AOI. Estas pruebas fijan ese contrato para evitar regresiones.
"""
import pytest

# `from_origin` (rasterio) es obligatorio para construir el transform.
pytest.importorskip("rasterio")

from src.ingesta.alinear_capas import (  # noqa: E402
    _GRID_ANCHOR_X,
    _GRID_ANCHOR_Y,
    _common_transform,
)

RES = 25.0

# AOI con bounds deliberadamente NO alineados a la malla (floats arbitrarios).
AOI_1 = (431012.3, 4482097.9, 448933.1, 4501044.4)
# AOI solapado y desplazado (p. ej. otro escenario) con bounds también sueltos.
AOI_2 = (432000.0, 4483000.0, 449000.0, 4502000.0)


def test_edges_on_global_mesh():
    """Todos los bordes de píxel son múltiplos exactos de RES desde el ancla."""
    transform, width, height = _common_transform(*AOI_1, RES)
    assert (transform.c - _GRID_ANCHOR_X) % RES == 0  # west
    assert (transform.f - _GRID_ANCHOR_Y) % RES == 0  # north
    assert transform.a == RES        # tamaño de píxel en x
    assert transform.e == -RES       # tamaño de píxel en y (norte→sur)
    assert width > 0 and height > 0


def test_aoi_fully_covered():
    """La rejilla ajustada contiene por completo el AOI original."""
    xmin, ymin, xmax, ymax = AOI_1
    transform, width, height = _common_transform(*AOI_1, RES)
    west, north = transform.c, transform.f
    east = west + width * RES
    south = north - height * RES
    assert west <= xmin and south <= ymin
    assert east >= xmax and north >= ymax


def test_two_aois_share_the_same_lattice():
    """Reproducibilidad: dos AOIs distintos caen sobre la MISMA retícula global.

    El desfase entre sus orígenes debe ser un número entero de celdas, no un
    desplazamiento sub-píxel. Es lo que garantiza que las capas de escenarios
    distintos sean comparables sin remuestreo adicional.
    """
    t1, _, _ = _common_transform(*AOI_1, RES)
    t2, _, _ = _common_transform(*AOI_2, RES)
    dx = t2.c - t1.c
    dy = t2.f - t1.f
    assert dx % RES == 0
    assert dy % RES == 0
    # Y ambos comparten pixel size idéntico.
    assert (t1.a, t1.e) == (t2.a, t2.e) == (RES, -RES)
