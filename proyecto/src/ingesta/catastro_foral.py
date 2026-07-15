"""Descarga automática del catastro FORAL (Navarra y País Vasco) por AOI.

El Catastro nacional (Dirección General del Catastro / Sede Electrónica) NO cubre
Navarra ni País Vasco: ambos tienen **catastro foral** con competencia e IDE
propias, por lo que sus parcelas no están en los servicios del Catastro común.
Cada territorio foral publica sus parcelas por bbox mediante un servicio abierto
(sin cl@ve). Recetas verificadas en vivo (13-jul-2026):

  * Navarra  → IDENA/SITNA, WFS 2.0.0, GeoJSON, bbox EPSG:25830 (eje X primero).
               Capas urbana + rústica + mixta. La respuesta ya viene en 25830.
  * Gipuzkoa → Diputación Foral (b5m), WFS 2.0.0 INSPIRE (cp:CadastralParcel),
               GML; bbox EPSG:25830. La geometría vuelve en EPSG:4258 → se
               reproyecta a 25830.
  * Álava    → Diputación Foral de Araba (geo.araba.eus). Su WFS es ArcGIS y
               **ignora el filtro BBOX por KVP** (bug conocido de ArcGIS
               WFSServer), así que se usa su REST /query con esriGeometryEnvelope
               (mismo patrón que download_igme). Capas: 19 (urbanas), 23 (rústicas).
  * Bizkaia  → Diputación Foral, INSPIRE sobre ArcGIS Server (host
               geo.bizkaia.eus, ruta 'arcgisserverinspire'), REST /query igual que
               Álava. Layer 8 = "Cadastral Parcel". (Nota: el host arcgis.bizkaia.eus
               que figura en algunas guías está filtrado/no resuelve; el operativo
               es geo.bizkaia.eus.)

Para cada territorio cuyo extent provincial intersecta el AOI se descargan las
parcelas y se escriben como

    data/raw/Catastro/foral_<territorio>_<escenario>/PARCELA.shp

con columnas [refcat, geometry] en EPSG:25830. alinear_capas.py descubre esos
PARCELA.shp con su glob habitual y los fusiona con el Catastro nacional sin
cambios (mismo formato shapefile de parcelas).

Es **best-effort**: un fallo se registra pero NO bloquea el pipeline (el Catastro
es una capa que la alineación trata como opcional). Si el AOI no toca Navarra ni
País Vasco (p. ej. los escenarios A/B en Aragón) no se hace ninguna petición.

Uso por línea de comandos (para probar un bbox suelto):
    python -m ingesta.catastro_foral <xmin> <ymin> <xmax> <ymax> [escenario]
"""
from __future__ import annotations

import io
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

try:
    import geopandas as gpd
except ImportError:  # pragma: no cover - geopandas es dependencia del pipeline
    gpd = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # proyecto/
DATA_RAW = PROJECT_ROOT / "data" / "raw"

# Connection: close evita el ConnectionResetError(10054) de keepalive en Windows.
_HEADERS = {
    "User-Agent": "ENAGAS-Proyecto6/1.0 (academic; ETSI-ICAI Comillas)",
    "Connection": "close",
    "Accept": "*/*",
}

# Límite de features por petición WFS y tope de páginas REST (salvaguardas de
# truncado). El AOI es el buffer de ~1 km de un corredor ≤15 km: rara vez supera
# unos pocos miles de parcelas, pero avisamos si se toca el límite.
_WFS_COUNT = 50_000
_REST_PAGE = 1_000
_REST_MAX_PAGES = 40


