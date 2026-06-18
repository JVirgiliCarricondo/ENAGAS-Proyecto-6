"""
Script 4 — Superficies de coste multicriterio por perfil y escenario.

Combina las capas P1 (pendiente) y P4 (protegida) con longitud base y
uso_suelo placeholder según los pesos de data/config/perfiles.yaml.

Salida: data/processed/Capas_Coste/superficie_{perfil_id}_{escenario}.tif
"""

from pathlib import Path
import sys

import numpy as np
import rasterio

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from src.superficie.coste import (  # noqa: E402
    BARRERA_LCP,
    combinar,
    construir_capas_escenario,
    cargar_perfiles,
    guardar_superficie,
)

CAPAS_DIR = BASE_DIR / "data" / "processed" / "Capas_Coste"
PERFILES_PATH = BASE_DIR / "data" / "config" / "perfiles.yaml"
ESCENARIOS = ["A", "B"]


def main() -> None:
    perfiles = cargar_perfiles(PERFILES_PATH)

    for escenario in ESCENARIOS:
        capas = construir_capas_escenario(escenario, CAPAS_DIR)
        ref_path = CAPAS_DIR / f"pendiente_{escenario}.tif"
        with rasterio.open(ref_path) as src:
            profile_ref = src.profile.copy()

        for perfil in perfiles:
            pesos = perfil["pesos"]
            superficie = combinar(capas, pesos)
            salida = CAPAS_DIR / f"superficie_{perfil['id']}_{escenario}.tif"
            guardar_superficie(salida, superficie, profile_ref, para_lcp=True)

            validas = superficie[np.isfinite(superficie) & (superficie != BARRERA_LCP)]
            print(
                f"[{escenario}] perfil '{perfil['id']}' ({perfil['nombre']}): "
                f"guardado {salida.name} | "
                f"celdas transitables={validas.size}, "
                f"min={validas.min():.3f}, max={validas.max():.3f}, media={validas.mean():.3f}"
            )

    print("Script 4 completado: superficies multicriterio generadas.")


if __name__ == "__main__":
    main()
