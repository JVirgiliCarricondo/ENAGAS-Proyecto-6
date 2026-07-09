"""
Descarga automática de capas GIS para el AOI de cada escenario.

Para cada escenario (A y B) definido en escenario.yaml, calcula el AOI y
descarga la unidad mínima de cada fuente que lo contenga:

  - Todas las fuentes exponen servicios WFS, WCS o Overpass que aceptan
    consultas espaciales por bbox.  La "unidad mínima" es el propio bbox
    del AOI: el servidor filtra y devuelve únicamente las geometrías dentro
    del área de interés, sin descargar capas regionales ni nacionales.

Archivos generados en data/raw/ (sufijo _A o _B según el escenario):

  DEM_{s}.tif      → Copernicus GLO-30 (tiles COG en AWS S3), ~30 m, GeoTIFF
  OSM_{s}.gpkg     → Carreteras + ferrocarril, Overpass API
  HID_{s}.gpkg     → Hidrografía IGN, WFS INSPIRE (HY.PhysicalWaters.Watercourses)
  IGME_{s}.gpkg    → Mapa geológico IGME MAGNA50, ArcGIS REST
  INUND_{s}.gpkg   → Zonas inundables SNCZI (MITECO), OGC API Features, unión T10+T100+T500
  RN2000_{s}.gpkg  → Red Natura 2000 (ZEPA/LIC/ZEC), WFS INSPIRE IGN (PS.ProtectedSite)

Solo Catastro NO se descarga automáticamente (no hay servicio bbox fiable):
se coloca a mano en data/raw/Catastro/ y alinear_capas.py lo recorta al AOI.

Además se escribe un manifiesto de estado por capa en data/raw/manifiesto_estado.json
que distingue tres situaciones que antes se confundían en "guardar vacío y seguir":

  - ok      → capa descargada con datos.
  - empty   → el servicio respondió pero el AOI no tiene cobertura (GPKG vacío
              legítimo: ausencia CONFIRMADA de datos).
  - failed  → la descarga falló (servicio caído/timeout/error): NO se escribe un
              GPKG vacío; no sabemos si hay cobertura. El proceso termina con
              código de salida ≠ 0 para que el pipeline no continúe a ciegas.

Para verificar los nombres de capa de cada WFS:
  GET {endpoint}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities

Uso:
    python -m src.ingesta.descargar_capas              # ambos escenarios
    python -m src.ingesta.descargar_capas --escenario A
    python -m src.ingesta.descargar_capas --escenario B
    python -m src.ingesta.descargar_capas -y           # sobrescribir sin preguntar
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

import urllib.request
import urllib.parse

import requests
import yaml

_MISSING: list[str] = []

try:
    import geopandas as gpd
    from shapely.geometry import LineString
except ImportError:
    _MISSING.append("geopandas")

try:
    import rasterio  # noqa: F401  (importado para verificar disponibilidad)
except ImportError:
    _MISSING.append("rasterio")

try:
    from pyproj import Transformer
except ImportError:
    _MISSING.append("pyproj")

# ──────────────────────────────────────────────────────────────────────────── #
# Rutas                                                                        #
# ──────────────────────────────────────────────────────────────────────────── #
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # proyecto/
DATA_RAW = PROJECT_ROOT / "data" / "raw"
CONFIG_ESCENARIO = PROJECT_ROOT / "data" / "config" / "escenario.yaml"
LOG_PATH = DATA_RAW / "log_descarga.txt"
MANIFEST_PATH = DATA_RAW / "manifiesto_estado.json"


# ──────────────────────────────────────────────────────────────────────────── #
# Estado de descarga por capa                                                  #
# ──────────────────────────────────────────────────────────────────────────── #
class LayerStatus(str, Enum):
    """Estado del resultado de descarga de una capa en un escenario."""
    OK = "ok"           # datos descargados y escritos en disco
    EMPTY = "empty"     # el servicio respondió, pero el AOI no tiene cobertura
                        #   (GPKG vacío legítimo: ausencia confirmada de datos)
    FAILED = "failed"   # la descarga falló (servicio caído, timeout, error de
                        #   parseo…): NO se escribe GPKG vacío, no sabemos si hay
                        #   cobertura o no
    SKIPPED = "skipped" # el archivo ya existía y no se solicitó sobrescribir


@dataclass
class LayerResult:
    """Resultado de descargar una capa: estado + nº de filas + detalle."""
    status: LayerStatus
    rows: int = 0
    detail: str = ""

# ──────────────────────────────────────────────────────────────────────────── #
# Endpoints de servicios OGC públicos                                          #
# ──────────────────────────────────────────────────────────────────────────── #
_IGN_WFS_HID   = "https://servicios.idee.es/wfs-inspire/hidrografia"
_IGN_WFS_RN2000 = "https://servicios.idee.es/wfs-inspire/redes-ecologicas"
_IGME_REST     = "https://mapas.igme.es/gis/rest/services/Cartografia_Geologica/IGME_MAGNA_50/MapServer/11/query"
# Endpoints Overpass en orden de preferencia; se prueban en secuencia si fallan.
_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]
# SNCZI (Sistema Nacional de Cartografía de Zonas Inundables), MITECO.
# El WFS clásico (wfs.aspx) no expone estas capas (error interno del servidor,
# verificado); MITECO migró la descarga por bbox a OGC API Features:
# GetCapabilities → https://wmts.mapama.gob.es/sig-api/ogc/features/v1/collections
_MITECO_OAFEAT_ZI = "https://wmts.mapama.gob.es/sig-api/ogc/features/v1"

# Nombres de capa WFS INSPIRE (obtenidos vía GetCapabilities)
_WFS_HID    = "hy-n:WatercourseLink"   # enlaces de cursos de agua (tramos lineales)
_WFS_RN2000 = "PS.ProtectedSite"       # zonas protegidas INSPIRE (ZEPA/LIC/ZEC)
# SNCZI: láminas de inundación por periodo de retorno (T10, T100, T500 años).
# IDs de colección confirmados en /collections del API-Features (29-jun-2026).
# El modelo de coste solo usa la UNIÓN de las tres (binario, sin distinguir T).
_OAFEAT_ZI = ["agua:Zi_laminas_q10", "agua:Zi_laminas_q100", "agua:Zi_laminas_q500"]

# Cabeceras HTTP que evitan el reseteo de conexión en servicios IGN
# Connection: close desactiva keepalive, que causa ConnectionResetError(10054) en Windows
_HEADERS = {
    "User-Agent": "ENAGAS-Proyecto6/1.0 (academic; ETSI-ICAI Comillas)",
    "Connection": "close",
    "Accept": "*/*",
}


# ──────────────────────────────────────────────────────────────────────────── #
# Utilidades                                                                   #
# ──────────────────────────────────────────────────────────────────────────── #
def _setup_logging() -> logging.Logger:
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    log = logging.getLogger("descarga")
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


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _scenario_aoi(cfg_s: dict) -> tuple[float, float, float, float]:
    """Devuelve (xmin, ymin, xmax, ymax) en EPSG:25830."""
    aoi = cfg_s.get("aoi", {})
    if aoi and all(aoi.get(k, 0) != 0 for k in ("xmin", "ymin", "xmax", "ymax")):
        return aoi["xmin"], aoi["ymin"], aoi["xmax"], aoi["ymax"]
    line = LineString([
        (cfg_s["origen"]["x"], cfg_s["origen"]["y"]),
        (cfg_s["destino"]["x"], cfg_s["destino"]["y"]),
    ])
    return line.buffer(1000, cap_style=2).bounds


def _to_4326(xmin: float, ymin: float, xmax: float, ymax: float
             ) -> tuple[float, float, float, float]:
    """Convierte bbox EPSG:25830 → (west, south, east, north) en WGS84."""
    tr = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
    w, s = tr.transform(xmin, ymin)
    e, n = tr.transform(xmax, ymax)
    return w, s, e, n


def _write_gpkg(
    gdf: "gpd.GeoDataFrame",
    out_path: Path,
    log: logging.Logger,
) -> int:
    """Escribe un GeoDataFrame (posiblemente vacío, pero válido) reproyectado a
    EPSG:25830. Devuelve el nº de filas escritas."""
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:25830")
    elif gdf.crs.to_epsg() != 25830:
        gdf = gdf.to_crs("EPSG:25830")
    gdf.to_file(out_path, driver="GPKG")
    return len(gdf)


def _vector_result(
    gdf: "gpd.GeoDataFrame | None",
    out_path: Path,
    log: logging.Logger,
    source: str,
) -> LayerResult:
    """
    Traduce el resultado de un descargador a LayerResult, distinguiendo los tres
    estados que antes se colapsaban en "guardar vacío y devolver True":

      - gdf is None  → FAILED: la descarga falló. NO se escribe GPKG vacío; si ya
        existe un archivo previo se conserva (mejor dato viejo que fabricar un
        "sin cobertura" falso).
      - gdf vacío    → EMPTY:  el servicio respondió pero el AOI no tiene cobertura.
        Se escribe un GPKG vacío (ausencia confirmada, legítima aguas abajo).
      - gdf con filas → OK:    se escribe con sus geometrías.
    """
    if gdf is None:
        log.error(f"  ✗ descarga fallida ({source}) → no se escribe GPKG "
                  f"(estado FAILED, se conserva el archivo previo si lo hubiera)")
        return LayerResult(LayerStatus.FAILED, 0, f"descarga fallida: {source}")

    if gdf.empty:
        empty = gpd.GeoDataFrame(geometry=gpd.GeoSeries(crs="EPSG:25830"))
        _write_gpkg(empty, out_path, log)
        log.warning(f"  ○ AOI sin cobertura ({source}) → GPKG vacío: {out_path.name}")
        return LayerResult(LayerStatus.EMPTY, 0, f"AOI sin cobertura: {source}")

    rows = _write_gpkg(gdf, out_path, log)
    log.info(f"  ✓ {out_path.name}  ({rows} filas)")
    return LayerResult(LayerStatus.OK, rows, source)


def _parse_wfs_response(
    resp: requests.Response,
    fallback_crs: str = "EPSG:25830",
) -> "gpd.GeoDataFrame | None":
    """Intenta parsear la respuesta de un WFS como GeoDataFrame."""
    content = resp.content
    # Descartar respuestas de error OGC
    if b"ExceptionReport" in content[:2000] or b"ServiceException" in content[:2000]:
        return None
    # Intentar lectura directa (GeoJSON o GML)
    try:
        gdf = gpd.read_file(io.BytesIO(content))
        if gdf.crs is None:
            gdf = gdf.set_crs(fallback_crs)
        return gdf
    except Exception:
        pass
    # Fallback: guardar en fichero temporal y releer (ayuda con algunas variantes GML)
    is_gml = b"<wfs:" in content[:500] or b"<gml:" in content[:500]
    suffix = ".gml" if is_gml else ".geojson"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(content)
            tmp = f.name
        try:
            gdf = gpd.read_file(tmp)
            if gdf.crs is None:
                gdf = gdf.set_crs(fallback_crs)
            return gdf
        finally:
            os.unlink(tmp)
    except Exception:
        return None


def _wfs_url(
    endpoint: str,
    typename: str,
    version: str,
    bbox_str: str,
    out_fmt: str,
    max_features: int,
) -> str:
    """
    Construye la URL de un WFS GetFeature preservando los dos puntos del namespace
    (lcv:LandCoverUnit, hy-n:WatercourseLink…) sin URL-encodificarlos.
    requests.get(params=…) encoda ':' como '%3A', lo que algunos servidores rechazan.
    """
    tname_key = "TYPENAMES" if version == "2.0.0" else "TYPENAME"
    count_key = "COUNT" if version == "2.0.0" else "MAXFEATURES"
    # Construir pares key=value; los valores con ':' se dejan literales
    parts = [
        ("SERVICE", "WFS"),
        ("VERSION", version),
        ("REQUEST", "GetFeature"),
        (tname_key, typename),
        ("BBOX", bbox_str),
        ("OUTPUTFORMAT", out_fmt),
        (count_key, str(max_features)),
    ]
    # safe=':,+/' preserva namespace, comas del BBOX y el + de 'gml+xml'.
    # Las comillas dobles (" → %22) y punto y coma (; → %3B) SÍ se encodifican
    # porque así los acepta el servidor IGN INSPIRE.
    qs = "&".join(
        f"{k}={urllib.parse.quote(v, safe=':,+/')}" for k, v in parts
    )
    sep = "&" if "?" in endpoint else "?"
    return endpoint + sep + qs


def _wfs_bbox(
    endpoint: str,
    typename: str,
    bbox_25830: tuple[float, float, float, float],
    log: logging.Logger,
    max_features: int = 50_000,
) -> "gpd.GeoDataFrame | None":
    """
    Descarga capa WFS por bbox probando WFS 2.0.0 y 1.1.0 con JSON y GML.
    Devuelve GeoDataFrame en EPSG:25830, o None si todos los intentos fallan.
    """
    xmin, ymin, xmax, ymax = bbox_25830

    # Formatos verificados vía GetCapabilities de los servicios IGN INSPIRE.
    # Las comillas interiores son obligatorias; urllib.parse.quote las codifica a %22.
    attempts = [
        # (versión, outputformat)
        ("2.0.0", 'application/json'),
        ("2.0.0", 'text/xml; subtype="gml/3.2.1"'),
        ("2.0.0", 'text/xml; subtype="gml/2.1.2"'),
        ("1.1.0", 'application/json'),
    ]

    for version, out_fmt in attempts:
        # Coordenadas como enteros (sin decimales .0) para compatibilidad con proxies IGN
        bbox_str = f"{int(xmin)},{int(ymin)},{int(xmax)},{int(ymax)},EPSG:25830"
        url = _wfs_url(endpoint, typename, version, bbox_str, out_fmt, max_features)
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=120)
            resp.raise_for_status()
            gdf = _parse_wfs_response(resp)
            if gdf is not None:
                log.debug(f"    OK WFS {version} / {out_fmt[:30]} → {len(gdf)} filas")
                if len(gdf) >= max_features:
                    log.warning(
                        f"    Respuesta WFS en el límite ({max_features} features): "
                        f"la capa puede estar TRUNCADA para este AOI."
                    )
                return gdf.to_crs("EPSG:25830") if gdf.crs else gdf
        except requests.exceptions.Timeout:
            log.debug(f"    Timeout WFS {version} / {out_fmt[:30]}")
        except Exception as exc:
            log.debug(f"    Error WFS {version} / {out_fmt[:30]}: {exc}")

    return None


def _ogc_features_bbox(
    base_url: str,
    collection_id: str,
    bbox_25830: tuple[float, float, float, float],
    log: logging.Logger,
    limit: int = 5_000,
) -> "gpd.GeoDataFrame | None":
    """
    Descarga una colección OGC API Features (estándar OGC 17-069r3, sucesor del
    WFS clásico) filtrando por bbox. El bbox se da en WGS84 (CRS84), como exige
    el estándar; la respuesta GeoJSON viene en WGS84 y se reproyecta a 25830.

    Distingue fallo de ausencia de cobertura:
      - None                → el servicio no respondió o dio un error (FAILED).
      - GeoDataFrame vacío  → respondió correctamente sin features en el AOI.
      - GeoDataFrame lleno  → features reproyectadas a EPSG:25830.
    """
    w, s, e, n = _to_4326(*bbox_25830)
    url = (
        f"{base_url}/collections/{collection_id}/items"
        f"?f=application%2Fgeo%2Bjson&bbox={w},{s},{e},{n}&limit={limit}"
    )
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.debug(f"    Error OGC API Features {collection_id}: {exc}")
        return None

    features = data.get("features", [])
    if not features:
        # El servicio respondió bien, pero el AOI no tiene cobertura: vacío ≠ fallo.
        return gpd.GeoDataFrame(geometry=gpd.GeoSeries(crs="EPSG:25830"))
    if len(features) >= limit:
        log.warning(
            f"    {collection_id}: respuesta en el límite ({limit} features): "
            f"la capa puede estar TRUNCADA para este AOI."
        )
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    return gdf.to_crs("EPSG:25830")


# ──────────────────────────────────────────────────────────────────────────── #
# Descargadores por fuente                                                     #
# ──────────────────────────────────────────────────────────────────────────── #
_COP_S3 = "https://copernicus-dem-30m.s3.amazonaws.com"


def _cop_tile_url(lat: int, lon: int) -> str:
    """URL de un tile Copernicus GLO-30 (1°×1°) en AWS S3 según lat/lon floor."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    la = abs(lat)
    lo = abs(lon)
    name = f"Copernicus_DSM_COG_10_{ns}{la:02d}_00_{ew}{lo:03d}_00_DEM"
    return f"{_COP_S3}/{name}/{name}.tif"


