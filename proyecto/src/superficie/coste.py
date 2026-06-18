"""Construcción de superficies de coste multicriterio.

Trabaja sobre arrays 2D ya ALINEADOS (misma rejilla) producidos por src.ingesta.

Convención: el coste es un índice ADIMENSIONAL normalizado (0-1), nunca €. Una celda
puede ser "prohibida" (coste infinito) para zonas que el trazado no debe atravesar.

Capas de coste (ver CAPAS_COSTE_P*.md):
  P1) Pendiente — desde DEM derivada (np.gradient/Horn), curva por tramos normativa
  P2) Geotecnia — IGME litología (lookup por roca)
  P3) Expropiación — Catastro (lookup por tipo de suelo)
  P4) Zonas protegidas — Red Natura 2000 (lookup por figura protegida)
  P5) Cruces — OSM viario + hidrografía (penalización puntual)
"""

from __future__ import annotations

import numpy as np
import rasterio
from pathlib import Path


COSTE_PROHIBIDO = np.inf  # celdas intransitables (p.ej. núcleo urbano denso, masa de agua)


def cargar_coste_pendiente(corredor: str, ruta_capas: str = "data/processed/Capas_Coste") -> np.ndarray:
    """Carga la capa de pendiente pre-calculada (P1) desde archivo GeoTIFF.

    La capa debe estar pre-rasterizada por scripts/01_pendiente_opcion_B.py con:
    - Curva normativa: 0°–5° → 0.0; 5°–15° → rampa 0.6; 15°–30° → rampa 1.0; >30° → ∞ (nodata)
    - CRS: EPSG:25830 (alineado)
    - Cobertura: 100% (sin nodata en valores válidos)
    - Rango: [0, 1] ∪ {-9999.0 (barrera dura)}

    Parámetros:
        corredor (str): 'A' o 'B'
        ruta_capas (str): directorio donde se guardan las capas

    Retorna:
        np.ndarray: coste de pendiente [0, 1] ∪ {∞ para barreras duras}

    Lanza:
        FileNotFoundError: si la capa no existe (necesita ejecutar 01_pendiente_opcion_B.py primero)
    """
    ruta_capa = Path(ruta_capas) / f"pendiente_{corredor}.tif"

    if not ruta_capa.exists():
        raise FileNotFoundError(
            f"❌ Capa de pendiente no encontrada: {ruta_capa}\n"
            f"   Ejecuta primero: python scripts/01_pendiente_opcion_B.py"
        ) única.

    Flujo:
      1. Validar que todas las capas tienen la misma shape
      2. Para cada capa en pesos: multiplicar capa × peso
      3. Sumar: coste_multicriterio = Σ(capa_i × peso_i)
      4. Propagar coste prohibido (∞): si cualquier celda tiene ∞, result es ∞
      5. Coste base de longitud: suma siempre presente (>0)

    Parámetros:
        capas_coste (dict[str, np.ndarray]): {nombre_capa: array_coste}
            Claves esperadas: 'pendiente', 'uso_suelo', 'protegida', 'longitud', etc.
            Todos con misma shape, dtype float32, rango [0, 1] ∪ {∞}

        pesos (dict[str, float]): {nombre_capa: peso}
            Pesos no negativos (típicamente normalizados ~Σ = 1-2)
            Solo incluyen capas a combinar

    Retorna:
        np.ndarray: coste multicriterio = Σ(capa_i × peso_i) [shape idéntica a capas_coste]

    Validaciones:
        - Todas las capas con misma shape
        - Todos los pesos >= 0
        - Rango de capas [0, 1] ∪ {∞} (validable pero no crítico en producción)
        - Coste prohibido (∞) se propaga

    Ejemplo:
        capas = {
            'pendiente': array_pendiente,     # [0, 1]
            'protegida': array_protegida,     # [0, 1] ∪ {∞}
            'longitud': array_longitud        # [0, 1]
        }
        pesos = {'pendiente': 0.4, 'protegida': 1.0, 'longitud': 0.3}

        coste = combinar(capas, pesos)
        # Resultado: 0.4*pendiente + 1.0*protegida + 0.3*longitud
    """
    if not capas_coste:
        raise ValueError("❌ Diccionario de capas vacío")
    if not pesos:
        raise ValueError("❌ Diccionario de pesos vacío")

    # ─────────────────────────────────────────────────────────────────────────
    # Validación 1: shape común
    # ─────────────────────────────────────────────────────────────────────────
    shapes = {nombre: arr.shape for nombre, arr in capas_coste.items()}
    if len(set(shapes.values())) > 1:
        raise ValueError(
            f"❌ Las capas no tienen la misma shape:\n{shapes}"
        )
    shape_comun = list(shapes.values())[0]

    # ─────────────────────────────────────────────────────────────────────────
    # Validación 2: pesos no negativos
    # ─────────────────────────────────────────────────────────────────────────
    if any(w < 0 for w in pesos.values()):
        raise ValueError(
            f"❌ Pesos negativos no permitidos: {pesos}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Validación 3: capas solicitadas existen
    # ─────────────────────────────────────────────────────────────────────────
    capas_faltantes = set(pesos.keys()) - set(capas_coste.keys())
    if capas_faltantes:
        raise KeyError(
            f"❌ Capas solicitadas no disponibles: {capas_faltantes}\n"
            f"   Disponibles: {list(capas_coste.keys())}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Inicializar coste multicriterio
    # ─────────────────────────────────────────────────────────────────────────
    coste_multi = np.zeros(shape_comun, dtype=np.float32)

    # ─────────────────────────────────────────────────────────────────────────
    # Combinar: suma ponderada
    # ─────────────────────────────────────────────────────────────────────────
    for nombre_capa, peso in pesos.items():
        capa = capas_coste[nombre_capa]

        # Contribución ponderada
        coste_multi += peso * capa

    # ─────────────────────────────────────────────────────────────────────────
    # Propagar coste prohibido (∞)
    # ─────────────────────────────────────────────────────────────────────────
    # Si cualquier capa tiene ∞ en una celda, el resultado es ∞
    for capa in capas_coste.values():
        coste_multi[np.isinf(capa)] = COSTE_PROHIBIDO

    return coste_multi
    # Convertir marcador nodata de disco (-9999.0) en infinito de memoria (∞)
    if nodata is not None:
        coste[coste == nodata] = np.inf

    return coste


def coste_pendiente(dem: np.ndarray, resolucion_m: float) -> np.ndarray:
    """
    DEPRECADO: Usa cargar_coste_pendiente() en su lugar.

    Esta función era para calcular pendiente bajo demanda. Ahora la capa
    se pre-calcula en scripts/01_pendiente_opcion_B.py con la curva normativa.

    Mantiene esta función para compatibilidad si hace falta recompute.
    """
    import warnings
    warnings.warn(
        "coste_pendiente() es obsoleto. Usa cargar_coste_pendiente() que lee "
        "desde archivo pre-rasterizado (reproducible y más rápido).",
        DeprecationWarning,
        stacklevel=2
    )
    raise NotImplementedError(
        "La pendiente debe estar pre-rasterizada en "
        "data/processed/Capas_Coste/pendiente_{s}.tif. "
        "Ver CAPAS_COSTE_P1_Pendiente.md"
    )


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
