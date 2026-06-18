# FICHA TÉCNICA — Capa P1: Pendiente (Opción B — Pre-calculada)

> Especificación técnica de la capa de pendiente según la **Guía de Capas de Coste** y alineada con la **Opción B del Análisis Técnico** (pendientes pre-calculadas, isotrópicas, con curva por tramos normativa).
>
> **Fecha:** 18 de junio de 2026  
> **Estado:** Especificación cerrada (implementación en `scripts/01_pendiente_opcion_B.py`)  
> **Validación:** Contrato de salida obligatorio

---

## 1. Descripción General

**Objetivo:** Convertir el DEM nativo (Copernicus GLO-30, 30m resolución) en una capa de **coste de pendiente** normalizado [0, 1], aplicando una **curva por tramos fija (normativa)** que no depende de los datos observados en el AOI.

**Enfoque:** Opción B — Pendientes pre-calculadas (isotrópicas). La dirección del gradiente no se captura; solo la magnitud, como aproximación aceptable para MVP 1-4.

---

## 2. Fuente de Datos

| Parámetro | Valor |
|-----------|-------|
| **Input archivo** | `data/processed/rasters_aoi/dem_aoi_{s}.tif` |
| **Formato input** | GeoTIFF, float32, EPSG:25830 (alineado) |
| **Resolución** | 30m (nativo Copernicus GLO-30) |
| **Cobertura** | Total sobre AOI (sin nodata) |
| **Validación previa** | Debe estar reproyectado a EPSG:25830 y alineado a rejilla común |

---

## 3. Pasos de Procesamiento

### Paso 1: Leer Rejilla de Referencia

**Entrada:** DEM alineado (`dem_aoi_{s}.tif`)

**Acción:**
```python
import rasterio
import numpy as np

# Abrir DEM como referencia
with rasterio.open(f"data/processed/rasters_aoi/dem_aoi_{s}.tif") as src_dem:
    dem_data = src_dem.read(1)  # banda 1
    transform = src_dem.transform
    width = src_dem.width
    height = src_dem.height
    crs = src_dem.crs  # Debe ser EPSG:25830
    
    # Validaciones
    assert crs.to_epsg() == 25830, f"CRS incorrecto: {crs}"
    print(f"DEM shape: {dem_data.shape} | Transform: {transform} | CRS: {crs}")
```

**Output:** Parámetros de la rejilla de salida (`transform`, `width`, `height`, `crs`).

---

### Paso 2: Calcular Pendiente (Método Horn o np.gradient)

**Concepto:** Derivar la pendiente en grados a partir del DEM nativo.

#### Opción 2A: Horn (recomendado, robusto)
```python
import richdem as rd

# Cargar DEM como análisis de richdem
dem_rd = rd.LoadElevation(dem_data)
rd.ResolveFlats(dem_rd)  # Resolver terrazas planas
pendiente_grados = rd.SurfaceDerivative(dem_rd, "slope")  # en grados
```

#### Opción 2B: np.gradient (más rápido, aceptable para MVP)
```python
# Calcular gradientes en dirección Y (norte-sur) y X (este-oeste)
pixelsize_m = 30  # resolución en metros
dz_dy, dz_dx = np.gradient(dem_data, pixelsize_m, pixelsize_m)

# Calcular magnitud de la pendiente
pendiente_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
pendiente_grados = np.degrees(pendiente_rad)
```

**Recomendación para MVP 1-4:** Usar **Opción 2B (np.gradient)** por rapidez. Cambiar a Horn (2A) en MVP 5-6 como mejora.

**Output:** Raster `pendiente_grados` con misma shape que DEM [degrees].

---

### Paso 3: Aplicar Curva por Tramos (Mapeo a Coste Normalizado)

**Concepto:** Convertir pendiente en grados → coste en [0, 1], con barrera dura en 30°.

**Tabla normativa (FIJA, no data-driven):**

