"""
P1 — Capa de Pendiente (Opción B: Pre-calculada, Isotrópica)

Script de implementación de la especificación técnica en CAPAS_COSTE_P1_Pendiente.md.

Sigue los 5 pasos estándar de la Guía de Capas de Coste:
  1. Leer rejilla de referencia (DEM alineado)
  2. Calcular pendiente (Horn o np.gradient)
  3. Aplicar curva por tramos normativa (0-5: 0.0 → 5-15: rampa 0.6 → 15-30: rampa 1.0 → >30: ∞)
  4. Reemplazar infinito por nodata (-9999.0)
  5. Guardar raster con parámetros obligatorios

Entrada: dem_aoi_{s}.tif (DEM alineado a EPSG:25830, rejilla común)
Salida: data/processed/Capas_Coste/pendiente_{s}.tif (coste en [0, 1])

Autor: Grupo 6, CI2 Lab 2026
Fecha: 18 de junio de 2026
Estado: Implementación lista para MVP 1 (Hito 2)
"""

import numpy as np
import rasterio
from rasterio.plot import show
import matplotlib.pyplot as plt
from pathlib import Path
import sys
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s — %(levelname)s — %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# PASO 2: Función de Mapeo Coste-Pendiente (Curva Normativa)
# ============================================================================

def mapeo_coste_pendiente(pendiente_grados):
    """
    Mapea pendiente en grados → coste normalizado [0, 1] ∪ {∞}.

    Tabla de mapeo (NORMATIVA, FIJA, no data-driven):
    ├─ 0°–5°:     coste = 0.0
    ├─ 5°–15°:    coste = 0.0 + 0.6 × (pend - 5) / 10  [rampa]
    ├─ 15°–30°:   coste = 0.6 + 0.4 × (pend - 15) / 15 [rampa]
    └─ >30°:      coste = ∞ (barrera dura, intransitable)

    Parámetros:
        pendiente_grados (float o np.ndarray): pendiente en grados

    Retorna:
        coste (float o np.ndarray): coste normalizado en [0, 1] ∪ {∞}

    Notas:
        - Umbrales FIJOS (0, 5, 15, 30): nunca cambian entre AOIs/escenarios
        - Garantiza reproducibilidad: misma pendiente → mismo coste siempre
        - ∞ se guarda en disco como nodata=-9999.0
    """
    if np.isscalar(pendiente_grados):
        # Versión escalar (para tests)
        if pendiente_grados <= 5:
            return 0.0
        elif pendiente_grados <= 15:
            return 0.6 * (pendiente_grados - 5) / 10
        elif pendiente_grados <= 30:
            return 0.6 + 0.4 * (pendiente_grados - 15) / 15
        else:
            return np.inf
    else:
        # Versión vectorizada (para rasters)
        coste = np.zeros_like(pendiente_grados, dtype=np.float32)

        # Rango 1: 0°–5°
        mask1 = pendiente_grados <= 5
        coste[mask1] = 0.0

        # Rango 2: 5°–15° (rampa 0.0 → 0.6)
        mask2 = (pendiente_grados > 5) & (pendiente_grados <= 15)
        coste[mask2] = 0.6 * (pendiente_grados[mask2] - 5) / 10

        # Rango 3: 15°–30° (rampa 0.6 → 1.0)
        mask3 = (pendiente_grados > 15) & (pendiente_grados <= 30)
        coste[mask3] = 0.6 + 0.4 * (pendiente_grados[mask3] - 15) / 15

        # Rango 4: >30° (barrera dura = ∞)
        mask4 = pendiente_grados > 30
        coste[mask4] = np.inf

        return coste


# ============================================================================
# PASO 1: Función para Leer Rejilla de Referencia
# ============================================================================

