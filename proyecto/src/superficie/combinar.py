"""Combinación de capas de coste individuales en una superficie única por escenario.

Lee todas las capas de Capas_Coste/ (excluyendo las propias superficies) y las
combina con pesos iguales en Trazados/superficie_{s}.tif. El coste base de
longitud (BASE_LONG) garantiza que la distancia siempre cuente en el LCP.

Primera iteración: pesos iguales (w=1.0 para cada capa, BASE_LONG=1.0).
Para perfiles diferenciados, ver data/config/perfiles.yaml y combinar_perfiles.py.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import rasterio

try:
    from .config import get_perfil as _get_perfil
except ImportError:
    from config import get_perfil as _get_perfil

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
DATA = _ROOT / "data"
CAPAS_COSTE = DATA / "processed" / "Capas_Coste"
TRAZADOS = DATA / "processed" / "Trazados"

BASE_LONG = 1.0  # coste constante por celda — garantiza que la distancia cuente
NODATA = -9999.0
BARRERA_DISCO = 999.0  # valor que representa barrera dura en el TIFF


def _layer_paths(scenario: str) -> list[Path]:
    s = scenario.upper()
    return sorted([
        p for p in CAPAS_COSTE.glob(f"*_{s}.tif")
        if not p.stem.startswith("superficie_")
    ])


def _layer_name(path: Path, scenario: str) -> str:
    """pendiente_A.tif → 'pendiente'"""
    suffix = f"_{scenario.upper()}"
    return path.stem[: -len(suffix)] if path.stem.endswith(suffix) else path.stem


def run(scenario: str, pesos: dict[str, float] | None = None) -> Path:
    """Genera la superficie de coste combinada.

    Args:
        scenario: 'A' o 'B'.
        pesos:    dict nombre_capa → peso. La clave especial 'longitud' escala
                  BASE_LONG. Capas no listadas reciben peso 0 (ignoradas).
                  None → peso igual 1/n para todas las capas encontradas.
    """
    s = scenario.upper()
    paths = _layer_paths(s)
    if not paths:
        raise FileNotFoundError(
            f"No hay capas de coste para escenario {s} en {CAPAS_COSTE}"
        )

    if pesos is None:
        n = len(paths)
        weights = {_layer_name(p, s): 1.0 / n for p in paths}
        base = BASE_LONG
    else:
        weights = {_layer_name(p, s): float(pesos.get(_layer_name(p, s), 0.0)) for p in paths}
        base = BASE_LONG * float(pesos.get("longitud", 1.0))

    log.info("[combinar_%s] base=%.2f | capas:", s, base)
    for p in paths:
        log.info("[combinar_%s]   %-22s  w=%.3f", s, p.name, weights[_layer_name(p, s)])

    TRAZADOS.mkdir(parents=True, exist_ok=True)
    out_path = TRAZADOS / f"superficie_{s}.tif"

    # ── Leer profile de referencia ────────────────────────────────────────────
    with rasterio.open(paths[0]) as src:
        profile = src.profile.copy()
        height, width = src.height, src.width

    # ── Apilar capas ─────────────────────────────────────────────────────────
    arrays: list[np.ndarray] = []
    layer_weights: list[float] = []
    for p in paths:
        with rasterio.open(p) as src:
            arr = src.read(1).astype("float64")
        arr = np.where(arr == NODATA, np.nan, arr)   # fuera del AOI → nan
        arrays.append(arr)
        layer_weights.append(weights[_layer_name(p, s)])

    stack = np.stack(arrays, axis=0)                          # (n, H, W)
    wvec = np.array(layer_weights, dtype="float64")[:, None, None]  # broadcast

    # Máscara: celda fuera del AOI si cualquier capa es nan
    outside_aoi = np.any(np.isnan(stack), axis=0)

    # Barrera dura: si alguna capa tiene inf → celda intransitable
    is_barrier = np.any(np.isposinf(stack), axis=0)

    # Suma ponderada (inf → nan para el cálculo, barreras se re-aplican después)
    stack_calc = np.where(np.isposinf(stack), np.nan, stack)
    weighted_sum = np.nansum(stack_calc * wvec, axis=0)

    # Superficie: base + suma ponderada
    superficie = base + weighted_sum
    superficie = np.where(is_barrier, np.inf, superficie)
    superficie = np.where(outside_aoi, np.nan, superficie)

    # ── Estadísticas ─────────────────────────────────────────────────────────
    valid = superficie[np.isfinite(superficie) & ~np.isnan(superficie)]
    if valid.size:
        log.info(
            "[combinar_%s] rango válido: [%.4f, %.4f]  |  barreras: %d celdas  |  fuera AOI: %d celdas",
            s, float(valid.min()), float(valid.max()),
            int(np.sum(is_barrier)), int(np.sum(outside_aoi)),
        )

    # ── Convertir para escritura en disco ─────────────────────────────────────
    out_arr = np.where(np.isposinf(superficie), BARRERA_DISCO, superficie)
    out_arr = np.where(np.isnan(out_arr), NODATA, out_arr).astype("float32")

    profile.update(
        driver="GTiff", dtype="float32", count=1,
        nodata=NODATA, compress="lzw", tiled=False,
    )
    for key in ("blockxsize", "blockysize"):
        profile.pop(key, None)

    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(out_arr, 1)

    _write_qml(out_path, float(valid.min()) if valid.size else 1.0,
               float(valid.max()) if valid.size else 2.0)
    log.info("[combinar_%s] guardado: %s", s, out_path)
    return out_path


def _write_qml(tif_path: Path, vmin: float, vmax: float) -> None:
    """Leyenda de rampa continua verde→amarillo→rojo para QGIS."""
    qml = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer opacity="1" alphaBand="-1" band="1" type="singlebandpseudocolor"
      classificationMin="{vmin:.4f}" classificationMax="{vmax:.4f}" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0"
          minimumValue="{vmin:.4f}" maximumValue="{vmax:.4f}"
          classificationMode="1" labelPrecision="3">
          <item value="{vmin:.4f}"  color="#1a9850" label="Coste bajo"   alpha="255"/>
          <item value="{(vmin + vmax) / 2:.4f}" color="#ffffbf" label="Coste medio"  alpha="255"/>
          <item value="{vmax:.4f}"  color="#d73027" label="Coste alto"   alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>"""
    tif_path.with_suffix(".qml").write_text(qml, encoding="utf-8")


