"""Combinación de capas de coste individuales en una superficie única por escenario.

Lee las capas de Capas_Coste/ (excluyendo las propias superficies) y las combina
con los pesos de un perfil en Trazados/superficie_{s}.tif. El coste base de
longitud (BASE_LONG) garantiza que la distancia siempre cuente en el LCP.

`combinar_pesos()` es la ÚNICA fuente de verdad de la ponderación por perfil:
la usan tanto `run()` (que escribe la superficie a disco) como
`trazados.ruta_pendiente.run_perfiles` (que la consume en memoria para el LCP).

Sin argumento `--perfil` se aplican pesos iguales (w=1/n por capa, BASE_LONG=1.0).
Los perfiles diferenciados viven en data/config/perfiles.yaml.
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
# Convenio de barreras: las capas de coste codifican la barrera dura como
# NODATA (-9999) en disco (igual que "fuera del AOI"); al leer se convierte a
# nan y se propaga por la suma, de modo que la celda queda intransitable para
# el LCP. No existe ningún valor centinela adicional en los TIFF.

# Mapeo peso (perfiles.yaml) → nombre de fichero de capa en Capas_Coste/.
# La clave 'longitud' NO es una capa: escala el coste base por celda (BASE_LONG).
PESO_A_CAPA = {
    "tpi": "tpi",
    "protegida": "protegida",
    "inundable": "inundable",
    "cruces": "cruces",
    "expropiacion": "expropiacion",
    "geotecnia": "geotecnia",
}


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


def combinar_pesos(
    scenario: str, pesos: dict[str, float]
) -> tuple[np.ndarray, rasterio.Affine, object]:
    """Superficie de coste escalar PONDERADA por los pesos de un perfil.

    Única fuente de verdad de la ponderación por perfil (la reutiliza también
    `trazados.ruta_pendiente.run_perfiles`). Devuelve el array en memoria, sin
    escribir a disco.

        superficie = BASE_LONG · peso('longitud') + Σ peso_capa · capa

    Convenio de impasabilidad: NODATA (-9999, cubre "fuera del AOI" y barrera
    dura) → nan. Una celda es impasable (nan) si cualquier capa usada lo es;
    el nan se propaga por la suma. Solo se leen las capas con peso en `pesos`
    (`PESO_A_CAPA`); la clave 'longitud' escala el coste base por celda.

    Args:
        scenario: 'A' o 'B'.
        pesos:    dict nombre_capa → peso, tal como aparece en perfiles.yaml.
    """
    s = scenario.upper()
    base = BASE_LONG * float(pesos.get("longitud", 1.0))

    acc: np.ndarray | None = None
    transform = crs = None
    for key, w in pesos.items():
        cap = PESO_A_CAPA.get(key)
        if cap is None:
            continue  # 'longitud' u otra clave sin capa raster
        path = CAPAS_COSTE / f"{cap}_{s}.tif"
        if not path.exists():
            log.warning("[combinar_%s] capa ausente para peso '%s': %s", s, key, path.name)
            continue
        with rasterio.open(path) as src:
            arr = src.read(1).astype("float64")
            if acc is None:
                transform, crs = src.transform, src.crs
                acc = np.full(arr.shape, base, dtype="float64")
        arr = np.where(arr == NODATA, np.nan, arr)  # fuera del AOI o barrera → nan
        log.info("[combinar_%s]   %-22s  w=%.3f", s, path.name, float(w))
        acc = acc + float(w) * arr                        # nan se propaga

    if acc is None:
        raise FileNotFoundError(
            f"[{s}] perfil sin capas ponderables en {CAPAS_COSTE}: {pesos}"
        )
    return acc, transform, crs


def run(scenario: str, pesos: dict[str, float] | None = None) -> Path:
    """Genera la superficie de coste combinada y la escribe en Trazados/.

    Args:
        scenario: 'A' o 'B'.
        pesos:    dict nombre_capa → peso (ver `combinar_pesos`). La clave
                  especial 'longitud' escala BASE_LONG. Capas no listadas se
                  ignoran. None → peso igual 1/n para todas las capas halladas.
    """
    s = scenario.upper()
    if pesos is None:
        paths = _layer_paths(s)
        if not paths:
            raise FileNotFoundError(
                f"No hay capas de coste para escenario {s} en {CAPAS_COSTE}"
            )
        n = len(paths)
        # longitud=1.0 → base=BASE_LONG; cada capa hallada con peso igual 1/n.
        pesos = {"longitud": 1.0, **{_layer_name(p, s): 1.0 / n for p in paths}}

    log.info("[combinar_%s] base=%.2f | capas:", s, BASE_LONG * float(pesos.get("longitud", 1.0)))
    superficie, transform, crs = combinar_pesos(s, pesos)

    # ── Estadísticas ─────────────────────────────────────────────────────────
    outside_aoi = np.isnan(superficie)
    valid = superficie[np.isfinite(superficie)]
    if valid.size:
        log.info(
            "[combinar_%s] rango válido: [%.4f, %.4f]  |  fuera AOI/barrera: %d celdas",
            s, float(valid.min()), float(valid.max()), int(np.sum(outside_aoi)),
        )

    # ── Convertir para escritura en disco (nan → NODATA) ─────────────────────
    out_arr = np.where(np.isnan(superficie), NODATA, superficie).astype("float32")

    profile = dict(
        driver="GTiff", dtype="float32", count=1,
        height=superficie.shape[0], width=superficie.shape[1],
        transform=transform, crs=crs, nodata=NODATA, compress="lzw", tiled=False,
    )

    TRAZADOS.mkdir(parents=True, exist_ok=True)
    out_path = TRAZADOS / f"superficie_{s}.tif"
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
    valid = arr[arr != NODATA]
    print(f"  Shape    : {src.height}×{src.width}")
    print(f"  dtype    : {arr.dtype}")
    print(f"  nodata   : {src.nodata}")
    print(f"  rango válido : [{valid.min():.4f}, {valid.max():.4f}]")
    print(f"  fuera AOI / barrera ({NODATA}): {int(np.sum(arr == NODATA))} celdas")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Superficie de coste combinada")
    parser.add_argument("--escenario", default="ambos",
                        help="id de escenario.yaml (p. ej. A, B o C) o 'ambos' (=A y B)")
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

    scenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario.upper()]
    for sc in scenarios:
        print(f"\n{'='*60}\n  Escenario {sc}\n{'='*60}")
        try:
            out = run(sc, pesos=pesos)
            print(f"\n  Verificación:")
            _verify(out)
        except FileNotFoundError as e:
            print(f"  [ERROR] {e}")