def leer_rejilla_referencia(dem_path):
    """
    Lee metadatos de alineación del DEM (usado como referencia).

    Retorna:
        dict con keys: transform, width, height, crs
    """
    with rasterio.open(dem_path) as src:
        rejilla = {
            'transform': src.transform,
            'width': src.width,
            'height': src.height,
            'crs': src.crs,
        }

        # Validación: CRS debe ser EPSG:25830
        if rejilla['crs'].to_epsg() != 25830:
            raise ValueError(
                f"❌ CRS incorrecto en {dem_path}: {rejilla['crs']}, "
                f"se esperaba EPSG:25830"
            )

        logger.info(
            f"✓ Rejilla de referencia: "
            f"shape={rejilla['height']}×{rejilla['width']}, "
            f"CRS={rejilla['crs']}"
        )

    return rejilla


# ============================================================================
# PASO 2: Función para Calcular Pendiente
# ============================================================================

def calcular_pendiente_np_gradient(dem_data, pixelsize_m=30):
    """
    Calcula pendiente usando np.gradient (rápido, aceptable para MVP).

    Método: Sobel-like (diferencias centrales)
    Parámetro: pixelsize_m = resolución del píxel en metros

    Retorna:
        pendiente_grados (np.ndarray): pendiente en grados [0, 90]
    """
    logger.info(f"Calculando pendiente con np.gradient (resolución={pixelsize_m}m)...")

    # Calcular gradientes en Y (norte-sur) y X (este-oeste)
    dz_dy, dz_dx = np.gradient(dem_data, pixelsize_m, pixelsize_m)

    # Magnitud del gradiente 2D
    magnitud_gradiente = np.sqrt(dz_dx**2 + dz_dy**2)

    # Convertir a radianes y luego a grados
    pendiente_rad = np.arctan(magnitud_gradiente)
    pendiente_grados = np.degrees(pendiente_rad)

    logger.info(
        f"✓ Pendiente calculada: "
        f"rango=[{pendiente_grados.min():.1f}°, {pendiente_grados.max():.1f}°], "
        f"media={pendiente_grados.mean():.1f}°"
    )

    return pendiente_grados


def calcular_pendiente_richdem(dem_data, pixelsize_m=30):
    """
    Calcula pendiente usando richdem (Horn, más robusto).

    Nota: Requiere library richdem (pip install richdem).
    Recomendado para MVP 5-6 (producción). MVP 1-4 usa np.gradient.

    Retorna:
        pendiente_grados (np.ndarray): pendiente en grados [0, 90]
    """
    try:
        import richdem as rd
    except ImportError:
        logger.warning(
            "⚠️ richdem no está instalado. Usando np.gradient como fallback."
        )
        return calcular_pendiente_np_gradient(dem_data, pixelsize_m)

    logger.info("Calculando pendiente con richdem (Horn)...")

    # Cargar DEM en análisis richdem
    dem_analysis = rd.LoadElevation(dem_data)

    # Resolver terrazas planas (evita pendientes 0 ficticio)
    rd.ResolveFlats(dem_analysis)

    # Calcular pendiente en grados
    pendiente_grados = rd.SurfaceDerivative(dem_analysis, "slope_degrees")

    logger.info(
        f"✓ Pendiente (Horn) calculada: "
        f"rango=[{pendiente_grados.min():.1f}°, {pendiente_grados.max():.1f}°], "
        f"media={pendiente_grados.mean():.1f}°"
    )

    return pendiente_grados


# ============================================================================
# PASO 3: Función para Validar Curva
# ============================================================================

def validar_curva_mapeo():
    """
    Valida que la curva de mapeo cumpla la especificación normativa.
    """
    logger.info("Validando curva de mapeo...")

    test_cases = [
        (0.0, 0.0),
        (2.5, 0.0),
        (5.0, 0.0),
        (10.0, 0.3),
        (15.0, 0.6),
        (22.5, 0.8),
        (30.0, 1.0),
        (31.0, np.inf),
        (45.0, np.inf),
    ]

    for pend, expected in test_cases:
        result = mapeo_coste_pendiente(pend)
        if np.isinf(expected):
            assert np.isinf(result), f"Fallo: pend={pend}°, resultado={result}, esperado={expected}"
        else:
            assert abs(result - expected) < 1e-5, \
                f"Fallo: pend={pend}°, resultado={result:.4f}, esperado={expected:.4f}"

    logger.info("✓ Curva de mapeo validada correctamente")


