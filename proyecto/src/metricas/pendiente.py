"""Metricas de pendiente para rutas generadas.

Calcula, para una ruta sobre rejilla:
  - pendiente maxima de la ruta (%),
  - pendiente media de la ruta (%),
  - porcentaje de ruta que sigue la direccion de la pendiente (%),
  - distancia (km) de ruta que sigue la direccion de la pendiente.

Entrada esperada:
  - `celdas`: secuencia [(row, col), ...] de una ruta LCP.
  - `dem`: raster de elevacion alineado a la misma rejilla.
  - `aspecto_grados` (opcional): direccion de maxima pendiente por celda [0, 360).

Convenciones:
  - La pendiente local por tramo se calcula como atan(|dh| / distancia_tramo).
  - "Seguir la pendiente" significa ir paralelo al gradiente (subiendo o bajando),
    no transversal: |cos(delta)| >= cos(umbral_alineacion_grados).
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
    porcentaje_ruta_sigue_pendiente: float
    km_ruta_sigue_pendiente: float


def _angulo_ruta_grados(dr: int, dc: int) -> float:
    """Azimut de avance en grados [0, 360), 0=N, 90=E."""
    # dr crece hacia el Sur -> componente Norte = -dr
    ang = math.degrees(math.atan2(dc, -dr))
    return (ang + 360.0) % 360.0


def _distancia_tramo_m(dr: int, dc: int, resolucion_m: float) -> float:
    return math.hypot(dr, dc) * resolucion_m


def _es_tramo_alineado(theta_ruta: float, theta_aspecto: float, umbral_grados: float) -> bool:
    """True si el tramo sigue la pendiente (paralelo u opuesto al gradiente)."""
    delta = abs(theta_ruta - theta_aspecto) % 360.0
    delta = min(delta, 360.0 - delta)  # [0, 180]
    # Seguir pendiente acepta paralelo en ambos sentidos: 0 o 180.
    return abs(math.cos(math.radians(delta))) >= math.cos(math.radians(umbral_grados))


def calcular_metricas_pendiente(
    celdas: list[tuple[int, int]],
    dem: np.ndarray,
    resolucion_m: float = 30.0,
    aspecto_grados: np.ndarray | None = None,
    umbral_alineacion_grados: float = 30.0,
) -> MetricasPendienteRuta:
    """Calcula metricas de pendiente para una ruta.

    Args:
        celdas: Ruta como secuencia de celdas (row, col).
        dem: Elevacion (misma rejilla que celdas).
        resolucion_m: Tamano de celda.
        aspecto_grados: Direccion de maxima pendiente [0, 360). Si no se aporta,
            no se calcula alineacion y se devuelve 0 en las metricas de seguimiento.
        umbral_alineacion_grados: Umbral angular para considerar que un tramo
            "sigue pendiente" (por defecto 30 grados).
    """
    if len(celdas) < 2:
        return MetricasPendienteRuta(
            pendiente_max_pct=0.0,
            pendiente_media_pct=0.0,
            porcentaje_ruta_sigue_pendiente=0.0,
            km_ruta_sigue_pendiente=0.0,
        )

    if dem.ndim != 2:
        raise ValueError("dem debe ser un array 2D")
    if aspecto_grados is not None and aspecto_grados.shape != dem.shape:
        raise ValueError("aspecto_grados debe tener la misma shape que dem")

    pendientes_pct: list[float] = []
    longitudes_m: list[float] = []
    longitud_total_m = 0.0
    longitud_sigue_m = 0.0

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

        if aspecto_grados is not None:
            a0 = float(aspecto_grados[r0, c0])
            a1 = float(aspecto_grados[r1, c1])
            if math.isfinite(a0) and math.isfinite(a1):
                theta_aspecto = (a0 + a1) / 2.0
                theta_ruta = _angulo_ruta_grados(dr, dc)
                if _es_tramo_alineado(theta_ruta, theta_aspecto, umbral_alineacion_grados):
                    longitud_sigue_m += dist_m

    if not pendientes_pct or longitud_total_m <= 0:
        return MetricasPendienteRuta(
            pendiente_max_pct=0.0,
            pendiente_media_pct=0.0,
            porcentaje_ruta_sigue_pendiente=0.0,
            km_ruta_sigue_pendiente=0.0,
        )

    pendientes_arr = np.asarray(pendientes_pct, dtype=np.float64)
    longitudes_arr = np.asarray(longitudes_m, dtype=np.float64)
    pendiente_media = float(np.average(pendientes_arr, weights=longitudes_arr))
    pendiente_max = float(np.max(pendientes_arr))
    porcentaje_sigue = 100.0 * (longitud_sigue_m / longitud_total_m) if aspecto_grados is not None else 0.0

    return MetricasPendienteRuta(
        pendiente_max_pct=pendiente_max,
        pendiente_media_pct=pendiente_media,
        porcentaje_ruta_sigue_pendiente=float(porcentaje_sigue),
        km_ruta_sigue_pendiente=float(longitud_sigue_m / 1000.0),
    )

