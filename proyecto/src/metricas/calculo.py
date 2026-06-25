"""Orquestador de métricas multicriterio por ruta.

Para cada combinación (escenario × perfil) reúne las métricas parciales de
todos los módulos de src/metricas/ y las ensambla en un MetricasRuta.
La diversidad de corredores se calcula una vez por escenario (es una métrica
de conjunto, no por ruta individual).

Módulos integrados:
  · longitud.py            → longitud_km, coste_relativo
  · pendiente.py           → pendiente_max_pct, pendiente_media_pct,
                              porcentaje_ruta_sigue_pendiente, km_ruta_sigue_pendiente
  · zonas_protegidas.py    → km_protegida, pct_protegida
  · zonas_urbanas.py       → km_suelo_{urbano,diseminado,rustico,especial}
  · cruces.py              → n_cruces_{rios,carreteras,ferrocarril}
  · diversidad_corredores.py → solap_max_par, diferenciadas, pares, distancias

Uso (desde proyecto/):
    python -m src.metricas.calculo
    python -m src.metricas.calculo --escenario A
    python -m src.metricas.calculo --escenario B --perfil equilibrio
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.transform
from shapely.geometry import LineString

try:
    from .longitud import longitud_km as _longitud_km_fn
    from .longitud import coste_relativo as _coste_relativo_fn
    from . import zonas_protegidas as _prot_mod
    from . import zonas_urbanas as _urb_mod
    from . import cruces as _cruces_mod
    from . import diversidad_corredores as _div_mod
    from .pendiente import calcular_metricas_pendiente as _calcular_pendiente
except ImportError:
    from longitud import longitud_km as _longitud_km_fn  # type: ignore[no-redef]
    from longitud import coste_relativo as _coste_relativo_fn  # type: ignore[no-redef]
    import zonas_protegidas as _prot_mod  # type: ignore[no-redef]
    import zonas_urbanas as _urb_mod  # type: ignore[no-redef]
    import cruces as _cruces_mod  # type: ignore[no-redef]
    import diversidad_corredores as _div_mod  # type: ignore[no-redef]
    from pendiente import calcular_metricas_pendiente as _calcular_pendiente  # type: ignore[no-redef]

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DATA = _ROOT / "data" / "processed"
_RUTAS_DIR = _DATA / "Rutas"
_RECORTE_DIR = _DATA / "Recorte_AOI"
_TRAZADOS_DIR = _DATA / "Trazados"

PERFILES = ["corto", "equilibrio", "ambiental", "pendiente"]
ESCENARIOS = ["A", "B"]

_NODATA_DEM = -9999.0


# ── Dataclass de resultado ────────────────────────────────────────────────────

@dataclass
class MetricasRuta:
    escenario: str
    perfil: str

    # Longitud y coste (longitud.py)
    longitud_km: float = 0.0
    coste_relativo: float = 0.0          # índice [0, 1], NUNCA €

    # Pendiente a lo largo del trazado (pendiente.py)
    pendiente_max_pct: float = 0.0
    pendiente_media_pct: float = 0.0
    porcentaje_ruta_sigue_pendiente: float = 0.0
    km_ruta_sigue_pendiente: float = 0.0

    # Zonas protegidas Red Natura 2000 (zonas_protegidas.py)
    km_protegida: float = 0.0
    pct_protegida: float = 0.0

    # Uso del suelo catastral (zonas_urbanas.py)
    km_suelo_urbano: float = 0.0
    km_suelo_diseminado: float = 0.0
    km_suelo_rustico: float = 0.0
    km_suelo_especial: float = 0.0

    # Cruces especiales (cruces.py)
    n_cruces_rios: int = 0
    n_cruces_carreteras: int = 0
    n_cruces_ferrocarril: int = 0

    # Módulos que fallaron por falta de datos u otro error
    errores: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict plano para pandas / comparador."""
        d: dict[str, Any] = {
            "escenario": self.escenario,
            "perfil": self.perfil,
            "longitud_km": self.longitud_km,
            "coste_relativo": self.coste_relativo,
            "pendiente_max_pct": self.pendiente_max_pct,
            "pendiente_media_pct": self.pendiente_media_pct,
            "pct_ruta_sigue_pendiente": self.porcentaje_ruta_sigue_pendiente,
            "km_ruta_sigue_pendiente": self.km_ruta_sigue_pendiente,
            "km_protegida": self.km_protegida,
            "pct_protegida": self.pct_protegida,
            "km_suelo_urbano": self.km_suelo_urbano,
            "km_suelo_diseminado": self.km_suelo_diseminado,
            "km_suelo_rustico": self.km_suelo_rustico,
            "km_suelo_especial": self.km_suelo_especial,
            "n_cruces_rios": self.n_cruces_rios,
            "n_cruces_carreteras": self.n_cruces_carreteras,
            "n_cruces_ferrocarril": self.n_cruces_ferrocarril,
        }
        if self.errores:
            d["errores"] = "; ".join(f"{k}: {v}" for k, v in self.errores.items())
        return d


