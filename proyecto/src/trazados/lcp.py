"""Camino de mínimo coste (LCP) y diferenciación de rutas.

Sprint 4: camino_minimo_coste() + Ruta.como_linea() implementados.
Sprint 5: aplicar_corridor_masking(), generar_rutas_diferenciadas(), solapamiento().
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry import LineString
from skimage.graph import route_through_array

_BIG = 1e9  # sustituto de nan/inf para skimage (que no acepta esos valores)


@dataclass
class Ruta:
    perfil: str
    celdas: list[tuple[int, int]]  # secuencia (fila, columna) sobre la rejilla
    coste_relativo: float          # índice normalizado 0-1, NUNCA €

    def como_linea(self, transform) -> LineString:
        """Convierte la secuencia de celdas en un LineString georreferenciado.

        transform: rasterio Affine del raster de referencia (EPSG:25830).
        """
        import rasterio.transform as rt
        coords = [rt.xy(transform, r, c, offset="center") for r, c in self.celdas]
        return LineString(coords)


def camino_minimo_coste(
    superficie_coste: np.ndarray,
    origen: tuple[int, int],
    destino: tuple[int, int],
    perfil: str,
) -> Ruta:
    """Calcula el LCP origen→destino sobre una superficie de coste 2D.

    Algoritmo: skimage.graph.route_through_array (MCP_Geometric).
    - Movimiento en 8 direcciones; desplazamiento diagonal = √2 × coste_celda.
    - nan → celda fuera del AOI (coste _BIG, evitada).
    - inf → barrera dura (coste _BIG, evitada salvo que no haya otra salida).

    coste_relativo: coste medio por celda normalizado al máximo de la superficie (0-1).
    """
    height, width = superficie_coste.shape
    for nombre, rc in [("origen", origen), ("destino", destino)]:
        r, c = rc
        if not (0 <= r < height and 0 <= c < width):
            raise ValueError(
                f"{nombre} {rc} fuera de la rejilla ({height}×{width})"
            )

    # Preparar array: skimage no admite nan ni inf
    arr = np.where(np.isnan(superficie_coste), _BIG, superficie_coste)
    arr = np.where(np.isposinf(arr), _BIG, arr)
    arr = np.clip(arr, 0, _BIG)

    indices, total_cost = route_through_array(
        arr, origen, destino, fully_connected=True, geometric=True
    )
    celdas = [(int(r), int(c)) for r, c in indices]

    # Normalización: total_cost / (n_transiciones × vmax × √2)
    # √2 es el factor geométrico máximo por paso (diagonal); garantiza rango [0, 1].
    transitable = arr[arr < _BIG]
    vmax = float(transitable.max()) if transitable.size else 1.0
    n_transiciones = max(len(celdas) - 1, 1)
    coste_relativo = float(np.clip(
        total_cost / (n_transiciones * vmax * np.sqrt(2)),
        0.0, 1.0,
    ))

    return Ruta(perfil=perfil, celdas=celdas, coste_relativo=coste_relativo)


# ── Sprint 5 ──────────────────────────────────────────────────────────────────


def aplicar_corridor_masking(
    superficie_coste: np.ndarray,
    rutas_previas: list[Ruta],
    radio_celdas: int,
    penalizacion: float,
) -> np.ndarray:
    """Penaliza la proximidad a rutas ya generadas para forzar corredores distintos.

    TODO(S5): dilatar las celdas de rutas_previas (radio_celdas) y multiplicar
              su coste por penalizacion. Devuelve superficie modificada.
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
      1. Para cada perfil, calcular el LCP con corridor masking respecto a las anteriores.
      2. Medir solapamiento con las rutas ya aceptadas.
      3. Aceptar solo si solapamiento <= max_solapamiento.
    """
    raise NotImplementedError("Generar rutas diferenciadas — Sprint 5")


def solapamiento(ruta_a: Ruta, ruta_b: Ruta) -> float:
    """Fracción de celdas compartidas entre dos rutas (0 = disjuntas, 1 = idénticas).

    TODO(S5): comparar conjuntos de celdas y devolver la fracción de solapamiento.
    """
    raise NotImplementedError("Medir solapamiento — Sprint 5")
