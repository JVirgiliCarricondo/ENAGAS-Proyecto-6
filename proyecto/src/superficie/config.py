"""Cargador centralizado de perfiles.yaml para los módulos de superficie.

Lee data/config/perfiles.yaml una sola vez (lru_cache) y expone los
parámetros de coste de cada capa. Editar el YAML y volver a ejecutar el
pipeline es suficiente para recalibrar cualquier peso.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

# Ruta al YAML de configuración: sube dos niveles desde src/superficie/ hasta la
# raíz del proyecto y baja a data/config/perfiles.yaml.
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config" / "perfiles.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    """Lee y parsea perfiles.yaml una sola vez (cacheado en memoria).

    El decorador ``lru_cache(maxsize=1)`` garantiza que el fichero se lee del
    disco solo la primera vez; las llamadas posteriores devuelven el mismo dict
    ya parseado. Para recargar tras editar el YAML hay que reiniciar el proceso.

    Returns:
        El contenido completo de perfiles.yaml como diccionario anidado.
    """
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def params_geotecnia() -> dict:
    """Parámetros de coste de la capa de geotecnia (tabla_costes, default_cost)."""
    return _load()["parametros_capas"]["geotecnia"]


def params_expropiacion() -> dict:
    """Parámetros de coste de la capa de expropiación catastral (tipos, umbrales)."""
    return _load()["parametros_capas"]["expropiacion"]


def params_zonas_protegidas() -> dict:
    """Parámetros de coste de la capa de zonas protegidas (valor_protegida, fondo)."""
    return _load()["parametros_capas"]["zonas_protegidas"]


def params_zonas_inundables() -> dict:
    """Parámetros de coste de la capa de zonas inundables (valor_inundable, fondo)."""
    return _load()["parametros_capas"]["zonas_inundables"]


def params_cruces() -> dict:
    """Parámetros de coste de la capa de cruces viario/ríos (highway, ferrocarril, ríos)."""
    return _load()["parametros_capas"]["cruces"]


def params_tpi() -> dict:
    """Parámetros de la capa TPI (radios del anillo, sigma_clip, umbral de barrera)."""
    return _load()["parametros_capas"]["tpi"]


def get_perfil(perfil_id: str) -> dict:
    """Devuelve un perfil de prioridad por id (p.ej. 'equilibrio').

    Cada perfil contiene el vector de pesos por capa que la combinación
    multicriterio (``combinar.py``) usa para ponderar las superficies de coste.

    Args:
        perfil_id: Identificador del perfil en perfiles.yaml (campo 'id').

    Returns:
        El diccionario del perfil (incluye al menos la clave 'pesos').

    Raises:
        KeyError: Si no existe ningún perfil con ese id.
    """
    for p in _load()["perfiles"]:
        if p["id"] == perfil_id:
            return p
    raise KeyError(f"Perfil '{perfil_id}' no encontrado en perfiles.yaml")