# ──────────────────────────────────────────────────────────────────────────── #
# Catálogo de servicios forales                                                #
# ──────────────────────────────────────────────────────────────────────────── #
@dataclass(frozen=True)
class ForalService:
    """Describe el servicio de catastro de un territorio foral.

    Reúne todo lo necesario para decidir si hay que consultar el territorio (por
    su extent) y cómo descargar sus parcelas (protocolo, endpoint, capas y campo
    de referencia catastral).

    Attributes:
        key: Id corto del territorio (navarra, araba, …), usado en nombres de salida.
        label: Etiqueta legible para los logs.
        bounds_25830: Extent provincial (xmin, ymin, xmax, ymax) en EPSG:25830, solo
            para el dispatch (decidir a qué servicios se pregunta).
        kind: Protocolo del servicio: "wfs_json", "wfs_gml" o "arcgis_rest".
        endpoint: URL base del servicio.
        layers: typenames WFS o ids de capa REST (o "auto" para autodescubrir).
        ref_field: Nombre del campo que contiene la referencia catastral; se renombra
            a 'refcat' en la salida (None si el servicio no lo expone).
        layer_tipos: TIPO catastral ('U' urbana / 'R' rústica / None desconocido) de
            cada capa de `layers`, en el mismo orden. Los servicios que separan
            urbana y rústica en capas distintas (Navarra, Álava) permiten etiquetar
            el TIPO; los que exponen una única capa INSPIRE (Gipuzkoa, Bizkaia) lo
            dejan a None → la expropiación les aplica el coste por defecto. Vacío =
            todas las capas sin tipo.
    """
    key: str                                   # id corto: navarra, araba, …
    label: str                                 # etiqueta para logs
    bounds_25830: tuple[float, float, float, float]  # extent provincial (dispatch)
    kind: str                                  # wfs_json | wfs_gml | arcgis_rest
    endpoint: str
    layers: tuple[str, ...]                     # typenames WFS o ids/"auto" REST
    ref_field: str | None                       # campo → 'refcat' (o None)
    layer_tipos: tuple[str | None, ...] = ()    # TIPO por capa ('U'/'R'/None)


# Extents provinciales aproximados en EPSG:25830 (generosos y solapados: solo
# sirven para decidir a qué servicios se pregunta; el filtro real es el bbox del
# AOI en cada servicio, que devuelve 0 parcelas si el AOI cae fuera del territorio).
FORAL_SERVICES: tuple[ForalService, ...] = (
    ForalService(
        key="navarra",
        label="Navarra (IDENA/SITNA)",
        bounds_25830=(555_000, 4_625_000, 690_000, 4_800_000),
        kind="wfs_json",
        endpoint="https://idena.navarra.es/ogc/wfs",
        layers=(
            "IDENA:CATAST_Pol_ParcelaUrba",
            "IDENA:CATAST_Pol_ParcelaRusti",
            "IDENA:CATAST_Pol_ParcelaMixta",
        ),
        ref_field="IDCATASTRO",
        layer_tipos=("U", "R", None),   # urbana / rústica / mixta (sin tipo)
    ),
    ForalService(
        key="gipuzkoa",
        label="Gipuzkoa (Diputación Foral)",
        bounds_25830=(530_000, 4_740_000, 610_000, 4_810_000),
        kind="wfs_gml",
        endpoint="https://b5m.gipuzkoa.eus/inspire/wfs/gipuzkoa_wfs_cp",
        layers=("cp:CadastralParcel",),
        ref_field="localId",
    ),
    ForalService(
        key="araba",
        label="Álava (Diputación Foral de Araba)",
        bounds_25830=(470_000, 4_690_000, 580_000, 4_778_000),
        kind="arcgis_rest",
        endpoint="https://geo.araba.eus/geoaraba/rest/services/OGC_ARABA/WFS_Katastroa/MapServer",
        layers=("19", "23"),   # 19 = parcelas urbanas, 23 = parcelas rústicas
        ref_field="REF_CATASTRAL",
        layer_tipos=("U", "R"),   # 19 urbanas / 23 rústicas
    ),
    ForalService(
        key="bizkaia",
        label="Bizkaia (Diputación Foral)",
        bounds_25830=(460_000, 4_758_000, 548_000, 4_826_000),
        kind="arcgis_rest",
        # INSPIRE Annex I sobre ArcGIS Server (host geo.bizkaia.eus, ruta
        # 'arcgisserverinspire'). Layer 8 = "Cadastral Parcel" (la 7 es
        # "Cadastral Zoning", que NO son parcelas).
        endpoint="https://geo.bizkaia.eus/arcgisserverinspire/rest/services/Catastro/Annex1/MapServer",
        layers=("8",),
        ref_field="nationalCadastralRef",
    ),
)


# ──────────────────────────────────────────────────────────────────────────── #
# Resultado por territorio                                                     #
# ──────────────────────────────────────────────────────────────────────────── #
@dataclass
class ForalResult:
    """Resultado de descargar el catastro de un territorio foral.

    Attributes:
        key: Id corto del territorio (navarra, araba, …).
        label: Etiqueta legible del territorio.
        status: Estado de la descarga: "ok" | "empty" | "failed" | "skipped".
        rows: Nº de parcelas escritas (0 si vacío o fallido).
        detail: Texto libre con el motivo (fallo, "ya existía", …).
        salida: Ruta del PARCELA.shp escrito, o None si no se escribió nada.
    """
    key: str
    label: str
    status: str          # ok | empty | failed | skipped
    rows: int = 0
    detail: str = ""
    salida: Path | None = None