| Rango pendiente | Coste | Fórmula |
|---|---|---|
| 0° – 5° | 0.0 | `0.0` |
| 5° – 15° | 0.0 → 0.6 | `0.6 × (pend - 5) / 10` |
| 15° – 30° | 0.6 → 1.0 | `0.6 + 0.4 × (pend - 15) / 15` |
| > 30° | **∞ (barrera dura)** | `np.inf` → guardado como `nodata` |

**Implementación:**

```python
def mapeo_coste_pendiente(pendiente_grados):
    """
    Mapea pendiente en grados → coste normalizado [0, 1].
    
    Parámetros:
        pendiente_grados: float o array
    
    Retorna:
        coste: float o array en [0, 1] ∪ {∞}
    
    Notas:
        - Umbrales FIJOS (0, 5, 15, 30): no dependen de datos del AOI
        - Barrera dura a >30°: coste = ∞ (intransitable)
        - Reproducibilidad garantizada entre escenarios
    """
    if np.isscalar(pendiente_grados):
        if pendiente_grados <= 5:
            return 0.0
        elif pendiente_grados <= 15:
            return 0.6 * (pendiente_grados - 5) / 10
        elif pendiente_grados <= 30:
            return 0.6 + 0.4 * (pendiente_grados - 15) / 15
        else:
            return np.inf
    else:
        # Versión vectorizada para arrays
        coste = np.zeros_like(pendiente_grados)
        
        # Rango 1: 0-5°
        mask1 = pendiente_grados <= 5
        coste[mask1] = 0.0
        
        # Rango 2: 5-15°
        mask2 = (pendiente_grados > 5) & (pendiente_grados <= 15)
        coste[mask2] = 0.6 * (pendiente_grados[mask2] - 5) / 10
        
        # Rango 3: 15-30°
        mask3 = (pendiente_grados > 15) & (pendiente_grados <= 30)
        coste[mask3] = 0.6 + 0.4 * (pendiente_grados[mask3] - 15) / 15
        
        # Rango 4: >30° (barrera dura)
        mask4 = pendiente_grados > 30
        coste[mask4] = np.inf
        
        return coste

# Aplicar vectorizado
coste_pendiente = mapeo_coste_pendiente(pendiente_grados)
```

**Validación:**
```python
# Verificar que los costes cumplen la curva
print(f"Coste(0°) = {mapeo_coste_pendiente(0)}; esperado = 0.0")
print(f"Coste(5°) = {mapeo_coste_pendiente(5)}; esperado = 0.0")
print(f"Coste(10°) = {mapeo_coste_pendiente(10)}; esperado = 0.3")
print(f"Coste(15°) = {mapeo_coste_pendiente(15)}; esperado = 0.6")
print(f"Coste(22.5°) = {mapeo_coste_pendiente(22.5)}; esperado = 0.8")
print(f"Coste(30°) = {mapeo_coste_pendiente(30)}; esperado = 1.0")
print(f"Coste(31°) = {mapeo_coste_pendiente(31)}; esperado = inf")

# Contar barreras duras (infinito)
n_barriers = np.sum(np.isinf(coste_pendiente))
print(f"Celdas intransitables (>30°): {n_barriers} de {coste_pendiente.size}")
```

**Output:** Raster `coste_pendiente` [0, 1] ∪ {∞} con misma shape que DEM.

---

### Paso 4: Reemplazar Infinito por Nodata

**Concepto:** En memoria usamos `np.inf` para representar barreras duras. En disco (GeoTIFF), se guardan como `nodata = -9999.0`.

```python
# Reemplazar infinito por un marcador temporal
coste_pendiente[np.isinf(coste_pendiente)] = -9999.0
```

---

### Paso 5: Guardar Raster (Contrato de Salida Obligatorio)

**Ruta de salida:** `data/processed/Capas_Coste/pendiente_{s}.tif`

**Parámetros (obligatorios, no negociables):**

```python
output_path = f"data/processed/Capas_Coste/pendiente_{s}.tif"

# Metadatos del GeoTIFF
profile = {
    'driver': 'GTiff',
    'dtype': 'float32',
    'width': width,
    'height': height,
    'count': 1,  # una banda
    'crs': crs,  # EPSG:25830
    'transform': transform,
    'nodata': -9999.0,  # marcador de barrera dura
    'compress': 'lzw',  # compresión sin pérdida
    'TILED': 'YES',
    'BLOCKXSIZE': 256,
    'BLOCKYSIZE': 256
}

# Escribir
with rasterio.open(output_path, 'w', **profile) as dst:
    dst.write(coste_pendiente.astype('float32'), 1)

print(f"✓ Guardado: {output_path}")
```

