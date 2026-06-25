"""Métrica — diversidad real de los corredores (diferenciación de rutas).

El reto exige que las 3-5 alternativas sean corredores REALMENTE distintos, no
el mismo trazado con ruido. La diferenciación se valida midiendo el SOLAPAMIENTO
espacial entre rutas: una ruta solo es aceptable si su solapamiento con las demás
queda por debajo de un umbral (ver docs/reto6_enagas.md §3.2, arquitectura.md).

Medida de solapamiento (por LONGITUD compartida):
  Cada ruta se "engorda" a corredor con un buffer de semiancho BUFFER_M (250 m por
  defecto). El solapamiento dirigido de A respecto a B es el porcentaje de la
  LONGITUD de A que discurre dentro del corredor de B:

      solap(A->B) = long( A ∩ buffer(B, BUFFER_M) ) / long(A) · 100

  Es asimétrico (A puede ir casi entera dentro del corredor de B sin que ocurra
  al revés), por eso se reporta la matriz completa. El solapamiento de un PAR es
  el máximo de las dos direcciones: solap_par(A,B) = max(solap(A->B), solap(B->A)).

Veredicto: las rutas del escenario están diferenciadas si NINGÚN par supera el
umbral de solapamiento (UMBRAL_PCT, 50 % por defecto).

Interfaz:
    calcular(escenario, buffer_m=250, umbral_pct=50) -> dict

Uso standalone (desde proyecto/):
    python -m src.metricas.diversidad_corredores
    python -m src.metricas.diversidad_corredores --escenario A --buffer 250 --umbral 50
"""

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry.base import BaseGeometry

CRS_TRABAJO = "EPSG:25830"

BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
RUTAS_DIR = BASE / "Rutas"

ESCENARIOS = ["A", "B"]
PERFILES = ["corto", "equilibrio", "ambiental", "pendiente"]

BUFFER_M = 250.0        # semiancho del corredor (m) para engordar la línea a corredor
UMBRAL_PCT = 50.0       # % de solapamiento por encima del cual un par es redundante
PASO_MUESTREO_M = 50.0  # separación entre puntos al muestrear una ruta (distancias)


def solapamiento_dirigido(linea_a: BaseGeometry, linea_b: BaseGeometry,
                          buffer_m: float) -> float:
    """% de la longitud de A que cae dentro del corredor (buffer) de B."""
    if linea_a is None or linea_a.is_empty or linea_a.length == 0:
        return 0.0
    corredor_b = linea_b.buffer(buffer_m)
    compartido = linea_a.intersection(corredor_b)
    return 100.0 * compartido.length / linea_a.length


def _muestrear(linea: BaseGeometry, paso: float) -> list[BaseGeometry]:
    """Puntos equiespaciados a lo largo de la línea, paso ~'paso' m (incluye extremos)."""
    L = linea.length
    if L == 0:
        return [linea.interpolate(0.0)]
    n = max(1, int(np.ceil(L / paso)))
    return [linea.interpolate(min(k * paso, L)) for k in range(n + 1)]


def distancias_entre(linea_a: BaseGeometry, linea_b: BaseGeometry,
                     paso: float) -> tuple[float, float]:
    """Distancia (media, máxima) en m entre dos ramales.

    media:  media de la distancia al otro ramal sobre puntos muestreados a lo
            largo de AMBAS rutas (separación típica del corredor).
    máxima: distancia de Hausdorff (la mayor separación en el punto más alejado;
            es simétrica = max de las dos direcciones).
    """
    pa = _muestrear(linea_a, paso)
    pb = _muestrear(linea_b, paso)
    dists = [p.distance(linea_b) for p in pa] + [p.distance(linea_a) for p in pb]
    media = float(np.mean(dists)) if dists else 0.0
    maxima = float(linea_a.hausdorff_distance(linea_b))
    return media, maxima


def _cargar_rutas(escenario: str) -> dict[str, BaseGeometry]:
    """Carga las rutas existentes del escenario como {perfil: geometría}."""
    s = escenario.upper()
    rutas: dict[str, BaseGeometry] = {}
    for perfil in PERFILES:
        path = RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg"
        if not path.exists():
            continue
        gdf = gpd.read_file(path)
        if gdf.crs is not None and gdf.crs.to_epsg() != 25830:
            gdf = gdf.to_crs(CRS_TRABAJO)
        rutas[perfil] = gdf.geometry.iloc[0]
    return rutas


