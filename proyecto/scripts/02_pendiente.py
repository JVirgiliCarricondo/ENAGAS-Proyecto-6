"""
Script 1 - Calculo del coste por pendiente.

Lee el DEM recortado al AOI corredor, calcula la pendiente en grados con numpy,
la normaliza a un indice relativo 0-1 y guarda el resultado como raster de coste
para los scripts posteriores.
"""

from pathlib import Path

import numpy as np
import rasterio


# Rutas relativas a la raiz de "proyecto".
BASE_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BASE_DIR / "data" / "processed"
RASTERS_AOI_DIR = PROCESSED_DIR / "rasters_AOI"

# DEM preferente generado por el Script 0. Si no existe, se busca otro DEM de
# corredor para que el script sea tolerante a pequenas diferencias de nombres.
DEM_CORREDOR_PATH = RASTERS_AOI_DIR / "dem_aoi_corredor.tif"
SALIDA_PENDIENTE_PATH = RASTERS_AOI_DIR / "coste_pendiente.tif"

# Valor nodata para la capa de coste. Mantenerlo fuera del rango 0-1 evita
# confundir celdas sin datos con zonas llanas.
NODATA_COSTE = -9999.0


def localizar_dem_corredor() -> Path:
    """Encuentra el DEM ya recortado al corredor por el Script 0."""
    if DEM_CORREDOR_PATH.exists():
        return DEM_CORREDOR_PATH

    # Buscamos candidatos por nombre para evitar depender de una unica ruta si
    # el DEM procesado original estaba dentro de una subcarpeta.
    candidatos = sorted(RASTERS_AOI_DIR.glob("*dem*_corredor.tif"))
    if not candidatos:
        raise FileNotFoundError(
            "No se encontro ningun DEM de corredor. Ejecuta primero scripts/01_aoi.py."
        )

    return candidatos[0]


def leer_dem(dem_path: Path) -> tuple[np.ndarray, dict]:
    """Lee la primera banda del DEM y convierte nodata a NaN para calcular."""
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")
        perfil = src.profile.copy()

        # Las celdas fuera del corredor llegan como nodata desde el Script 0.
        # Pasarlas a NaN permite que numpy las ignore en la normalizacion.
        if src.nodata is not None:
            dem = np.where(dem == src.nodata, np.nan, dem)

    return dem, perfil


def calcular_pendiente_grados(dem: np.ndarray, resolucion_x: float, resolucion_y: float) -> np.ndarray:
    """Calcula la pendiente en grados a partir del cambio de cota entre celdas."""
    dem_calculo = dem.copy()

    # np.gradient no interpreta NaN como barrera; rellenamos temporalmente los
    # huecos con la mediana valida para evitar que el borde del AOI genere
    # pendientes artificiales enormes. Despues se recupera la mascara original.
    mascara_valida = np.isfinite(dem_calculo)
    if not np.any(mascara_valida):
        raise ValueError("El DEM no contiene celdas validas dentro del corredor.")

    dem_calculo[~mascara_valida] = np.nanmedian(dem_calculo)

    # dz_dy mide el cambio norte-sur y dz_dx el cambio este-oeste. Las
    # resoluciones se pasan en metros, por lo que el gradiente queda en m/m.
    dz_dy, dz_dx = np.gradient(dem_calculo, resolucion_y, resolucion_x)
    pendiente_radianes = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    pendiente_grados = np.degrees(pendiente_radianes).astype("float32")

    # Restauramos el exterior del corredor como NaN para que no participe en
    # la normalizacion ni aparezca como coste valido.
    pendiente_grados[~mascara_valida] = np.nan
    return pendiente_grados


def normalizar_0_1(pendiente_grados: np.ndarray) -> np.ndarray:
    """Normaliza la pendiente a un indice relativo 0-1."""
    mascara_valida = np.isfinite(pendiente_grados)
    pendiente_normalizada = np.full(
        pendiente_grados.shape,
        NODATA_COSTE,
        dtype="float32",
    )

    max_pendiente = float(np.nanmax(pendiente_grados))
    if max_pendiente <= 0:
        # Si todo el DEM fuese plano, todas las celdas validas tendrian coste 0.
        pendiente_normalizada[mascara_valida] = 0.0
        return pendiente_normalizada

    # 0 equivale a terreno llano y 1 a la maxima pendiente observada dentro del
    # corredor; es un indice relativo, no un coste economico.
    pendiente_normalizada[mascara_valida] = pendiente_grados[mascara_valida] / max_pendiente
    pendiente_normalizada[mascara_valida] = np.clip(
        pendiente_normalizada[mascara_valida],
        0.0,
        1.0,
    )
    return pendiente_normalizada


def guardar_coste_pendiente(coste: np.ndarray, perfil_dem: dict) -> None:
    """Guarda el raster de coste conservando CRS, transform y resolucion del DEM."""
    perfil_salida = perfil_dem.copy()
    perfil_salida.update(
        {
            "driver": "GTiff",
            "count": 1,
            "dtype": "float32",
            "nodata": NODATA_COSTE,
            "compress": "deflate",
        }
    )

    with rasterio.open(SALIDA_PENDIENTE_PATH, "w", **perfil_salida) as dst:
        dst.write(coste.astype("float32"), 1)

    print(f"Coste por pendiente guardado en: {SALIDA_PENDIENTE_PATH}")


def main() -> None:
    """Ejecuta el flujo completo del Script 1."""
    dem_path = localizar_dem_corredor()
    dem, perfil = leer_dem(dem_path)

    resolucion_x = abs(perfil["transform"].a)
    resolucion_y = abs(perfil["transform"].e)

    pendiente_grados = calcular_pendiente_grados(dem, resolucion_x, resolucion_y)
    coste_pendiente = normalizar_0_1(pendiente_grados)
    guardar_coste_pendiente(coste_pendiente, perfil)

    valores_validos = coste_pendiente[coste_pendiente != NODATA_COSTE]
    print(f"DEM usado: {dem_path}")
    print(f"Pendiente maxima normalizada: {valores_validos.max():.3f}")
    print(f"Celdas validas: {valores_validos.size}")


if __name__ == "__main__":
    main()
