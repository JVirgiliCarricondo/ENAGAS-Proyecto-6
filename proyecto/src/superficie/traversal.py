"""Capa de coste: traversalidad del trazado respecto a la pendiente.

Fórmula:
    traversal = pendiente_normalizada × |sin(aspecto − azimut_OD)|

- pendiente_{s}.tif  : coste de pendiente normalizado [0, 1] (generado por pendiente.py)
- aspecto_{s}.tif    : dirección del gradiente de elevación en radianes (generado por pendiente.py)
- azimut_OD          : ángulo del vector origen→destino leído de escenario.yaml, en radianes.
                       Convención matemática (0 = Este, positivo = antihorario).

El factor |sin(aspect − az)| vale:
  0  → el gradiente apunta hacia/desde el destino (el trazado sigue la pendiente).
  1  → el gradiente es perpendicular al trazado (el trazado cruza la ladera).

Multiplicar por la pendiente normalizada anula la penalización en terreno plano
(donde la dirección del aspecto no tiene sentido físico).

Limitación: usa el azimut global O→D como proxy de la dirección local del trazado.
Es una aproximación isotrópica; válida cuando el corredor no gira más de ~60°.

Salida: data/processed/Capas_Coste/traversal_{s}.tif  (coste normalizado [0, 1])

Uso (desde proyecto/):
    python src/superficie/traversal.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
import yaml

BASE = Path(__file__).resolve().parents[2] / "data"
CAPAS = BASE / "processed" / "Capas_Coste"
CONFIG = BASE / "config"
NODATA = -9999.0
ESCENARIOS = ["A", "B"]


def _azimut_od(escenario: str) -> float:
    """Lee origen/destino de escenario.yaml y devuelve azimut en radianes.

    Convención matemática: arctan2(dy, dx), con dy = Norte, dx = Este.
    """
    with open(CONFIG / "escenario.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    esc = cfg[f"escenario_{escenario.upper()}"]
    dx = esc["destino"]["x"] - esc["origen"]["x"]
    dy = esc["destino"]["y"] - esc["origen"]["y"]
    return float(np.arctan2(dy, dx))


def procesar_escenario(s: str) -> Path:
    """Genera traversal_{s}.tif a partir de pendiente_{s}.tif y aspecto_{s}.tif."""
    s = s.upper()
    pendiente_path = CAPAS / f"pendiente_{s}.tif"
    aspecto_path = CAPAS / f"aspecto_{s}.tif"
    for p in [pendiente_path, aspecto_path]:
        if not p.exists():
            raise FileNotFoundError(
                f"No existe: {p}\n"
                "Ejecuta primero: python src/superficie/pendiente.py"
            )

    with rasterio.open(pendiente_path) as src:
        slope = src.read(1).astype("float64")
        profile = src.profile.copy()
    with rasterio.open(aspecto_path) as src:
        aspect = src.read(1).astype("float64")

    # NODATA → nan en memoria
    slope = np.where(slope == NODATA, np.nan, slope)
    aspect = np.where(aspect == NODATA, np.nan, aspect)

    az = _azimut_od(s)

    # Coste: 0 = sigue la pendiente, 1 = cruza la ladera
    raw = slope * np.abs(np.sin(aspect - az))

    # Normalizar a [0, 1] usando el máximo del AOI
    valid_mask = np.isfinite(raw) & ~np.isnan(raw)
    vmax = float(raw[valid_mask].max()) if valid_mask.any() else 1.0
    traversal = raw / vmax if vmax > 0 else raw

    # nan → NODATA en disco
    out = np.where(np.isnan(traversal), NODATA, traversal).astype("float32")

    salida = CAPAS / f"traversal_{s}.tif"
    profile.update(driver="GTiff", dtype="float32", count=1, nodata=NODATA, compress="lzw")
    with rasterio.open(salida, "w", **profile) as dst:
        dst.write(out, 1)

    v = out[out != NODATA]
    print(
        f"[{s}] {salida.name}: rango=[{v.min():.3f}, {v.max():.3f}]  "
        f"azimut_OD={np.degrees(az):.1f}°"
    )
    return salida


def main() -> None:
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("Traversal completado: capa de traversalidad generada (A y B).")


if __name__ == "__main__":
    main()
