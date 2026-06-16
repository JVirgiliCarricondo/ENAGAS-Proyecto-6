"""
Ingesta y alineación de capas GIS al CRS y rejilla comunes del proyecto.

Paso 1: Construye el AOI (desde escenario.yaml o desde origen+destino+1 km buffer).
Paso 2: Reproyecta todas las capas a EPSG:25830.
Paso 3: Remuestrea rasters a la rejilla común; recorta y reproyecta vectores → GeoPackage.
Paso 4: Detecta solapamientos entre capas vectoriales (umbral: 70 %).

Ejecutar desde la raíz del proyecto (proyecto/):
    python -m src.ingesta.alinear_capas
"""
from __future__ import annotations

import argparse
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
    from rasterio.transform import from_origin
    from rasterio.warp import reproject as rio_reproject
except ImportError:
    _MISSING.append("rasterio")

try:
    import geopandas as gpd
    from shapely.geometry import LineString, box
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
DATA_RECORTE = DATA_PROCESSED / "Recorte_AOI"   # vectores recortados al AOI (.gpkg)
DATA_RASTERS = DATA_PROCESSED / "Rasters_AOI"   # rasters alineados (.tif)
CONFIG_ESCENARIO = PROJECT_ROOT / "data" / "config" / "escenario.yaml"
LOG_PATH = DATA_PROCESSED / "log_alineacion.txt"

DUPLICATE_THRESHOLD = 0.70  # fracción de solapamiento para avisar de duplicados
CATASTRO_MUNICIPALITY_RE = re.compile(r"^\d+[ur]A \d+ .+", re.IGNORECASE)

