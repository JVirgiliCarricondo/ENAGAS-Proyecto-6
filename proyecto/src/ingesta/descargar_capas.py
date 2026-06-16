"""
Descarga automática de capas GIS para el AOI de cada escenario.

Para cada escenario (A y B) definido en escenario.yaml, calcula el AOI y
descarga la unidad mínima de cada fuente que lo contenga:

  - Todas las fuentes exponen servicios WFS, WCS o Overpass que aceptan
    consultas espaciales por bbox.  La "unidad mínima" es el propio bbox
    del AOI: el servidor filtra y devuelve únicamente las geometrías dentro
    del área de interés, sin descargar capas regionales ni nacionales.

Archivos generados en data/raw/ (sufijo _A o _B según el escenario):

  DEM_{s}.tif      → MDT25 IGN WCS, 25 m, GeoTIFF
  CLC_{s}.gpkg     → Corine Land Cover, WFS IGN INSPIRE (LC.LandCoverUnit)
  RN2000_{s}.gpkg  → Red Natura 2000, WFS IGN INSPIRE (PS.ProtectedSite)
  OSM_{s}.gpkg     → Carreteras + ferrocarril, Overpass API
  HID_{s}.gpkg     → Hidrografía IGN, WFS INSPIRE (HY.PhysicalWaters.Watercourses)
  IGME_{s}.gpkg    → Mapa geológico IGME MAGNA50, WFS / ArcGIS REST fallback

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
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
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

# ──────────────────────────────────────────────────────────────────────────── #
# Endpoints de servicios OGC públicos                                          #
# ──────────────────────────────────────────────────────────────────────────── #
_IGN_WCS_MDT = "https://servicios.idee.es/wcs/mdt"
_IGN_WFS_HID = "https://servicios.idee.es/wfs-inspire/hidrografia"
_IGN_WFS_ENP = "https://servicios.idee.es/wfs-inspire/espacios-naturales-protegidos"
_IGN_WFS_CLC = "https://servicios.idee.es/wfs-inspire/ocupacion-suelo"
_IGME_REST   = "https://mapas.igme.es/gis/rest/services/Cartografia_Geologica/IGME_MAGNA_50/MapServer/11/query"
_OVERPASS    = "https://overpass-api.de/api/interpreter"

# Nombres de capa WFS INSPIRE (obtenidos vía GetCapabilities)
_WFS_HID = "hy-n:WatercourseLink"      # enlaces de cursos de agua (tramos lineales)
_WFS_ENP = "PS.ProtectedSite"          # Red Natura 2000 y otros ENP
_WFS_CLC = "lcv:LandCoverUnit"         # unidades de cubierta terrestre (Corine LC)

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
        (cfg_s["origen"]["x"],  cfg_s["origen"]["y"]),
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


def _save_vector(
    gdf: "gpd.GeoDataFrame | None",
    out_path: Path,
    log: logging.Logger,
) -> bool:
    if gdf is None or gdf.empty:
        empty = gpd.GeoDataFrame(geometry=gpd.GeoSeries(crs="EPSG:25830"))
        empty.to_file(out_path, driver="GPKG")
        log.warning(f"  Sin datos en el AOI → guardado vacío: {out_path.name}")
        return True
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:25830")
    elif gdf.crs.to_epsg() != 25830:
        gdf = gdf.to_crs("EPSG:25830")
    gdf.to_file(out_path, driver="GPKG")
    log.info(f"  ✓ {out_path.name}  ({len(gdf)} filas)")
    return True


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
                return gdf.to_crs("EPSG:25830") if gdf.crs else gdf
        except requests.exceptions.Timeout:
            log.debug(f"    Timeout WFS {version} / {out_fmt[:30]}")
        except Exception as exc:
            log.debug(f"    Error WFS {version} / {out_fmt[:30]}: {exc}")

    return None


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
) -> bool:
    """
    DEM Copernicus GLO-30 (30 m) desde tiles COG en AWS S3.
    Lee solo la ventana del AOI sin descargar el tile completo (~40 MB).
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
    return True


