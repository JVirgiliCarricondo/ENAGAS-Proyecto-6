"""Cálculo de las métricas multicriterio de una ruta.

Esqueleto de partida — completar en el Sprint 5. Recibe una ruta (de src.trazados) y las
capas alineadas (de src.ingesta) y devuelve el diccionario de métricas para la comparativa.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetricasRuta:
    perfil: str
    longitud_km: float = 0.0
    coste_relativo: float = 0.0                 # índice 0-1, NUNCA €
    cruces: dict[str, int] = field(default_factory=dict)  # {"rio": n, "carretera": n, ...}
    km_protegida: float = 0.0
    km_urbana: float = 0.0
    pendiente_max_pct: float = 0.0
    pendiente_media_pct: float = 0.0


def longitud_km(ruta, rejilla) -> float:
    """Longitud total de la ruta en km (a partir de la geometría sobre la rejilla).

    TODO(S5): sumar distancias entre celdas consecutivas (diagonales incluidas).
    """
    raise NotImplementedError("Calcular longitud — Sprint 5")


def contar_cruces(ruta, capas_vectoriales: dict) -> dict[str, int]:
    """Cuenta y clasifica los cruces de la ruta con ríos, carreteras, ferrocarril, etc.

    TODO(S5): intersecar la línea de la ruta con cada capa vectorial (shapely) y contar.
    """
    raise NotImplementedError("Contar cruces especiales — Sprint 5")


def km_en_zona(ruta, mascara_zona, rejilla) -> float:
    """Km de la ruta dentro de una zona (Red Natura 2000, suelo urbano…) dada como máscara.

    TODO(S5): longitud de la porción de ruta cuyas celdas caen en la máscara.
    """
    raise NotImplementedError("Calcular km en zona — Sprint 5")


def pendiente_a_lo_largo(ruta, dem, resolucion_m) -> tuple[float, float]:
    """Pendiente (máxima, media) en % a lo largo de la ruta, a partir del DEM.

    TODO(S5): muestrear la pendiente en las celdas de la ruta y agregar máx/media.
    """
    raise NotImplementedError("Calcular pendiente de la ruta — Sprint 5")


def calcular_metricas(ruta, capas) -> MetricasRuta:
    """Orquesta el cálculo de todas las métricas de una ruta.

    TODO(S5): componer longitud + coste + cruces + km protegida/urbana + pendiente.
    """
    raise NotImplementedError("Componer métricas de la ruta — Sprint 5")
