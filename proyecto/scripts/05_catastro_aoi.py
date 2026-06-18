"""
Script 05 - Ingesta del Catastro (todas las capas) al AOI.

Toma las descargas del Catastro Inmobiliario (formato SHP por municipio) y
procesa TODAS sus capas espaciales (parcelas, edificaciones, subparcelas,
masas, ejes, elementos lineales/puntuales/textuales, limites, hojas, mapa) y,
en rustica, el cultivo de las subparcelas. Cada capa se reproyecta al CRS de
trabajo (EPSG:25830) y se recorta al MISMO AOI que el resto de capas de
data/processed/Recorte_AOI.

El AOI se construye igual que en src/ingesta/alinear_capas.py: un rectangulo
ORIENTADO con la linea origen->destino (buffer perpendicular de 1 km a cada
lado, tapas planas). El origen, el destino y el CRS se leen de
data/config/escenario.yaml. Si el yaml define un bbox 'aoi:' explicito
(formato antiguo), se respeta ese rectangulo axis-aligned.

Las carpetas de origen vienen organizadas por Ramal, que mapean a los
escenarios del proyecto:

  - Ramal A -> escenario A (Teruel / Alcaniz, provincia 44)
  - Ramal B -> escenario B (Zaragoza, provincia 50)

Los tipos catastrales venian CRUZADOS en el nombre de carpeta, asi que se
etiquetan por su tipo REAL (deducido del codigo de descarga del Catastro):

  - carpeta 'catastro_rural'        -> ficheros 'UA' = Urbana  -> salida 'urbano'
  - carpeta 'catastro_urbanistico'  -> ficheros 'RA' = Rustica -> salida 'rural'

Salida: un GeoPackage MULTICAPA por tipo y escenario en
data/processed/Recorte_AOI/:

  catastro_urbano_aoi_A.gpkg, catastro_urbano_aoi_B.gpkg
  catastro_rural_aoi_A.gpkg,  catastro_rural_aoi_B.gpkg

Cada GeoPackage contiene una capa por cada capa catastral con geometrias
dentro del AOI (parcela, constru, masa, subparce, ejes, elemlin, elempun,
elemtex, altipun, limites, hojas, mapa).

Tablas sin geometria del Catastro (solo DBF), tratadas asi:
  - RUSUBPARCELA (subparcela rustica) y RUCULTIVO (cultivos) NO tienen
    geometria propia, pero su informacion de cultivo se UNE a la geometria de
    SUBPARCE por (REFCAT + letra de subparcela) y por codigo de cultivo (CC),
    quedando como atributos espaciales recortados al AOI (columnas
    'subp_tiposubp', 'cultivo_cc', 'cultivo_nombre', 'cultivo_regadio',
    'subp_superficie'). El cruce de claves se valido en ~99% de subparcelas.
  - CARVIA (nombres de via) se incluye como tabla aspacial integra del ramal
    (no se puede recortar al AOI por no tener geometria), solo cuando el
    GeoPackage tiene alguna capa espacial dentro del AOI.

Uso:
  python scripts/05_catastro_aoi.py            # procesa todo lo que encuentre
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import LineString, box


# --------------------------------------------------------------------------- #
# Rutas y configuracion                                                        #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]            # proyecto/
CONFIG_ESCENARIO = PROJECT_ROOT / "data" / "config" / "escenario.yaml"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "Recorte_AOI"

# Semiancho perpendicular del corredor (mismo valor que alinear_capas.py).
PERP_BUFFER_M = 1000.0

# Carpetas de descarga del Catastro (fuera del repo, en OneDrive). Cada carpeta
# trae los dos ramales dentro. 'tipo' es el tipo REAL del dato, no el nombre de
# la carpeta (que venia cruzado).
ENAGAS_DIR = Path(
    r"C:\Users\monic\OneDrive - Universidad Pontificia Comillas\ENAGAS"
)
SOURCES = [
    {"dir": ENAGAS_DIR / "catastro_rural",        "tipo": "urbano", "codigo": "UA"},
    {"dir": ENAGAS_DIR / "catastro_urbanistico",  "tipo": "rural",  "codigo": "RA"},
]

# Tokens de las capas catastrales que llegan como ZIP por capa y municipio.
# Se excluye 'SHP' (ZIP contenedor provincial, ya descomprimido en carpetas).
LAYER_TOKENS = [
    "PARCELA", "CONSTRU", "SUBPARCE", "MASA", "EJES", "ELEMLIN", "ELEMPUN",
    "ELEMTEX", "ALTIPUN", "LIMITES", "HOJAS", "MAPA", "CARVIA",
    "RUCULTIVO", "RUSUBPARCELA",
]
_TOKEN_RE = re.compile(r"_(" + "|".join(LAYER_TOKENS) + r")$")

# Orden de presentacion preferido de las capas en el GeoPackage de salida.
LAYER_ORDER = [
    "PARCELA", "SUBPARCE", "RUSUBPARCELA", "RUCULTIVO", "MASA", "CONSTRU",
    "EJES", "ELEMLIN", "LIMITES", "ELEMTEX", "ELEMPUN", "ALTIPUN",
    "HOJAS", "MAPA",
]

DEFAULT_CRS = "EPSG:25830"


# --------------------------------------------------------------------------- #
# Lectura del AOI desde escenario.yaml (sin dependencia de PyYAML)            #
# --------------------------------------------------------------------------- #
def _bloque_escenario(escenario: str) -> str:
    texto = CONFIG_ESCENARIO.read_text(encoding="utf-8")
    m = re.search(rf"escenario_{escenario}:(.*?)(?=\nescenario_|\Z)", texto, flags=re.DOTALL)
    if not m:
        raise ValueError(f"No se encontro 'escenario_{escenario}' en {CONFIG_ESCENARIO}")
    return m.group(1)


def _xy(subbloque: str) -> tuple[float, float]:
    x = re.search(r"x:\s*([-\d.]+)", subbloque)
    y = re.search(r"y:\s*([-\d.]+)", subbloque)
    if not (x and y):
        raise ValueError("No se pudieron leer las coordenadas x/y del punto")
    return float(x.group(1)), float(y.group(1))


def load_aoi(escenario: str):
    """Devuelve el poligono del AOI del escenario ('A' o 'B').

    Construye el mismo rectangulo orientado que alinear_capas.py: la linea
    origen->destino con un buffer perpendicular de 1 km y tapas planas. Si el
    yaml trae un bloque 'aoi:' con bbox explicito (formato antiguo), devuelve
    ese rectangulo axis-aligned.
    """
    bloque = _bloque_escenario(escenario)

    # Compatibilidad: bbox explicito 'aoi:' (formato antiguo de escenario.yaml).
    aoi_match = re.search(r"aoi:(.*?)(?:\n\s*origen:|\Z)", bloque, flags=re.DOTALL)
    if aoi_match:
        sub = aoi_match.group(1)
        try:
            vals = {k: float(re.search(rf"{k}:\s*([-\d.]+)", sub).group(1))
                    for k in ("xmin", "ymin", "xmax", "ymax")}
            if all(vals.values()):
                return box(vals["xmin"], vals["ymin"], vals["xmax"], vals["ymax"])
        except (AttributeError, ValueError):
            pass

    # Formato actual: rectangulo orientado con la linea origen->destino.
    origen_sub = re.search(r"origen:(.*?)(?:\n\s*destino:|\Z)", bloque, flags=re.DOTALL)
    destino_sub = re.search(r"destino:(.*)", bloque, flags=re.DOTALL)
    if not (origen_sub and destino_sub):
        raise ValueError(f"Faltan origen/destino en el escenario {escenario}")
    ox, oy = _xy(origen_sub.group(1))
    dx, dy = _xy(destino_sub.group(1))
    return LineString([(ox, oy), (dx, dy)]).buffer(PERP_BUFFER_M, cap_style=2)


def load_crs() -> str:
    """CRS de trabajo declarado en escenario.yaml (por defecto EPSG:25830)."""
    texto = CONFIG_ESCENARIO.read_text(encoding="utf-8")
    m = re.search(r'crs_trabajo:\s*"?([A-Za-z:0-9]+)"?', texto)
    return m.group(1) if m else DEFAULT_CRS


# --------------------------------------------------------------------------- #
# Descubrimiento y extraccion de capas del Catastro                            #
# --------------------------------------------------------------------------- #
def ramal_de_ruta(p: Path) -> str | None:
    """Detecta el ramal ('A' o 'B') a partir del nombre de la carpeta PETICION."""
    m = re.search(r"\(Ramal([AB])\)", str(p))
    return m.group(1) if m else None


def _clave_municipio(shp: Path) -> str:
    """Clave de municipio a partir de la carpeta '50074uA 50533 CASPE'."""
    for parent in shp.parents:
        if re.match(r"^\d{5}[ru]A\s+\d+\s+", parent.name, flags=re.IGNORECASE):
            return parent.name
    return shp.parent.name


def _nombre_municipio(shp: Path) -> str:
    """Nombre legible del municipio (ultimo campo de '50074uA 50533 CASPE')."""
    for parent in shp.parents:
        if re.match(r"^\d{5}[ru]A\s+\d+\s+", parent.name, flags=re.IGNORECASE):
            return parent.name.split(" ", 2)[-1].strip()
    return shp.parent.name


def _zip_ya_extraido(destino: Path) -> bool:
    """True si la carpeta destino ya contiene algun fichero de datos extraido."""
    if not destino.exists():
        return False
    return any(
        p.is_file() and p.suffix.lower() not in {".zip", ".gz", ".tar"}
        for p in destino.rglob("*")
    )


def extraer_capas_del_ramal(source_dir: Path, escenario: str) -> None:
    """Descomprime los ZIP por capa del ramal que aun no esten extraidos."""
    vistos: set[Path] = set()
    for zip_capa in sorted(source_dir.rglob("*.[Zz][Ii][Pp]")):
        if zip_capa in vistos:
            continue
        vistos.add(zip_capa)
        if not _TOKEN_RE.search(zip_capa.stem.upper()):
            continue  # no es un ZIP de capa (p. ej. contenedor provincial _SHP)
        if ramal_de_ruta(zip_capa) != escenario:
            continue
        destino = zip_capa.parent / zip_capa.stem
        if _zip_ya_extraido(destino):
            continue
        destino.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_capa) as zf:
                zf.extractall(destino)
        except (zipfile.BadZipFile, OSError) as exc:
            print(f"    [WARN] No se pudo extraer {zip_capa.name}: {exc}")


def descubrir_capas(source_dir: Path, escenario: str) -> dict[str, list[Path]]:
    """Agrupa todos los .shp del ramal por nombre de capa, uno por municipio."""
    extraer_capas_del_ramal(source_dir, escenario)

    capas: dict[str, dict[str, Path]] = {}
    for shp in sorted(source_dir.rglob("*")):
        if not (shp.is_file() and shp.suffix.lower() == ".shp"):
            continue
        if ramal_de_ruta(shp) != escenario:
            continue
        nombre = shp.stem.upper()
        capas.setdefault(nombre, {}).setdefault(_clave_municipio(shp), shp)

    return {capa: [paths[m] for m in sorted(paths)] for capa, paths in capas.items()}


# --------------------------------------------------------------------------- #
# Recorte y reproyeccion                                                       #
# --------------------------------------------------------------------------- #
def _familia_geometrica(gdf: gpd.GeoDataFrame) -> set[str] | None:
    """Familia de geometria de una capa, para descartar slivers de otra dimension."""
    tipos = set(gdf.geom_type.dropna().unique())
    for familia in (
        {"Polygon", "MultiPolygon"},
        {"LineString", "MultiLineString"},
        {"Point", "MultiPoint"},
    ):
        if tipos <= familia:
            return familia
    return None  # capa con geometrias mixtas: se conservan todas


def recortar_capa(shp_paths: list[Path], aoi_poly, target_crs: str) -> gpd.GeoDataFrame:
    """Carga, reproyecta a `target_crs` y recorta al AOI una capa (varios municipios)."""
    aoi_bounds = aoi_poly.bounds
    aoi_gdf = gpd.GeoDataFrame({"geometry": [aoi_poly]}, crs=target_crs)

    trozos: list[gpd.GeoDataFrame] = []
    for shp in shp_paths:
        municipio = _nombre_municipio(shp)
        # Leer solo lo que cae en el bbox del AOI acelera mucho municipios grandes.
        try:
            gdf = gpd.read_file(shp, bbox=aoi_bounds)
        except Exception:
            try:
                gdf = gpd.read_file(shp)
            except Exception as exc:
                print(f"      [WARN] No se pudo leer {shp.name} ({municipio}): {exc}")
                continue

        if gdf.empty or "geometry" not in gdf or gdf.geometry.isna().all():
            continue

        if gdf.crs is None:
            gdf = gdf.set_crs(target_crs)
        gdf = gdf.to_crs(target_crs)

        familia = _familia_geometrica(gdf)

        # Reparar poligonos invalidos antes del clip (auto-intersecciones).
        if familia == {"Polygon", "MultiPolygon"}:
            invalidas = ~gdf.geometry.is_valid
            if invalidas.any():
                gdf.loc[invalidas, "geometry"] = gdf.loc[invalidas, "geometry"].buffer(0)

        recortado = gpd.clip(gdf, aoi_gdf)
        recortado = recortado[recortado.geometry.notnull() & ~recortado.geometry.is_empty]
        if familia is not None:
            recortado = recortado[recortado.geom_type.isin(familia)]
        if recortado.empty:
            continue

        recortado = recortado.copy()
        # 'municipio' colisionaria con la columna 'MUNICIPIO' (codigo INE) del
        # Catastro, asi que el nombre legible se guarda como 'municipio_nombre'.
        recortado["municipio_nombre"] = municipio
        trozos.append(recortado)

    if not trozos:
        return gpd.GeoDataFrame({"geometry": []}, crs=target_crs)
    return gpd.GeoDataFrame(pd.concat(trozos, ignore_index=True), crs=target_crs)


def _orden_capa(nombre: str) -> tuple[int, str]:
    """Clave de ordenacion para presentar las capas en un orden estable."""
    nombre = nombre.upper()
    return (LAYER_ORDER.index(nombre) if nombre in LAYER_ORDER else len(LAYER_ORDER), nombre)


# --------------------------------------------------------------------------- #
# Tablas sin geometria (DBF) y enriquecimiento de SUBPARCE                      #
# --------------------------------------------------------------------------- #
def tablas_dbf(source_dir: Path, escenario: str, nombre: str) -> list[Path]:
    """Localiza un <nombre>.DBF por municipio del ramal (ya extraidos)."""
    nombre = nombre.upper()
    por_municipio: dict[str, Path] = {}
    for dbf in sorted(source_dir.rglob("*")):
        if not (dbf.is_file() and dbf.suffix.lower() == ".dbf" and dbf.stem.upper() == nombre):
            continue
        if ramal_de_ruta(dbf) != escenario:
            continue
        por_municipio.setdefault(_clave_municipio(dbf), dbf)
    return [por_municipio[m] for m in sorted(por_municipio)]


def leer_tabla(paths: list[Path]) -> pd.DataFrame:
    """Lee y concatena varias tablas DBF (sin geometria) anadiendo el municipio."""
    trozos: list[pd.DataFrame] = []
    for p in paths:
        try:
            df = pyogrio.read_dataframe(p, read_geometry=False)
        except Exception as exc:
            print(f"      [WARN] No se pudo leer la tabla {p.name}: {exc}")
            continue
        df["municipio_nombre"] = _nombre_municipio(p)
        trozos.append(df)
    return pd.concat(trozos, ignore_index=True) if trozos else pd.DataFrame()


def enriquecer_subparce(
    subparce: gpd.GeoDataFrame,
    source_dir: Path,
    escenario: str,
) -> gpd.GeoDataFrame:
    """Une a SUBPARCE el cultivo de RUSUBPARCELA (por REFCAT+letra) y su nombre
    de RUCULTIVO (por codigo CC). Solo aplica en rustica, donde existen esas
    tablas; en urbana devuelve la capa sin cambios."""
    rus_paths = tablas_dbf(source_dir, escenario, "RUSUBPARCELA")
    if not rus_paths or subparce.empty:
        return subparce

    rus = leer_tabla(rus_paths)
    if rus.empty or "REFCAT" not in rus or "SUBPARCELA" not in rus:
        return subparce

    # Clave de union: referencia catastral + letra de subparcela (en minuscula).
    rus["_k"] = rus["REFCAT"].astype(str) + "|" + rus["SUBPARCELA"].astype(str).str.lower()
    rus = rus.drop_duplicates("_k")

    atributos = (
        rus.set_index("_k")[["TIPOSUBP", "CC", "SUPERFICIE"]]
        .rename(columns={
            "TIPOSUBP": "subp_tiposubp",
            "CC": "cultivo_cc",
            "SUPERFICIE": "subp_superficie",
        })
    )

    g = subparce.copy()
    g["_k"] = g["REFCAT"].astype(str) + "|" + g["SUBPARCE"].astype(str).str.lower()
    g = g.join(atributos, on="_k")

    # Diccionario de cultivos (CC -> nombre y regadio).
    cul_paths = tablas_dbf(source_dir, escenario, "RUCULTIVO")
    if cul_paths:
        cul = leer_tabla(cul_paths).drop_duplicates("CC")
        nombre_cc = dict(zip(cul["CC"], cul.get("DENOMINA")))
        regadio_cc = dict(zip(cul["CC"], cul.get("REGADIO")))
        g["cultivo_nombre"] = g["cultivo_cc"].map(nombre_cc)
        g["cultivo_regadio"] = g["cultivo_cc"].map(regadio_cc)

    enlazadas = g["cultivo_cc"].notna().sum()
    print(f"      cultivo unido a {enlazadas}/{len(g)} subparcelas")
    return g.drop(columns="_k")


# --------------------------------------------------------------------------- #
# Orquestacion                                                                 #
# --------------------------------------------------------------------------- #
def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    target_crs = load_crs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"CRS de trabajo: {target_crs}")
    print(f"Salida en:      {OUTPUT_DIR}\n")

    resumen: list[str] = []

    for source in SOURCES:
        src_dir = source["dir"]
        tipo = source["tipo"]
        if not src_dir.exists():
            print(f"[SKIP] No existe la carpeta de origen: {src_dir}")
            continue

        print(f"=== Catastro {tipo.upper()} (codigo {source['codigo']}) "
              f"desde {src_dir.name} ===")

        for escenario in ("A", "B"):
            aoi_poly = load_aoi(escenario)
            capas = descubrir_capas(src_dir, escenario)
            capas = {k: v for k, v in capas.items() if k != "CARVIA"}
            salida = OUTPUT_DIR / f"catastro_{tipo}_aoi_{escenario}.gpkg"
            print(f"  Escenario {escenario}: {len(capas)} capa(s) catastrales detectadas")

            if salida.exists():
                salida.unlink()

            capas_escritas: list[str] = []
            for nombre_capa in sorted(capas, key=_orden_capa):
                shp_paths = capas[nombre_capa]
                fusion = recortar_capa(shp_paths, aoi_poly, target_crs)
                if fusion.empty:
                    print(f"    - {nombre_capa:13s}: 0 dentro del AOI")
                    continue
                if nombre_capa == "SUBPARCE":
                    fusion = enriquecer_subparce(fusion, src_dir, escenario)
                layer_name = nombre_capa.lower()
                try:
                    fusion.to_file(salida, layer=layer_name, driver="GPKG")
                except Exception as exc:
                    print(f"    - {nombre_capa:13s}: [WARN] no se pudo escribir ({exc})")
                    continue
                print(f"    - {nombre_capa:13s}: {len(fusion):6d} -> capa '{layer_name}'")
                capas_escritas.append(f"{layer_name}({len(fusion)})")

            # Tabla aspacial CARVIA (nombres de via), solo si hay capas en el AOI.
            if capas_escritas:
                carvia_paths = tablas_dbf(src_dir, escenario, "CARVIA")
                carvia = leer_tabla(carvia_paths) if carvia_paths else pd.DataFrame()
                if not carvia.empty:
                    try:
                        pyogrio.write_dataframe(carvia, salida, layer="carvia", driver="GPKG")
                        print(f"    - {'CARVIA':13s}: {len(carvia):6d} -> tabla aspacial 'carvia'")
                        capas_escritas.append(f"carvia({len(carvia)}, aspacial)")
                    except Exception as exc:
                        print(f"    - {'CARVIA':13s}: [WARN] no se pudo escribir ({exc})")

            if capas_escritas:
                print(f"  -> {salida.name}: {len(capas_escritas)} capas: "
                      f"{', '.join(capas_escritas)}")
                resumen.append(f"{salida.name}: {len(capas_escritas)} capas")
            else:
                print(f"  -> {salida.name}: sin geometrias en el AOI (no se crea fichero)")
                resumen.append(f"{salida.name}: VACIO")
            print()

    print("=" * 60)
    print("Resumen:")
    for linea in resumen:
        print(f"  {linea}")
    print("Script 05 completado.")


if __name__ == "__main__":
    main()
