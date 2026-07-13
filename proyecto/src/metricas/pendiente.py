"""Metricas de pendiente para rutas generadas.

Calcula, para una ruta sobre rejilla:
  - pendiente maxima de la ruta (%),
  - pendiente media de la ruta (%).

Entrada esperada:
  - `celdas`: secuencia [(row, col), ...] de una ruta LCP.
  - `dem`: raster de elevacion alineado a la misma rejilla.

Convenciones:
  - La pendiente local por tramo se calcula como |dh| / distancia_tramo · 100 (%).
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass
class MetricasPendienteRuta:
    """Resumen de metricas de pendiente de una ruta."""

    pendiente_max_pct: float
    pendiente_media_pct: float


def _distancia_tramo_m(dr: int, dc: int, resolucion_m: float) -> float:
    """Longitud en metros de un paso de (dr, dc) celdas sobre la rejilla.

    hypot(dr, dc) da 1 para un paso ortogonal y √2 para uno diagonal; multiplicado
    por el tamaño de celda se obtiene la distancia real del tramo en metros.
    """
    return math.hypot(dr, dc) * resolucion_m


def calcular_metricas_pendiente(
    celdas: list[tuple[int, int]],
    dem: np.ndarray,
    resolucion_m: float = 30.0,
) -> MetricasPendienteRuta:
    """Calcula metricas de pendiente para una ruta.

    Recorre la ruta tramo a tramo (celda→celda), estima la pendiente local de cada
    tramo como |dz| / distancia · 100 (%) y agrega: la maxima es el mayor valor de
    tramo; la media se pondera por la longitud de cada tramo (los tramos diagonales,
    mas largos, pesan mas que los ortogonales). Los tramos con elevacion nodata/nan
    en alguno de sus extremos se descartan.

    Args:
        celdas: Ruta como secuencia de celdas (row, col).
        dem: Elevacion en metros (misma rejilla que celdas; nan = sin dato).
        resolucion_m: Tamano de celda en metros.

    Returns:
        MetricasPendienteRuta con pendiente_max_pct y pendiente_media_pct (%).
        Ambas 0.0 si la ruta tiene <2 celdas o ningun tramo valido.

    Raises:
        ValueError: Si `dem` no es un array 2D.
    """
    if len(celdas) < 2:
        return MetricasPendienteRuta(
            pendiente_max_pct=0.0,
            pendiente_media_pct=0.0,
        )

    if dem.ndim != 2:
        raise ValueError("dem debe ser un array 2D")

    pendientes_pct: list[float] = []
    longitudes_m: list[float] = []
    longitud_total_m = 0.0

    for (r0, c0), (r1, c1) in zip(celdas[:-1], celdas[1:]):
        dr, dc = r1 - r0, c1 - c0
        dist_m = _distancia_tramo_m(dr, dc, resolucion_m)
        if dist_m <= 0:
            continue

        z0 = float(dem[r0, c0])
        z1 = float(dem[r1, c1])
        if not (math.isfinite(z0) and math.isfinite(z1)):
            continue

        # slope_pct = tan(atan(|dh|/dist))*100 = |dh|/dist*100
        slope_pct = abs(z1 - z0) / dist_m * 100.0
        pendientes_pct.append(slope_pct)
        longitudes_m.append(dist_m)
        longitud_total_m += dist_m

    if not pendientes_pct or longitud_total_m <= 0:
        return MetricasPendienteRuta(
            pendiente_max_pct=0.0,
            pendiente_media_pct=0.0,
        )

    pendientes_arr = np.asarray(pendientes_pct, dtype=np.float64)
    longitudes_arr = np.asarray(longitudes_m, dtype=np.float64)
    pendiente_media = float(np.average(pendientes_arr, weights=longitudes_arr))
    pendiente_max = float(np.max(pendientes_arr))

    return MetricasPendienteRuta(
        pendiente_max_pct=pendiente_max,
        pendiente_media_pct=pendiente_media,
    )