# ── Helpers internos ─────────────────────────────────────────────────────────

def _cargar_linea(escenario: str, perfil: str) -> LineString:
    path = _RUTAS_DIR / f"ruta_{escenario}_{perfil}.gpkg"
    if not path.exists():
        raise FileNotFoundError(f"Ruta no encontrada: {path}")
    gdf = gpd.read_file(path)
    return gdf.geometry.iloc[0]


def _superficie_path(escenario: str) -> Path | None:
    """Superficie de referencia común del escenario (pesos iguales)."""
    p = _TRAZADOS_DIR / f"superficie_{escenario}.tif"
    return p if p.exists() else None


def _linea_a_celdas(
    linea: LineString,
    transform: rasterio.Affine,
    shape: tuple[int, int],
) -> list[tuple[int, int]]:
    """Convierte vértices de un LineString a índices (row, col) de la rejilla."""
    coords = list(linea.coords)
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    rows, cols = rasterio.transform.rowcol(transform, xs, ys)
    H, W = shape
    return [
        (int(np.clip(r, 0, H - 1)), int(np.clip(c, 0, W - 1)))
        for r, c in zip(rows, cols)
    ]


# ── Cálculo por ruta ─────────────────────────────────────────────────────────

def calcular_metricas_ruta(escenario: str, perfil: str) -> MetricasRuta:
    """Reúne todas las métricas de una ruta dada por escenario y perfil.

    Los módulos que no puedan ejecutarse (archivo de entrada ausente, etc.) no
    abortan el cálculo: su error queda registrado en MetricasRuta.errores y
    sus campos quedan a 0.
    """
    s = escenario.upper()
    m = MetricasRuta(escenario=s, perfil=perfil)

    linea = _cargar_linea(s, perfil)  # FileNotFoundError propagada al llamante

    # 1. Longitud y coste relativo ─────────────────────────────────────────────
    try:
        m.longitud_km = round(_longitud_km_fn(linea), 3)
        sup_path = _superficie_path(s)
        if sup_path is not None:
            m.coste_relativo = round(_coste_relativo_fn(linea, sup_path), 3)
        else:
            m.errores["coste_relativo"] = "superficie no encontrada"
    except Exception as exc:
        m.errores["longitud"] = str(exc)

    # 2. Pendiente ─────────────────────────────────────────────────────────────
    dem_path = _RECORTE_DIR / f"dem_aoi_{s}.tif"
    try:
        if not dem_path.exists():
            raise FileNotFoundError(f"DEM no encontrado: {dem_path}")
        with rasterio.open(dem_path) as src:
            dem_arr = src.read(1).astype(np.float32)
            dem_arr = np.where(dem_arr == _NODATA_DEM, np.nan, dem_arr)
            transform = src.transform
            res_m = abs(src.res[0])
        celdas = _linea_a_celdas(linea, transform, dem_arr.shape)
        mp = _calcular_pendiente(celdas, dem_arr, resolucion_m=res_m)
        m.pendiente_max_pct = round(mp.pendiente_max_pct, 2)
        m.pendiente_media_pct = round(mp.pendiente_media_pct, 2)
        m.porcentaje_ruta_sigue_pendiente = round(mp.porcentaje_ruta_sigue_pendiente, 2)
        m.km_ruta_sigue_pendiente = round(mp.km_ruta_sigue_pendiente, 3)
    except Exception as exc:
        m.errores["pendiente"] = str(exc)

    # 3. Zonas protegidas ──────────────────────────────────────────────────────
    try:
        prot = _prot_mod.calcular(linea, s)
        m.km_protegida = prot["km_protegida"]
        m.pct_protegida = prot["pct_protegida"]
    except Exception as exc:
        m.errores["zonas_protegidas"] = str(exc)

    # 4. Uso del suelo catastral ───────────────────────────────────────────────
    try:
        urb = _urb_mod.calcular(linea, s)
        m.km_suelo_urbano = urb.get("km_suelo_urbano", 0.0)
        m.km_suelo_diseminado = urb.get("km_suelo_diseminado", 0.0)
        m.km_suelo_rustico = urb.get("km_suelo_rustico", 0.0)
        m.km_suelo_especial = urb.get("km_suelo_especial", 0.0)
    except Exception as exc:
        m.errores["zonas_urbanas"] = str(exc)

    # 5. Cruces especiales ─────────────────────────────────────────────────────
    try:
        ruta_path = _RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg"
        cruces = _cruces_mod.cruces_escenario(ruta_path, s)
        m.n_cruces_rios = cruces["n_cruces_rios"]
        m.n_cruces_carreteras = cruces["n_cruces_carreteras"]
        m.n_cruces_ferrocarril = cruces["n_cruces_ferrocarril"]
    except Exception as exc:
        m.errores["cruces"] = str(exc)

    return m