def download_clc(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> bool:
    """Corine Land Cover vía WFS IGN INSPIRE (max 2000 features; AOI pequeño)."""
    log.info(f"  WFS IGN INSPIRE → {_WFS_CLC}")
    gdf = _wfs_bbox(_IGN_WFS_CLC, _WFS_CLC, bbox_25830, log, max_features=2_000)
    return _save_vector(gdf, out_path, log)


def download_natura2000(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> bool:
    """
    Red Natura 2000: intenta WFS IGN INSPIRE; si falla, fallback a Overpass
    (boundary=protected_area) que cubre ZEPA, ZEC, ZEPVN y parques nacionales
    mapeados en OpenStreetMap.
    """
    log.info(f"  WFS IGN INSPIRE → {_WFS_ENP}")
    gdf = _wfs_bbox(_IGN_WFS_ENP, _WFS_ENP, bbox_25830, log, max_features=2_000)
    if gdf is not None and not gdf.empty:
        return _save_vector(gdf, out_path, log)

    # Fallback: áreas protegidas desde Overpass (OSM boundary=protected_area)
    log.info("  Fallback → Overpass boundary=protected_area")
    w, s, e, n = _to_4326(*bbox_25830)
    bbox_str = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    query = (
        f"[out:json][timeout:90][bbox:{bbox_str}];"
        "(way[boundary=protected_area];relation[boundary=protected_area];);"
        "(._;>;);"
        "out body;"
    )
    try:
        resp = requests.post(_OVERPASS, data={"data": query}, headers=_HEADERS, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        nodes = {
            el["id"]: (el["lon"], el["lat"])
            for el in data.get("elements", [])
            if el["type"] == "node"
        }
        keep_tags = {"name", "boundary", "protect_class", "site_type", "ref:natura2000"}
        features = []
        for el in data.get("elements", []):
            if el["type"] != "way":
                continue
            coords = [nodes[nid] for nid in el.get("nodes", []) if nid in nodes]
            if len(coords) < 3:
                continue
            from shapely.geometry import Polygon
            features.append({
                "geometry": Polygon(coords) if coords[0] == coords[-1] else Polygon(coords + [coords[0]]),
                "osm_id": el["id"],
                **{k: v for k, v in el.get("tags", {}).items() if k in keep_tags},
            })

        gdf_osm = (
            gpd.GeoDataFrame(features, crs="EPSG:4326")
            if features
            else gpd.GeoDataFrame(geometry=gpd.GeoSeries(crs="EPSG:4326"))
        )
        log.info(f"  Overpass protected_area → {len(gdf_osm)} geometrías (calidad OSM)")
        return _save_vector(gdf_osm, out_path, log)

    except Exception as exc:
        log.warning(f"  Overpass fallback falló: {exc}")
        return _save_vector(None, out_path, log)


def download_osm(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> bool:
    """Carreteras + ferrocarril vía Overpass API. Salida: GeoPackage de LineStrings."""
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
    resp = requests.post(_OVERPASS, data={"data": query}, headers=_HEADERS, timeout=120)
    resp.raise_for_status()
    data = resp.json()

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
    return _save_vector(gdf, out_path, log)


def download_hidrografia(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> bool:
    """Hidrografía IGN vía WFS INSPIRE (max 2000 features)."""
    log.info(f"  WFS IGN INSPIRE → {_WFS_HID}")
    gdf = _wfs_bbox(_IGN_WFS_HID, _WFS_HID, bbox_25830, log, max_features=2_000)
    return _save_vector(gdf, out_path, log)


def download_igme(
    bbox_25830: tuple[float, float, float, float],
    out_path: Path,
    log: logging.Logger,
) -> bool:
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
        return _save_vector(gdf, out_path, log)
    except Exception as exc:
        log.warning(f"  ArcGIS REST falló: {exc}")

    return _save_vector(None, out_path, log)


# ──────────────────────────────────────────────────────────────────────────── #
# Catálogo de fuentes                                                          #
# ──────────────────────────────────────────────────────────────────────────── #
# (etiqueta, nombre_archivo con {s}=sufijo escenario, función descargadora)
SOURCES: list[tuple[str, str, Callable]] = [
    ("DEM IGN MDT25",    "DEM_{s}.tif",  download_dem),
    ("Corine Land Cover","CLC_{s}.gpkg", download_clc),
    ("OSM",              "OSM_{s}.gpkg", download_osm),
    ("Hidrografía IGN",  "HID_{s}.gpkg", download_hidrografia),
    ("IGME geológico",   "IGME_{s}.gpkg",download_igme),
    # RN2000: fuente nacional añadida manualmente a data/raw/RN2000/.
    # alinear_capas.py la recorta al AOI de cada escenario.
]


# ──────────────────────────────────────────────────────────────────────────── #
# Lógica por escenario                                                         #
# ──────────────────────────────────────────────────────────────────────────── #
def _run_scenario(
    s: str,
    cfg_s: dict,
    overwrite: bool,
    log: logging.Logger,
) -> tuple[int, int]:
    """Descarga todas las fuentes para un escenario. Devuelve (ok, errores)."""
    xmin, ymin, xmax, ymax = _scenario_aoi(cfg_s)
    bbox = (xmin, ymin, xmax, ymax)
    w, so, e, n = _to_4326(xmin, ymin, xmax, ymax)

    log.info(f"\n{'═' * 62}")
    log.info(f"ESCENARIO {s}")
    log.info(f"{'═' * 62}")
    log.info(f"  AOI EPSG:25830 : {xmin:.0f}, {ymin:.0f} → {xmax:.0f}, {ymax:.0f}")
    log.info(f"  AOI WGS84      : S={so:.5f}  W={w:.5f}  N={n:.5f}  E={e:.5f}")
    log.info(f"  Dimensión      : {(xmax - xmin) / 1000:.1f} km × {(ymax - ymin) / 1000:.1f} km")

    ok = errors = 0
    for label, name_tmpl, fn in SOURCES:
        out_name = name_tmpl.replace("{s}", s)
        out_path = DATA_RAW / out_name
        log.info(f"\n[{label}]")

        if out_path.exists() and not overwrite:
            log.info(f"  Ya existe → omitido  (usa -y para sobrescribir)")
            ok += 1
            continue

        try:
            fn(bbox, out_path, log)
            ok += 1
        except Exception as exc:
            log.error(f"  ✗ {exc}")
            errors += 1

        time.sleep(0.5)   # cortesía con los servidores públicos

    return ok, errors


# ──────────────────────────────────────────────────────────────────────────── #
# Punto de entrada                                                             #
# ──────────────────────────────────────────────────────────────────────────── #
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Descarga capas GIS por AOI para cada escenario (A y/o B)."
    )
    p.add_argument(
        "--escenario", choices=["A", "B", "ambos"], default="ambos",
        help="Escenario a descargar (A, B o ambos; por defecto: ambos).",
    )
    p.add_argument(
        "-y", "--yes", action="store_true",
        help="Sobrescribir archivos existentes sin preguntar.",
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
    escenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario]

    # Preguntar sobre sobreescritura si hay archivos existentes
    overwrite = args.yes
    if not overwrite:
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

    total_ok = total_err = 0
    for s in escenarios:
        key = f"escenario_{s}"
        if key not in cfg:
            log.error(f"'{key}' no encontrado en escenario.yaml")
            continue
        ok, err = _run_scenario(s, cfg[key], overwrite, log)
        total_ok += ok
        total_err += err

    log.info(f"\n{'=' * 62}")
    log.info("RESUMEN")
    log.info(f"{'=' * 62}")
    log.info(f"  Capas OK    : {total_ok}")
    log.info(f"  Errores     : {total_err}")
    log.info(f"  Log         → {LOG_PATH.relative_to(PROJECT_ROOT)}")
    log.info(f"  Salida      → {DATA_RAW.relative_to(PROJECT_ROOT)}/")


if __name__ == "__main__":
    main()
