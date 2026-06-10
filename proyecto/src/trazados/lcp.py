"""Camino de mínimo coste y diferenciación de rutas.

Esqueleto de partida — completar en los Sprints 4-5.
LCP por defecto con `skimage.graph` (MCP_Geometric / route_through_array);
alternativa con `networkx` (Dijkstra sobre la rejilla como grafo).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Ruta:
    perfil: str
    celdas: list[tuple[int, int]]   # secuencia (fila, columna) sobre la rejilla
    coste_relativo: float           # índice normalizado 0-1, NUNCA €

    def como_linea(self, rejilla):
        """Convierte la secuencia de celdas en una geometría (LineString) en el CRS de trabajo.

        TODO(S5): mapear (fila, col) -> (x, y) con el transform de la rejilla.
        """
        raise NotImplementedError("Pasar celdas a geometría — Sprint 5")


def camino_minimo_coste(
    superficie_coste: np.ndarray,
    origen: tuple[int, int],
    destino: tuple[int, int],
    perfil: str,
) -> Ruta:
    """Calcula el LCP origen->destino sobre una superficie de coste.

    TODO(S4): usar skimage.graph.route_through_array (o MCP_Geometric) y devolver la
    secuencia de celdas y el coste acumulado normalizado.
    """
    raise NotImplementedError("Implementar LCP — Sprint 4")


def aplicar_corridor_masking(
    superficie_coste: np.ndarray,
    rutas_previas: list[Ruta],
    radio_celdas: int,
    penalizacion: float,
) -> np.ndarray:
    """Penaliza la proximidad a rutas ya generadas para forzar corredores distintos.

    TODO(S5): dilatar las celdas de `rutas_previas` (radio_celdas) y multiplicar su coste
    por `penalizacion`. Devuelve una superficie de coste modificada.
    """
    raise NotImplementedError("Implementar corridor masking — Sprint 5")


def generar_rutas_diferenciadas(
    superficies_por_perfil: dict[str, np.ndarray],
    origen: tuple[int, int],
    destino: tuple[int, int],
    max_solapamiento: float,
    n_rutas: int,
) -> list[Ruta]:
    """Genera n rutas demostrablemente distintas (perfiles + corridor masking).

    TODO(S5):
      1. Para cada perfil, calcular el LCP (con corridor masking respecto a las anteriores).
      2. Medir el solapamiento con las rutas ya aceptadas.
      3. Aceptar solo si solapamiento <= max_solapamiento; si no, reintentar penalizando más.
    """
    raise NotImplementedError("Generar rutas diferenciadas — Sprint 5")


def solapamiento(ruta_a: Ruta, ruta_b: Ruta) -> float:
    """Fracción de celdas compartidas entre dos rutas (0 = disjuntas, 1 = idénticas).

    TODO(S5): comparar conjuntos de celdas (o con un buffer) y devolver la fracción.
    """
    raise NotImplementedError("Medir solapamiento — Sprint 5")
