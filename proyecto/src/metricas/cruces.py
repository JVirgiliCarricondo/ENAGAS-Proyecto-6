"""
Conteo de cruces especiales de un trazado con infraestructuras lineales.

Para cada ruta (.gpkg de Rutas/) cuenta:
  - n_cruces_rios        : cursos de agua (hidrografia_aoi_{s}.gpkg, IGN)
  - n_cruces_carreteras  : viario rodado  (osm_aoi_{s}.gpkg, campo 'highway' no nulo)
  - n_cruces_ferrocarril : ferrocarril    (osm_aoi_{s}.gpkg, campo 'railway' no nulo)

Un cruce se registra como el número de puntos de intersección transversal entre la
línea de la ruta y cada geometría de infraestructura. Los solapamientos lineales
(ruta co-lineal con una infraestructura) no se cuentan como cruce.

Uso como script:
  python src/metricas/cruces.py

Uso como librería (desde calculo.py u otros módulos):
  from src.metricas.cruces import contar_cruces, cruces_escenario
  resultado = cruces_escenario(ruta_path, escenario="A")
"""

from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

CRS_TRABAJO = "EPSG:25830"

BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
RECORTE_DIR = BASE / "Recorte_AOI"
RUTAS_DIR = BASE / "Rutas"

ESCENARIOS = ["A", "B"]
PERFILES = ["corto", "equilibrio", "ambiental", "pendiente"]


def _puntos_interseccion(geom_a: BaseGeometry, geom_b: BaseGeometry) -> int:
    """Número de puntos de cruce transversal entre dos geometrías lineales.

    Un cruce = la ruta atraviesa la infraestructura, cortándola en un punto. Se
    cuenta clasificando la geometría de la intersección de las dos líneas:

      · Point           → 1 cruce transversal.
      · MultiPoint      → tantos cruces como puntos (la ruta cruza varias veces).
      · GeometryCollection → se cuentan solo las componentes Point (mezcla de
        cortes puntuales y tramos solapados: los tramos no son cruces).
      · LineString/otros → 0: es un solapamiento lineal (la ruta va co-lineal con
        la infraestructura, no la cruza), que por convenio NO se cuenta como cruce.

    Args:
        geom_a: Geometría lineal (la ruta).
        geom_b: Geometría lineal (una infraestructura: río, carretera o vía).

    Returns:
        Número de puntos de cruce transversal (0 si no se tocan o solo se solapan).
    """
    # intersects es una comprobación rápida (bounding box + relación topológica);
    # evita calcular la intersección exacta cuando no hay contacto.
    if not geom_a.intersects(geom_b):
        return 0
    inter = geom_a.intersection(geom_b)
    t = inter.geom_type
    if t == "Point":
        return 1
    if t == "MultiPoint":
        return len(inter.geoms)
    if t == "GeometryCollection":
        return sum(1 for g in inter.geoms if g.geom_type == "Point")
    return 0


