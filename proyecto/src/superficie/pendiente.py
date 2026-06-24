"""
Capa de coste P1: pendiente.

Convierte dem_aoi_{s}.tif en pendiente_{s}.tif (coste relativo [0, 1] + barreras).
Modelo de coste en modelo_coste.md (4.1, 5.1) y contrato de salida del hito 2.

Patron comun de las capas de coste (hito 2):
  Paso 1 - Leer la rejilla de referencia: copiar SIEMPRE transform/width/height/
           CRS del DEM (dem_aoi_{s}.tif). Nunca calcular la rejilla a mano.
  Paso 2 - Asignar coste: pendiente en grados (Horn) + curva por tramos normativa
           sobre el array numpy. No usa atributos vectoriales.
  Paso 3 - Rasterizar: no aplica (el DEM ya esta sobre la rejilla comun).
  Paso 4 - Rellenar fondo: no aplica (el DEM cubre toda la rejilla).
  Paso 5 - Guardar con el mismo profile que el DEM (GTiff, float32,
           nodata=-9999.0, compress=lzw).

Tabla de coste P1 (umbrales FIJOS, nunca min/max del AOI):

  Rango pendiente   Coste              Tratamiento
  0° – 5°           0.0                Trivial
  5° – 15°          0.0 → 0.6 (lineal) Continuo
  15° – 30°         0.6 → 1.0 (lineal) Continuo
  > 30°             np.inf             Barrera dura — celda intransitable

Metodo: richdem (Horn) si esta instalado; si no, Horn equivalente en numpy.

Salida: data/processed/Capas_Coste/pendiente_{s}.tif  (uno por escenario).

Uso (desde proyecto/):
  python src/superficie/pendiente.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio


BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
ENTRADA_DIR = BASE / "Recorte_AOI"
SALIDA_DIR = BASE / "Capas_Coste"

ESCENARIOS = ["A", "B"]
CRS_TRABAJO = "EPSG:25830"
NODATA = -9999.0
RESOLUCION_M = 30.0


def mapeo_coste_pendiente(pendiente_grados: np.ndarray) -> np.ndarray:
    """Curva por tramos normativa: [0, 1] en memoria; >30° -> np.inf."""
    coste = np.zeros_like(pendiente_grados, dtype=np.float32)

    mask2 = (pendiente_grados > 5) & (pendiente_grados <= 15)
    coste[mask2] = 0.6 * (pendiente_grados[mask2] - 5) / 10

    mask3 = (pendiente_grados > 15) & (pendiente_grados <= 30)
    coste[mask3] = 0.6 + 0.4 * (pendiente_grados[mask3] - 15) / 15

    mask4 = pendiente_grados > 30
    coste[mask4] = np.inf

    return coste


def _pendiente_horn_numpy(
    dem: np.ndarray,
    cellsize: float,
    nodata: float,
) -> np.ndarray:
    """Algoritmo Horn (1981) — equivalente a richdem TerrainAttribute(slope_degrees)."""
    z = dem.astype(np.float64)
    valid = np.isfinite(z) & (z != nodata)

    z_work = z.copy()
    z_work[~valid] = np.nan

    zpad = np.pad(z_work, 1, mode="edge")
    z1 = zpad[:-2, :-2]
    z2 = zpad[:-2, 1:-1]
    z3 = zpad[:-2, 2:]
    z4 = zpad[1:-1, :-2]
    z6 = zpad[1:-1, 2:]
    z7 = zpad[2:, :-2]
    z8 = zpad[2:, 1:-1]
    z9 = zpad[2:, 2:]

    dzdx = ((z3 + 2 * z6 + z9) - (z1 + 2 * z4 + z7)) / (8.0 * cellsize)
    dzdy = ((z7 + 2 * z8 + z9) - (z1 + 2 * z2 + z3)) / (8.0 * cellsize)

    slope_deg = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    slope_deg = slope_deg.astype(np.float32)
    slope_deg[~valid] = np.nan
    return slope_deg


def _pendiente_richdem(
    dem: np.ndarray,
    transform,
    nodata: float,
) -> np.ndarray:
    """Pendiente con richdem (Horn) cuando la libreria esta disponible."""
    import richdem as rd

    dem_rd = rd.rdarray(dem.astype(np.float64), no_data=nodata)
    dem_rd.geotransform = [
        transform.c,
        transform.a,
        transform.b,
        transform.f,
        transform.d,
        transform.e,
    ]
    rd.ResolveFlats(dem_rd, in_place=True)
    slope = rd.TerrainAttribute(dem_rd, attrib="slope_degrees")
    return np.asarray(slope, dtype=np.float32)


def calcular_pendiente_horn(
    dem: np.ndarray,
    transform,
    nodata: float = NODATA,
    cellsize: float = RESOLUCION_M,
) -> np.ndarray:
    """Calcula pendiente en grados con Horn (richdem si esta instalado)."""
    try:
        return _pendiente_richdem(dem, transform, nodata)
    except ImportError:
        return _pendiente_horn_numpy(dem, cellsize, nodata)


def validar_contrato_salida(raster_path: Path, dem_path: Path) -> None:
    """Valida el contrato de salida obligatorio frente al DEM de referencia."""
    with rasterio.open(dem_path) as dem:
        dem_transform = dem.transform
        dem_shape = (dem.height, dem.width)
        dem_crs = dem.crs

    with rasterio.open(raster_path) as src:
        data = src.read(1)
        if src.crs != dem_crs:
            raise ValueError(f"CRS incorrecto: {src.crs}, esperado {dem_crs}")
        if src.transform != dem_transform:
            raise ValueError("Transform no coincide con dem_aoi")
        if (src.height, src.width) != dem_shape:
            raise ValueError(f"Shape incorrecta: {(src.height, src.width)} vs {dem_shape}")
        if src.dtypes[0] != "float32":
            raise ValueError(f"dtype incorrecto: {src.dtypes[0]}")
        if src.nodata != NODATA:
            raise ValueError(f"nodata incorrecto: {src.nodata}")
        if src.profile.get("compress") != "lzw":
            raise ValueError("Compresion incorrecta: se requiere lzw")

        validos = data[data != NODATA]
        if validos.size and (validos.min() < 0.0 or validos.max() > 1.0):
            raise ValueError(
                f"Rango fuera de [0, 1]: min={validos.min()}, max={validos.max()}"
            )


def procesar_escenario(s: str) -> Path:
    """Genera pendiente_{s}.tif a partir de dem_aoi_{s}.tif."""
    dem_path = ENTRADA_DIR / f"dem_aoi_{s}.tif"
    if not dem_path.exists():
        raise FileNotFoundError(f"No existe el DEM de referencia: {dem_path}")

    # --- Paso 1: rejilla de referencia (copiada del DEM, nunca recalculada) ---
    with rasterio.open(dem_path) as ref:
        dem_data = ref.read(1).astype(np.float32)
        transform = ref.transform
        width, height = ref.width, ref.height
        profile = ref.profile.copy()
        dem_nodata = ref.nodata if ref.nodata is not None else NODATA

        if ref.crs is None or ref.crs.to_epsg() != 25830:
            raise ValueError(f"CRS incorrecto en {dem_path}: se requiere {CRS_TRABAJO}")

    # --- Paso 2: pendiente Horn + curva por tramos sobre array numpy ---
    pendiente_grados = calcular_pendiente_horn(dem_data, transform, nodata=dem_nodata)
    cost_array = mapeo_coste_pendiente(pendiente_grados)

    mascara_dem_invalido = ~np.isfinite(dem_data) | (dem_data == dem_nodata)
    cost_array[mascara_dem_invalido] = np.inf
    cost_array[~np.isfinite(pendiente_grados)] = np.inf

    # --- Paso 3: rasterizar — no aplica (rejilla = DEM) ---
    # --- Paso 4: fondo — no aplica (DEM cubre toda la rejilla) ---

    # --- Paso 5: barreras np.inf -> nodata en disco; guardar con profile del DEM ---
    cost_array[np.isinf(cost_array)] = NODATA

    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    profile.update(
        driver="GTiff",
        dtype="float32",
        nodata=NODATA,
        count=1,
        compress="lzw",
    )
    salida = SALIDA_DIR / f"pendiente_{s}.tif"
    with rasterio.open(salida, "w", **profile) as dst:
        dst.write(cost_array.astype(np.float32), 1)

    validar_contrato_salida(salida, dem_path)

    validos = cost_array[cost_array != NODATA]
    barreras = int((cost_array == NODATA).sum())
    print(
        f"[{s}] {salida.name}: {width}x{height} celdas | "
        f"pendiente media={np.nanmean(pendiente_grados):.1f}° | "
        f"coste [{validos.min():.3f}, {validos.max():.3f}] | "
        f"barreras={barreras} ({100 * barreras / cost_array.size:.1f}%)"
    )

    return salida


def main() -> None:
    for s in ESCENARIOS:
        procesar_escenario(s)
    print("P1 completado: capa de coste 'pendiente' generada (A y B).")


if __name__ == "__main__":
    main()