# --------------------------------------------------------------------------- #
# Registro de capas esperadas                                                  #
# --------------------------------------------------------------------------- #
class LayerSpec(NamedTuple):
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
    "DEM Copernicus":    "DEM_{s}.tif",
    "Corine Land Cover": "CLC_{s}.gpkg",
    "OSM":               "OSM_{s}.gpkg",
    "Hidrografía IGN":   "HID_{s}.gpkg",
    "IGME geológico":    "IGME_{s}.gpkg",
    # RN2000 no tiene sufijo de escenario: es una capa nacional única en data/raw/RN2000/.
    # Se descubre por glob_patterns y se recorta al AOI de cada escenario.
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
        label="Corine Land Cover",
        layer_type="vector",
        categorical=True,
        glob_patterns=[
            "CLC.gpkg", "CLC.shp", "CLC.geojson",
            "**/CLC.gpkg", "**/CLC.shp", "**/CLC.geojson",
            "**/*corine*.gpkg", "**/*CORINE*.gpkg",
        ],
        output_name="clc_aoi.gpkg",
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
    "Corine Land Cover": (
        "  → https://land.copernicus.eu/\n"
        "    Guárdalo como: data/raw/CLC.gpkg  (o CLC.shp)"
    ),
    "Red Natura 2000": (
        "  → https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/biodiversidad/rn2000.html\n"
        "    Guárdalo como: data/raw/RN2000.gpkg  (o RN2000.geojson)"
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
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    DATA_RECORTE.mkdir(parents=True, exist_ok=True)
    DATA_RASTERS.mkdir(parents=True, exist_ok=True)
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
    if not log.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        log.addHandler(ch)
    fh = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return log


def _load_escenario(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_aoi(cfg: dict):
    """Devuelve un polígono Shapely orientado alineado con la línea origen-destino.

    Si escenario.yaml define un bounding box explícito, devuelve ese rectángulo
    axis-aligned. Si no, devuelve el rectángulo girado obtenido como buffer de
    1 km a cada lado con tapas planas (cap_style=2): los lados del rectángulo
    son paralelos a la línea origen→destino y ésta queda perfectamente centrada.
    """
    aoi = cfg.get("aoi", {})
    if aoi and all(aoi.get(k, 0) != 0 for k in ("xmin", "ymin", "xmax", "ymax")):
        return box(aoi["xmin"], aoi["ymin"], aoi["xmax"], aoi["ymax"])

    ox, oy = cfg["origen"]["x"], cfg["origen"]["y"]
    dx, dy = cfg["destino"]["x"], cfg["destino"]["y"]
    line = LineString([(ox, oy), (dx, dy)])
    # cap_style=2 → tapas planas: rectángulo girado alineado con la línea,
    # 1 km a cada lado perpendicular. NO se llama a .bounds para no perder
    # la orientación (ese era el bug anterior que convertía a axis-aligned box).
    return line.buffer(1000, cap_style=2)


def _common_transform(xmin: float, ymin: float, xmax: float, ymax: float,
                       res: float):
    """Calcula el transform, ancho y alto de la rejilla común."""
    width = math.ceil((xmax - xmin) / res)
    height = math.ceil((ymax - ymin) / res)
    # from_origin(west, north, xsize, ysize)
    transform = from_origin(xmin, ymin + height * res, res, res)
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
    descargar_capas.py (p. ej. DEM_A.tif) antes de recorrer glob_patterns.
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


def _catastro_municipality_name(shp: Path, catastro_dir: Path) -> str:
    """Identifica la carpeta de municipio aunque esté anidada bajo un ZIP provincial."""
    for parent in shp.parents:
        if parent == catastro_dir:
            break
        if CATASTRO_MUNICIPALITY_RE.match(parent.name):
            return parent.name
    return shp.relative_to(catastro_dir).parts[0]


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
    return any(
        CATASTRO_MUNICIPALITY_RE.match(path.name)
        and any(path.rglob("PARCELA.shp"))
        for path in catastro_dir.iterdir()
        if path.is_dir()
    )


def _extract_catastro_archives(log: logging.Logger) -> int:
    """Descomprime recursivamente los ZIP bajo data/raw/Catastro/."""
    catastro_dir = DATA_RAW / "Catastro"
    if not catastro_dir.exists():
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


def _discover_catastro_sources(log: logging.Logger) -> list[Path]:
    """Un PARCELA.shp por municipio bajo data/raw/Catastro/ (exportación fechada si existe)."""
    catastro_dir = DATA_RAW / "Catastro"
    if not catastro_dir.exists():
        return []

    _extract_catastro_archives(log)

    by_municipality: dict[str, list[Path]] = {}
    for shp in sorted(catastro_dir.rglob("PARCELA.shp")):
        municipality = _catastro_municipality_name(shp, catastro_dir)
        by_municipality.setdefault(municipality, []).append(shp)

    selected: list[Path] = []
    for municipality, paths in sorted(by_municipality.items()):
        dated_exports = [p for p in paths if p.parent.name.endswith("_PARCELA")]
        chosen = dated_exports[0] if dated_exports else paths[0]
        selected.append(chosen)
        log.debug(
            f"  [Catastro] {municipality} → {chosen.relative_to(PROJECT_ROOT)}"
        )
    return selected


def _warn_archives(log: logging.Logger) -> list[Path]:
    """Detecta archivos comprimidos en data/raw/ e imprime instrucciones."""
    catastro_dir = DATA_RAW / "Catastro"
    if catastro_dir.exists():
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
    log: logging.Logger,
) -> Path | None:
    """Reproyecta y remuestrea un raster a la rejilla común. Devuelve la ruta de salida."""
    out_path = DATA_RASTERS / spec.output_name
    resampling = Resampling.nearest if spec.categorical else Resampling.bilinear

    try:
        with rasterio.open(src_path) as src:
            orig_crs = src.crs.to_string() if src.crs else "desconocido"
            log.info(f"  CRS original : {orig_crs}")
            log.info(f"  Resolución   : {src.res[0]:.1f} × {src.res[1]:.1f} m")
            log.info(f"  Bandas       : {src.count}")

            dst_crs = RasterioCRS.from_string(target_crs)
            nodata = float(src.nodata) if src.nodata is not None else -9999.0
            n_bands = src.count
            dst_data = np.full((n_bands, grid_h, grid_w), nodata, dtype=np.float32)

            for band in range(1, n_bands + 1):
                rio_reproject(
                    source=rasterio.band(src, band),
                    destination=dst_data[band - 1],
                    dst_transform=target_transform,
                    dst_crs=dst_crs,
                    resampling=resampling,
                    dst_nodata=nodata,
                )

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
    """Reproyecta y recorta una capa vectorial al AOI. Devuelve (ruta_salida, gdf)."""
    out_path = DATA_RECORTE / spec.output_name
    paths = [src_paths] if isinstance(src_paths, Path) else list(src_paths)

    try:
        frames: list["gpd.GeoDataFrame"] = []
        read_kwargs: dict = {}
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

        if gdf.crs is None:
            log.warning(f"  CRS no definido en {paths[0].name}; se asume EPSG:4326")
            gdf = gdf.set_crs(epsg=4326)

        gdf = gdf.to_crs(target_crs)

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
    """Avisa si dos capas vectoriales se solapan más del umbral dado."""
    if len(processed_vectors) < 2:
        log.info("  Solo hay una capa vectorial procesada; no hay pares que comparar.")
        return

    found_any = False
    for i, (name1, gdf1) in enumerate(processed_vectors):
        union1 = unary_union(gdf1.geometry)
        for name2, gdf2 in processed_vectors[i + 1:]:
            union2 = unary_union(gdf2.geometry)
            if union1.is_empty or union2.is_empty:
                continue
            try:
                area_inter = union1.intersection(union2).area
            except Exception:
                continue
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
                print(
                    f"\n[AVISO] {name1!r} y {name2!r} se solapan en un {overlap:.0%}.\n"
                    f"¿Conservar? [ambas / 1={name1} / 2={name2}]: ",
                    end="",
                )
                try:
                    ans = input().strip().lower()
                    if ans == "1":
                        log.info(f"  Usuario eligió conservar: {name1}")
                    elif ans == "2":
                        log.info(f"  Usuario eligió conservar: {name2}")
                    else:
                        log.info("  Usuario eligió conservar ambas capas.")
                except EOFError:
                    log.info("  Modo no interactivo — se conservan ambas capas.")

    if not found_any:
        log.info(
            f"  No se detectaron solapamientos > {threshold:.0%} "
            f"entre las {len(processed_vectors)} capas vectoriales."
        )


# --------------------------------------------------------------------------- #
# Punto de entrada                                                              #
# --------------------------------------------------------------------------- #
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingesta y alineación de capas GIS al AOI.")
    parser.add_argument(
        "--escenario", choices=["A", "B"], default="A",
        help="Escenario a procesar (A o B, según escenario.yaml). Por defecto: A.",
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
    args = _parse_args()

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
        f"  Semiancho perpendicular a la línea: 1.0 km"
    )

    target_transform, grid_w, grid_h = _common_transform(xmin, ymin, xmax, ymax, res_m)
    log.info(f"Rejilla común  : {grid_w} × {grid_h} celdas @ {res_m} m")

    # ── Avisar de archivos comprimidos ──────────────────────────────────── #
    archives = _warn_archives(log)

    # ── Comprobar sobreescritura ─────────────────────────────────────────  #
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    DATA_RECORTE.mkdir(parents=True, exist_ok=True)
    DATA_RASTERS.mkdir(parents=True, exist_ok=True)

    layers_to_run = LAYERS
    if args.only:
        layers_to_run = [s for s in LAYERS if s.label == args.only]
        if not layers_to_run:
            valid = ", ".join(s.label for s in LAYERS)
            log.error(f"Capa desconocida: {args.only!r}. Opciones: {valid}")
            sys.exit(1)

    # Añadir sufijo de escenario a los nombres de salida (e.g. clc_aoi_A.gpkg)
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
        subdir / spec.output_name
        for spec in layers_to_run
        for subdir in ([DATA_RASTERS] if spec.layer_type == "raster" else [DATA_RECORTE])
        if (subdir / spec.output_name).exists()
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
    missing_layers: list[str] = []
    found_layers: list[str] = []
    processed_vectors: list[tuple[str, gpd.GeoDataFrame]] = []

    for spec in layers_to_run:
        log.info(f"\n[{spec.label}]")
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
                target_transform, grid_w, grid_h, log,
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

    # ── Resumen ──────────────────────────────────────────────────────────── #
    log.info("\n" + "=" * 62)
    log.info("RESUMEN")
    log.info("=" * 62)
    log.info(f"  Capas encontradas    : {len(found_layers)}/{len(layers_to_run)}")
    log.info(f"  Archivos comprimidos : {len(archives)} (requieren extracción manual)")

    if missing_layers:
        log.warning("  Capas NO encontradas :")
        for name in missing_layers:
            log.warning(f"    - {name}")

    log.info(f"\n  Log → {LOG_PATH.relative_to(PROJECT_ROOT)}")
    log.info(f"  Salida → {DATA_PROCESSED.relative_to(PROJECT_ROOT)}/")

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


if __name__ == "__main__":
    main()
