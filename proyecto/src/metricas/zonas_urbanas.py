"""Métrica de uso del suelo: km de ruta por cada tipo catastral.

Para cada ruta calcula cuántos km discurren sobre cada tipo de suelo
según la capa del Catastro (data/processed/Recorte_AOI/catastro_aoi_{s}.gpkg).

Tipos catastrales presentes en el AOI:
    U  Urbano         — suelo urbano consolidado
    D  Diseminado     — núcleos diseminados, periurbano
    R  Rústico        — suelo agrícola o no urbanizable
    X  Especial       — grandes infraestructuras, zonas especiales

Interfaz común del módulo de métricas:
    calcular(linea, escenario) -> dict[str, float]

Uso standalone (desde proyecto/):
    python -m src.metricas.zonas_urbanas
    python -m src.metricas.zonas_urbanas --escenario A
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

_ROOT = Path(__file__).resolve().parents[2]
_RECORTE_AOI = _ROOT / "data" / "processed" / "Recorte_AOI"
_RUTAS = _ROOT / "data" / "processed" / "Rutas"

_CRS = "EPSG:25830"

# Mapeo código catastral → nombre legible en las claves del dict de salida
_TIPO_LABEL: dict[str, str] = {
    "U": "urbano",
    "D": "diseminado",
    "R": "rustico",
    "X": "especial",
}


def calcular(linea: LineString, escenario: str) -> dict[str, float]:
    """Km de la ruta sobre cada tipo de suelo catastral.

    Args:
        linea:     geometría de la ruta en EPSG:25830.
        escenario: 'A' o 'B'.

    Returns:
        dict con claves ``km_suelo_<tipo>`` para cada tipo catastral
        encontrado en el AOI. Los tipos sin intersección devuelven 0.0.
        Tipos conocidos: urbano, diseminado, rustico, especial.

    Raises:
        FileNotFoundError: Si no existe la capa catastro_aoi_{s}.gpkg del escenario.
    """
    s = escenario.upper()
    cat_path = _RECORTE_AOI / f"catastro_aoi_{s}.gpkg"
    if not cat_path.exists():
        raise FileNotFoundError(
            f"Capa de catastro no encontrada: {cat_path}\n"
            f"Ejecuta primero src/ingesta/alinear_capas.py --escenario {s}"
        )

    catastro = gpd.read_file(cat_path)
    if catastro.crs is None or catastro.crs.to_epsg() != 25830:
        catastro = catastro.to_crs(_CRS)

    # Inicializar todas las claves conocidas a 0.0 para que la tabla
    # comparativa siempre tenga las mismas columnas aunque un tipo no aparezca
    result: dict[str, float] = {
        f"km_suelo_{label}": 0.0 for label in _TIPO_LABEL.values()
    }

    # Un grupo por tipo de suelo (columna TIPO del catastro). Para cada tipo:
    #   union_all fusiona todas sus parcelas en un solo polígono, y la intersección
    #   de la ruta con ese polígono da los tramos de línea que caen sobre ese suelo.
    #   Su longitud (m → km) es el km_suelo_<tipo> de la ruta.
    for tipo, grupo in catastro.groupby("TIPO"):
        label = _TIPO_LABEL.get(str(tipo).upper())
        if label is None:
            # Tipo no catalogado: añadir con su código original en minúsculas
            label = str(tipo).lower()

        union = grupo.geometry.union_all()
        interseccion = linea.intersection(union)
        result[f"km_suelo_{label}"] = round(interseccion.length / 1000, 4)

    return result


def _cargar_linea(perfil: str, escenario: str) -> LineString:
    s = escenario.upper()
    path = _RUTAS / f"ruta_{s}_{perfil}.gpkg"
    if not path.exists():
        raise FileNotFoundError(f"Ruta no encontrada: {path}")
    gdf = gpd.read_file(path)
    return gdf.geometry.iloc[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calcula km por tipo de suelo catastral para todas las rutas."
    )
    parser.add_argument("--escenario", default="ambos",
                        help="id de escenario.yaml (p. ej. A, B o C) o 'ambos' (=A y B)")
    args = parser.parse_args()

    escenarios = ["A", "B"] if args.escenario == "ambos" else [args.escenario.upper()]
    perfiles = ["equilibrio", "corto", "ambiental", "pendiente"]

    for s in escenarios:
        print(f"\n=== Escenario {s} ===")
        for perfil in perfiles:
            try:
                linea = _cargar_linea(perfil, s)
                metricas = calcular(linea, s)
                partes = "  ".join(
                    f"{k.replace('km_suelo_', '')}={v:.3f} km"
                    for k, v in metricas.items()
                )
                print(f"  {perfil:12s}: {partes}")
            except FileNotFoundError as e:
                print(f"  {perfil:12s}: [OMITIDA] {e}")


if __name__ == "__main__":
    main()
