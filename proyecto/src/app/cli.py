"""Punto de entrada CLI del generador de ramales (esqueleto — Sprint 7).

Orquestador por línea de comandos: ejecuta el pipeline geoespacial completo para
cada perfil de prioridad y genera la tabla comparativa + el mapa de las rutas. Es
la alternativa no interactiva a la app Streamlit.

Estado: esqueleto documentado pendiente de implementación en el Sprint 7; la
lógica de orquestación (``generar_trazados``) aún lanza ``NotImplementedError``.

Uso previsto:
    python -m src.app.cli --escenario data/config/escenario.yaml --perfiles data/config/perfiles.yaml
"""

from __future__ import annotations

import argparse
import sys


def generar_trazados(escenario_path: str, perfiles_path: str) -> str:
    """Ejecuta el pipeline completo y devuelve un resumen de la comparativa.

    Pendiente de implementación (Sprint 7). Encadenará las etapas del pipeline:

      1. Cargar escenario (AOI, origen, destino) y perfiles (pesos).
      2. Ingesta + alineación de capas a la rejilla común (src.ingesta).
      3. Superficie de coste por perfil (src.superficie).
      4. LCP + diferenciación de rutas (src.trazados).
      5. Métricas por ruta (src.metricas) y comparativa + mapa (src.comparacion).

    Args:
        escenario_path: Ruta al YAML del caso de estudio (AOI, origen, destino).
        perfiles_path: Ruta al YAML de perfiles de prioridad (pesos por capa).

    Returns:
        str: Resumen textual de la comparativa generada.

    Raises:
        NotImplementedError: Siempre; función aún no implementada (Sprint 7).
    """
    raise NotImplementedError("Implementar orquestador del pipeline — Sprint 5")


def main(argv: list[str] | None = None) -> int:
    """Analiza los argumentos, lanza el pipeline e imprime el resumen.

    Args:
        argv: Lista de argumentos de línea de comandos. Si es ``None``, usa
            ``sys.argv[1:]``.

    Returns:
        int: Código de salida del proceso (0 en éxito).
    """
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="Genera y compara trazados alternativos.")
    # Configuración por defecto: rutas relativas a data/config/ (caso de estudio
    # y perfiles versionados en el repo).
    parser.add_argument("--escenario", default="data/config/escenario.yaml",
                        help="ruta al YAML del caso de estudio (AOI, origen, destino)")
    parser.add_argument("--perfiles", default="data/config/perfiles.yaml",
                        help="ruta al YAML de perfiles de prioridad (pesos)")
    args = parser.parse_args(argv)
    # Lanza el pipeline y vuelca el resumen por stdout.
    print(generar_trazados(args.escenario, args.perfiles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