# ──────────────────────────────────────────────────────────────────────────── #
# Utilidades de dispatch                                                        #
# ──────────────────────────────────────────────────────────────────────────── #
def _rel(p: Path) -> str:
    """Ruta relativa al proyecto para logs; cae a la absoluta si está fuera."""
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def _intersecta(aoi: tuple[float, float, float, float],
                bounds: tuple[float, float, float, float]) -> bool:
    """Indica si dos rectángulos (bbox) en el mismo CRS se solapan.

    Test de solape estándar de rectángulos alineados a ejes: no se tocan si uno
    queda completamente a un lado del otro en X o en Y.

    Args:
        aoi: bbox del AOI (xmin, ymin, xmax, ymax) en EPSG:25830.
        bounds: bbox del extent provincial en EPSG:25830.

    Returns:
        True si ambos rectángulos se solapan.
    """
    axmin, aymin, axmax, aymax = aoi
    bxmin, bymin, bxmax, bymax = bounds
    return not (axmax < bxmin or axmin > bxmax or aymax < bymin or aymin > bymax)


def servicios_para_aoi(aoi_25830: tuple[float, float, float, float]
                       ) -> list[ForalService]:
    """Devuelve los servicios forales cuyo extent provincial intersecta el AOI.

    Args:
        aoi_25830: AOI como (xmin, ymin, xmax, ymax) en EPSG:25830.

    Returns:
        Lista de ForalService a consultar (vacía si el AOI no toca ningún
        territorio foral).
    """
    return [s for s in FORAL_SERVICES if _intersecta(aoi_25830, s.bounds_25830)]


# ──────────────────────────────────────────────────────────────────────────── #
# Descargadores por tipo de servicio                                            #
# ──────────────────────────────────────────────────────────────────────────── #
def _fetch_wfs(endpoint: str, typename: str,
               bbox_25830: tuple[float, float, float, float],
               as_json: bool, log: logging.Logger) -> "gpd.GeoDataFrame | None":
    """Descarga una capa WFS 2.0.0 por bbox y la devuelve como GeoDataFrame.

    Detecta las respuestas de error OGC (ExceptionReport / ServiceException, que
    llegan con HTTP 200) y avisa si la respuesta toca el tope de features
    (posible truncado). No reproyecta: la normalización posterior lo hace.

    Args:
        endpoint: URL base del servicio WFS.
        typename: Nombre de la capa (typename) a pedir.
        bbox_25830: AOI como (xmin, ymin, xmax, ymax) en EPSG:25830.
        as_json: Si True pide GeoJSON (OUTPUTFORMAT); si False, el GML por defecto.
        log: Logger para el detalle de errores.

    Returns:
        GeoDataFrame con las parcelas, o None si la petición o el parseo fallan.
    """
    xmin, ymin, xmax, ymax = bbox_25830
    # Eje X primero + etiqueta 'EPSG:25830' (validado para IDENA y b5m). Enteros
    # para no chocar con proxies quisquillosos.
    bbox_str = f"{int(xmin)},{int(ymin)},{int(xmax)},{int(ymax)},EPSG:25830"
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": typename,
        "BBOX": bbox_str,
        "COUNT": str(_WFS_COUNT),
    }
    if as_json:
        params["OUTPUTFORMAT"] = "application/json"
    try:
        resp = requests.get(endpoint, params=params, headers=_HEADERS, timeout=120)
        resp.raise_for_status()
    except Exception as exc:
        log.debug(f"    WFS {typename}: petición fallida: {exc}")
        return None
    if b"ExceptionReport" in resp.content[:1500] or \
            b"ServiceException" in resp.content[:1500]:
        log.debug(f"    WFS {typename}: ExceptionReport")
        return None
    try:
        gdf = gpd.read_file(io.BytesIO(resp.content))
    except Exception as exc:
        log.debug(f"    WFS {typename}: parseo fallido: {exc}")
        return None
    if len(gdf) >= _WFS_COUNT:
        log.warning(f"    WFS {typename}: respuesta en el límite "
                    f"({_WFS_COUNT}): parcelas posiblemente TRUNCADAS en el AOI.")
    return gdf