---

## 4. Validación (Contrato de Salida)

**Obligatorio: Validar antes de considerar la capa como aceptada.**

| Parámetro | Validación | Fallo = |
|-----------|-----------|---------|
| **CRS** | Debe ser EPSG:25830 | ❌ Recalcular |
| **Transform** | Idéntico a `dem_aoi_{s}.tif` | ❌ Recalcular |
| **Shape** | Mismo (H, W) que DEM | ❌ Recalcular |
| **dtype** | float32 | ❌ Recalcular |
| **nodata en disco** | -9999.0 exacto | ❌ Validar manualmente |
| **Rango [0, 1]** | Todos los valores en [0.0, 1.0] ∪ {-9999.0} | ⚠️ Revisar con 5% de tolerancia |
| **Barreras duras** | -9999.0 aparece solo en celdas >30° originales | ✓ Información útil |
| **Compresión** | LZW | ✓ Tamaño típico ~5-8 MB |

**Script de validación:**

```python
def validar_capa_pendiente(raster_path, dem_ref_path):
    """Valida que la capa de pendiente cumpla el contrato de salida."""
    
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
        coste_compress = src.tags().get('compress', 'unknown')
    
    # Validaciones
    assert coste_crs.to_epsg() == 25830, f"❌ CRS: {coste_crs}, expected EPSG:25830"
    assert coste_transform == dem_transform, f"❌ Transform mismatch"
    assert coste_shape == dem_shape, f"❌ Shape mismatch: {coste_shape} vs {dem_shape}"
    assert coste_dtype == 'float32', f"❌ dtype: {coste_dtype}, expected float32"
    assert coste_nodata == -9999.0, f"❌ nodata: {coste_nodata}, expected -9999.0"
    
    # Estadísticas
    coste_valid = coste_data[coste_data != -9999.0]
    print(f"✓ CRS: {coste_crs} (EPSG:25830)")
    print(f"✓ Transform: {coste_transform}")
    print(f"✓ Shape: {coste_shape}")
    print(f"✓ dtype: {coste_dtype}")
    print(f"✓ nodata: {coste_nodata}")
    print(f"✓ Compresión: {coste_compress}")
    print(f"  Valores válidos: {len(coste_valid)} / {coste_data.size} celdas ({100*len(coste_valid)/coste_data.size:.1f}%)")
    print(f"  Rango coste: [{coste_valid.min():.3f}, {coste_valid.max():.3f}]")
    print(f"  Barreras duras (nodata): {np.sum(coste_data == -9999.0)} celdas")
    
    if coste_valid.min() < 0.0 or coste_valid.max() > 1.0:
        print(f"⚠️ ADVERTENCIA: Coste fuera de [0, 1]")

validar_capa_pendiente(f"data/processed/Capas_Coste/pendiente_{s}.tif",
                       f"data/processed/rasters_aoi/dem_aoi_{s}.tif")
```

---

## 5. Reproducibilidad y Comparabilidad

**Principio crítico:** Los umbrales de la curva (0°, 5°, 15°, 30°) son **FIJOS y nunca cambian**, independientemente del AOI o del escenario.

**Consecuencias:**

- ✅ Una pendiente de 20° siempre cuesta 0.8 (dentro de [15°, 30°]).
- ✅ Dos ejecuciones con mismo AOI producen **idéntica salida bit-a-bit**.
- ✅ La capa es reproducible y versionable.
- ✅ El backtesting es posible (comparar ruta real vs generada).

**Garantía:** Si cambias AOI (Corredor A → B), la capa `pendiente_B.tif` tiene costes comparables con `pendiente_A.tif` (no dependen de max/min del corredor).

---

## 6. Decisiones de Diseño (Opción B vs Alternativas)

