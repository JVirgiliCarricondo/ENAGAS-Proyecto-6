"""Cargador centralizado de perfiles.yaml para los módulos de superficie.

Lee data/config/perfiles.yaml una sola vez (lru_cache) y expone los
parámetros de coste de cada capa. Editar el YAML y volver a ejecutar el
pipeline es suficiente para recalibrar cualquier peso.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config" / "perfiles.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def params_geotecnia() -> dict:
    return _load()["parametros_capas"]["geotecnia"]


def params_expropiacion() -> dict:
    return _load()["parametros_capas"]["expropiacion"]


def params_zonas_protegidas() -> dict:
    return _load()["parametros_capas"]["zonas_protegidas"]


def params_zonas_inundables() -> dict:
    return _load()["parametros_capas"]["zonas_inundables"]


def params_cruces() -> dict:
    return _load()["parametros_capas"]["cruces"]


def params_tpi() -> dict:
    return _load()["parametros_capas"]["tpi"]


def get_perfil(perfil_id: str) -> dict:
    """Devuelve un perfil de prioridad por id (p.ej. 'equilibrio')."""
    for p in _load()["perfiles"]:
        if p["id"] == perfil_id:
            return p
    raise KeyError(f"Perfil '{perfil_id}' no encontrado en perfiles.yaml")