def _verify(path: Path) -> None:
    with rasterio.open(path) as src:
        arr = src.read(1)
    valid = arr[(arr != NODATA) & (arr != BARRERA_DISCO)]
    print(f"  Shape    : {src.height}×{src.width}")
    print(f"  dtype    : {arr.dtype}")
    print(f"  nodata   : {src.nodata}")
    print(f"  rango válido : [{valid.min():.4f}, {valid.max():.4f}]")
    print(f"  barreras ({BARRERA_DISCO}): {int(np.sum(arr == BARRERA_DISCO))} celdas")
    print(f"  fuera AOI ({NODATA}): {int(np.sum(arr == NODATA))} celdas")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Superficie de coste combinada")
    parser.add_argument("--escenario", choices=["A", "B", "ambos"], default="ambos")
    parser.add_argument(
        "--perfil",
        default=None,
        help="ID del perfil de perfiles.yaml (p.ej. 'equilibrio'). "
             "Sin este argumento: pesos iguales para todas las capas.",
    )
    args = parser.parse_args()

    pesos = _get_perfil(args.perfil)["pesos"] if args.perfil else None
    if pesos:
        print(f"  Perfil: {args.perfil}  |  pesos: {pesos}")

    scenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario]
    for sc in scenarios:
        print(f"\n{'='*60}\n  Escenario {sc}\n{'='*60}")
        try:
            out = run(sc, pesos=pesos)
            print(f"\n  Verificación:")
            _verify(out)
        except FileNotFoundError as e:
            print(f"  [ERROR] {e}")