def download_dem(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> LayerResult:
    """
    DEM Copernicus GLO-30 (30 m) desde tiles COG en AWS S3.
    Lee solo la ventana del AOI sin descargar el tile completo (~40 MB).

    Un fallo (ningún tile accesible) lanza excepción y se registra como FAILED
    aguas arriba; nunca se produce un raster vacío que finja "sin cobertura".
    """
    import os
    import rasterio
    from rasterio.crs import CRS
    from rasterio.merge import merge
    from rasterio.windows import from_bounds
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    xmin, ymin, xmax, ymax = bbox_25830
    w, s, e, n = _to_4326(xmin, ymin, xmax, ymax)

    # Determinar qué tiles cubre el AOI (tiles de 1°×1°, esquina SW)
    lat_tiles = range(int(s), int(n) + 1)
    lon_tiles = range(int(w) - 1, int(e) + 1)
    tile_urls = [_cop_tile_url(la, lo) for la in lat_tiles for lo in lon_tiles]

    # Configurar GDAL para leer COGs remotos
    os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "30")
    os.environ.setdefault("GDAL_HTTP_TIMEOUT", "120")
    os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

    datasets: list = []
    for tile_url in tile_urls:
        # Comprobar que el tile existe antes de abrirlo
        try:
            head = requests.head(tile_url, headers=_HEADERS, timeout=15)
            if head.status_code != 200:
                log.debug(f"  Tile no encontrado ({head.status_code}): {tile_url[-60:]}")
                continue
        except Exception as exc:
            log.debug(f"  Error HEAD tile: {exc}")
            continue

        vsi_url = f"/vsicurl/{tile_url}"
        log.info(f"  COG tile → {tile_url[-60:]}")
        try:
            ds = rasterio.open(vsi_url)
            datasets.append(ds)
        except Exception as exc:
            log.warning(f"  No se pudo abrir COG: {exc}")

    if not datasets:
        raise RuntimeError("Ningún tile Copernicus GLO-30 pudo abrirse.")

    # Mosaico y recorte al AOI (en WGS84)
    mosaic, mosaic_transform = merge(datasets, bounds=(w, s, e, n), nodata=-9999)
    mosaic_crs = datasets[0].crs
    for ds in datasets:
        ds.close()

    # Reproyectar a EPSG:25830
    import numpy as np
    dst_crs = CRS.from_epsg(25830)
    dst_transform, dst_width, dst_height = calculate_default_transform(
        mosaic_crs, dst_crs, mosaic.shape[-1], mosaic.shape[-2],
        left=w, bottom=s, right=e, top=n,
    )
    reprojected = np.zeros((1, dst_height, dst_width), dtype=mosaic.dtype)
    reproject(
        source=mosaic,
        destination=reprojected,
        src_transform=mosaic_transform,
        src_crs=mosaic_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
    )

    with rasterio.open(
        out_path, "w",
        driver="GTiff",
        height=dst_height, width=dst_width,
        count=1, dtype=reprojected.dtype,
        crs=dst_crs,
        transform=dst_transform,
        compress="lzw",
    ) as dst:
        dst.write(reprojected)

    log.info(f"  ✓ {out_path.name}  ({out_path.stat().st_size // 1024} KB)  "
             f"{dst_width}×{dst_height} px @ ~30 m EPSG:25830")
    return LayerResult(
        LayerStatus.OK, dst_width * dst_height,
        f"{dst_width}×{dst_height} px @ ~30 m EPSG:25830",
    )