def calcular(escenario: str, buffer_m: float = BUFFER_M,
             umbral_pct: float = UMBRAL_PCT,
             paso_muestreo: float = PASO_MUESTREO_M) -> dict:
    """Estudia la diversidad de los corredores de un escenario.

    Returns:
        dict con:
          perfiles        lista de perfiles presentes (orden de la matriz)
          matriz          solap(i->j) en %, fila i sobre corredor de j (diagonal 100)
          pares           [(p_i, p_j, solap_par_%), ...] solapamiento simétrico por par
          distancias      [(p_i, p_j, dist_media_m, dist_max_m), ...] por par
          solap_max_par   solapamiento del par más redundante (%)
          diferenciadas   True si ningún par supera umbral_pct
          buffer_m, umbral_pct, paso_muestreo
    """
    rutas = _cargar_rutas(escenario)
    perfiles = list(rutas.keys())

    matriz: dict[str, dict[str, float]] = {}
    for pi in perfiles:
        matriz[pi] = {}
        for pj in perfiles:
            if pi == pj:
                matriz[pi][pj] = 100.0
            else:
                matriz[pi][pj] = solapamiento_dirigido(rutas[pi], rutas[pj], buffer_m)

    pares = []
    distancias = []
    for pi, pj in combinations(perfiles, 2):
        pares.append((pi, pj, max(matriz[pi][pj], matriz[pj][pi])))
        media, maxima = distancias_entre(rutas[pi], rutas[pj], paso_muestreo)
        distancias.append((pi, pj, media, maxima))

    solap_max_par = max((s for _, _, s in pares), default=0.0)

    return {
        "perfiles": perfiles,
        "matriz": matriz,
        "pares": pares,
        "distancias": distancias,
        "solap_max_par": solap_max_par,
        "diferenciadas": solap_max_par < umbral_pct,
        "buffer_m": buffer_m,
        "umbral_pct": umbral_pct,
        "paso_muestreo": paso_muestreo,
    }


def _imprimir(escenario: str, res: dict) -> None:
    perfiles = res["perfiles"]
    print(f"\n=== Escenario {escenario}  "
          f"(buffer {res['buffer_m']:.0f} m, umbral {res['umbral_pct']:.0f}%) ===")
    if not perfiles:
        print("  sin rutas")
        return

    # Matriz dirigida: fila i = % de la ruta i dentro del corredor de la ruta j
    print("  solap(fila->col) = % de la longitud de la ruta FILA dentro del corredor de la ruta COL")
    cab = "  " + " " * 12 + "".join(f"{p[:10]:>11s}" for p in perfiles)
    print(cab)
    for pi in perfiles:
        fila = "".join(f"{res['matriz'][pi][pj]:>10.1f}%" for pj in perfiles)
        print(f"  {pi:12s}{fila}")

    # Solapamiento simétrico por par (máx de las dos direcciones)
    print("\n  Solapamiento por par (max de ambas direcciones):")
    for pi, pj, s in sorted(res["pares"], key=lambda x: -x[2]):
        marca = "  <-- redundante" if s >= res["umbral_pct"] else ""
        print(f"    {pi:12s} <-> {pj:12s}: {s:5.1f}%{marca}")

    veredicto = "DIFERENCIADAS [OK]" if res["diferenciadas"] else "REDUNDANTES [NO]"
    print(f"\n  Par mas solapado: {res['solap_max_par']:.1f}%  ->  {veredicto}")

    # Distancia entre ramales (separación geométrica del corredor)
    print(f"\n  Distancia entre ramales (m)  [muestreo {res['paso_muestreo']:.0f} m]:")
    print(f"    {'par':27s} {'media':>8s} {'maxima':>8s}")
    for pi, pj, media, maxima in sorted(res["distancias"], key=lambda x: -x[2]):
        print(f"    {pi + ' <-> ' + pj:27s} {media:>8.0f} {maxima:>8.0f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diversidad real de los corredores (solapamiento entre rutas)."
    )
    parser.add_argument("--escenario", choices=["A", "B", "ambos"], default="ambos")
    parser.add_argument("--buffer", type=float, default=BUFFER_M,
                        help=f"semiancho del corredor en m (def: {BUFFER_M:.0f})")
    parser.add_argument("--umbral", type=float, default=UMBRAL_PCT,
                        help=f"%% de solapamiento que marca un par como redundante (def: {UMBRAL_PCT:.0f})")
    args = parser.parse_args()

    escenarios = ESCENARIOS if args.escenario == "ambos" else [args.escenario]
    for s in escenarios:
        res = calcular(s, buffer_m=args.buffer, umbral_pct=args.umbral)
        _imprimir(s, res)


if __name__ == "__main__":
    main()
