"""
Capa de coste P6: TPI (Topographic Position Index — posicion topografica).

Convierte dem_aoi_{s}.tif en tpi_{s}.tif (coste relativo [0, 1] + barreras).

Esta capa SUSTITUYE a la antigua capa de pendiente como descriptor del relieve.
El TPI mide la POSICION del terreno respecto a su entorno:

    TPI(celda) = z(celda) - media( z en un vecindario anular de radio R )

  TPI > 0  -> la celda sobresale  -> CRESTA / divisoria / loma
  TPI ~ 0  -> llano O ladera de pendiente constante
  TPI < 0  -> la celda esta hundida -> VALLE / vaguada / fondo de cauce

Objetivo de esta capa (estrategia "ir por la cresta", evitar cruces de cauce):
coste DECRECIENTE con el TPI -> CRESTA barata, VALLE caro. Asi el motor LCP, al
buscar el camino mas barato, tiende a seguir divisorias (que por definicion no
cruzan rios). El peso de la capa por perfil (perfiles.yaml) modula cuanto pesa
esta preferencia; los perfiles que no la quieran le ponen peso 0.

NOTA DE DISENO (importante): el TPI es intrinsecamente RELATIVO al terreno, asi
que su normalizacion se centra en la media del AOI (z-score). Se acota a
+/- SIGMA_CLIP sigmas (umbral FIJO) para que la escala sea comparable entre
escenarios salvo el centrado. Calibrar/validar con Enagas (ver radio del anillo).

BARRERA DURA: como esta capa reemplaza a la pendiente, hereda la responsabilidad
de la transitabilidad. Calcula la pendiente del DEM (algoritmo Horn) y marca las
celdas > umbral_barrera_deg (35 deg) como nodata (intransitables). El TPI por si
solo NO ve la inclinacion (una ladera recta de 35 deg tiene TPI ~ 0), por eso la
barrera se calcula aparte, directamente del DEM. El coste morfologico de las
celdas transitables sigue en [0, 1].

Patron comun de las capas de coste (hito 2):
  Paso 1 - Leer la rejilla de referencia: copiar SIEMPRE transform/width/height/
           CRS del DEM (dem_aoi_{s}.tif). Nunca calcular la rejilla a mano.
  Paso 2 - Asignar coste: TPI (vecindario anular) + z-score + mapeo decreciente.
  Paso 3 - Rasterizar: no aplica (el DEM ya esta sobre la rejilla comun).
  Paso 4 - Rellenar fondo: no aplica (el DEM cubre toda la rejilla).
  Paso 5 - Guardar con el mismo profile que el DEM (GTiff, float32,
           nodata=-9999.0, compress=lzw).

Salida: data/processed/Capas_Coste/tpi_{s}.tif  (uno por escenario).

Uso (desde proyecto/):
  python -m src.superficie.tpi
  python -m src.superficie.tpi --radio 250   # comparar otra escala de anillo
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio

try:
    from .config import params_tpi as _params_tpi
except ImportError:
    from config import params_tpi as _params_tpi

BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
ENTRADA_DIR = BASE / "Recorte_AOI"
SALIDA_DIR = BASE / "Capas_Coste"

ESCENARIOS = ["A", "B"]
CRS_TRABAJO = "EPSG:25830"
NODATA = -9999.0
RESOLUCION_M = 30.0  # solo fallback; el cellsize real se deriva del transform del DEM

# --- Parametros de la capa (en perfiles.yaml -> parametros_capas.tpi) ---
_tcfg = _params_tpi()
RADIO_EXT_M = float(_tcfg["radio_ext_m"])      # radio exterior del vecindario anular (m)
RADIO_INT_M = float(_tcfg["radio_int_m"])      # radio interior (m); 0 = disco
SIGMA_CLIP = float(_tcfg["sigma_clip"])        # acota el TPI estandarizado a +/- este nº de sigmas
UMBRAL_BARRERA_DEG = float(_tcfg["umbral_barrera_deg"])  # pendiente > este valor -> intransitable


# ── Pendiente de Horn (heredada de la antigua pendiente.py, solo para la BARRERA) ──


def _pendiente_horn_numpy(dem: np.ndarray, cellsize: float, nodata: float) -> np.ndarray:
    """Algoritmo Horn (1981) — equivalente a richdem TerrainAttribute(slope_degrees)."""
    z = dem.astype(np.float64)
    valid = np.isfinite(z) & (z != nodata)
    z_work = z.copy()
    z_work[~valid] = np.nan

    zpad = np.pad(z_work, 1, mode="edge")
    z1 = zpad[:-2, :-2]; z2 = zpad[:-2, 1:-1]; z3 = zpad[:-2, 2:]
    z4 = zpad[1:-1, :-2];                       z6 = zpad[1:-1, 2:]
    z7 = zpad[2:, :-2];   z8 = zpad[2:, 1:-1];  z9 = zpad[2:, 2:]

    dzdx = ((z3 + 2 * z6 + z9) - (z1 + 2 * z4 + z7)) / (8.0 * cellsize)
    dzdy = ((z7 + 2 * z8 + z9) - (z1 + 2 * z2 + z3)) / (8.0 * cellsize)

    slope_deg = np.degrees(np.arctan(np.hypot(dzdx, dzdy))).astype(np.float32)
    slope_deg[~valid] = np.nan
    return slope_deg


def calcular_pendiente_horn(dem: np.ndarray, transform, nodata: float = NODATA,
                            cellsize: float = RESOLUCION_M) -> np.ndarray:
    """Pendiente en grados (Horn). Usa richdem si esta instalado; si no, numpy."""
    try:
        import richdem as rd
        dem_rd = rd.rdarray(dem.astype(np.float64), no_data=nodata)
        dem_rd.geotransform = [transform.c, transform.a, transform.b,
                               transform.f, transform.d, transform.e]
        rd.ResolveFlats(dem_rd, in_place=True)
        return np.asarray(rd.TerrainAttribute(dem_rd, attrib="slope_degrees"), dtype=np.float32)
    except ImportError:
        return _pendiente_horn_numpy(dem, cellsize, nodata)


def _kernel_anular(radio_ext_celdas: float, radio_int_celdas: float) -> np.ndarray:
    """Kernel binario del vecindario: 1 dentro del anillo (centro excluido), 0 fuera."""
    r = int(np.ceil(radio_ext_celdas))
    y, x = np.ogrid[-r : r + 1, -r : r + 1]
    dist = np.hypot(x, y)
    k = ((dist <= radio_ext_celdas) & (dist > radio_int_celdas)).astype(np.float64)
    k[r, r] = 0.0  # la celda central nunca entra en su propia media
    return k


def _media_vecindario(z: np.ndarray, valid: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Media del vecindario consciente de nodata: num/den solo sobre celdas validas.

    Los bordes del AOI y las celdas nodata se excluyen de forma natural (cuentan 0
    en el denominador), igual que el suavizado de gradiente.py.
    """
    from scipy.ndimage import convolve  # kernel simetrico -> convolve == correlate

    zf = np.where(valid, z, 0.0).astype(np.float64)
    w = valid.astype(np.float64)
    num = convolve(zf, kernel, mode="constant", cval=0.0)
    den = convolve(w, kernel, mode="constant", cval=0.0)
    mean = np.full(z.shape, np.nan, dtype=np.float64)
    np.divide(num, den, out=mean, where=den > 0)
    return mean


