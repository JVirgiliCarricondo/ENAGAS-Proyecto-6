"""Construcción de superficies de coste multicriterio.

Esqueleto de partida — completar en el Sprint 3. Trabaja sobre arrays 2D ya ALINEADOS
(misma rejilla) producidos por src.ingesta.

Convención: el coste es un índice ADIMENSIONAL normalizado (0-1), nunca €. Una celda
puede ser "prohibida" (coste infinito) para zonas que el trazado no debe atravesar.
"""

from __future__ import annotations

import numpy as np


COSTE_PROHIBIDO = np.inf  # celdas intransitables (p.ej. núcleo urbano denso, masa de agua)


def coste_pendiente(dem: np.ndarray, resolucion_m: float) -> np.ndarray:
    """Deriva un coste por celda a partir de la pendiente del DEM.

    TODO(S3): calcular la pendiente (gradiente del DEM) y mapearla a un coste 0-1 creciente.
    """
    raise NotImplementedError("Coste por pendiente — Sprint 3")


def coste_uso_suelo(clc: np.ndarray) -> np.ndarray:
    """Coste por tipo de suelo (CLC/OSM): urbano caro, agrícola/forestal más barato.

    TODO(S3): tabla de coste por clase de CLC; suelo urbano -> coste alto.
    """
    raise NotImplementedError("Coste por uso de suelo — Sprint 3")


def coste_protegida(red_natura: np.ndarray) -> np.ndarray:
    """Coste por estar en Red Natura 2000: muy alto o COSTE_PROHIBIDO.

    TODO(S3): decidir con dominio (Enagás) si es penalización fuerte o prohibición.
    """
    raise NotImplementedError("Coste por zona protegida — Sprint 3")


def combinar(capas_coste: dict[str, np.ndarray], pesos: dict[str, float]) -> np.ndarray:
    """Combina las capas de coste (alineadas) con un vector de pesos en una superficie.

    Las claves de `pesos` (perfil de prioridad) seleccionan y ponderan las capas.
    TODO(S3): validar que todas las capas comparten shape; suma ponderada normalizada;
    propagar COSTE_PROHIBIDO.
    """
    raise NotImplementedError("Combinar capas con pesos del perfil — Sprint 3")
