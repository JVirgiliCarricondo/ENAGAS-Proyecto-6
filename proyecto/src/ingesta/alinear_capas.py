"""
Ingesta y alineación de capas GIS al CRS y rejilla comunes del proyecto.

Corazón del reto: ninguna capa entra en el pipeline sin estar reproyectada al
CRS común (EPSG:25830) y remuestreada/rasterizada a la MISMA rejilla. Solo así la
celda (i, j) representa el mismo trozo de terreno en todas las capas y los costes
son comparables. Si las capas no están alineadas, los costes mienten.

Entradas:
    * ``data/config/escenario.yaml`` — origen, destino y (opcional) AOI del escenario.
    * ``data/raw/*`` — crudos GIS descargados por ``descargar_capas.py`` (sufijo
      ``_A`` / ``_B``) o colocados a mano (DEM ``.tif``, vectores ``.gpkg`` / ``.shp``
      / ``.geojson``, ZIP del Catastro).
    * ``data/raw/manifiesto_estado.json`` — manifiesto de estado por capa
      (contrato con ``descargar_capas.py``): ``ok`` / ``empty`` / ``failed`` /
      ``partial``. Un ``failed`` NO se alinea (evita recortes vacíos engañosos).

Salidas (en ``data/processed/``):
    * ``Recorte_AOI/*_{escenario}.tif`` — rasters (DEM) alineados a la rejilla.
    * ``Recorte_AOI/*_{escenario}.gpkg`` — vectores reproyectados y recortados al AOI.
    * ``aoi_corredor_{escenario}.gpkg`` / ``puntos_{escenario}.gpkg`` — AOI y O/D.
    * ``Capas_Coste/tpi_{escenario}.tif`` — capa de coste TPI (Paso 5).
    * ``log_alineacion.txt`` — traza completa de la ejecución.

Pasos del pipeline:
    Paso 1: Construye el AOI (desde escenario.yaml o desde origen+destino+1 km buffer).
    Paso 2: Reproyecta todas las capas a EPSG:25830.
    Paso 3: Remuestrea rasters a la rejilla común; recorta y reproyecta vectores → GeoPackage.
    Paso 4: Detecta solapamientos entre capas vectoriales (umbral: 70 %).
    Paso 5: Deriva la capa de coste TPI (posición topográfica) del DEM ya alineado.

Papel en el pipeline: segundo bloque de ingesta (tras ``descargar_capas.py``).
Produce el recorte alineado que consumen los módulos de ``superficie/``.

Ejecutar desde la raíz del proyecto (proyecto/):
    python -m src.ingesta.alinear_capas
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import numpy as np
import yaml

# --------------------------------------------------------------------------- #
# Dependencias opcionales (aviso claro si faltan)                              #
# --------------------------------------------------------------------------- #
_MISSING: list[str] = []

try:
    import rasterio
    from rasterio.crs import CRS as RasterioCRS
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask as rio_geometry_mask
    from rasterio.transform import from_origin
    from rasterio.warp import reproject as rio_reproject
except ImportError:
    _MISSING.append("rasterio")

try:
    import geopandas as gpd
    from shapely.geometry import LineString, box, mapping as shapely_mapping
    from shapely.ops import unary_union
except ImportError:
    _MISSING.append("geopandas")
    _MISSING.append("shapely")

# --------------------------------------------------------------------------- #
# Rutas                                                                        #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # proyecto/
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
# Recorte_AOI recibe TODO el recorte alineado del AOI: vectores (.gpkg) y el
# DEM (.tif). Las capas de coste derivadas van a Capas_Coste/ (superficie/).
DATA_RECORTE = DATA_PROCESSED / "Recorte_AOI"
CONFIG_ESCENARIO = PROJECT_ROOT / "data" / "config" / "escenario.yaml"
LOG_PATH = DATA_PROCESSED / "log_alineacion.txt"
# Manifiesto de estado por capa que escribe descargar_capas.py. Es la fuente de
# verdad sobre si un GPKG de data/raw/ es "sin cobertura" (empty, vacío legítimo)
# o "descarga fallida" (failed): en este segundo caso NO se debe alinear.
DOWNLOAD_MANIFEST_PATH = DATA_RAW / "manifiesto_estado.json"

DUPLICATE_THRESHOLD = 0.70  # fracción de solapamiento para avisar de duplicados
CATASTRO_MUNICIPALITY_RE = re.compile(r"^\d+[ur]A \d+ .+", re.IGNORECASE)

# --------------------------------------------------------------------------- #
# Registro de capas esperadas                                                  #
# --------------------------------------------------------------------------- #
class LayerSpec(NamedTuple):
    """Especificación de una capa esperada: cómo encontrarla y cómo alinearla.

    El campo ``categorical`` decide el método de remuestreo: en datos
    categóricos (clases discretas, p. ej. tipo de zona protegida) hay que usar
    ``nearest`` (vecino más cercano) para no inventar valores intermedios; en
    datos continuos (elevación del DEM) se usa ``bilinear``, que interpola suave.

    Attributes:
        label:         Nombre canónico de la capa (clave para logs y manifiesto).
        layer_type:    ``"raster"`` o ``"vector"``.
        categorical:   True → remuestreo ``nearest``; False → ``bilinear``.
        glob_patterns: Patrones buscados recursivamente bajo ``data/raw/``.
        output_name:   Nombre base de salida en ``data/processed/Recorte_AOI/``.
        multi_source:  True → fusionar varias fuentes (p. ej. municipios de Catastro).
    """
    label: str
    layer_type: str            # "raster" | "vector"
    categorical: bool          # True → nearest; False → bilinear
    glob_patterns: list[str]   # buscados recursivamente bajo DATA_RAW
    output_name: str           # nombre de salida en data/processed/
    multi_source: bool = False  # True → fusionar varias fuentes (p. ej. Catastro)


# Nombres canónicos generados por descargar_capas.py (sufijo _A o _B).
# _discover_layer_sources los comprueba ANTES de los glob_patterns cuando se
# indica un escenario, de modo que los datos descargados tienen prioridad.
_SCENARIO_FILES: dict[str, str] = {
    "DEM Copernicus":   "DEM_{s}.tif",
    "OSM":              "OSM_{s}.gpkg",
    "Hidrografía IGN":  "HID_{s}.gpkg",
    "IGME geológico":   "IGME_{s}.gpkg",
    "Zonas inundables": "INUND_{s}.gpkg",
    "Red Natura 2000":  "RN2000_{s}.gpkg",  # descargado automáticamente por descargar_capas.py
}

LAYERS: list[LayerSpec] = [
    LayerSpec(
        label="DEM Copernicus",
        layer_type="raster",
        categorical=False,
        glob_patterns=[
            "DEM.tif", "DEM.tiff",
            "**/DEM.tif", "**/DEM.tiff",
            "**/*COP30*.tif", "**/*cop30*.tif",
            "**/rasters_COP30/*.tif",           # output_hh.tif bajo ModeloDigitalElevacion/
            "**/dem*.tif", "**/elevation*.tif",
        ],
        output_name="dem_aoi.tif",
    ),
    LayerSpec(
        label="Red Natura 2000",
        layer_type="vector",
        categorical=True,
        glob_patterns=[
            "RN2000.gpkg", "RN2000.shp", "RN2000.geojson",
            "**/RN2000*.gpkg", "**/RN2000*.geojson",
            "**/n2000_spatial_es_pibal*.geojson",  # Península+Baleares (prioridad)
            "**/n2000*.geojson",
            "**/*natura2000*.gpkg", "**/*natura*.gpkg",
        ],
        output_name="natura2000_aoi.gpkg",
    ),
    LayerSpec(
        label="OSM",
        layer_type="vector",
        categorical=False,
        glob_patterns=[
            "OSM.gpkg", "OSM.shp", "OSM.geojson",
            "**/OSM.gpkg", "**/osm*.gpkg",
            "**/gis_osm_roads_free_1.shp",      # capa de carreteras Geofabrik
        ],
        output_name="osm_aoi.gpkg",
    ),
    LayerSpec(
        label="Hidrografía IGN",
        layer_type="vector",
        categorical=False,
        glob_patterns=[
            "HID-IGN.gpkg", "HID-IGN.shp", "HIDROGRAFIA.gpkg",
            "**/HID*.gpkg", "**/hidrografia*.gpkg", "**/Hidrografia*.gpkg",
            "**/hi_redtramo_l_ES040.shp",       # red fluvial Guadiana (Puertollano en ES040)
            "**/hi_redtramo_l_ES050.shp",       # red fluvial Guadalquivir
            "**/hi_redtramo_l_*.shp",            # red fluvial genérica
            "**/IGR_HI*.gpkg",
        ],
        output_name="hidrografia_aoi.gpkg",
    ),
    LayerSpec(
        label="IGME geológico",
        layer_type="vector",
        categorical=False,
        glob_patterns=[
            "GEO-IGME.gpkg", "GEO-IGME.shp", "IGME.gpkg",
            "**/IGME*.gpkg", "**/igme*.gpkg", "**/GEO*.gpkg",
            "**/geopb*.shp",                    # geopb_1000.shp bajo geologico_1000_shapes/
        ],
        output_name="igme_aoi.gpkg",
    ),
    LayerSpec(
        label="Zonas inundables",
        layer_type="vector",
        categorical=True,
        glob_patterns=[
            "INUND.gpkg", "INUND.shp", "INUND.geojson",
            "**/INUND*.gpkg", "**/inundable*.gpkg", "**/Inundable*.gpkg",
            "**/*zonas_inundables*.gpkg", "**/*ZonasInundables*.shp",
            "**/SNCZI*.gpkg", "**/snczi*.gpkg",
        ],
        output_name="inundable_aoi.gpkg",
    ),
    LayerSpec(
        label="Catastro - Usos del Suelo Urbanística",
        layer_type="vector",
        categorical=True,
        glob_patterns=[
            "Catastro.gpkg", "Catastro.shp",
            "**/PARCELA.shp",                   # Parcelas del Catastro Inmobiliario
            "**/Catastro/*.shp", "**/Catastro/**/*.shp",
            "**/*PARCELA*.shp",
        ],
        output_name="catastro_aoi.gpkg",
        multi_source=True,
    ),
]

# Instrucciones de descarga por capa (para el mensaje de capas faltantes)
_DOWNLOAD_HINTS: dict[str, str] = {
    "DEM Copernicus": (
        "  → Copernicus DEM GLO-30: https://dataspace.copernicus.eu/\n"
        "    Extrae el .tif y guárdalo como: data/raw/DEM.tif\n"
        "    (si ya tienes rasters_COP30.tar.gz, extráelo primero)"
    ),
    "Red Natura 2000": (
        "  → Se descarga automáticamente (descargar_capas.py, OGC API Features de\n"
        "    MITECO, colección biodiversidad:RedNatura); ejecuta la descarga o, como\n"
        "    alternativa manual, baja el dataset nacional de\n"
        "    https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/biodiversidad/rn2000.html\n"
        "    y guárdalo como: data/raw/RN2000.gpkg  (o RN2000.geojson)"
    ),
    "OSM": (
        "  → https://download.geofabrik.de/europe/spain.html\n"
        "    O descarga programática con osmnx. Guárdalo como: data/raw/OSM.gpkg"
    ),
    "Hidrografía IGN": (
        "  → https://centrodedescargas.cnig.es/\n"
        "    Guárdalo como: data/raw/HID-IGN.gpkg"
    ),
    "IGME geológico": (
        "  → https://www.igme.es/\n"
        "    Guárdalo como: data/raw/GEO-IGME.gpkg"
    ),
    "Zonas inundables": (
        "  → SNCZI (MITECO): https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/agua/zonas-inundables.html\n"
        "    Guárdalo como: data/raw/INUND.gpkg  (o INUND.geojson; une T10/T100/T500 si descargas por separado)"
    ),
    "Catastro - Usos del Suelo Urbanística": (
        "  → Catastro Inmobiliario: https://www.catastro.minhap.gob.es/\n"
        "    Descarga por municipio y descomprime los ZIP.\n"
        "    Los archivos PARCELA.shp se procesan automáticamente desde data/raw/Catastro/"
    ),
}


# --------------------------------------------------------------------------- #
# Utilidades                                                                   #
# --------------------------------------------------------------------------- #
def _setup_logging() -> logging.Logger:
    """Configura el logger 'ingesta' con salida a consola y a fichero.

    Crea los directorios de salida, fuerza UTF-8 en la consola de Windows (para
    no romper con acentos ni símbolos ✓/✗) y añade dos handlers idempotentes:
    consola (stdout) y fichero (``log_alineacion.txt``, modo 'w').

    Returns:
        El logger configurado, listo para usar en todo el módulo.
    """
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    DATA_RECORTE.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    log = logging.getLogger("ingesta")
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Guard sobre AMBOS handlers: llamadas repetidas en el mismo proceso no
    # deben duplicar salidas ni dejar el fichero de log abierto dos veces.
    if not log.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        log.addHandler(ch)
        fh = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    return log


def _load_escenario(path: Path) -> dict:
    """Carga y parsea ``escenario.yaml`` (CRS de trabajo, resolución y escenarios).

    Args:
        path: Ruta al fichero YAML de configuración de escenarios.

    Returns:
        Diccionario con el contenido del YAML.
    """
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


_PERP_BUFFER_M = 1000.0  # semiancho perpendicular del corredor, en metros


def _build_aoi(cfg: dict):
    """Devuelve un polígono Shapely orientado alineado con la línea origen-destino.

    El rectángulo tiene como largo la distancia origen→destino y 1 km a cada
    lado perpendicular. Los puntos origen y destino caen exactamente en el punto
    medio del lado corto más próximo (cap_style=2 → tapas planas en los extremos).

    Si el escenario define un AOI explícito (``aoi`` con xmin/ymin/xmax/ymax no
    nulos), se usa ese rectángulo axis-aligned en lugar del corredor orientado.

    Args:
        cfg: Sub-diccionario del escenario activo. Coordenadas en EPSG:25830
             (metros). Debe contener ``origen`` y ``destino`` (claves x, y), y
             opcionalmente ``aoi`` (xmin, ymin, xmax, ymax).

    Returns:
        Polígono Shapely del AOI en EPSG:25830.
    """
    # AOI explícito en la config: rectángulo alineado a ejes (no orientado).
    aoi = cfg.get("aoi", {})
    if aoi and all(aoi.get(k, 0) != 0 for k in ("xmin", "ymin", "xmax", "ymax")):
        return box(aoi["xmin"], aoi["ymin"], aoi["xmax"], aoi["ymax"])

    # Corredor orientado: buffer perpendicular a la línea origen→destino. El
    # buffer de una línea genera un "capsule"; cap_style=2 (flat) recorta las
    # tapas semicirculares de los extremos, dejando un rectángulo girado cuyos
    # lados cortos pasan justo por el origen y el destino.
    ox, oy = cfg["origen"]["x"], cfg["origen"]["y"]
    dx, dy = cfg["destino"]["x"], cfg["destino"]["y"]
    line = LineString([(ox, oy), (dx, dy)])
    return line.buffer(_PERP_BUFFER_M, cap_style=2)


# Ancla global de la rejilla común: todas las celdas caen sobre una malla
# universal de paso `res` con origen en (_GRID_ANCHOR_X, _GRID_ANCHOR_Y). Así
# dos AOIs/escenarios distintos que solapen comparten exactamente los mismos
# bordes de píxel y son directamente comparables, sin depender de los bounds
# concretos del AOI.
_GRID_ANCHOR_X = 0.0
_GRID_ANCHOR_Y = 0.0


def _snap_down(value: float, res: float, anchor: float) -> float:
    """Baja `value` al múltiplo de `res` (respecto a `anchor`) igual o menor.

    "Snap" = ajustar una coordenada al borde de píxel más cercano de la malla
    global. Aquí se ajusta hacia abajo (floor), para los bordes oeste/sur del AOI.

    Args:
        value:  Coordenada a ajustar (metros, EPSG:25830).
        res:    Tamaño de celda / paso de la rejilla (metros).
        anchor: Origen de la malla global de referencia (metros).

    Returns:
        La coordenada ajustada al borde de píxel igual o inferior.
    """
    return anchor + math.floor((value - anchor) / res) * res


def _snap_up(value: float, res: float, anchor: float) -> float:
    """Sube `value` al múltiplo de `res` (respecto a `anchor`) igual o mayor.

    Igual que ``_snap_down`` pero redondeando hacia arriba (ceil), para los
    bordes este/norte del AOI, de modo que el AOI quede totalmente cubierto.

    Args:
        value:  Coordenada a ajustar (metros, EPSG:25830).
        res:    Tamaño de celda / paso de la rejilla (metros).
        anchor: Origen de la malla global de referencia (metros).

    Returns:
        La coordenada ajustada al borde de píxel igual o superior.
    """
    return anchor + math.ceil((value - anchor) / res) * res


def _common_transform(xmin: float, ymin: float, xmax: float, ymax: float,
                       res: float):
    """Calcula el transform, ancho y alto de la rejilla común.

    La rejilla se ancla a una malla global de paso `res` (origen en
    (_GRID_ANCHOR_X, _GRID_ANCHOR_Y)): los bordes de píxel son múltiplos
    exactos de `res` y por tanto reproducibles entre AOIs y escenarios. El
    AOI se expande hacia fuera hasta el múltiplo de `res` más cercano para
    quedar cubierto por completo.

    El "transform" (transformación afín de rasterio) es la fórmula que traduce
    coordenadas de píxel (fila, columna) a coordenadas de terreno (x, y) en
    EPSG:25830. Fijar este transform es lo que garantiza que todas las capas
    remuestreadas compartan exactamente la misma rejilla.

    Args:
        xmin, ymin, xmax, ymax: Bounding box del AOI (metros, EPSG:25830).
        res:                    Tamaño de celda de la rejilla común (metros).

    Returns:
        Tupla ``(transform, width, height)``: el ``Affine`` de la rejilla y sus
        dimensiones en número de columnas (width) y filas (height).
    """
    # Ajustar cada borde del AOI a la malla global: oeste/sur hacia fuera (abajo),
    # este/norte hacia fuera (arriba), de modo que el AOI quede envuelto.
    west = _snap_down(xmin, res, _GRID_ANCHOR_X)
    east = _snap_up(xmax, res, _GRID_ANCHOR_X)
    south = _snap_down(ymin, res, _GRID_ANCHOR_Y)
    north = _snap_up(ymax, res, _GRID_ANCHOR_Y)
    width = round((east - west) / res)
    height = round((north - south) / res)
    # from_origin(west, north, xsize, ysize): la esquina noroeste (top-left) de
    # la rejilla es (west, north); `north` es el borde superior = máx. y ajustado.
    transform = from_origin(west, north, res, res)
    return transform, width, height


def _discover_layer(
    spec: LayerSpec, log: logging.Logger, scenario: str | None = None
) -> Path | None:
    """Busca el primer archivo que coincida con alguno de los patrones de la capa."""
    sources = _discover_layer_sources(spec, log, scenario=scenario)
    return sources[0] if sources else None


def _discover_layer_sources(
    spec: LayerSpec,
    log: logging.Logger,
    scenario: str | None = None,
) -> list[Path]:
    """Devuelve una o varias fuentes para la capa.

    Si se indica escenario ('A' o 'B'), busca primero el archivo generado por
    descargar_capas.py (p. ej. DEM_A.tif) antes de recorrer glob_patterns. Así
    los datos descargados automáticamente tienen prioridad sobre los colocados
    a mano. Se descartan los archivos comprimidos (.gz/.zip/.tar) sin extraer.

    Args:
        spec:     Especificación de la capa a buscar.
        log:      Logger para trazar la fuente elegida.
        scenario: Id de escenario ('A', 'B', …) o None si no se filtra por él.

    Returns:
        Lista de rutas fuente (una para la mayoría de capas; varias para el
        Catastro multi-municipio). Lista vacía si no se encuentra nada.
    """
    if spec.multi_source and spec.label.startswith("Catastro"):
        return _discover_catastro_sources(log)

    # Prioridad: archivo descargado por descargar_capas.py con sufijo de escenario
    if scenario and spec.label in _SCENARIO_FILES:
        candidate = DATA_RAW / _SCENARIO_FILES[spec.label].replace("{s}", scenario)
        if candidate.exists():
            log.debug(f"  [{spec.label}] → {candidate.relative_to(PROJECT_ROOT)}")
            return [candidate]

    for pattern in spec.glob_patterns:
        hits = sorted(DATA_RAW.glob(pattern))
        hits = [h for h in hits if h.suffix not in (".gz", ".zip", ".tar")]
        if hits:
            log.debug(f"  [{spec.label}] → {hits[0].relative_to(PROJECT_ROOT)}")
            return [hits[0]]
    return []


def _load_download_manifest(scenario: str, log: logging.Logger) -> dict[str, dict]:
    """Lee el manifiesto de estado que escribe descargar_capas.py.

    Devuelve {nombre_archivo_raw: {status, rows, detail}} para el escenario dado,
    o {} si el manifiesto no existe (p. ej. capas colocadas a mano sin pasar por
    descargar_capas.py). Un manifiesto ilegible se degrada a {} con aviso: nunca
    debe impedir la alineación de capas cuyo estado sí conocemos por el disco."""
    if not DOWNLOAD_MANIFEST_PATH.exists():
        log.debug("  Sin manifiesto de descarga; se procede solo con lo que hay en disco.")
        return {}
    try:
        data = json.loads(DOWNLOAD_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning(f"  No se pudo leer el manifiesto de descarga ({exc}); se ignora.")
        return {}
    return data.get("escenarios", {}).get(scenario, {})


def _scenario_raw_name(spec: "LayerSpec", scenario: str) -> str | None:
    """Nombre del archivo raw que descargar_capas.py generaría para esta capa y
    escenario (p. ej. IGME_A.gpkg), o None si la capa no proviene de la descarga
    automática (hoy solo el Catastro de régimen común, que se aporta a mano y no
    tiene manifiesto; RN2000 y el catastro foral ya se descargan solos)."""
    tmpl = _SCENARIO_FILES.get(spec.label)
    return tmpl.replace("{s}", scenario) if tmpl else None


def _find_catastro_dir() -> Path | None:
    """Localiza data/raw/CATASTRO/ con independencia de mayúsculas."""
    for name in ("CATASTRO", "Catastro", "catastro"):
        candidate = DATA_RAW / name
        if candidate.exists():
            return candidate.resolve()
    return None


def _is_catastro_layer_zip(archive: Path) -> bool:
    """ZIP de capa municipal del Catastro (p. ej. *_PARCELA.ZIP)."""
    tokens = (
        "_PARCELA", "_CONSTRU", "_SUBPARCE", "_ALTIPUN", "_CARVIA", "_EJES",
        "_ELEMLIN", "_ELEMPUN", "_ELEMTEX", "_HOJAS", "_LIMITES", "_MAPA",
        "_MASA", "_RUCULTIVO", "_RUSUBPARCE",
    )
    stem = archive.stem.upper()
    return any(token in stem for token in tokens)


def _zip_extracted(archive: Path, target_dir: Path) -> bool:
    """True si el ZIP ya parece extraído en target_dir."""
    if not target_dir.exists():
        return False
    data_files = [
        p for p in target_dir.rglob("*")
        if p.is_file() and p.suffix.lower() not in {".zip", ".gz", ".tar"}
    ]
    return bool(data_files)


def _safe_extract_zip(archive: Path, target_dir: Path, log: logging.Logger) -> tuple[int, int]:
    """Extrae un ZIP miembro a miembro; devuelve (ok, errores)."""
    ok = errors = 0
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            try:
                zf.extract(member, target_dir)
                ok += 1
            except (zipfile.BadZipFile, OSError, ValueError) as exc:
                errors += 1
                if errors <= 3:
                    log.warning(
                        f"    No se pudo extraer {member.filename} "
                        f"de {archive.name}: {exc}"
                    )
    if errors > 3:
        log.warning(f"    … y {errors - 3} entradas más con error en {archive.name}")
    return ok, errors


def _has_extracted_municipalities(catastro_dir: Path) -> bool:
    """True si ya hay algún ``PARCELA.shp`` extraído bajo el árbol del Catastro."""
    return any(catastro_dir.rglob("PARCELA.shp"))


def _extract_catastro_archives(log: logging.Logger) -> int:
    """Descomprime recursivamente los ZIP bajo data/raw/CATASTRO/."""
    catastro_dir = _find_catastro_dir()
    if catastro_dir is None:
        return 0

    municipalities_ready = _has_extracted_municipalities(catastro_dir)
    extracted = 0
    for _ in range(100):
        archives = sorted({
            p for p in catastro_dir.rglob("*")
            if p.is_file() and p.suffix.lower() == ".zip"
        })
        archives = [a for a in archives if "recovered" not in a.name.lower()]

        pending: list[tuple[Path, Path]] = []
        for archive in archives:
            if _is_catastro_layer_zip(archive):
                target_dir = archive.parent / archive.stem
            elif archive.parent == catastro_dir:
                if municipalities_ready:
                    continue
                target_dir = catastro_dir / archive.stem
            else:
                target_dir = archive.parent / archive.stem

            if _zip_extracted(archive, target_dir):
                continue
            pending.append((archive, target_dir))

        if not pending:
            break

        for archive, target_dir in pending:
            log.info(
                f"  Extrayendo {archive.relative_to(PROJECT_ROOT)} "
                f"→ {target_dir.relative_to(PROJECT_ROOT)}/"
            )
            ok, errors = _safe_extract_zip(archive, target_dir, log)
            if ok:
                extracted += 1
            elif errors:
                log.warning(
                    f"  ZIP omitido o incompleto: {archive.name} "
                    f"({errors} entradas con error)"
                )

    if extracted:
        log.info(f"  ZIPs extraídos en Catastro: {extracted}")
    return extracted


def _discover_catastro_sources(log: logging.Logger, scenario: str | None = None) -> list[Path]:
    """Todos los PARCELA.SHP disponibles bajo data/raw/CATASTRO/.

    Usa todos los archivos sin filtrar por escenario: el recorte espacial al AOI
    determina qué parcelas caen dentro de cada corredor. Esto es necesario porque
    un municipio descargado bajo la carpeta de un ramal puede cubrir geográficamente
    el AOI de otro (p. ej. Caspe/Zaragoza cubre la zona norte del Escenario A aunque
    esté en la carpeta RamalB).
    """
    catastro_dir = _find_catastro_dir()
    if catastro_dir is None:
        return []

    _extract_catastro_archives(log)

    all_parcelas = sorted(catastro_dir.rglob("PARCELA.shp"))

    # Deduplicar: si hay PARCELA.shp tanto en *_PARCELA/ como en la raíz del municipio,
    # preferir el de la subcarpeta fechada (su parent termina en _PARCELA).
    deduped: dict[Path, Path] = {}
    for p in all_parcelas:
        in_parcela_subdir = p.parent.name.endswith("_PARCELA")
        muni_dir = p.parent.parent if in_parcela_subdir else p.parent
        if muni_dir not in deduped or in_parcela_subdir:
            deduped[muni_dir] = p

    selected = sorted(deduped.values())
    for p in selected:
        log.debug(f"  [Catastro] → {p.relative_to(PROJECT_ROOT)}")

    return selected


def _warn_archives(log: logging.Logger) -> list[Path]:
    """Detecta archivos comprimidos en data/raw/ e imprime instrucciones."""
    catastro_dir = _find_catastro_dir()
    if catastro_dir is not None:
        _extract_catastro_archives(log)

    archives = (
        list(DATA_RAW.rglob("*.tar.gz"))
        + list(DATA_RAW.rglob("*.tar.bz2"))
        + list(DATA_RAW.rglob("*.zip"))
    )
    remaining = [
        arch for arch in archives
        if catastro_dir not in arch.parents and arch.parent != catastro_dir
    ]
    for arch in remaining:
        log.warning(
            f"Archivo comprimido detectado: {arch.relative_to(PROJECT_ROOT)}\n"
            f"  → Extrae su contenido en {arch.parent.relative_to(PROJECT_ROOT)}/ "
            f"y vuelve a ejecutar el script."
        )
    return remaining


# --------------------------------------------------------------------------- #
# Procesado de capas                                                           #
# --------------------------------------------------------------------------- #
def process_raster(
    src_path: Path,
    spec: LayerSpec,
    target_crs: str,
    target_transform,
    grid_w: int,
    grid_h: int,
    aoi_box,
    log: logging.Logger,
) -> Path | None:
    """Reproyecta, remuestrea y recorta un raster al AOI orientado.

    Núcleo de la alineación raster: lee el raster crudo (con su CRS y resolución
    originales) y lo re-genera sobre la rejilla común (``target_transform`` +
    ``grid_w`` × ``grid_h``) en EPSG:25830. Fuera del corredor orientado los
    píxeles se marcan como ``nodata`` (valor centinela que indica "sin dato").

    Args:
        src_path:         Ruta del raster de entrada (p. ej. el DEM crudo).
        spec:             Especificación de la capa (decide nearest/bilinear).
        target_crs:       CRS de destino (EPSG:25830).
        target_transform: ``Affine`` de la rejilla común (píxel → terreno).
        grid_w:           Ancho de la rejilla común (nº de columnas).
        grid_h:           Alto de la rejilla común (nº de filas).
        aoi_box:          Polígono AOI orientado; recorta a nodata lo de fuera.
        log:              Logger de la ejecución.

    Returns:
        Ruta del GeoTIFF alineado escrito en ``Recorte_AOI/``, o None si falló.
    """
    out_path = DATA_RECORTE / spec.output_name
    # Categórico → nearest (no inventa clases); continuo (DEM) → bilinear (suaviza).
    resampling = Resampling.nearest if spec.categorical else Resampling.bilinear

    try:
        with rasterio.open(src_path) as src:
            orig_crs = src.crs.to_string() if src.crs else "desconocido"
            log.info(f"  CRS original : {orig_crs}")
            log.info(f"  Resolución   : {src.res[0]:.1f} × {src.res[1]:.1f} m")
            log.info(f"  Bandas       : {src.count}")

            dst_crs = RasterioCRS.from_string(target_crs)
            # nodata: valor que marca "celda sin dato". Si el origen no lo define,
            # se usa -9999 como centinela. El destino se pre-rellena con nodata,
            # de modo que lo que el reproyectado no cubra queda como "sin dato".
            nodata = float(src.nodata) if src.nodata is not None else -9999.0
            n_bands = src.count
            dst_data = np.full((n_bands, grid_h, grid_w), nodata, dtype=np.float32)

            # Reproyecta+remuestrea banda a banda desde el CRS/rejilla de origen a
            # la rejilla común de destino. rio_reproject hace warp (cambio de CRS)
            # y resample (cambio de resolución) en un solo paso.
            for band in range(1, n_bands + 1):
                rio_reproject(
                    source=rasterio.band(src, band),
                    destination=dst_data[band - 1],
                    dst_transform=target_transform,
                    dst_crs=dst_crs,
                    resampling=resampling,
                    dst_nodata=nodata,
                )

        # Aplicar máscara del polígono AOI orientado: píxeles fuera del corredor → nodata.
        # geometry_mask devuelve un booleano por píxel; con invert=False, True =
        # el píxel está FUERA de la geometría (ausente), así que ahí ponemos nodata.
        if aoi_box is not None:
            outside = rio_geometry_mask(
                [shapely_mapping(aoi_box)],
                out_shape=(grid_h, grid_w),
                transform=target_transform,
                invert=False,  # True donde la geometría está AUSENTE
            )
            for band_idx in range(n_bands):
                dst_data[band_idx][outside] = nodata

        # Perfil del GeoTIFF de salida: fija el CRS común y el transform de la
        # rejilla, de modo que este raster queda alineado con el resto de capas.
        profile = {
            "driver": "GTiff",
            "dtype": "float32",
            "width": grid_w,
            "height": grid_h,
            "count": n_bands,
            "crs": target_crs,
            "transform": target_transform,
            "nodata": nodata,
            "compress": "lzw",
        }
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(dst_data)

        log.info(f"  ✓ guardado: {out_path.relative_to(PROJECT_ROOT)}")
        return out_path

    except Exception as exc:
        log.error(f"  ✗ error procesando {src_path.name}: {exc}")
        return None


def process_vector(
    src_paths: Path | list[Path],
    spec: LayerSpec,
    target_crs: str,
    aoi_box,
    log: logging.Logger,
) -> tuple[Path | None, "gpd.GeoDataFrame | None"]:
    """Reproyecta y recorta una capa vectorial al AOI.

    A diferencia de los rasters, los vectores no se remuestrean a la rejilla:
    basta con reproyectarlos al CRS común (EPSG:25830) y recortarlos al polígono
    del AOI. La rasterización a la rejilla común (cuando hace falta) la hacen
    después los módulos de ``superficie/``.

    Si la capa es multi-fuente (Catastro), fusiona todos los municipios en un
    único GeoDataFrame. Si ninguna geometría cae dentro del AOI, escribe un GPKG
    vacío legítimo (capa "sin cobertura", no un error) y devuelve gdf None.

    Args:
        src_paths:   Ruta única o lista de rutas fuente (multi-municipio).
        spec:        Especificación de la capa.
        target_crs:  CRS de destino (EPSG:25830).
        aoi_box:     Polígono AOI de recorte (en target_crs).
        log:         Logger de la ejecución.

    Returns:
        Tupla ``(ruta_salida, gdf)``. ``gdf`` es None si no hubo datos en el AOI
        o si el procesado falló (en cuyo caso ruta_salida también es None).
    """
    out_path = DATA_RECORTE / spec.output_name
    paths = [src_paths] if isinstance(src_paths, Path) else list(src_paths)

    try:
        frames: list["gpd.GeoDataFrame"] = []
        read_kwargs: dict = {}
        # Multi-fuente: filtrar en lectura por el bbox del AOI (bounds = caja
        # axis-aligned) para no cargar municipios enteros en memoria innecesariamente.
        if spec.multi_source and len(paths) > 1:
            read_kwargs["bbox"] = aoi_box.bounds

        for src_path in paths:
            part = gpd.read_file(src_path, **read_kwargs)
            if part.empty:
                log.debug(
                    f"  Sin datos en AOI: {src_path.relative_to(PROJECT_ROOT)}"
                )
                continue
            log.info(
                f"  Fuente       : {src_path.relative_to(PROJECT_ROOT)} "
                f"({len(part)} filas en ventana AOI)"
            )
            frames.append(part)

        if not frames:
            log.warning(f"  Ninguna geometría de {spec.label} cae dentro del AOI.")
            try:
                gpd.GeoDataFrame(geometry=[], crs=target_crs).to_file(out_path, driver="GPKG")
                log.info(
                    f"  Guardado (sin datos en AOI): {out_path.relative_to(PROJECT_ROOT)}"
                )
            except Exception as exc_empty:
                log.warning(f"  No se pudo guardar el archivo vacío: {exc_empty}")
            return out_path, None

        gdf = (
            frames[0]
            if len(frames) == 1
            else gpd.GeoDataFrame(gpd.pd.concat(frames, ignore_index=True), crs=frames[0].crs)
        )
        orig_crs = str(gdf.crs) if gdf.crs else "desconocido"
        log.info(f"  CRS original : {orig_crs}")
        log.info(f"  Filas        : {len(gdf)}")

        # Sin CRS declarado no se puede reproyectar con seguridad. Se asume
        # EPSG:4326 (lon/lat WGS84), el más habitual en GeoJSON/GML sin metadatos.
        if gdf.crs is None:
            log.warning(f"  CRS no definido en {paths[0].name}; se asume EPSG:4326")
            gdf = gdf.set_crs(epsg=4326)

        # Reproyección al CRS común: el paso que alinea el vector con el resto.
        gdf = gdf.to_crs(target_crs)

        # Recorte al AOI: descarta la parte de las geometrías que cae fuera del corredor.
        aoi_gdf = gpd.GeoDataFrame({"geometry": [aoi_box]}, crs=target_crs)
        try:
            gdf_clipped = gpd.clip(gdf, aoi_gdf)
        except Exception as clip_exc:
            # buffer(0) repara auto-intersecciones en polígonos (WFS GML)
            # No se aplica a LineStrings/Points: buffer(0) los vaciaría
            log.warning(f"  Clip falló ({clip_exc}); reintentando con buffer(0) en polígonos")
            gdf = gdf.copy()
            mask_poly = gdf.geom_type.isin(["Polygon", "MultiPolygon"])
            if mask_poly.any():
                gdf.loc[mask_poly, "geometry"] = gdf.loc[mask_poly, "geometry"].buffer(0)
            gdf_clipped = gpd.clip(gdf, aoi_gdf)

        # Descarta cualquier geometría vacía o no intersectante después del corte.
        if not gdf_clipped.empty:
            gdf_clipped = gdf_clipped[gdf_clipped.geometry.notnull()]
            gdf_clipped = gdf_clipped[gdf_clipped.geometry.intersects(aoi_box)]

        if gdf_clipped.empty:
            src_label = paths[0].name if len(paths) == 1 else f"{len(paths)} fuentes"
            log.warning(f"  Ninguna geometría de {src_label} cae dentro del AOI.")
            try:
                gdf_clipped.to_file(out_path, driver="GPKG")
                log.info(
                    f"  Guardado (sin datos en AOI): {out_path.relative_to(PROJECT_ROOT)}"
                )
            except Exception as exc_empty:
                log.warning(f"  No se pudo guardar el archivo vacío: {exc_empty}")
            return out_path, None

        gdf_clipped.to_file(out_path, driver="GPKG")
        log.info(
            f"  ✓ guardado: {out_path.relative_to(PROJECT_ROOT)} "
            f"({len(gdf_clipped)} filas)"
        )
        return out_path, gdf_clipped

    except Exception as exc:
        src_label = paths[0].name if len(paths) == 1 else spec.label
        log.error(f"  ✗ error procesando {src_label}: {exc}")
        return None, None


# --------------------------------------------------------------------------- #
# Detección de duplicados                                                      #
# --------------------------------------------------------------------------- #
def detect_duplicates(
    processed_vectors: list[tuple[str, "gpd.GeoDataFrame"]],
    threshold: float,
    log: logging.Logger,
) -> None:
    """Avisa si dos capas vectoriales se solapan más del umbral dado.

    Compara cada par de capas por área de solapamiento. Un solapamiento alto
    sugiere que dos fuentes distintas representan la misma información (duplicado),
    lo que distorsionaría los costes al contar el mismo terreno dos veces.

    Args:
        processed_vectors: Lista de ``(nombre, GeoDataFrame)`` ya alineados.
        threshold:         Fracción de solapamiento [0, 1] a partir de la cual avisar.
        log:               Logger de la ejecución.
    """
    if len(processed_vectors) < 2:
        log.info("  Solo hay una capa vectorial procesada; no hay pares que comparar.")
        return

    found_any = False
    for i, (name1, gdf1) in enumerate(processed_vectors):
        # unary_union: fusiona todas las geometrías de la capa en una sola, para
        # medir el área total sin contar dos veces las que se solapan entre sí.
        union1 = unary_union(gdf1.geometry)
        for name2, gdf2 in processed_vectors[i + 1:]:
            union2 = unary_union(gdf2.geometry)
            if union1.is_empty or union2.is_empty:
                continue
            try:
                area_inter = union1.intersection(union2).area
            except Exception:
                continue
            # Solapamiento relativo respecto a la capa MÁS pequeña: si la menor
            # está casi contenida en la mayor, overlap ≈ 1 (probable duplicado).
            min_area = min(union1.area, union2.area)
            if min_area == 0:
                continue
            overlap = area_inter / min_area
            if overlap > threshold:
                found_any = True
                log.warning(
                    f"SOLAPAMIENTO ALTO ({overlap:.0%}): {name1} ↔ {name2}\n"
                    f"  Pueden representar la misma información. "
                    f"Revisa FUENTES.md y considera descartar una de las dos."
                )

    if not found_any:
        log.info(
            f"  No se detectaron solapamientos > {threshold:.0%} "
            f"entre las {len(processed_vectors)} capas vectoriales."
        )


# --------------------------------------------------------------------------- #
# Paso 5: capa de coste TPI derivada del DEM                                    #
# --------------------------------------------------------------------------- #
def _generar_tpi(scenario: str, log: logging.Logger) -> None:
    """Deriva la capa de coste TPI del DEM ya alineado (dem_aoi_{s}.tif).

    Al preparar un AOI nuevo (origen+destino) el relieve se describe con el TPI
    (posición topográfica), no con la dirección del gradiente. Reutiliza
    src.superficie.tpi.procesar_escenario, que lee dem_aoi_{s}.tif de
    Recorte_AOI y escribe tpi_{s}.tif en Capas_Coste/.
    """
    dem_path = DATA_RECORTE / f"dem_aoi_{scenario}.tif"
    if not dem_path.exists():
        log.warning(
            f"  ✗ No existe {dem_path.relative_to(PROJECT_ROOT)}; "
            f"no se puede derivar el TPI (¿faltó el DEM en data/raw/?)."
        )
        return

    try:
        from src.superficie.tpi import procesar_escenario as _procesar_tpi
    except ImportError:
        try:
            from superficie.tpi import procesar_escenario as _procesar_tpi
        except ImportError as exc:
            log.warning(f"  ✗ No se pudo importar la capa TPI: {exc}")
            return

    try:
        salida = _procesar_tpi(scenario)
        log.info(f"  ✓ TPI generado: {salida.relative_to(PROJECT_ROOT)}")
    except Exception as exc:
        log.error(f"  ✗ error generando el TPI: {exc}")


# --------------------------------------------------------------------------- #
# Punto de entrada                                                              #
# --------------------------------------------------------------------------- #
def _parse_args() -> argparse.Namespace:
    """Parsea los argumentos de línea de comandos (--escenario, --only, -y)."""
    parser = argparse.ArgumentParser(description="Ingesta y alineación de capas GIS al AOI.")
    parser.add_argument(
        "--escenario", default="A",
        help="Escenario a procesar: A, B o cualquier otro id definido en "
             "escenario.yaml (p. ej. C). Por defecto: A.",
    )
    parser.add_argument(
        "--only",
        metavar="CAPA",
        help="Procesar solo la capa indicada (nombre exacto del registro LAYERS).",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Sobrescribir salidas existentes sin preguntar.",
    )
    return parser.parse_args()


def main() -> None:
    """Ejecuta el pipeline de alineación completo (Pasos 1-5) para un escenario.

    Carga la config, construye el AOI, comprueba el manifiesto de descarga,
    alinea cada capa (reproyección + remuestreo/recorte a la rejilla común),
    detecta duplicados y deriva el TPI. Sale con código ≠ 0 si alguna descarga
    estaba marcada como ``failed`` (para no continuar con capas ausentes por un
    fallo de red confundido con "sin datos").
    """
    args = _parse_args()
    args.escenario = args.escenario.upper()

    if _MISSING:
        print(
            "ERROR: Faltan dependencias Python:\n"
            f"  {', '.join(_MISSING)}\n\n"
            "Instálalas con:\n"
            f"  pip install {' '.join(_MISSING)}"
        )
        sys.exit(1)

    log = _setup_logging()
    log.info("=" * 62)
    log.info(
        f"INGESTA Y ALINEACIÓN DE CAPAS  "
        f"{datetime.now().isoformat(timespec='seconds')}"
    )
    log.info("=" * 62)

    # ── Cargar escenario ────────────────────────────────────────────────── #
    if not CONFIG_ESCENARIO.exists():
        log.error(f"No se encuentra {CONFIG_ESCENARIO}. Revisa la estructura del proyecto.")
        sys.exit(1)

    cfg = _load_escenario(CONFIG_ESCENARIO)
    target_crs = cfg.get("crs_trabajo", "EPSG:25830")
    res_m = float(cfg.get("resolucion_m", 30))

    # Seleccionar el sub-dict del escenario activo
    scenario_key = f"escenario_{args.escenario}"
    if scenario_key not in cfg:
        available = [k for k in cfg if k.startswith("escenario_")]
        log.error(
            f"'{scenario_key}' no encontrado en escenario.yaml. "
            f"Escenarios disponibles: {available}"
        )
        sys.exit(1)
    cfg_s = cfg[scenario_key]

    log.info(f"CRS de trabajo : {target_crs}")
    log.info(f"Resolución     : {res_m} m")
    log.info(f"Escenario      : {args.escenario}")
    log.info(f"Origen         : {cfg_s['origen'].get('nombre', '')}  "
             f"({cfg_s['origen']['x']}, {cfg_s['origen']['y']})")
    log.info(f"Destino        : {cfg_s['destino'].get('nombre', '')}  "
             f"({cfg_s['destino']['x']}, {cfg_s['destino']['y']})")

    # ── Paso 1: AOI ─────────────────────────────────────────────────────── #
    log.info("\n─── Paso 1: Área de Interés (AOI) ──────────────────────────────")
    aoi_box = _build_aoi(cfg_s)  # polígono orientado (rectángulo girado con la línea)
    xmin, ymin, xmax, ymax = aoi_box.bounds  # bbox axis-aligned solo para la rejilla raster
    log.info(
        f"AOI (EPSG:25830) — rectángulo orientado con la línea origen-destino:\n"
        f"  Bounding box: xmin={xmin:.0f}  ymin={ymin:.0f}\n"
        f"                xmax={xmax:.0f}  ymax={ymax:.0f}\n"
        f"  Ancho (bbox): {(xmax-xmin)/1000:.1f} km  Alto (bbox): {(ymax-ymin)/1000:.1f} km\n"
        f"  Semiancho perpendicular a la línea: {_PERP_BUFFER_M/1000:.1f} km\n"
        f"  Largo = distancia origen→destino; puntos en el punto medio del lado corto"
    )

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    aoi_path = DATA_PROCESSED / f"aoi_corredor_{args.escenario}.gpkg"
    gpd.GeoDataFrame({"geometry": [aoi_box]}, crs=target_crs).to_file(aoi_path, driver="GPKG")
    log.info(f"AOI guardado   : {aoi_path.relative_to(PROJECT_ROOT)}")

    from shapely.geometry import Point as ShapelyPoint
    pts_path = DATA_PROCESSED / f"puntos_{args.escenario}.gpkg"
    gpd.GeoDataFrame(
        {
            "nombre": [cfg_s["origen"].get("nombre", "origen"), cfg_s["destino"].get("nombre", "destino")],
            "rol":    ["origen", "destino"],
            "geometry": [
                ShapelyPoint(cfg_s["origen"]["x"], cfg_s["origen"]["y"]),
                ShapelyPoint(cfg_s["destino"]["x"], cfg_s["destino"]["y"]),
            ],
        },
        crs=target_crs,
    ).to_file(pts_path, driver="GPKG")
    log.info(f"Puntos guardados: {pts_path.relative_to(PROJECT_ROOT)}")

    target_transform, grid_w, grid_h = _common_transform(xmin, ymin, xmax, ymax, res_m)
    log.info(f"Rejilla común  : {grid_w} × {grid_h} celdas @ {res_m} m")

    # ── Avisar de archivos comprimidos ──────────────────────────────────── #
    archives = _warn_archives(log)

    # ── Comprobar sobreescritura ─────────────────────────────────────────  #
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    DATA_RECORTE.mkdir(parents=True, exist_ok=True)

    layers_to_run = LAYERS
    if args.only:
        layers_to_run = [s for s in LAYERS if s.label == args.only]
        if not layers_to_run:
            valid = ", ".join(s.label for s in LAYERS)
            log.error(f"Capa desconocida: {args.only!r}. Opciones: {valid}")
            sys.exit(1)

    # Añadir sufijo de escenario a los nombres de salida (e.g. catastro_aoi_A.gpkg).
    # spec._replace es el copy-with-changes de los NamedTuple: crea una copia con
    # output_name modificado sin mutar el registro LAYERS original.
    layers_to_run = [
        spec._replace(
            output_name=(
                Path(spec.output_name).stem
                + f"_{args.escenario}"
                + Path(spec.output_name).suffix
            )
        )
        for spec in layers_to_run
    ]

    existing = [
        DATA_RECORTE / spec.output_name
        for spec in layers_to_run
        if (DATA_RECORTE / spec.output_name).exists()
    ]

    if existing and not args.yes:
        print(
            f"\n{len(existing)} archivo(s) ya existen en "
            f"{DATA_PROCESSED.relative_to(PROJECT_ROOT)}/."
        )
        print("¿Sobrescribir? [s/N]: ", end="")
        try:
            ans = input().strip().lower()
        except EOFError:
            ans = "s"
        if ans != "s":
            log.info("Operación cancelada por el usuario.")
            return

    # ── Pasos 2-3: Reproyección y alineación ────────────────────────────── #
    log.info("\n─── Pasos 2-3: Reproyección y alineación ───────────────────────")
    # Manifiesto de descarga: distingue "sin cobertura" (empty, se alinea vacío)
    # de "descarga fallida" (failed, NO se alinea).
    download_manifest = _load_download_manifest(args.escenario, log)
    missing_layers: list[str] = []
    failed_layers: list[str] = []
    found_layers: list[str] = []
    processed_vectors: list[tuple[str, gpd.GeoDataFrame]] = []

    for spec in layers_to_run:
        log.info(f"\n[{spec.label}]")

        # Blindaje: si la descarga de esta capa falló, NO alinear. Un 'failed' no
        # es "sin cobertura": puede haber datos que no pudimos bajar, y el GPKG en
        # disco (si existe) es obsoleto o inexistente. Alinearlo produciría un
        # recorte vacío engañoso. Se re-ejecuta descargar_capas.py en su lugar.
        raw_name = _scenario_raw_name(spec, args.escenario)
        entry = download_manifest.get(raw_name) if raw_name else None
        if entry and entry.get("status") == "failed":
            detail = entry.get("detail", "sin detalle")
            # RN2000 es opcional: su fallo no bloquea el pipeline. Se trata
            # como capa sin datos (missing) en lugar de fallo crítico.
            _OPTIONAL_LABELS = {"Red Natura 2000"}
            if spec.label in _OPTIONAL_LABELS:
                log.warning(f"  ⚠ descarga de capa opcional FAILED ({detail}); se omite sin bloquear.")
                missing_layers.append(spec.label)
            else:
                log.error(f"  ✗ descarga marcada como FAILED en el manifiesto: {detail}")
                log.error(f"    → se omite la alineación (re-ejecuta descargar_capas.py "
                          f"para {raw_name})")
                failed_layers.append(spec.label)
            continue

        src_paths = _discover_layer_sources(spec, log, scenario=args.escenario)

        if not src_paths:
            log.warning(f"  ✗ no encontrado en data/raw/")
            missing_layers.append(spec.label)
            continue

        found_layers.append(spec.label)
        if len(src_paths) == 1:
            log.info(f"  Fuente : {src_paths[0].relative_to(PROJECT_ROOT)}")
        else:
            log.info(f"  Fuentes: {len(src_paths)} archivos (fusión multi-municipio)")
        log.info(f"  Tipo   : {spec.layer_type}")

        if spec.layer_type == "raster":
            process_raster(
                src_paths[0], spec, target_crs,
                target_transform, grid_w, grid_h, aoi_box, log,
            )
        else:
            _, gdf = process_vector(src_paths, spec, target_crs, aoi_box, log)
            if gdf is not None:
                processed_vectors.append((spec.label, gdf))

    # ── Paso 4: Detección de duplicados ─────────────────────────────────── #
    log.info("\n─── Paso 4: Detección de duplicados ────────────────────────────")
    if processed_vectors:
        detect_duplicates(processed_vectors, DUPLICATE_THRESHOLD, log)
    else:
        log.info("  No hay capas vectoriales procesadas; se omite este paso.")

    # ── Paso 5: Capa de coste TPI (derivada del DEM alineado) ───────────── #
    log.info("\n─── Paso 5: Capa de coste TPI (posición topográfica) ───────────")
    _generar_tpi(args.escenario, log)

    # ── Resumen ──────────────────────────────────────────────────────────── #
    log.info("\n" + "=" * 62)
    log.info("RESUMEN")
    log.info("=" * 62)
    log.info(f"  Capas encontradas    : {len(found_layers)}/{len(layers_to_run)}")
    log.info(f"  Archivos comprimidos : {len(archives)} (requieren extracción manual)")
    if failed_layers:
        log.info(f"  Descargas fallidas   : {len(failed_layers)} (omitidas, NO alineadas)")

    if failed_layers:
        log.error("  Capas con descarga FALLIDA (según manifiesto de descarga):")
        for name in failed_layers:
            log.error(f"    - {name}")

    if missing_layers:
        log.warning("  Capas NO encontradas :")
        for name in missing_layers:
            log.warning(f"    - {name}")

    log.info(f"\n  Log → {LOG_PATH.relative_to(PROJECT_ROOT)}")
    log.info(f"  Salida → {DATA_PROCESSED.relative_to(PROJECT_ROOT)}/")

    if failed_layers:
        log.error(
            "\n" + "─" * 62 + "\n"
            "Hay capas cuya DESCARGA falló; no se han alineado para no producir\n"
            "recortes vacíos engañosos. Re-ejecuta la descarga antes de continuar:\n"
            "    python -m src.ingesta.descargar_capas -y --escenario "
            f"{args.escenario}"
        )

    if missing_layers or archives:
        log.info("\n" + "─" * 62)
        log.info("ACCIÓN REQUERIDA — coloca estos archivos en data/raw/:")
        for name in missing_layers:
            hint = _DOWNLOAD_HINTS.get(name, f"  ver data/raw/FUENTES.md")
            log.info(f"\n  {name}:\n{hint}")
        if archives:
            log.info(
                "\n  Archivos comprimidos — extrae el contenido antes de re-ejecutar:\n"
                + "\n".join(f"    {a.relative_to(PROJECT_ROOT)}" for a in archives)
            )

    # Salir con código ≠ 0 si alguna descarga había fallado: el pipeline no debe
    # continuar con capas ausentes por un fallo de red confundido con "sin datos".
    if failed_layers:
        sys.exit(1)


if __name__ == "__main__":
    main()