def calcular_tpi(dem: np.ndarray, valid: np.ndarray, cellsize: float,
                 radio_ext_m: float = RADIO_EXT_M,
                 radio_int_m: float = RADIO_INT_M) -> np.ndarray:
    """TPI bruto en metros: z - media(vecindario anular). nan donde invalido."""
    z = np.where(valid, dem.astype(np.float64), np.nan)
    kernel = _kernel_anular(radio_ext_m / cellsize, radio_int_m / cellsize)
    media = _media_vecindario(z, valid, kernel)
    tpi = z - media
    tpi[~valid] = np.nan
    return tpi


def mapeo_coste_tpi(tpi: np.ndarray, sigma_clip: float = SIGMA_CLIP) -> np.ndarray:
    """TPI bruto -> coste [0, 1] DECRECIENTE (cresta barata, valle caro).

    Estandariza (z-score) sobre las celdas validas y acota a +/- sigma_clip sigmas:
      TPI = +sigma_clip*sigma (cresta) -> coste 0.0
      TPI = 0 (llano/ladera)            -> coste 0.5
      TPI = -sigma_clip*sigma (valle)   -> coste 1.0
    """
    finito = np.isfinite(tpi)
    coste = np.full(tpi.shape, np.nan, dtype=np.float32)
    if not finito.any():
        return coste

    mu = float(np.mean(tpi[finito]))
    sigma = float(np.std(tpi[finito]))
    if sigma <= 0:  # terreno perfectamente plano: morfologia neutra
        coste[finito] = 0.5
        return coste

    tpi_std = (tpi[finito] - mu) / sigma
    tpi_std = np.clip(tpi_std, -sigma_clip, sigma_clip)
    coste[finito] = ((sigma_clip - tpi_std) / (2.0 * sigma_clip)).astype(np.float32)
    return coste