# ── Cálculo a nivel de escenario ──────────────────────────────────────────────

def calcular_diversidad(escenario: str, **kwargs: Any) -> dict:
    """Diversidad de corredores del escenario (delega a diversidad_corredores.py)."""
    return _div_mod.calcular(escenario, **kwargs)


def calcular_todas(
    escenarios: list[str] | None = None,
    perfiles: list[str] | None = None,
) -> dict[str, dict]:
    """Calcula métricas y diversidad para todos los escenarios y perfiles.

    Returns:
        {
            "A": {
                "rutas": [MetricasRuta, ...],
                "diversidad": {...}   # resultado de diversidad_corredores
            },
            "B": { ... },
        }
    """
    ess = [s.upper() for s in (escenarios or ESCENARIOS)]
    prfs = perfiles or PERFILES
    resultados: dict[str, dict] = {}

    for s in ess:
        rutas_metricas: list[MetricasRuta] = []
        for perfil in prfs:
            ruta_path = _RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg"
            if not ruta_path.exists():
                log.warning("Ruta no encontrada: %s — omitida", ruta_path.name)
                continue
            try:
                m = calcular_metricas_ruta(s, perfil)
                if m.errores:
                    log.warning(
                        "[%s/%s] Módulos con error: %s", s, perfil,
                        ", ".join(m.errores.keys()),
                    )
                rutas_metricas.append(m)
            except Exception as exc:
                log.error("[%s/%s] Error fatal: %s", s, perfil, exc)

        try:
            diversidad = calcular_diversidad(s)
        except Exception as exc:
            log.error("[%s] Error en diversidad: %s", s, exc)
            diversidad = {}

        resultados[s] = {"rutas": rutas_metricas, "diversidad": diversidad}

    return resultados


# ── CLI ───────────────────────────────────────────────────────────────────────

def _imprimir_tabla(rutas: list[MetricasRuta]) -> None:
    if not rutas:
        print("  (sin rutas)")
        return
    cab = (
        f"  {'perfil':12s} {'km':>7s} {'coste':>6s} "
        f"{'pend_max%':>9s} {'pend_med%':>9s} "
        f"{'km_prot':>8s} {'km_urb':>7s} "
        f"{'rios':>5s} {'carr':>5s} {'ffcc':>5s}"
    )
    print(cab)
    print("  " + "-" * (len(cab) - 2))
    for m in rutas:
        err_tag = f"  [err: {','.join(m.errores.keys())}]" if m.errores else ""
        print(
            f"  {m.perfil:12s} {m.longitud_km:7.2f} {m.coste_relativo:6.3f} "
            f"{m.pendiente_max_pct:9.1f} {m.pendiente_media_pct:9.2f} "
            f"{m.km_protegida:8.3f} {m.km_suelo_urbano:7.3f} "
            f"{m.n_cruces_rios:5d} {m.n_cruces_carreteras:5d} {m.n_cruces_ferrocarril:5d}"
            f"{err_tag}"
        )


def _imprimir_diversidad(div: dict) -> None:
    if not div:
        print("  (diversidad no calculada)")
        return
    veredicto = "DIFERENCIADAS [OK]" if div.get("diferenciadas") else "REDUNDANTES [!]"
    print(f"  Solapamiento máximo entre pares: {div.get('solap_max_par', 0):.1f}%  →  {veredicto}")
    if "pares" in div:
        for pi, pj, s in sorted(div["pares"], key=lambda x: -x[2]):
            marca = " ← redundante" if s >= div.get("umbral_pct", 50) else ""
            print(f"    {pi:12s} <-> {pj:12s}:  {s:5.1f}%{marca}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Métricas multicriterio de todas las rutas."
    )
    parser.add_argument("--escenario", choices=["A", "B", "ambos"], default="ambos")
    parser.add_argument(
        "--perfil", choices=PERFILES + ["todos"], default="todos",
        help="Perfil de prioridad (def: todos).",
    )
    args = parser.parse_args()

    ess = ["A", "B"] if args.escenario == "ambos" else [args.escenario]
    prfs = PERFILES if args.perfil == "todos" else [args.perfil]

    resultados = calcular_todas(escenarios=ess, perfiles=prfs)

    for s, res in resultados.items():
        print(f"\n{'=' * 70}")
        print(f"  Escenario {s}")
        print(f"{'=' * 70}")
        _imprimir_tabla(res["rutas"])
        if args.perfil == "todos":
            print("\n  Diversidad de corredores:")
            _imprimir_diversidad(res["diversidad"])


if __name__ == "__main__":
    main()