def _resolver_layer_arcgis(base: str, log: logging.Logger) -> str | None:
    """Autodescubre el id de la capa de parcelas de un MapServer ArcGIS.

    Lee el índice de capas del MapServer (?f=json) y busca por nombre la que sean
    parcelas, priorizando "parcel/parcela/partzel" sobre "cadastr/catastr" y
    descartando capas que también contienen esas palabras pero NO son parcelas
    (zonificación, límites, subparcelas…).

    Args:
        base: URL base del MapServer ArcGIS.
        log: Logger para el detalle de errores.

    Returns:
        Id de la capa de parcelas (como cadena), o None si no se pudo resolver.
    """
    try:
        meta = requests.get(f"{base}", params={"f": "json"},
                            headers=_HEADERS, timeout=60).json()
    except Exception as exc:
        log.debug(f"    ArcGIS {base}: no se pudo leer el índice de capas: {exc}")
        return None
    capas = meta.get("layers", [])
    # Preferir "parcela" y descartar zonificación/límites/subparcela, que también
    # contienen "cadastr"/"parcel" en el nombre pero no son parcelas.
    excluir = ("zoning", "zonif", "boundary", "límite", "limite", "subpar",
               "basprop", "componen")
    for prioridad in (("parcel", "parcela", "partzel"), ("cadastr", "catastr")):
        for capa in capas:
            nombre = str(capa.get("name", "")).lower()
            if any(x in nombre for x in excluir):
                continue
            if any(t in nombre for t in prioridad):
                return str(capa.get("id"))
    return None


def _fetch_arcgis(base: str, layer_id: str,
                  bbox_25830: tuple[float, float, float, float],
                  log: logging.Logger) -> "gpd.GeoDataFrame | None":
    """Descarga una capa de un MapServer ArcGIS por envelope, paginando resultados.

    El WFS de ArcGIS ignora el filtro BBOX por KVP (bug conocido), así que se usa
    su REST /query con `esriGeometryEnvelope`. ArcGIS limita el nº de registros por
    respuesta, de modo que se pagina con resultOffset/resultRecordCount hasta que
    una página venga incompleta (fin de datos) o se alcance el tope de páginas.

    Args:
        base: URL base del MapServer ArcGIS.
        layer_id: Id de la capa, o "auto" para autodescubrirla.
        bbox_25830: AOI como (xmin, ymin, xmax, ymax) en EPSG:25830.
        log: Logger para el detalle de errores y avisos.

    Returns:
        GeoDataFrame con las parcelas (posiblemente vacío) si el servicio responde,
        o None si la primera petición falla.
    """
    if layer_id == "auto":
        layer_id = _resolver_layer_arcgis(base, log) or ""
        if not layer_id:
            log.debug(f"    ArcGIS {base}: no se localizó capa de parcelas")
            return None
    xmin, ymin, xmax, ymax = bbox_25830
    frames: list["gpd.GeoDataFrame"] = []
    offset = 0
    for pagina in range(_REST_MAX_PAGES):
        params = {
            "geometry": f"{xmin},{ymin},{xmax},{ymax}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "25830",
            "outSR": "25830",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "f": "geojson",
            "returnGeometry": "true",
            "resultRecordCount": str(_REST_PAGE),
            "resultOffset": str(offset),
        }
        try:
            resp = requests.get(f"{base}/{layer_id}/query", params=params,
                                headers=_HEADERS, timeout=120)
            resp.raise_for_status()
            part = gpd.read_file(io.BytesIO(resp.content))
        except Exception as exc:
            if pagina == 0:
                log.debug(f"    ArcGIS {base}/{layer_id}: petición fallida: {exc}")
                return None
            log.debug(f"    ArcGIS {base}/{layer_id}: página {pagina} fallida: {exc}")
            break
        if part.empty:
            break
        frames.append(part)
        # Página incompleta = ya no quedan más registros → fin de la paginación.
        if len(part) < _REST_PAGE:
            break
        offset += _REST_PAGE
        if pagina == _REST_MAX_PAGES - 1:
            log.warning(f"    ArcGIS {base}/{layer_id}: alcanzado el tope de "
                        f"{_REST_MAX_PAGES} páginas: parcelas posiblemente "
                        f"TRUNCADAS en el AOI.")
    if not frames:
        return gpd.GeoDataFrame(geometry=gpd.GeoSeries(crs="EPSG:25830"))
    return gpd.GeoDataFrame(
        gpd.pd.concat(frames, ignore_index=True), crs=frames[0].crs)


