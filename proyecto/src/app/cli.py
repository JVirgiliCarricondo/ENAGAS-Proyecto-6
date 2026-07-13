"""Punto de entrada CLI del generador de ramales.

Esqueleto de partida — completar en el Sprint 5. Uso previsto:
    python -m src.app.cli --escenario data/config/escenario.yaml --perfiles data/config/perfiles.yaml

Ejecuta el pipeline para cada perfil y genera la tabla comparativa + el mapa de las rutas.
"""

from __future__ import annotations

import argparse
import sys


def generar_trazados(escenario_path: str, perfiles_path: str) -> str:
    """Ejecuta el pipeline completo y devuelve un resumen de la comparativa.

    TODO(S5):
      1. Cargar escenario (AOI, origen, destino) y perfiles (pesos).
      2. Ingesta + alineación de capas a la rejilla común (src.ingesta).
      3. Superficie de coste por perfil (src.superficie).
      4. LCP + diferenciación de rutas (src.trazados).
      5. Métricas por ruta (src.metricas) y comparativa + mapa (src.comparacion).
    """
    raise NotImplementedError("Implementar orquestador del pipeline — Sprint 5")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="Genera y compara trazados alternativos.")
    parser.add_argument("--escenario", default="data/config/escenario.yaml",
                        help="ruta al YAML del caso de estudio (AOI, origen, destino)")
    parser.add_argument("--perfiles", default="data/config/perfiles.yaml",
                        help="ruta al YAML de perfiles de prioridad (pesos)")
    args = parser.parse_args(argv)
    print(generar_trazados(args.escenario, args.perfiles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