def _write_qml(tif_path: Path) -> None:
    """Estilo QGIS por POSICIÓN TOPOGRÁFICA (rojo crestas → tan llano → azul valles).

    La capa guarda COSTE (cresta=0, valle=1), así que para colorear por morfología
    invertimos el sentido visual: coste bajo = cresta (rojo), coste alto = valle (azul),
    coste medio = ladera/llano (tan). Rampa divergente tipo RdYlBu, como en la imagen
    de referencia de TPI.
    """
    qml = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer opacity="1" alphaBand="-1" band="1" type="singlebandpseudocolor"
      classificationMin="0" classificationMax="1" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0"
          minimumValue="0" maximumValue="1" classificationMode="1" labelPrecision="2">
          <item value="0.00" color="#d7191c" label="Cresta / divisoria (coste bajo)" alpha="255"/>
          <item value="0.25" color="#fdae61" label="Ladera alta"                     alpha="255"/>
          <item value="0.50" color="#f7e8c3" label="Llano / ladera"                  alpha="255"/>
          <item value="0.75" color="#abd9e9" label="Ladera baja"                     alpha="255"/>
          <item value="1.00" color="#2c7bb6" label="Valle / vaguada (coste alto)"    alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>"""
    tif_path.with_suffix(".qml").write_text(qml, encoding="utf-8")


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


def procesar_escenario(s: str, radio_ext_m: float = RADIO_EXT_M,
                       radio_int_m: float = RADIO_INT_M) -> Path:
    """Genera tpi_{s}.tif a partir de dem_aoi_{s}.tif."""
    dem_path = ENTRADA_DIR / f"dem_aoi_{s}.tif"
    if not dem_path.exists():
        raise FileNotFoundError(f"No existe el DEM de referencia: {dem_path}")

    # --- Paso 1: rejilla de referencia (copiada del DEM, nunca recalculada) ---
    with rasterio.open(dem_path) as ref:
        dem_data = ref.read(1).astype(np.float64)
        transform = ref.transform
        width, height = ref.width, ref.height
        profile = ref.profile.copy()
        dem_nodata = ref.nodata if ref.nodata is not None else NODATA

        if ref.crs is None or ref.crs.to_epsg() != 25830:
            raise ValueError(f"CRS incorrecto en {dem_path}: se requiere {CRS_TRABAJO}")

    # Cellsize real de la rejilla, derivado del propio DEM (no de una constante).
    cellsize = abs(transform.a)
    valid = np.isfinite(dem_data) & (dem_data != dem_nodata)

    # --- Paso 2: TPI (vecindario anular) + z-score + mapeo decreciente ---
    tpi = calcular_tpi(dem_data, valid, cellsize, radio_ext_m, radio_int_m)
    cost_array = mapeo_coste_tpi(tpi)

    # --- Barrera dura: pendiente del DEM > umbral -> intransitable (nodata) ---
    # El TPI no ve la inclinacion, asi que la barrera se calcula aparte del DEM.
    slope_deg = calcular_pendiente_horn(dem_data, transform, nodata=dem_nodata, cellsize=cellsize)
    barrera = np.isfinite(slope_deg) & (slope_deg > UMBRAL_BARRERA_DEG)
    n_barreras = int(barrera.sum())
    cost_array[barrera] = NODATA

    # Fuera del AOI / sin dato / pendiente no computable -> nodata
    cost_array[~valid] = NODATA
    cost_array[~np.isfinite(slope_deg)] = NODATA
    cost_array[~np.isfinite(cost_array)] = NODATA

    # --- Paso 5: guardar con el profile del DEM ---
    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    profile.update(
        driver="GTiff",
        dtype="float32",
        nodata=NODATA,
        count=1,
        compress="lzw",
    )
    salida = SALIDA_DIR / f"tpi_{s}.tif"
    with rasterio.open(salida, "w", **profile) as dst:
        dst.write(cost_array.astype(np.float32), 1)

    validar_contrato_salida(salida, dem_path)
    _write_qml(salida)

    validos = cost_array[cost_array != NODATA]
    tpi_validos = tpi[np.isfinite(tpi)]
    n_cresta = int((validos < 0.25).sum())  # coste bajo = cresta
    n_valle = int((validos > 0.75).sum())   # coste alto = valle
    print(
        f"[{s}] {salida.name}: {width}x{height} celdas | "
        f"radio={radio_ext_m:.0f} m ({radio_ext_m / cellsize:.1f} celdas) | "
        f"TPI [{tpi_validos.min():.1f}, {tpi_validos.max():.1f}] m | "
        f"coste [{validos.min():.3f}, {validos.max():.3f}] | "
        f"crestas(<0.25)={n_cresta} valles(>0.75)={n_valle} | "
        f"barreras(>{UMBRAL_BARRERA_DEG:.0f}°)={n_barreras}"
    )
    return salida


def main() -> None:
    parser = argparse.ArgumentParser(description="Capa de coste TPI (posicion topografica).")
    parser.add_argument("--escenario", choices=["A", "B", "ambos"], default="ambos")
    parser.add_argument("--radio", type=float, default=RADIO_EXT_M,
                        help=f"radio exterior del anillo en metros (def: {RADIO_EXT_M:.0f})")
    parser.add_argument("--radio-interior", type=float, default=RADIO_INT_M,
                        help=f"radio interior del anillo en metros (def: {RADIO_INT_M:.0f}; 0 = disco)")
    args = parser.parse_args()

    escenarios = ESCENARIOS if args.escenario == "ambos" else [args.escenario]
    for s in escenarios:
        procesar_escenario(s, args.radio, args.radio_interior)
    print("P6 completado: capa de coste 'tpi' generada.")


if __name__ == "__main__":
    main()