def _descargar_servicio(svc: ForalService,
                        bbox_25830: tuple[float, float, float, float],
                        log: logging.Logger) -> "gpd.GeoDataFrame | None":
    """Descarga y fusiona todas las capas de parcelas de un territorio foral.

    Recorre las capas del servicio (urbana, rústica, mixta…), descarga cada una
    con el descargador que corresponda a su `kind` y las une en un solo
    GeoDataFrame normalizado a [refcat, geometry] en EPSG:25830.

    Distingue "todo falló" de "respondió sin parcelas": basta con que UNA capa
    responda (aunque venga vacía) para no considerarlo un fallo del servicio.

    Args:
        svc: Servicio foral a descargar.
        bbox_25830: AOI como (xmin, ymin, xmax, ymax) en EPSG:25830.
        log: Logger para el detalle.

    Returns:
        GeoDataFrame [refcat, geometry] en EPSG:25830 (vacío si el AOI no tiene
        parcelas), o None si NINGUNA capa respondió (fallo real del servicio).
    """
    partes: list["gpd.GeoDataFrame"] = []
    algun_ok = False
    # TIPO por capa (urbana/rústica/None), en el mismo orden que svc.layers; si el
    # servicio no lo declara, todas las capas van sin tipo.
    tipos = svc.layer_tipos or (None,) * len(svc.layers)
    for capa, tipo in zip(svc.layers, tipos):
        if svc.kind == "arcgis_rest":
            gdf = _fetch_arcgis(svc.endpoint, capa, bbox_25830, log)
        else:
            gdf = _fetch_wfs(svc.endpoint, capa, bbox_25830,
                             as_json=(svc.kind == "wfs_json"), log=log)
        if gdf is None:
            continue                     # esta capa falló; probamos las demás
        algun_ok = True
        if not gdf.empty:
            partes.append(_normalizar(gdf, svc.ref_field, tipo))
    if not algun_ok:
        return None                      # ninguna capa respondió → fallo real
    if not partes:
        return gpd.GeoDataFrame(columns=["refcat", "TIPO", "geometry"],
                                geometry="geometry", crs="EPSG:25830")
    fusion = gpd.GeoDataFrame(gpd.pd.concat(partes, ignore_index=True),
                              crs="EPSG:25830")
    return fusion


def _normalizar(gdf: "gpd.GeoDataFrame", ref_field: str | None,
                tipo: str | None = None) -> "gpd.GeoDataFrame":
    """Normaliza una capa de parcelas a [refcat, TIPO, geometry] en EPSG:25830.

    Reproyecta al CRS común, renombra el campo de referencia catastral a 'refcat'
    (o lo deja a None si el servicio no lo expone), etiqueta el TIPO catastral de
    la capa ('U'/'R'/None) para que la superficie de expropiación lo pondere igual
    que el catastro nacional, y descarta geometrías que no sean polígonos
    (puntos/líneas de rótulos o auxiliares) para quedarse solo con parcelas.

    Args:
        gdf: Capa cruda tal cual la devolvió el servicio.
        ref_field: Nombre del campo con la referencia catastral (o None).
        tipo: TIPO catastral de esta capa ('U' urbana, 'R' rústica) o None si el
            servicio no distingue (una sola capa INSPIRE).

    Returns:
        GeoDataFrame con columnas [refcat, TIPO, geometry] en EPSG:25830, solo
        polígonos.
    """
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:25830")
    elif gdf.crs.to_epsg() != 25830:
        gdf = gdf.to_crs("EPSG:25830")
    if ref_field and ref_field in gdf.columns:
        refcat = gdf[ref_field].astype("string")
    else:
        refcat = gpd.pd.Series([None] * len(gdf), dtype="string")
    out = gpd.GeoDataFrame({"refcat": refcat.values, "TIPO": tipo},
                           geometry=gdf.geometry.values, crs="EPSG:25830")
    out = out[out.geometry.geom_type.isin(("Polygon", "MultiPolygon"))]
    return out




