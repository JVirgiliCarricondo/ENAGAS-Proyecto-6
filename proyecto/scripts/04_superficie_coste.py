"""
Script 3 - Combinacion de rasters en superficies de coste.

Combina los rasters de coste ya preparados en una superficie relativa 0-1 para
tres perfiles de decision. Las celdas fuera del corredor, o sin datos en algun
factor, se escriben con coste 999 para que el algoritmo de minimo coste no
pueda atravesarlas.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask


BASE_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BASE_DIR / "data" / "processed"
RASTERS_AOI_DIR = PROCESSED_DIR / "rasters_AOI"

AOI_PATH = PROCESSED_DIR / "aoi_corredor.gpkg"
COSTE_PENDIENTE = RASTERS_AOI_DIR / "coste_pendiente.tif"
COSTE_SUELO = RASTERS_AOI_DIR / "coste_suelo.tif"
COSTE_PROTEGIDA = RASTERS_AOI_DIR / "coste_protegida.tif"
COSTE_CRUCES = RASTERS_AOI_DIR / "coste_cruces.tif"

SALIDAS = {
    "A": RASTERS_AOI_DIR / "superficie_coste_A.tif",
    "B": RASTERS_AOI_DIR / "superficie_coste_B.tif",
    "C": RASTERS_AOI_DIR / "superficie_coste_C.tif",
}

CRS_TRABAJO = "EPSG:25830"
BARRERA_COSTE = 999.0

# Cada perfil suma 1.0 y representa un criterio relativo, nunca economico.
PERFILES = {
    "A": {
        "nombre": "minima longitud",
        "pesos": {
            "pendiente": 0.1,
            "suelo": 0.3,
            "protegida": 0.3,
            "cruces": 0.3,
        },
    },
    "B": {
        "nombre": "minimo impacto",
        "pesos": {
            "pendiente": 0.2,
            "suelo": 0.2,
            "protegida": 0.5,
            "cruces": 0.1,
        },
    },
    "C": {
        "nombre": "minima pendiente",
        "pesos": {
            "pendiente": 0.6,
            "suelo": 0.2,
            "protegida": 0.1,
            "cruces": 0.1,
        },
    },
}

RASTERS_ENTRADA = {
    "pendiente": COSTE_PENDIENTE,
    "suelo": COSTE_SUELO,
    "protegida": COSTE_PROTEGIDA,
    "cruces": COSTE_CRUCES,
}


def validar_pesos() -> None:
    """Comprueba que los pesos de cada perfil suman exactamente 1.0."""
    for codigo, perfil in PERFILES.items():
        suma = sum(perfil["pesos"].values())
        if not np.isclose(suma, 1.0):
            raise ValueError(f"Los pesos del perfil {codigo} suman {suma}, no 1.0.")


def leer_raster_coste(path: Path, perfil_ref: dict | None = None) -> tuple[np.ndarray, dict, np.ndarray]:
    """Lee un raster de coste y devuelve datos, perfil y mascara de celdas validas."""
    if not path.exists():
        raise FileNotFoundError(f"No existe el raster de coste esperado: {path}")

    with rasterio.open(path) as src:
        datos = src.read(1).astype("float32")
        perfil = src.profile.copy()

        if perfil_ref is not None:
            misma_rejilla = (
                src.crs == perfil_ref["crs"]
                and src.width == perfil_ref["width"]
                and src.height == perfil_ref["height"]
                and src.transform == perfil_ref["transform"]
            )
            if not misma_rejilla:
                raise ValueError(f"El raster no coincide con la rejilla de referencia: {path}")

        # Las celdas validas deben estar dentro del rango relativo 0-1 y no ser
        # nodata. Cualquier otra celda se convertira en barrera 999.
        if src.nodata is None:
            mascara_valida = np.isfinite(datos)
        else:
            mascara_valida = (datos != src.nodata) & np.isfinite(datos)
        mascara_valida &= (datos >= 0.0) & (datos <= 1.0)

    return datos, perfil, mascara_valida


def leer_rasters_entrada() -> tuple[dict[str, np.ndarray], dict, np.ndarray]:
    """Carga los cuatro factores de coste y obtiene su mascara comun valida."""
    rasters = {}
    mascara_comun = None
    perfil_ref = None

    for nombre, path in RASTERS_ENTRADA.items():
        datos, perfil, mascara_valida = leer_raster_coste(path, perfil_ref)
        if perfil_ref is None:
            perfil_ref = perfil
            mascara_comun = mascara_valida.copy()
        else:
            mascara_comun &= mascara_valida
        rasters[nombre] = datos

    return rasters, perfil_ref, mascara_comun


def crear_mascara_aoi(perfil_ref: dict) -> np.ndarray:
    """Rasteriza el AOI corredor como mascara booleana en la rejilla de referencia."""
    if not AOI_PATH.exists():
        raise FileNotFoundError("No se encontro el AOI corredor. Ejecuta primero scripts/01_aoi.py.")

    aoi = gpd.read_file(AOI_PATH, layer="aoi_corredor").to_crs(CRS_TRABAJO)

    # invert=True hace que True represente el interior del corredor permitido.
    return geometry_mask(
        aoi.geometry,
        out_shape=(perfil_ref["height"], perfil_ref["width"]),
        transform=perfil_ref["transform"],
        invert=True,
    )


def combinar_costes(
    rasters: dict[str, np.ndarray],
    mascara_valida: np.ndarray,
    pesos: dict[str, float],
) -> np.ndarray:
    """Calcula una superficie de coste ponderada y aplica barrera fuera del AOI."""
    superficie = np.full(next(iter(rasters.values())).shape, BARRERA_COSTE, dtype="float32")

    # La combinacion ponderada mantiene el resultado dentro de 0-1 porque todos
    # los factores estan normalizados y los pesos suman 1.
    coste = (
        rasters["pendiente"] * pesos["pendiente"]
        + rasters["suelo"] * pesos["suelo"]
        + rasters["protegida"] * pesos["protegida"]
        + rasters["cruces"] * pesos["cruces"]
    )
    superficie[mascara_valida] = np.clip(coste[mascara_valida], 0.0, 1.0)
    return superficie


def guardar_superficie(path: Path, datos: np.ndarray, perfil_ref: dict) -> None:
    """Guarda la superficie de coste en GeoTIFF con la rejilla del DEM corredor."""
    perfil = perfil_ref.copy()
    perfil.update(
        {
            "driver": "GTiff",
            "count": 1,
            "dtype": "float32",
            "nodata": None,
            "compress": "deflate",
        }
    )

    with rasterio.open(path, "w", **perfil) as dst:
        dst.write(datos.astype("float32"), 1)

    print(f"Superficie de coste guardada: {path}")


def imprimir_estadisticas(codigo: str, nombre: str, superficie: np.ndarray) -> None:
    """Muestra un resumen rapido para detectar valores fuera de rango."""
    mascara_coste = superficie != BARRERA_COSTE
    valores = superficie[mascara_coste]
    barreras = int((~mascara_coste).sum())

    print(
        f"Perfil {codigo} ({nombre}): "
        f"validas={valores.size}, barreras={barreras}, "
        f"min={valores.min():.3f}, max={valores.max():.3f}, media={valores.mean():.3f}"
    )


def main() -> None:
    """Ejecuta la creacion de las tres superficies de coste."""
    validar_pesos()
    rasters, perfil_ref, mascara_comun = leer_rasters_entrada()
    dentro_aoi = crear_mascara_aoi(perfil_ref)

    # La mascara final exige estar dentro del corredor y tener datos validos en
    # los cuatro factores. Todo lo demas queda como barrera 999 para el LCP.
    mascara_valida = dentro_aoi & mascara_comun

    for codigo, perfil in PERFILES.items():
        superficie = combinar_costes(
            rasters=rasters,
            mascara_valida=mascara_valida,
            pesos=perfil["pesos"],
        )
        guardar_superficie(SALIDAS[codigo], superficie, perfil_ref)
        imprimir_estadisticas(codigo, perfil["nombre"], superficie)

    print("Script 3 completado: superficies de coste A, B y C generadas.")


if __name__ == "__main__":
    main()