def _limpiar(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Reproyecta al CRS de trabajo y elimina geometrías nulas o vacías."""
    if gdf.crs is None:
        raise ValueError("La capa no tiene CRS definido.")
    gdf = gdf.to_crs(CRS_TRABAJO)
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()


def contar_cruces(
    ruta_geom: BaseGeometry,
    osm_gdf: gpd.GeoDataFrame,
    hidro_gdf: gpd.GeoDataFrame,
) -> dict[str, int | None]:
    """Cuenta cruces transversales de una ruta con ríos, carreteras y ferrocarril.

    Parámetros
    ----------
    ruta_geom : geometría shapely de la ruta (LineString o MultiLineString).
    osm_gdf   : GeoDataFrame con el viario OSM (columna 'highway' y opcionalmente 'railway').
    hidro_gdf : GeoDataFrame con la hidrografía IGN.

    Devuelve
    --------
    Dict con las claves n_cruces_rios, n_cruces_carreteras, n_cruces_ferrocarril.

    Contrato de n_cruces_ferrocarril
    --------------------------------
    - ``int``  → medición real: la capa OSM trae la columna 'railway' y se contaron
      los cruces transversales (puede ser 0: "comprobado, no cruza ninguna vía").
    - ``None`` → NO comprobable: la capa OSM no incluye la columna 'railway', así que
      no hay datos de ferrocarril sobre los que medir. NO se devuelve 0, porque un 0
      callado se confundiría con "comprobado = 0 cruces". Se emite además un warning.
    """
    if "railway" in osm_gdf.columns:
        # Una fila OSM es ferrocarril si tiene 'railway' no vacío; el resto con
        # 'highway' no nulo son viario rodado. La exclusión (~ferrocarril_mask)
        # evita contar dos veces una fila que trajera ambos campos.
        ferrocarril_mask = osm_gdf["railway"].notna() & (osm_gdf["railway"].str.strip() != "")
        carretera_mask = ~ferrocarril_mask & osm_gdf["highway"].notna()
        ferrocarril = osm_gdf[ferrocarril_mask]
        # Suma de cruces transversales de la ruta con cada geometría de ferrocarril.
        n_ferrocarril: int | None = sum(
            _puntos_interseccion(ruta_geom, g) for g in ferrocarril.geometry
        )
    else:
        # Sin columna 'railway' no se puede medir: marcar como no comprobable (None),
        # nunca como 0. Avisar para que el hueco de dato sea visible aguas arriba.
        warnings.warn(
            "La capa OSM no tiene columna 'railway'; n_cruces_ferrocarril es no "
            "comprobable (None), no 0. (Sin vías férreas en el AOI, la columna no se "
            "crea al armar el GeoDataFrame.)",
            stacklevel=2,
        )
        carretera_mask = osm_gdf["highway"].notna()
        n_ferrocarril = None

    carreteras = osm_gdf[carretera_mask]

    # Cruces con ríos y carreteras: se suma, por cada geometría de la capa, el
    # número de cortes transversales que la ruta hace con ella.
    n_rios = sum(_puntos_interseccion(ruta_geom, g) for g in hidro_gdf.geometry)
    n_carreteras = sum(_puntos_interseccion(ruta_geom, g) for g in carreteras.geometry)

    return {
        "n_cruces_rios": n_rios,
        "n_cruces_carreteras": n_carreteras,
        "n_cruces_ferrocarril": n_ferrocarril,
    }


def cruces_escenario(ruta_path: Path | str, escenario: str) -> dict[str, int | None]:
    """Carga la ruta y las capas del escenario y devuelve el conteo de cruces.

    Args:
        ruta_path: Ruta al .gpkg de la ruta a analizar.
        escenario: 'A' o 'B' (selecciona las capas osm/hidrografía del AOI).

    Returns:
        Dict con n_cruces_rios, n_cruces_carreteras y n_cruces_ferrocarril
        (este último None si la capa OSM no trae la columna 'railway').

    Raises:
        FileNotFoundError: Si falta la ruta o alguna de las capas del escenario.
        ValueError: Si alguna capa no tiene CRS definido (vía ``_limpiar``).
    """
    ruta_path = Path(ruta_path)
    osm_path = RECORTE_DIR / f"osm_aoi_{escenario}.gpkg"
    hidro_path = RECORTE_DIR / f"hidrografia_aoi_{escenario}.gpkg"

    for p in (ruta_path, osm_path, hidro_path):
        if not p.exists():
            raise FileNotFoundError(f"No existe la entrada esperada: {p}")

    ruta_gdf = _limpiar(gpd.read_file(ruta_path))
    # union_all fusiona todas las filas de la ruta en una sola geometría, para
    # intersectarla de una vez contra cada infraestructura.
    ruta_geom = ruta_gdf.geometry.union_all()

    osm_gdf = _limpiar(gpd.read_file(osm_path))
    hidro_gdf = _limpiar(gpd.read_file(hidro_path))

    return contar_cruces(ruta_geom, osm_gdf, hidro_gdf)


def main() -> None:
    for s in ESCENARIOS:
        print(f"\n=== Escenario {s} ===")
        for perfil in PERFILES:
            ruta_path = RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg"
            if not ruta_path.exists():
                print(f"  [{perfil}] No encontrada: {ruta_path.name}")
                continue
            resultado = cruces_escenario(ruta_path, s)
            ffcc = resultado["n_cruces_ferrocarril"]
            ffcc_txt = f"{ffcc:3d}" if ffcc is not None else "s/d"
            print(
                f"  [{perfil}]"
                f"  ríos={resultado['n_cruces_rios']:3d}"
                f"  carreteras={resultado['n_cruces_carreteras']:3d}"
                f"  ferrocarril={ffcc_txt}"
            )


if __name__ == "__main__":
    main()
