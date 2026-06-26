"""
Capa de coste P1-bis: gradiente (DIRECCIÓN de la pendiente).

Complementa a pendiente.py (magnitud, escalar) con la capa VECTORIAL pedida por
Enagás (reunión 2026-06-22): la dirección de la línea de máxima pendiente, para
que la tubería cruce las laderas DE FRENTE (perpendicular a las curvas de nivel)
y nunca en transversal (riesgo de cizalla ante deslizamientos).

Idea clave — DOS ESCALAS desde la MISMA fuente (el DEM original no se toca):

    dem_aoi_{s}.tif (30 m, intacto)
       ├─► pendiente.py : MAGNITUD  (sin suavizar → barreras y métricas finas)
       └─► [este módulo]: DIRECCIÓN (sobre COPIA SUAVIZADA → ladera estable)

Por qué la copia suavizada: la dirección es una derivada del terreno y las
derivadas amplifican el ruido. A 30 m, la línea de máxima pendiente "tiembla"
celda a celda y "perpendicular a la ladera" deja de tener sentido. Suavizando
(Gaussiano, sigma en metros) se ve la forma de la LADERA, no los guijarros.
La magnitud y las barreras NO se suavizan (viven en pendiente.py).

Convenio de signos (coordenadas de mapa Este/Norte, EPSG:25830):
  ascenso  (cuesta arriba) ∝ ( dz/dx, -dz/dy)
  descenso (línea de caída) ∝ (-dz/dx,  dz/dy)   ← la que sigue el agua / la tubería
  azimut_descenso = atan2(Este, Norte) en grados [0=N, 90=E, 180=S, 270=O]

Salida (capa de coste, junto a la pendiente-MAGNITUD pendiente_{s}.tif):
  data/processed/Capas_Coste/
    pendiente_direccion_{s}.tif          (4 bandas: dz/dx, dz/dy, pendiente°, azimut_descenso°)
    pendiente_direccion_{s}_flechas.gpkg (flechas cuesta abajo para validar el sentido en QGIS)

La escala de suavizado elegida es sigma = 150 m (la capa final NO lleva sufijo).
Otras escalas de comparación (p.ej. 90 / 250 m) se generan con --sigmas y SÍ llevan
sufijo `_sig{N}m` para no pisar la capa canónica.

Uso (desde proyecto/):
  python -m src.superficie.gradiente
  python -m src.superficie.gradiente --escenario A --sigmas 90 150 250  # comparar escalas
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import LineString

BASE = Path(__file__).resolve().parents[2] / "data" / "processed"
ENTRADA_DIR = BASE / "Recorte_AOI"
SALIDA_DIR = BASE / "Capas_Coste"  # junto a pendiente_{s}.tif (magnitud)

ESCENARIOS = ["A", "B"]
SIGMA_CANONICO_M = 150.0          # escala elegida; su salida es la capa de coste final (sin sufijo)
SIGMAS_M = [SIGMA_CANONICO_M]     # por defecto solo la escala elegida; pásale más para comparar


def _nombre_salida(s: str, sigma_m: float, sufijo: str = "") -> str:
    """Nombre de fichero de salida. El sigma canónico (150 m) es la capa de coste
    final y NO lleva sufijo de sigma; cualquier otra escala lo lleva (`_sig{N}m`)
    para no pisar la capa canónica."""
    base = f"pendiente_direccion_{s}"
    if abs(sigma_m - SIGMA_CANONICO_M) > 1e-6:
        base += f"_sig{int(round(sigma_m))}m"
    return base + sufijo
NODATA = -9999.0
RESOLUCION_M = 30.0  # solo valor por defecto/fallback; el cellsize real se deriva del transform del DEM

# Visualización de flechas
PASO_FLECHAS = 6           # 1 flecha cada 6 celdas (≈180 m) — rejilla fija, comparable entre sigmas
PENDIENTE_MIN_FLECHA = 1.0  # grados; por debajo no se dibuja (en llano la dirección no importa)
PENDIENTE_SAT_FLECHA = 20.0  # grados a los que la flecha alcanza longitud máxima


# ── Suavizado Gaussiano separable, consciente de nodata (numpy puro) ────────────


def _conv1d(a: np.ndarray, kernel: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """Convolución 1D a lo largo de `axis` con padding 'edge'."""
    pad = [(radius, radius) if i == axis else (0, 0) for i in range(a.ndim)]
    ap = np.moveaxis(np.pad(a, pad, mode="edge"), axis, -1)
    n = a.shape[axis]
    res = np.zeros(ap.shape[:-1] + (n,), dtype=np.float64)
    for i, kv in enumerate(kernel):
        res += kv * ap[..., i:i + n]
    return np.moveaxis(res, -1, axis)


def suavizar_gaussiano(
    z: np.ndarray,
    sigma_celdas: float,
    truncate: float = 3.0,
) -> np.ndarray:
    """Gaussiano separable consciente de nan (normaliza por validez en los bordes)."""
    radius = max(1, int(truncate * sigma_celdas + 0.5))
    x = np.arange(-radius, radius + 1)
    k = np.exp(-(x ** 2) / (2.0 * sigma_celdas ** 2))
    k /= k.sum()

    valido = np.isfinite(z)
    zz = np.where(valido, z, 0.0).astype(np.float64)
    w = valido.astype(np.float64)

    num = _conv1d(_conv1d(zz, k, radius, 0), k, radius, 1)
    den = _conv1d(_conv1d(w, k, radius, 0), k, radius, 1)

    out = np.full(z.shape, np.nan, dtype=np.float64)
    np.divide(num, den, out=out, where=den > 0)
    out[~valido] = np.nan
    return out


# ── Gradiente de Horn (componentes dz/dx, dz/dy) ────────────────────────────────


def gradiente_horn(z: np.ndarray, cellsize: float) -> tuple[np.ndarray, np.ndarray]:
    """Componentes del gradiente (dz/dx Este+, dz/dy fila+/Sur+) por Horn (1981)."""
    zpad = np.pad(z, 1, mode="edge")
    z1 = zpad[:-2, :-2]; z2 = zpad[:-2, 1:-1]; z3 = zpad[:-2, 2:]
    z4 = zpad[1:-1, :-2];                       z6 = zpad[1:-1, 2:]
    z7 = zpad[2:, :-2];   z8 = zpad[2:, 1:-1];  z9 = zpad[2:, 2:]

    dzdx = ((z3 + 2 * z6 + z9) - (z1 + 2 * z4 + z7)) / (8.0 * cellsize)
    dzdy = ((z7 + 2 * z8 + z9) - (z1 + 2 * z2 + z3)) / (8.0 * cellsize)
    return dzdx, dzdy


# ── Generación por escenario y sigma ────────────────────────────────────────────


def procesar(s: str, sigma_m: float) -> tuple[Path, Path]:
    """Genera el raster de dirección + las flechas para un escenario y sigma."""
    dem_path = ENTRADA_DIR / f"dem_aoi_{s}.tif"
    if not dem_path.exists():
        raise FileNotFoundError(f"No existe el DEM de referencia: {dem_path}")

    with rasterio.open(dem_path) as ref:
        dem = ref.read(1).astype(np.float64)
        transform = ref.transform
        profile = ref.profile.copy()
        dem_nodata = ref.nodata if ref.nodata is not None else NODATA
        crs = ref.crs

    valido = np.isfinite(dem) & (dem != dem_nodata)
    z = np.where(valido, dem, np.nan)

    # Cellsize real de la rejilla: se deriva del propio DEM (su transform), no de
    # una constante. Así sigma (en celdas) y el gradiente siguen al dato si el DEM
    # se regenera a otra resolución, en vez de quedar mal escalados en silencio.
    resolucion_m = abs(transform.a)

    # --- COPIA suavizada (el DEM original queda intacto) ---
    sigma_celdas = sigma_m / resolucion_m
    z_suave = suavizar_gaussiano(z, sigma_celdas)

    # --- Gradiente sobre la copia suavizada ---
    dzdx, dzdy = gradiente_horn(z_suave, resolucion_m)
    pendiente_deg = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))

    # Azimut de la línea de máxima pendiente (sentido DESCENSO), brújula 0=N,90=E
    este_desc = -dzdx
    norte_desc = dzdy
    azimut_desc = np.degrees(np.arctan2(este_desc, norte_desc)) % 360.0

    invalido = ~valido | ~np.isfinite(pendiente_deg)
    for arr in (dzdx, dzdy, pendiente_deg, azimut_desc):
        arr[invalido] = NODATA

    # --- Guardar raster multibanda ---
    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    n = int(round(sigma_m))
    profile.update(driver="GTiff", dtype="float32", count=4,
                   nodata=NODATA, compress="lzw")
    tif = SALIDA_DIR / f"{_nombre_salida(s, sigma_m)}.tif"
    with rasterio.open(tif, "w", **profile) as dst:
        dst.write(dzdx.astype(np.float32), 1)
        dst.write(dzdy.astype(np.float32), 2)
        dst.write(pendiente_deg.astype(np.float32), 3)
        dst.write(azimut_desc.astype(np.float32), 4)
        dst.set_band_description(1, "dz/dx (Este+)")
        dst.set_band_description(2, "dz/dy (fila+/Sur+)")
        dst.set_band_description(3, "pendiente suavizada (grados)")
        dst.set_band_description(4, "azimut linea max pendiente, descenso (grados)")

    gpkg = _flechas(s, sigma_m, z_suave, transform, crs, valido, dzdx, dzdy, pendiente_deg)

    n_dir = int(np.sum((pendiente_deg != NODATA) & (pendiente_deg >= PENDIENTE_MIN_FLECHA)))
    print(f"[{s} sig={n}m] {tif.name}: pendiente_max={np.nanmax(np.where(pendiente_deg==NODATA,np.nan,pendiente_deg)):.1f}° | "
          f"celdas con dirección útil={n_dir}")
    return tif, gpkg


def _flechas(
    s: str, sigma_m: float, z_suave: np.ndarray, transform, crs,
    valido: np.ndarray, dzdx: np.ndarray, dzdy: np.ndarray, pendiente_deg: np.ndarray,
) -> Path:
    """Flechas cuesta abajo (línea de máxima pendiente) para validar el sentido.

    Truco de verificación: la dirección es una propiedad de la superficie SUAVIZADA,
    así que el chequeo de cota se hace sobre ella (no sobre el DEM ruidoso) y a una
    distancia fija (1.5 celdas), independiente de la longitud dibujada. Si el sentido
    de descenso es correcto, z_fin < z_inicio (dz < 0) en ~100% de las flechas — así
    Enagás confirma que NO está invertido sin necesidad de cabezas de flecha.
    La longitud DIBUJADA sí es proporcional a la pendiente (sólo visual).
    """
    a, e = transform.a, transform.e
    c, f = transform.c, transform.f
    H, W = z_suave.shape
    paso_m = PASO_FLECHAS * abs(a)  # cellsize real del DEM, no la constante
    long_max = paso_m * 0.45
    probe = 1.5  # celdas: distancia fija para el chequeo de cota

    geoms, attrs = [], []
    for r in range(0, H, PASO_FLECHAS):
        for col in range(0, W, PASO_FLECHAS):
            if not valido[r, col]:
                continue
            pend = float(pendiente_deg[r, col])
            if pend == NODATA or pend < PENDIENTE_MIN_FLECHA:
                continue
            # dirección de descenso unitaria en (Este, Norte)
            este, norte = -float(dzdx[r, col]), float(dzdy[r, col])
            mag = np.hypot(este, norte)
            if mag == 0:
                continue
            ux, uy = este / mag, norte / mag
            longitud = long_max * min(pend / PENDIENTE_SAT_FLECHA, 1.0)

            x0 = c + (col + 0.5) * a
            y0 = f + (r + 0.5) * e
            x1, y1 = x0 + ux * longitud, y0 + uy * longitud

            # cota en inicio y a distancia fija sobre la superficie SUAVIZADA
            # (Norte+ ⇒ fila−, por eso -uy)
            rr = min(max(int(round(r - uy * probe)), 0), H - 1)
            cc = min(max(int(round(col + ux * probe)), 0), W - 1)
            z0 = float(z_suave[r, col])
            z1v = float(z_suave[rr, cc])

            geoms.append(LineString([(x0, y0), (x1, y1)]))
            attrs.append({
                "pendiente_deg": round(pend, 2),
                "azimut_desc": round(np.degrees(np.arctan2(este, norte)) % 360, 1),
                "z_inicio": round(z0, 2),
                "z_fin": round(z1v, 2),
                "dz": round(z1v - z0, 2),  # debe ser < 0 si el sentido es correcto
            })

    gdf = gpd.GeoDataFrame(attrs, geometry=geoms, crs=crs)
    gpkg = SALIDA_DIR / f"{_nombre_salida(s, sigma_m)}_flechas.gpkg"
    gdf.to_file(gpkg, driver="GPKG")

    if len(gdf):
        frac_ok = float((gdf["dz"] < 0).mean())
        print(f"           flechas={len(gdf)} | dz<0 (descenso correcto)={100*frac_ok:.1f}%")
    return gpkg


def main() -> None:
    parser = argparse.ArgumentParser(description="Capa de DIRECCIÓN de pendiente (gradiente).")
    parser.add_argument("--escenario", choices=["A", "B", "ambos"], default="ambos")
    parser.add_argument("--sigmas", type=float, nargs="+", default=SIGMAS_M,
                        help="sigmas de suavizado en metros (def: 150, la escala elegida; "
                             "pásale p.ej. 90 150 250 para comparar escalas)")
    args = parser.parse_args()

    escenarios = ESCENARIOS if args.escenario == "ambos" else [args.escenario]
    for s in escenarios:
        for sig in args.sigmas:
            procesar(s, sig)
    print(f"\nCapa de dirección generada en: {SALIDA_DIR}")


if __name__ == "__main__":
    main()
