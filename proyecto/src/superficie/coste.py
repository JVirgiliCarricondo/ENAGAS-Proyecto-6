"""Construcción de superficies de coste multicriterio.

Trabaja sobre arrays 2D ya ALINEADOS (misma rejilla) producidos por src.ingesta.

Convención: el coste es un índice ADIMENSIONAL normalizado (0-1), nunca €. Una celda
puede ser "prohibida" (coste infinito) para zonas que el trazado no debe atravesar.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
import yaml


COSTE_PROHIBIDO = np.inf
NODATA_DISCO = -9999.0
BARRERA_LCP = 999.0


def _cargar_raster_coste(ruta: Path) -> tuple[np.ndarray, dict]:
    """Lee un GeoTIFF de coste y convierte nodata de disco en infinito en memoria."""
    with rasterio.open(ruta) as src:
        data = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        nodata = src.nodata

    if nodata is not None:
        data[data == nodata] = COSTE_PROHIBIDO
    data[~np.isfinite(data)] = COSTE_PROHIBIDO

    return data, profile


def cargar_coste_pendiente(
    corredor: str,
    ruta_capas: str | Path = "data/processed/Capas_Coste",
) -> np.ndarray:
    """Carga la capa P1 pre-rasterizada (scripts/01_pendiente_opcion_B.py)."""
    ruta_capa = Path(ruta_capas) / f"pendiente_{corredor}.tif"
    if not ruta_capa.exists():
        raise FileNotFoundError(
            f"Capa de pendiente no encontrada: {ruta_capa}\n"
            "Ejecuta primero: python scripts/01_pendiente_opcion_B.py"
        )
    data, _ = _cargar_raster_coste(ruta_capa)
    return data


def cargar_coste_protegida(
    corredor: str,
    ruta_capas: str | Path = "data/processed/Capas_Coste",
) -> np.ndarray:
    """Carga la capa P4 pre-rasterizada (scripts/06_protegida.py)."""
    ruta_capa = Path(ruta_capas) / f"protegida_{corredor}.tif"
    if not ruta_capa.exists():
        raise FileNotFoundError(
            f"Capa protegida no encontrada: {ruta_capa}\n"
            "Ejecuta primero: python scripts/06_protegida.py"
        )
    data, _ = _cargar_raster_coste(ruta_capa)
    return data


def coste_longitud_base(shape: tuple[int, int]) -> np.ndarray:
    """Coste base constante por celda (modelo_coste.md §7)."""
    return np.ones(shape, dtype=np.float32)


def coste_uso_suelo_placeholder(shape: tuple[int, int]) -> np.ndarray:
    """Placeholder neutro hasta disponer de P3 (Catastro/CLC)."""
    return np.zeros(shape, dtype=np.float32)


def combinar(capas_coste: dict[str, np.ndarray], pesos: dict[str, float]) -> np.ndarray:
    """Combina capas alineadas con un vector de pesos (suma ponderada + propagación de inf)."""
    if not capas_coste:
        raise ValueError("Diccionario de capas vacío")
    if not pesos:
        raise ValueError("Diccionario de pesos vacío")

    shapes = {nombre: arr.shape for nombre, arr in capas_coste.items()}
    if len(set(shapes.values())) > 1:
        raise ValueError(f"Las capas no tienen la misma shape: {shapes}")
    shape_comun = next(iter(shapes.values()))

    if any(w < 0 for w in pesos.values()):
        raise ValueError(f"Pesos negativos no permitidos: {pesos}")

    capas_faltantes = set(pesos.keys()) - set(capas_coste.keys())
    if capas_faltantes:
        raise KeyError(
            f"Capas solicitadas no disponibles: {capas_faltantes}. "
            f"Disponibles: {list(capas_coste.keys())}"
        )

    coste_multi = np.zeros(shape_comun, dtype=np.float32)
    for nombre_capa, peso in pesos.items():
        coste_multi += peso * capas_coste[nombre_capa]

    for capa in capas_coste.values():
        coste_multi[np.isinf(capa)] = COSTE_PROHIBIDO

    return coste_multi


def cargar_perfiles(ruta: str | Path = "data/config/perfiles.yaml") -> list[dict]:
    """Lee los perfiles de prioridad desde YAML."""
    with open(ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["perfiles"]


def construir_capas_escenario(
    corredor: str,
    ruta_capas: str | Path = "data/processed/Capas_Coste",
) -> dict[str, np.ndarray]:
    """Carga las capas disponibles para un escenario A/B."""
    pendiente = cargar_coste_pendiente(corredor, ruta_capas)
    protegida = cargar_coste_protegida(corredor, ruta_capas)
    shape = pendiente.shape
    return {
        "pendiente": pendiente,
        "protegida": protegida,
        "longitud": coste_longitud_base(shape),
        "uso_suelo": coste_uso_suelo_placeholder(shape),
    }


def superficie_para_lcp(coste: np.ndarray) -> np.ndarray:
    """Convierte infinito en barrera 999 para el solver LCP."""
    out = coste.astype(np.float32, copy=True)
    out[np.isinf(out)] = BARRERA_LCP
    return out


def guardar_superficie(
    path: str | Path,
    coste: np.ndarray,
    profile_ref: dict,
    para_lcp: bool = True,
) -> Path:
    """Guarda superficie de coste en GeoTIFF."""
    datos = superficie_para_lcp(coste) if para_lcp else coste.astype(np.float32)
    profile = profile_ref.copy()
    profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        nodata=BARRERA_LCP if para_lcp else NODATA_DISCO,
        compress="lzw",
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(datos, 1)
    return path


def coste_pendiente(dem: np.ndarray, resolucion_m: float) -> np.ndarray:
    """DEPRECADO: usar cargar_coste_pendiente()."""
    import warnings

    warnings.warn(
        "coste_pendiente() es obsoleto. Usa cargar_coste_pendiente().",
        DeprecationWarning,
        stacklevel=2,
    )
    raise NotImplementedError(
        "La pendiente debe estar pre-rasterizada en "
        "data/processed/Capas_Coste/pendiente_{s}.tif"
    )


def coste_uso_suelo(clc: np.ndarray) -> np.ndarray:
    """Coste por tipo de suelo (CLC/OSM)."""
    raise NotImplementedError("Coste por uso de suelo — Sprint 3")


def coste_protegida(red_natura: np.ndarray) -> np.ndarray:
    """Coste por estar en Red Natura 2000."""
    raise NotImplementedError("Coste por zona protegida — usar cargar_coste_protegida()")