def download_zonas_inundables(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> LayerResult:
    """
    Zonas inundables SNCZI (MITECO) vía OGC API Features: une T10, T100 y T500
    en una sola capa, ya que el modelo de coste solo distingue dentro/fuera
    (sin gradación por periodo de retorno; ver perfiles.yaml
    parametros_capas.zonas_inundables).

    La unión requiere que las colecciones respondan: si TODAS fallan no podemos
    afirmar que el AOI esté libre de inundables → FAILED. Si al menos una responde
    (aunque todas vengan vacías), es una ausencia de cobertura legítima → EMPTY.
    """
    log.info(f"  OGC API Features SNCZI/MITECO → {_MITECO_OAFEAT_ZI}")
    partes = []
    respondidas = 0
    for collection_id in _OAFEAT_ZI:
        gdf_t = _ogc_features_bbox(_MITECO_OAFEAT_ZI, collection_id, bbox_25830, log)
        if gdf_t is None:
            log.warning(f"    {collection_id} → descarga fallida")
            continue
        respondidas += 1
        if not gdf_t.empty:
            gdf_t["periodo_retorno"] = collection_id.rsplit("_q", 1)[-1]
            partes.append(gdf_t[["geometry", "periodo_retorno"]])
            log.info(f"    {collection_id} → {len(gdf_t)} polígonos")
        else:
            log.debug(f"    {collection_id} → sin cobertura en el AOI")

    if partes:
        gdf = (
            partes[0]
            if len(partes) == 1
            else gpd.GeoDataFrame(gpd.pd.concat(partes, ignore_index=True), crs=partes[0].crs)
        )
        return _vector_result(gdf, out_path, log, "SNCZI/MITECO")

    if respondidas == 0:
        log.error("  ✗ SNCZI: todas las colecciones fallaron → no se escribe GPKG")
        return LayerResult(LayerStatus.FAILED, 0, "SNCZI: todas las colecciones fallaron")

    # Alguna colección respondió correctamente pero vacía: ausencia confirmada.
    log.warning("  ○ SNCZI sin láminas de inundación en el AOI")
    empty = gpd.GeoDataFrame(geometry=gpd.GeoSeries(crs="EPSG:25830"))
    return _vector_result(empty, out_path, log, "SNCZI/MITECO")


def download_osm(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> LayerResult:
    """Carreteras + ferrocarril vía Overpass API. Salida: GeoPackage de LineStrings.

    Un fallo de Overpass lanza excepción (→ FAILED aguas arriba); una respuesta
    correcta sin vías es una ausencia de cobertura legítima (→ EMPTY)."""
    w, s, e, n = _to_4326(*bbox_25830)
    # Overpass usa orden lat,lon: sur,oeste,norte,este
    bbox_str = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    query = (
        f"[out:json][timeout:90][bbox:{bbox_str}];"
        "(way[highway];way[railway];);"
        "(._;>;);"
        "out body;"
    )
    log.info(f"  Overpass API bbox ({s:.4f},{w:.4f}) → ({n:.4f},{e:.4f})")
    last_exc: Exception | None = None
    data: dict = {}
    for endpoint in _OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(endpoint, data={"data": query}, headers=_HEADERS, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            log.info(f"  Overpass OK ({endpoint})")
            last_exc = None
            break
        except Exception as exc:
            log.warning(f"  Overpass fallback: {endpoint} → {exc}")
            last_exc = exc
    if last_exc is not None:
        raise last_exc

    nodes = {
        el["id"]: (el["lon"], el["lat"])
        for el in data.get("elements", [])
        if el["type"] == "node"
    }
    keep_tags = {"highway", "railway", "name", "oneway", "maxspeed", "lanes", "surface"}
    features = []
    for el in data.get("elements", []):
        if el["type"] != "way":
            continue
        coords = [nodes[nid] for nid in el.get("nodes", []) if nid in nodes]
        if len(coords) < 2:
            continue
        features.append({
            "geometry": LineString(coords),
            "osm_id": el["id"],
            **{k: v for k, v in el.get("tags", {}).items() if k in keep_tags},
        })

    gdf = (
        gpd.GeoDataFrame(features, crs="EPSG:4326")
        if features
        else gpd.GeoDataFrame(geometry=gpd.GeoSeries(crs="EPSG:4326"))
    )
    return _vector_result(gdf, out_path, log, "Overpass highway/railway")


def download_hidrografia(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> LayerResult:
    """Hidrografía IGN vía WFS INSPIRE (max 2000 features).

    _wfs_bbox devuelve None si TODOS los intentos WFS fallan (→ FAILED); un WFS
    que responde sin geometrías produce un GeoDataFrame vacío (→ EMPTY)."""
    log.info(f"  WFS IGN INSPIRE → {_WFS_HID}")
    gdf = _wfs_bbox(_IGN_WFS_HID, _WFS_HID, bbox_25830, log, max_features=2_000)
    return _vector_result(gdf, out_path, log, "WFS IGN INSPIRE hidrografía")


def download_rn2000(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> LayerResult:
    """Red Natura 2000 (ZEPA/LIC/ZEC) vía WFS INSPIRE IGN — redes-ecológicas.

    Capa PS.ProtectedSite del servicio INSPIRE de redes ecológicas del IGN.
    _wfs_bbox devuelve None si TODOS los intentos fallan (→ FAILED); una
    respuesta correcta sin geometrías es ausencia confirmada en el AOI (→ EMPTY).
    """
    log.info(f"  WFS IGN INSPIRE → {_WFS_RN2000}")
    gdf = _wfs_bbox(_IGN_WFS_RN2000, _WFS_RN2000, bbox_25830, log, max_features=2_000)
    return _vector_result(gdf, out_path, log, "WFS IGN INSPIRE Red Natura 2000")


def download_igme(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> LayerResult:
    """Litologías IGME MAGNA50 vía ArcGIS REST (layer 11: Litologías color)."""
    xmin, ymin, xmax, ymax = bbox_25830
    log.info("  ArcGIS REST IGME_MAGNA_50 → layer 11 (Litologías color)")
    params = {
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "25830",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "f": "geojson",
        "resultRecordCount": "5000",
        "returnGeometry": "true",
    }
    try:
        resp = requests.get(_IGME_REST, params=params, headers=_HEADERS, timeout=120)
        resp.raise_for_status()
        gdf = gpd.read_file(io.BytesIO(resp.content))
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        if len(gdf) >= int(params["resultRecordCount"]):
            log.warning(
                f"  IGME: respuesta en el límite ({params['resultRecordCount']} "
                f"features): la capa puede estar TRUNCADA para este AOI."
            )
        return _vector_result(gdf, out_path, log, "ArcGIS REST IGME MAGNA50")
    except Exception as exc:
        # El servicio falló: no sabemos si hay litología en el AOI. No escribir
        # un GPKG vacío que finja "sin datos" → FAILED.
        log.warning(f"  ArcGIS REST falló: {exc}")
        return LayerResult(LayerStatus.FAILED, 0, f"ArcGIS REST falló: {exc}")


# ──────────────────────────────────────────────────────────────────────────── #
# Catálogo de fuentes                                                          #
# ──────────────────────────────────────────────────────────────────────────── #
# (etiqueta, nombre_archivo con {s}=sufijo escenario, función descargadora)
SOURCES: list[tuple[str, str, Callable]] = [
    ("DEM Copernicus GLO-30", "DEM_{s}.tif",   download_dem),
    ("OSM",                   "OSM_{s}.gpkg",  download_osm),
    ("Hidrografía IGN",       "HID_{s}.gpkg",  download_hidrografia),
    ("IGME geológico",        "IGME_{s}.gpkg", download_igme),
    ("Zonas inundables",      "INUND_{s}.gpkg",download_zonas_inundables),
    ("Red Natura 2000",       "RN2000_{s}.gpkg",download_rn2000),
    # Catastro: sin descarga automática (no hay servicio bbox fiable).
    # Se coloca a mano en data/raw/Catastro/ y alinear_capas.py lo recorta.
]


# ──────────────────────────────────────────────────────────────────────────── #
# Lógica por escenario                                                         #
# ──────────────────────────────────────────────────────────────────────────── #
def _run_scenario(
    s: str,
    cfg_s: dict,
    overwrite: bool,
    log: logging.Logger,
) -> dict[str, LayerResult]:
    """Descarga todas las fuentes para un escenario.

    Devuelve un dict {nombre_archivo: LayerResult} con el estado por capa, para
    alimentar el manifiesto. Una excepción no controlada de un descargador se
    captura como FAILED (nunca deja el escenario a medias)."""
    xmin, ymin, xmax, ymax = _scenario_aoi(cfg_s)
    bbox = (xmin, ymin, xmax, ymax)
    w, so, e, n = _to_4326(xmin, ymin, xmax, ymax)

    log.info(f"\n{'═' * 62}")
    log.info(f"ESCENARIO {s}")
    log.info(f"{'═' * 62}")
    log.info(f"  AOI EPSG:25830 : {xmin:.0f}, {ymin:.0f} → {xmax:.0f}, {ymax:.0f}")
    log.info(f"  AOI WGS84      : S={so:.5f}  W={w:.5f}  N={n:.5f}  E={e:.5f}")
    log.info(f"  Dimensión      : {(xmax - xmin) / 1000:.1f} km × {(ymax - ymin) / 1000:.1f} km")

    results: dict[str, LayerResult] = {}
    for label, name_tmpl, fn in SOURCES:
        out_name = name_tmpl.replace("{s}", s)
        out_path = DATA_RAW / out_name
        log.info(f"\n[{label}]")

        if out_path.exists() and not overwrite:
            log.info(f"  Ya existe → omitido  (usa -y para sobrescribir)")
            results[out_name] = LayerResult(LayerStatus.SKIPPED, 0, "ya existía")
            continue

        try:
            res = fn(bbox, out_path, log)
            # Salvaguarda: un descargador que aún devuelva bool no debe romper el manifiesto.
            if not isinstance(res, LayerResult):
                res = LayerResult(
                    LayerStatus.OK if res else LayerStatus.FAILED, 0, str(res)
                )
            results[out_name] = res
        except Exception as exc:
            log.error(f"  ✗ {exc}")
            results[out_name] = LayerResult(LayerStatus.FAILED, 0, str(exc))

        time.sleep(0.5)   # cortesía con los servidores públicos

    return results


# ──────────────────────────────────────────────────────────────────────────── #
# Manifiesto de estado                                                         #
# ──────────────────────────────────────────────────────────────────────────── #
def _write_manifest(
    all_results: dict[str, dict[str, LayerResult]],
    log: logging.Logger,
) -> None:
    """Persiste el estado por capa y escenario en un JSON legible.

    El manifiesto es la fuente de verdad aguas abajo: un GPKG que existe pero
    figura como `failed` NO debe usarse como "sin cobertura"; un `empty` sí es
    una ausencia confirmada."""
    payload = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "escenarios": {
            s: {
                name: {
                    "status": r.status.value,
                    "rows": r.rows,
                    "detail": r.detail,
                }
                for name, r in res.items()
            }
            for s, res in all_results.items()
        },
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info(f"  Manifiesto  → {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")


# ──────────────────────────────────────────────────────────────────────────── #
# Punto de entrada                                                             #
# ──────────────────────────────────────────────────────────────────────────── #
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Descarga capas GIS por AOI para cada escenario (A y/o B)."
    )
    p.add_argument(
        "--escenario", default="ambos",
        help="Escenario a descargar: A, B, cualquier otro id definido en "
             "escenario.yaml (p. ej. C), o 'ambos' (=A y B). Por defecto: ambos.",
    )
    p.add_argument(
        "-y", "--yes", action="store_true",
        help="Sobrescribir archivos existentes sin preguntar.",
    )
    p.add_argument(
        "--keep-existing", action="store_true",
        help="Reutilizar archivos ya descargados sin preguntar ni sobrescribir. "
             "Útil para relanzar el pipeline sin repetir descargas.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if _MISSING:
        print(
            f"ERROR: faltan dependencias Python: {', '.join(_MISSING)}\n"
            f"  pip install {' '.join(_MISSING)}"
        )
        sys.exit(1)

    log = _setup_logging()
    log.info("=" * 62)
    log.info(f"DESCARGA DE CAPAS GIS  {datetime.now().isoformat(timespec='seconds')}")
    log.info("=" * 62)

    cfg = _load_yaml(CONFIG_ESCENARIO)
    escenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario.upper()]

    # Preguntar sobre sobreescritura si hay archivos existentes
    if getattr(args, "keep_existing", False):
        overwrite = False  # reutilizar sin preguntar
    elif args.yes:
        overwrite = True
    else:
        overwrite = False
    if not overwrite and not getattr(args, "keep_existing", False):
        existing = [
            DATA_RAW / tmpl.replace("{s}", s)
            for s in escenarios
            for _, tmpl, _ in SOURCES
            if (DATA_RAW / tmpl.replace("{s}", s)).exists()
        ]
        if existing:
            print(f"\n{len(existing)} archivo(s) ya existen en data/raw/.")
            print("¿Sobrescribir? [s/N]: ", end="", flush=True)
            try:
                ans = input().strip().lower() if sys.stdin.isatty() else "s"
            except EOFError:
                ans = "s"
            if ans != "s":
                log.info("Operación cancelada por el usuario.")
                return
            overwrite = True

    all_results: dict[str, dict[str, LayerResult]] = {}
    for s in escenarios:
        key = f"escenario_{s}"
        if key not in cfg:
            log.error(f"'{key}' no encontrado en escenario.yaml")
            continue
        all_results[s] = _run_scenario(s, cfg[key], overwrite, log)

    # Recuento por estado a partir de los resultados por capa
    counts = {st: 0 for st in LayerStatus}
    failed_layers: list[str] = []
    for s, res in all_results.items():
        for name, r in res.items():
            counts[r.status] += 1
            if r.status is LayerStatus.FAILED:
                failed_layers.append(f"{name}: {r.detail}")

    _write_manifest(all_results, log)

    log.info(f"\n{'=' * 62}")
    log.info("RESUMEN")
    log.info(f"{'=' * 62}")
    log.info(f"  OK          : {counts[LayerStatus.OK]}   (con datos)")
    log.info(f"  Sin cobertura: {counts[LayerStatus.EMPTY]}   (AOI vacío, GPKG vacío legítimo)")
    log.info(f"  Fallidas    : {counts[LayerStatus.FAILED]}   (descarga fallida, SIN escribir vacío)")
    log.info(f"  Omitidas    : {counts[LayerStatus.SKIPPED]}   (ya existían)")
    if failed_layers:
        log.warning("  Capas fallidas:")
        for item in failed_layers:
            log.warning(f"    - {item}")
    log.info(f"  Log         → {LOG_PATH.relative_to(PROJECT_ROOT)}")
    log.info(f"  Salida      → {DATA_RAW.relative_to(PROJECT_ROOT)}/")

    # Salir con código ≠ 0 si alguna descarga falló, para que el pipeline/CI no
    # continúe silenciosamente con capas ausentes o desactualizadas.
    if counts[LayerStatus.FAILED]:
        sys.exit(1)


if __name__ == "__main__":
    main()