# ──────────────────────────────────────────────────────────────────────────── #
# Punto de entrada de alto nivel                                                #
# ──────────────────────────────────────────────────────────────────────────── #
def descargar_catastro_foral(
    bbox_25830: tuple[float, float, float, float],
    scenario: str,
    log: logging.Logger,
    overwrite: bool = False,
    data_raw: Path = DATA_RAW,
) -> list[ForalResult]:
    """Descarga el catastro foral que intersecte el AOI y lo deja como PARCELA.shp.

    Es el punto de entrada que llama descargar_capas.py. Para cada territorio foral
    cuyo extent intersecta el AOI, descarga sus parcelas y las escribe en
    data/raw/Catastro/foral_<territorio>_<escenario>/PARCELA.shp, donde
    alinear_capas.py las descubre y fusiona con el catastro nacional.

    Best-effort: no lanza; captura los errores por territorio y los refleja en el
    estado del ForalResult correspondiente, de modo que un fallo del catastro foral
    nunca bloquea el resto del pipeline.

    Args:
        bbox_25830: AOI como (xmin, ymin, xmax, ymax) en EPSG:25830.
        scenario: Sufijo del escenario (A, B, …) para el nombre de la carpeta.
        log: Logger.
        overwrite: Si False, omite los territorios ya descargados (SKIPPED).
        data_raw: Raíz de data/raw/ donde escribir (por defecto, la del proyecto).

    Returns:
        Un ForalResult por territorio consultado (lista vacía si el AOI no toca
        Navarra ni País Vasco).
    """
    if gpd is None:
        log.warning("  Catastro foral: geopandas no disponible → omitido")
        return []

    servicios = servicios_para_aoi(bbox_25830)
    if not servicios:
        log.debug("  Catastro foral: el AOI no intersecta Navarra ni País Vasco "
                  "→ omitido (lo cubre el Catastro nacional)")
        return []

    resultados: list[ForalResult] = []
    for svc in servicios:
        dest = data_raw / "Catastro" / f"foral_{svc.key}_{scenario}"
        shp = dest / "PARCELA.shp"
        if shp.exists() and not overwrite:
            log.info(f"  [{svc.label}] ya descargado → omitido ({_rel(shp)})")
            resultados.append(ForalResult(svc.key, svc.label, "skipped",
                                          detail="ya existía", salida=shp))
            continue
        log.info(f"  [{svc.label}] descargando parcelas del AOI…")
        try:
            gdf = _descargar_servicio(svc, bbox_25830, log)
        except Exception as exc:   # best-effort: nada de lo foral bloquea
            log.warning(f"  [{svc.label}] descarga foral fallida "
                        f"(best-effort, no bloquea): {exc}")
            resultados.append(ForalResult(svc.key, svc.label, "failed",
                                          detail=str(exc)))
            continue

        if gdf is None:
            log.warning(f"  [{svc.label}] el servicio no respondió → sin datos "
                        f"(best-effort, no bloquea)")
            resultados.append(ForalResult(svc.key, svc.label, "failed",
                                          detail="servicio sin respuesta"))
            continue
        if gdf.empty:
            log.info(f"  [{svc.label}] sin parcelas en el AOI")
            resultados.append(ForalResult(svc.key, svc.label, "empty"))
            continue

        try:
            dest.mkdir(parents=True, exist_ok=True)
            gdf.to_file(shp, driver="ESRI Shapefile")
        except Exception as exc:
            log.warning(f"  [{svc.label}] no se pudo escribir el shapefile: {exc}")
            resultados.append(ForalResult(svc.key, svc.label, "failed",
                                          detail=f"escritura: {exc}"))
            continue
        log.info(f"  [{svc.label}] ✓ {len(gdf)} parcelas → {_rel(shp)}")
        resultados.append(ForalResult(svc.key, svc.label, "ok", rows=len(gdf),
                                      salida=shp))
    return resultados


def _main() -> None:
    """CLI de prueba: descarga el catastro foral de un bbox suelto pasado por argv.

    Uso: python -m ingesta.catastro_foral <xmin> <ymin> <xmax> <ymax> [escenario]
    Imprime una línea de resumen por territorio consultado. Pensado para probar un
    AOI concreto sin lanzar todo el pipeline de descarga.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("catastro_foral")
    if len(sys.argv) not in (5, 6):
        print("Uso: python -m ingesta.catastro_foral <xmin> <ymin> <xmax> <ymax> "
              "[escenario]")
        raise SystemExit(2)
    bbox = tuple(float(v) for v in sys.argv[1:5])  # type: ignore[assignment]
    escenario = sys.argv[5] if len(sys.argv) == 6 else "TEST"
    res = descargar_catastro_foral(bbox, escenario, log, overwrite=True)  # type: ignore[arg-type]
    if not res:
        print("El AOI no intersecta ningún territorio foral.")
    for r in res:
        print(f"  {r.key:9} {r.status:8} filas={r.rows} {r.detail}")


if __name__ == "__main__":
    _main()
