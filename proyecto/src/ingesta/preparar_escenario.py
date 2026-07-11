"""Prepara TODAS las capas de coste de un escenario end-to-end.

Un escenario nuevo (creado en la app con su origen/destino) no tiene capas de
coste en Capas_Coste/: hay que generarlas desde cero. Este orquestador encadena
el pipeline completo de ingesta para un escenario:

    1. Descargar   — datos GIS del AOI (WFS/WCS/Overpass) → data/raw/*_{s}
    2. Alinear     — reproyectar/remuestrear a la rejilla común → Recorte_AOI/*_{s}
                     (incluye el DEM y, como Paso 5, la capa de coste TPI)
    3. Superficies — protegida, inundable, cruces, expropiación, geotecnia
                     → Capas_Coste/*_{s}.tif

Tras esto, `trazados.ruta_pendiente.run_perfiles(s)` ya encuentra las capas y
puede combinar + trazar. Si algún paso falla (sin internet, servicio caído,
capa sin datos), se lanza `PreparacionError` con un mensaje accionable en vez
de dejar que reviente `combinar` con un traceback opaco.

Los pasos 1 y 2 se ejecutan como subproceso (`python -m src.ingesta.*`), que ya
gestionan logging a fichero, manifiesto de estado y códigos de salida. El paso 3
se ejecuta en proceso (funciones simples por capa).

Uso CLI:
    python -m src.ingesta.preparar_escenario --escenario C
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # proyecto/
DATA = PROJECT_ROOT / "data"
CONFIG_ESCENARIO = DATA / "config" / "escenario.yaml"
CAPAS_COSTE = DATA / "processed" / "Capas_Coste"
RECORTE_AOI = DATA / "processed" / "Recorte_AOI"
DOWNLOAD_MANIFEST_PATH = DATA / "raw" / "manifiesto_estado.json"

# Tolerancias al comparar el AOI pedido por escenario.yaml con los rasters en
# disco. El recorte procesado se ajusta a la rejilla común de 30 m (±2 celdas);
# el DEM crudo se descarga con un margen de píxel de origen algo mayor.
_TOL_RECORTE_M = 60.0
_TOL_RAW_M = 150.0

# Capas de coste que un escenario necesita tener en Capas_Coste/ para trazar.
# tpi lo genera la alineación (Paso 5); el resto, los módulos de superficie.
CAPAS_ESPERADAS = ["tpi", "protegida", "inundable", "cruces", "expropiacion", "geotecnia"]


class PreparacionError(Exception):
    """Fallo al preparar un escenario (descarga/alineación/superficies)."""


# --------------------------------------------------------------------------- #
# Estado de preparación                                                        #
# --------------------------------------------------------------------------- #
def capas_faltantes(scenario: str) -> list[str]:
    """Capas de coste esperadas que aún no existen para el escenario."""
    s = scenario.upper()
    return [
        cap for cap in CAPAS_ESPERADAS
        if not (CAPAS_COSTE / f"{cap}_{s}.tif").exists()
    ]


def _aoi_vigente(scenario: str) -> tuple[float, float, float, float] | None:
    """Bbox (xmin, ymin, xmax, ymax) del AOI según el escenario.yaml ACTUAL.

    Devuelve None si el escenario no está en la config (no se puede comparar).
    """
    if not CONFIG_ESCENARIO.exists():
        return None
    cfg = yaml.safe_load(CONFIG_ESCENARIO.read_text(encoding="utf-8")) or {}
    cfg_s = cfg.get(f"escenario_{scenario.upper()}")
    if not cfg_s:
        return None
    try:
        from src.ingesta.descargar_capas import _scenario_aoi  # noqa: PLC0415
    except ImportError:
        from ingesta.descargar_capas import _scenario_aoi  # type: ignore  # noqa: PLC0415
    return _scenario_aoi(cfg_s)


def recorte_desactualizado(scenario: str) -> bool:
    """True si el recorte procesado no corresponde al AOI actual del YAML.

    Detecta el caso "cambiaron las coordenadas del escenario": el DEM recortado
    (dem_aoi_{s}.tif) fija la rejilla de todas las capas, así que si sus bounds
    no encajan con el AOI que piden las coordenadas vigentes —o si el recorte
    quedó sin ninguna celda válida— hay que volver a preparar el escenario.
    """
    s = scenario.upper()
    esperado = _aoi_vigente(s)
    if esperado is None:
        return False   # sin config no hay con qué comparar
    dem_path = RECORTE_AOI / f"dem_aoi_{s}.tif"
    if not dem_path.exists():
        return True
    import numpy as np       # noqa: PLC0415
    import rasterio          # noqa: PLC0415
    with rasterio.open(dem_path) as src:
        b = src.bounds
        data = src.read(1)
        nodata = src.nodata
    if any(abs(real - esp) > _TOL_RECORTE_M
           for real, esp in zip((b.left, b.bottom, b.right, b.top), esperado)):
        return True
    valid = np.isfinite(data)
    if nodata is not None:
        valid &= data != nodata
    return not valid.any()   # recorte sin datos: preparado a partir de crudos de otra zona


def _raw_cubre_aoi(scenario: str) -> bool:
    """True si el DEM crudo descargado cubre el AOI actual del YAML.

    El DEM crudo es el proxy de todos los crudos del escenario (todas las capas
    se descargan juntas para el mismo bbox). Si no cubre el AOI vigente, los
    crudos son de otra zona y hay que re-descargar en vez de reutilizarlos.
    """
    s = scenario.upper()
    esperado = _aoi_vigente(s)
    if esperado is None:
        return True
    try:
        from src.ingesta.descargar_capas import DATA_RAW  # noqa: PLC0415
    except ImportError:
        from ingesta.descargar_capas import DATA_RAW  # type: ignore  # noqa: PLC0415
    dem_path = DATA_RAW / f"DEM_{s}.tif"
    if not dem_path.exists():
        return False
    import rasterio  # noqa: PLC0415
    with rasterio.open(dem_path) as src:
        b = src.bounds
    xmin, ymin, xmax, ymax = esperado
    return (b.left <= xmin + _TOL_RAW_M and b.bottom <= ymin + _TOL_RAW_M
            and b.right >= xmax - _TOL_RAW_M and b.top >= ymax - _TOL_RAW_M)


def escenario_preparado(scenario: str) -> bool:
    """True si el escenario ya tiene todas sus capas de coste generadas
    Y el recorte corresponde a las coordenadas actuales de escenario.yaml
    (si cambian las coordenadas, el escenario deja de estar preparado)."""
    return not capas_faltantes(scenario) and not recorte_desactualizado(scenario)


# --------------------------------------------------------------------------- #
# Utilidades internas                                                          #
# --------------------------------------------------------------------------- #
def _noop(_pct: float, _msg: str) -> None:
    pass


def _escenario_en_config(scenario: str) -> bool:
    if not CONFIG_ESCENARIO.exists():
        return False
    cfg = yaml.safe_load(CONFIG_ESCENARIO.read_text(encoding="utf-8")) or {}
    return f"escenario_{scenario.upper()}" in cfg


def _run_modulo(modulo: str, scenario: str) -> subprocess.CompletedProcess:
    """Ejecuta `python -m {modulo} --escenario {s} -y` desde proyecto/."""
    import os
    env = os.environ.copy()

    # En Windows con QGIS Python las DLLs de GDAL/PROJ están en QGIS/bin/.
    # subprocess no las encuentra si esa carpeta no está en PATH, lo que
    # provoca que geopandas y pyproj fallen al importar en el subproceso.
    if sys.platform == "win32":
        python_exe = Path(sys.executable)
        qgis_root = python_exe.parents[2]       # …/QGIS 4.x.x/
        qgis_bin = qgis_root / "bin"
        proj_data = qgis_root / "share" / "proj"
        if qgis_bin.exists():
            env["PATH"] = str(qgis_bin) + os.pathsep + env.get("PATH", "")
        if proj_data.exists() and "PROJ_DATA" not in env and "PROJ_LIB" not in env:
            env["PROJ_DATA"] = str(proj_data)
        gdal_data = qgis_root / "apps" / "gdal" / "share" / "gdal"
        if gdal_data.exists() and "GDAL_DATA" not in env:
            env["GDAL_DATA"] = str(gdal_data)

    # Para descargar_capas: si los archivos crudos ya existen para este escenario
    # Y cubren el AOI vigente, usar --keep-existing para no volver a descargarlos
    # (Overpass y los WFS son servicios externos que pueden estar caídos). Si las
    # coordenadas del escenario cambiaron, los crudos son de OTRA zona: hay que
    # forzar la re-descarga (-y) o el recorte al AOI nuevo saldría vacío.
    # Doble prefijo (src.ingesta / ingesta) para funcionar tanto lanzado por
    # `python -m src.ingesta...` (cwd=proyecto/, "src" en sys.path) como
    # importado desde la app (que mete solo "src/" en sys.path, así que el
    # paquete se ve como "ingesta", sin el prefijo "src.").
    try:
        from src.ingesta.descargar_capas import SOURCES, DATA_RAW  # noqa: PLC0415
    except ImportError:
        from ingesta.descargar_capas import SOURCES, DATA_RAW  # type: ignore  # noqa: PLC0415
    raw_files_exist = all(
        (DATA_RAW / tmpl.replace("{s}", scenario.upper())).exists()
        for _, tmpl, *_ in SOURCES
        if not tmpl.startswith("RN2000")  # RN2000 es opcional, no bloquea
    )
    if (modulo == "src.ingesta.descargar_capas" and raw_files_exist
            and _raw_cubre_aoi(scenario)):
        extra_flag = "--keep-existing"
    else:
        extra_flag = "-y"
    cmd = [sys.executable, "-m", modulo, "--escenario", scenario, extra_flag]
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _descargas_fallidas(scenario: str) -> list[str]:
    """Lee el manifiesto y devuelve las capas marcadas como 'failed'."""
    if not DOWNLOAD_MANIFEST_PATH.exists():
        return []
    try:
        data = json.loads(DOWNLOAD_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    entradas = data.get("escenarios", {}).get(scenario.upper(), {})
    return [
        name for name, e in entradas.items()
        if e.get("status") == "failed"
    ]


def _cola(texto: str, n: int = 1200) -> str:
    """Últimos n caracteres de un log de subproceso, para el mensaje de error."""
    texto = (texto or "").strip()
    return texto[-n:] if len(texto) > n else texto


def _superficie_steps():
    """Devuelve [(etiqueta, callable(s))] para las capas de superficie.

    Importa con doble prefijo (src.superficie / superficie) para funcionar tanto
    lanzado por `python -m src.ingesta...` como importado desde la app (que mete
    `src/` en sys.path).
    """
    try:
        from src.superficie import zonas_protegidas, zonas_inundables, \
            cruces_viario_rios, expropiacion, geotecnia
    except ImportError:
        from superficie import zonas_protegidas, zonas_inundables, \
            cruces_viario_rios, expropiacion, geotecnia  # type: ignore

    # (etiqueta, callable(s), pista si falta la fuente de datos).
    # Catastro NO se descarga automáticamente (única capa manual, por diseño);
    # RN2000 sí (OGC API Features de MITECO), pero si su descarga falló la capa
    # se omite con una pista clara (no es un error del pipeline).
    return [
        ("Zonas protegidas", zonas_protegidas.procesar_escenario,
         "la descarga automática de Red Natura 2000 (OGC API Features MITECO) "
         "no dejó datos — reintenta el procesado o coloca la capa nacional en "
         "data/raw/RN2000/ (o data/raw/RN2000.gpkg) y vuelve a procesar."),
        ("Zonas inundables", zonas_inundables.procesar_escenario, ""),
        ("Cruces (viario y ríos)", cruces_viario_rios.procesar_escenario, ""),
        ("Expropiación (catastro)", expropiacion.run,
         "coloca los datos de Catastro (PARCELA.shp por municipio) en "
         "data/raw/Catastro/ y vuelve a procesar."),
        ("Geotecnia (litología)", geotecnia.process_scenario, ""),
    ]


# --------------------------------------------------------------------------- #
# Orquestación                                                                 #
# --------------------------------------------------------------------------- #
def preparar(scenario: str, progress_cb=None) -> dict:
    """Prepara todas las capas de coste de un escenario end-to-end.

    Los pasos de descarga y alineación se lanzan siempre con -y (sobrescribir):
    preparar un escenario regenera sus artefactos.

    Args:
        scenario:    id del escenario (p. ej. 'C'); debe existir en escenario.yaml.
        progress_cb: callback opcional (pct: float 0-1, msg: str) para la UI.

    Returns:
        dict con {'scenario', 'capas', 'avisos'}.

    Raises:
        PreparacionError: si la descarga o la alineación fallan, o si no se pudo
        generar ninguna capa de coste.
    """
    s = scenario.upper()
    cb = progress_cb or _noop

    if not _escenario_en_config(s):
        raise PreparacionError(
            f"El escenario '{s}' no está en {CONFIG_ESCENARIO.name}. "
            f"Guárdalo (origen y destino) antes de prepararlo."
        )

    # ── Paso 1: descarga de datos GIS del AOI ──────────────────────────────── #
    cb(0.03, f"Descargando datos GIS del AOI del escenario {s} (puede tardar)…")
    dl = _run_modulo("src.ingesta.descargar_capas", s)
    fallidas = _descargas_fallidas(s)
    # RN2000 es opcional: si el WFS falla, el pipeline continúa sin capa de
    # zonas protegidas (zonas_protegidas.procesar_escenario lo trata como aviso).
    fallidas_criticas = [f for f in fallidas if not f.startswith("RN2000_")]
    if fallidas_criticas or (dl.returncode != 0 and not fallidas):
        detalle = ", ".join(fallidas_criticas) if fallidas_criticas else _cola(dl.stderr or dl.stdout)
        raise PreparacionError(
            f"No se pudieron descargar los datos GIS del escenario {s}. "
            f"Comprueba la conexión a internet (servicios WFS/WCS/Overpass). "
            f"Capas fallidas: {detalle}"
        )
    cb(0.45, "Datos descargados. Alineando a la rejilla común…")

    # ── Paso 2: alineación a la rejilla común (incluye DEM + TPI) ──────────── #
    al = _run_modulo("src.ingesta.alinear_capas", s)
    if al.returncode != 0:
        raise PreparacionError(
            f"Falló la alineación de capas del escenario {s}. "
            f"Detalle:\n{_cola(al.stderr or al.stdout)}"
        )
    cb(0.62, "Capas alineadas. Generando superficies de coste…")

    # ── Paso 3: generación de las capas de coste (en proceso) ──────────────── #
    steps = _superficie_steps()
    avisos: list[str] = []
    for i, (label, fn, pista) in enumerate(steps):
        cb(0.62 + 0.36 * i / len(steps), f"Generando capa de coste: {label}…")
        try:
            fn(s)
        except FileNotFoundError:
            # Falta la fuente de datos de esta capa (típico de RN2000/Catastro,
            # que se colocan a mano). No es un error del pipeline: se omite.
            avisos.append(
                f"{label}: sin datos de origen" + (f" — {pista}" if pista else ".")
            )
        except Exception as exc:  # noqa: BLE001 — se reporta como aviso por capa
            avisos.append(f"{label}: {exc}")

    generadas = [c for c in CAPAS_ESPERADAS if (CAPAS_COSTE / f"{c}_{s}.tif").exists()]
    if not generadas:
        raise PreparacionError(
            f"No se generó ninguna capa de coste para el escenario {s}. "
            f"Errores: {'; '.join(avisos) if avisos else 'desconocido'}"
        )

    cb(1.0, f"Escenario {s} preparado.")
    return {"scenario": s, "capas": generadas, "avisos": avisos}


# --------------------------------------------------------------------------- #
# Punto de entrada CLI                                                          #
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepara todas las capas de coste de un escenario "
                    "(descarga + alineación + superficies)."
    )
    parser.add_argument(
        "--escenario", required=True,
        help="Id del escenario a preparar (debe existir en escenario.yaml).",
    )
    args = parser.parse_args()

    def _log(pct: float, msg: str) -> None:
        print(f"[{pct * 100:5.1f}%] {msg}", flush=True)

    try:
        res = preparar(args.escenario, progress_cb=_log)
    except PreparacionError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nOK — escenario {res['scenario']} preparado. "
          f"Capas: {', '.join(res['capas'])}")
    if res["avisos"]:
        print("Avisos:")
        for a in res["avisos"]:
            print(f"  - {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