### ¿Por qué Opción B (pre-calculada, isotrópica)?

| Aspecto | Opción B | Opción C (anisotrópica) |
|--------|----------|---|
| **Dirección capturada** | ❌ No (magnitude solo) | ✅ Sí (pendiente efectiva = mag × cos(angle)) |
| **Complejidad LCP** | Baja (A*/Dijkstra) | Alta (r.walk GRASS) |
| **Velocidad búsqueda** | ~< 1s | ~3-5s (más lento) |
| **Reproducibilidad** | 100% determinista | 100% determinista |
| **Realismo físico** | ~70% | ~95% |
| **Para MVP 1-4** | ✅ **RECOMENDADO** | ⚠️ Futuro si backtesting falla |

### Cuándo cambiar a Opción C

1. **Backtesting (MVP 4):** Si la ruta real aparece pero desplazada sistemáticamente hacia pendientes menores, la anisotropía podría ayudar.
2. **Solicitud de Enagás:** Si dicen *"es crucial capturar subida vs bajada"*.
3. **Presupuesto disponible:** Si sobra tiempo en MVP 1-4 (implementable en 3-4 semanas).

---

## 7. Integración en el Pipeline

**Posición en el DAG:**

```
dem_aoi_{s}.tif
    ↓ [P1: scripts/01_pendiente_opcion_B.py]
pendiente_{s}.tif (coste normalizado [0, 1])
    ↓ [Combinación multicriterio: scripts/04_superficie_coste.py]
coste_multicriterio_{s}.tif (con otros pesos: geotecnia, expropiación, etc.)
    ↓ [LCP: A*/Dijkstra en src/trazados/lcp.py]
ruta_{perfil}_{s}.shp
```

**Archivos dependientes:**

- `src/superficie/coste.py` — debe cargar `pendiente_{s}.tif` y aplicar peso `w_pendiente`
- `data/config/perfiles.yaml` — debe definir `w_pendiente` por perfil
- `tests/test_alineacion.py` — debe incluir test de validación de P1

---

## 8. Anexo: Parámetros por Escenario

### Corredor A (Zona de prueba inicial)

| Parámetro | Valor |
|-----------|-------|
| **AOI** | `aoi_corredor_A.gpkg` |
| **DEM input** | `data/raw/dem_aoi_A.tif` |
| **DEM processed** | `data/processed/rasters_aoi/dem_aoi_A.tif` |
| **Pendiente output** | `data/processed/Capas_Coste/pendiente_A.tif` |
| **Rasterio metadata** | Ver perfil en §5 |

### Corredor B (Validación/backtesting)

| Parámetro | Valor |
|-----------|-------|
| **AOI** | `aoi_corredor_B.gpkg` |
| **DEM input** | `data/raw/dem_aoi_B.tif` |
| **DEM processed** | `data/processed/rasters_aoi/dem_aoi_B.tif` |
| **Pendiente output** | `data/processed/Capas_Coste/pendiente_B.tif` |
| **Rasterio metadata** | Idéntico a Corredor A |

---

## 9. Verificación Final (Checklist)

Antes de considerar P1 como **completado y aceptado**:

- [ ] Script `scripts/01_pendiente_opcion_B.py` implementado y testeado
- [ ] `pendiente_A.tif` generado y validado contra contrato
- [ ] `pendiente_B.tif` generado y validado contra contrato
- [ ] Ambas capas tienen **idéntica curva**, umbrales FIJOS
- [ ] Tests en `tests/test_alineacion.py` pasan (alineación, CRS, rango)
- [ ] Documentación actualizada en `CAPAS_COSTE_P1_Pendiente.md` (este archivo)
- [ ] Integración en `src/superficie/coste.py` completada
- [ ] Perfiles en `data/config/perfiles.yaml` definen pesos de pendiente
- [ ] Repositorio versionado (commit con tag "P1-completado")

---

**Documento redactado:** 18 de junio de 2026  
**Especificación:** Cerrada (no cambios sin revisión)  
**Implementación:** Ver `scripts/01_pendiente_opcion_B.py`  
**Validación:** Contrato obligatorio (§4)