# ============================================================================
# PASO 4 y 5: Función Principal de Procesamiento
# ============================================================================

def procesar_pendiente(
    corredor,
    dem_input_path=None,
    dem_alineado_path=None,
    output_dir="data/processed/Capas_Coste",
    metodo="np.gradient",
    plot=False
):
    """
    Procesa la capa P1 — Pendiente (Opción B: Pre-calculada, Isotrópica).

    Flujo:
      1. Leer rejilla de referencia (DEM alineado)
      2. Calcular pendiente (np.gradient o richdem)
      3. Aplicar curva por tramos normativa
      4. Reemplazar ∞ por nodata
      5. Guardar raster GeoTIFF con parámetros obligatorios

    Parámetros:
        corredor (str): 'A' o 'B' (zona de trabajo)
        dem_input_path (str, optional): ruta personalizada del DEM. Si None, usa default.
        dem_alineado_path (str, optional): ruta personalizada del DEM alineado.
        output_dir (str): directorio donde guardar salida (default: data/processed/Capas_Coste)
        metodo (str): 'np.gradient' (rápido, default) o 'richdem' (robusto)
        plot (bool): si True, muestra gráficos comparativos

    Retorna:
        dict con keys: 'coste', 'pendiente_grados', 'output_path', 'stats'
    """

    logger.info("=" * 80)
    logger.info(f"P1 — PENDIENTE (Opción B) — Corredor {corredor.upper()}")
    logger.info("=" * 80)

    # Rutas por defecto si no se especifican
    if dem_alineado_path is None:
        dem_alineado_path = f"data/processed/rasters_aoi/dem_aoi_{corredor}.tif"

    if not Path(dem_alineado_path).exists():
        raise FileNotFoundError(f"❌ DEM alineado no encontrado: {dem_alineado_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"pendiente_{corredor}.tif"

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 1: Leer rejilla de referencia
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("\n[PASO 1] Leyendo rejilla de referencia...")
    with rasterio.open(dem_alineado_path) as src:
        dem_data = src.read(1).astype(np.float32)
        rejilla = leer_rejilla_referencia(dem_alineado_path)

    logger.info(f"  Lectura completada: DEM shape={dem_data.shape}")

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 2: Calcular pendiente
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("\n[PASO 2] Calculando pendiente...")
    if metodo == "np.gradient":
        pendiente_grados = calcular_pendiente_np_gradient(dem_data, pixelsize_m=30)
    elif metodo == "richdem":
        pendiente_grados = calcular_pendiente_richdem(dem_data, pixelsize_m=30)
    else:
        raise ValueError(f"Método desconocido: {metodo}")

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 3: Aplicar curva por tramos normativa
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("\n[PASO 3] Aplicando curva por tramos normativa...")
    validar_curva_mapeo()  # Validar primero

    coste_pendiente = mapeo_coste_pendiente(pendiente_grados)
    logger.info(
        f"  Coste asignado: "
        f"finito en {(~np.isinf(coste_pendiente)).sum()} celdas, "
        f"barrera dura (∞) en {np.isinf(coste_pendiente).sum()} celdas"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 4: Reemplazar infinito por nodata
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("\n[PASO 4] Reemplazando barrera dura (∞) por nodata...")
    nodata_value = -9999.0
    coste_pendiente[np.isinf(coste_pendiente)] = nodata_value
    logger.info(f"  Nodata marcado como: {nodata_value}")

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 5: Guardar raster con parámetros obligatorios
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("\n[PASO 5] Guardando raster GeoTIFF...")

    profile = {
        'driver': 'GTiff',
        'dtype': 'float32',
        'width': rejilla['width'],
        'height': rejilla['height'],
        'count': 1,
        'crs': rejilla['crs'],
        'transform': rejilla['transform'],
        'nodata': nodata_value,
        'compress': 'lzw',
        'TILED': 'YES',
        'BLOCKXSIZE': 256,
        'BLOCKYSIZE': 256,
    }

    with rasterio.open(str(output_path), 'w', **profile) as dst:
        dst.write(coste_pendiente.astype('float32'), 1)

    logger.info(f"✓ Guardado: {output_path}")

    # Estadísticas finales
    coste_valido = coste_pendiente[coste_pendiente != nodata_value]
    stats = {
        'coste_min': coste_valido.min(),
        'coste_max': coste_valido.max(),
        'coste_media': coste_valido.mean(),
        'coste_std': coste_valido.std(),
        'n_celdas_validas': len(coste_valido),
        'n_barreras_duras': (coste_pendiente == nodata_value).sum(),
    }

    logger.info("\n[ESTADÍSTICAS]")
    logger.info(f"  Rango coste: [{stats['coste_min']:.3f}, {stats['coste_max']:.3f}]")
    logger.info(f"  Media coste: {stats['coste_media']:.3f} ± {stats['coste_std']:.3f}")
    logger.info(f"  Celdas válidas: {stats['n_celdas_validas']} "
                f"({100*stats['n_celdas_validas']/coste_pendiente.size:.1f}%)")
    logger.info(f"  Barreras duras: {stats['n_barreras_duras']} celdas")

    # Ploteo (opcional)
    if plot:
        logger.info("\n[VISUALIZACIÓN]")
        fig, axes = plt.subplots(1, 3, figsize=(15, 4))

        # DEM
        im0 = axes[0].imshow(dem_data, cmap='terrain')
        axes[0].set_title('DEM (m)')
        plt.colorbar(im0, ax=axes[0])

        # Pendiente
        im1 = axes[1].imshow(pendiente_grados, cmap='RdYlGn_r', vmin=0, vmax=45)
        axes[1].set_title('Pendiente (grados)')
        plt.colorbar(im1, ax=axes[1])

        # Coste
        coste_plot = np.ma.masked_where(coste_pendiente == nodata_value, coste_pendiente)
        im2 = axes[2].imshow(coste_plot, cmap='viridis', vmin=0, vmax=1)
        axes[2].set_title('Coste Normalizado [0, 1]')
        plt.colorbar(im2, ax=axes[2])

        plt.tight_layout()
        plot_path = output_dir / f"pendiente_{corredor}_plot.png"
        plt.savefig(plot_path, dpi=100)
        logger.info(f"  Gráficos guardados: {plot_path}")
        plt.close()

    logger.info("\n" + "=" * 80)
    logger.info(f"✓ P1 COMPLETADO para Corredor {corredor.upper()}")
    logger.info("=" * 80)

    return {
        'coste': coste_pendiente,
        'pendiente_grados': pendiente_grados,
        'output_path': str(output_path),
        'stats': stats,
    }


# ============================================================================
# VALIDACIÓN (Contrato de Salida Obligatorio)
# ============================================================================

def validar_capa_pendiente(raster_path, dem_ref_path):
    """
    Valida que la capa de pendiente cumpla el contrato de salida (obligatorio).

    Comprueba:
      - CRS = EPSG:25830
      - Transform idéntico al DEM de referencia
      - Shape idéntico al DEM
      - dtype = float32
      - nodata = -9999.0
      - Rango [0, 1] para valores válidos
      - Compresión = LZW

    Lanza excepciones si alguna validación falla.
    """
    logger.info("\n[VALIDACIÓN — CONTRATO DE SALIDA]")

    with rasterio.open(dem_ref_path) as src_dem:
        dem_transform = src_dem.transform
        dem_shape = (src_dem.height, src_dem.width)
        dem_crs = src_dem.crs

    with rasterio.open(raster_path) as src:
        coste_data = src.read(1)
        coste_transform = src.transform
        coste_shape = (src.height, src.width)
        coste_crs = src.crs
        coste_dtype = src.dtypes[0]
        coste_nodata = src.nodata
        coste_profile = src.profile

    # Validaciones
    errors = []

    if coste_crs.to_epsg() != 25830:
        errors.append(f"❌ CRS: {coste_crs}, esperado EPSG:25830")
    else:
        logger.info(f"✓ CRS: {coste_crs} (EPSG:25830)")

    if coste_transform != dem_transform:
        errors.append(f"❌ Transform mismatch")
    else:
        logger.info(f"✓ Transform: coincide con DEM de referencia")

    if coste_shape != dem_shape:
        errors.append(f"❌ Shape mismatch: {coste_shape} vs {dem_shape}")
    else:
        logger.info(f"✓ Shape: {coste_shape} (coincide con DEM)")

    if coste_dtype != 'float32':
        errors.append(f"❌ dtype: {coste_dtype}, esperado float32")
    else:
        logger.info(f"✓ dtype: {coste_dtype}")

    if coste_nodata != -9999.0:
        errors.append(f"❌ nodata: {coste_nodata}, esperado -9999.0")
    else:
        logger.info(f"✓ nodata: {coste_nodata}")

    if coste_profile.get('compress') != 'lzw':
        logger.warning(f"⚠️ Compresión: {coste_profile.get('compress')}, se recomienda lzw")
    else:
        logger.info(f"✓ Compresión: lzw")

    # Rango
    coste_valido = coste_data[coste_data != -9999.0]
    if len(coste_valido) > 0:
        if coste_valido.min() < 0.0 or coste_valido.max() > 1.0:
            errors.append(
                f"❌ Rango fuera de [0, 1]: min={coste_valido.min():.4f}, "
                f"max={coste_valido.max():.4f}"
            )
        else:
            logger.info(f"✓ Rango: [{coste_valido.min():.3f}, {coste_valido.max():.3f}] ⊂ [0, 1]")
    else:
        logger.warning("⚠️ No hay valores válidos (todos nodata)")

    # Resumen
    logger.info(f"\n  Estadísticas finales:")
    logger.info(f"    Celdas válidas: {len(coste_valido)} / {coste_data.size} ({100*len(coste_valido)/coste_data.size:.1f}%)")
    logger.info(f"    Celdas nodata: {(coste_data == -9999.0).sum()}")

    if errors:
        logger.error("\n❌ VALIDACIÓN FALLIDA:")
        for err in errors:
            logger.error(f"  {err}")
        raise RuntimeError("Validación de contrato fallida")
    else:
        logger.info("\n✓ VALIDACIÓN EXITOSA — Capa aceptada")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    """
    Ejemplo de uso:

    python scripts/01_pendiente_opcion_B.py

    Procesa ambos corredores (A, B) con visualización.
    """

    # Validar curva primero
    validar_curva_mapeo()

    # Procesar Corredor A
    resultado_A = procesar_pendiente(
        corredor='A',
        metodo='np.gradient',  # 'np.gradient' o 'richdem'
        plot=True
    )

    # Validar salida
    validar_capa_pendiente(
        resultado_A['output_path'],
        'data/processed/rasters_aoi/dem_aoi_A.tif'
    )

    # Procesar Corredor B
    resultado_B = procesar_pendiente(
        corredor='B',
        metodo='np.gradient',
        plot=True
    )

    # Validar salida
    validar_capa_pendiente(
        resultado_B['output_path'],
        'data/processed/rasters_aoi/dem_aoi_B.tif'
    )

    logger.info("\n🎉 ¡Todo completado exitosamente!")
    logger.info(f"  Pendiente A: {resultado_A['output_path']}")
    logger.info(f"  Pendiente B: {resultado_B['output_path']}")
