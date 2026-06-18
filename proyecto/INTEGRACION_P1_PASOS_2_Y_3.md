# Integración P1 — Pendiente: Pasos 2 y 3 Completados

> **Fecha:** 18 de junio de 2026  
> **Estado:** Pasos 2 y 3 completados; Paso 1 (ejecución del script) bloqueado en DEM  
> **Próximo:** Generar DEM alineado para ejecutar script

---

## Resumen de Cambios

### ✅ Paso 2: Integración en `src/superficie/coste.py`

**Cambios realizados:**

1. **Importaciones actualizadas:**
   - Añadido `rasterio` (para cargar GeoTIFF)
   - Añadido `Path` (manejo de rutas)

2. **Función nueva: `cargar_coste_pendiente(corredor, ruta_capas)`**
   - Carga la capa pre-rasterizada `pendiente_{s}.tif` desde disco
   - Convierte marcador de disco (nodata = -9999.0) a memoria (∞)
   - Valida que el archivo exista; si no, da mensaje claro sobre cómo ejecutar script
   - **Uso:** `coste_pend = cargar_coste_pendiente('A')`

3. **Función `coste_pendiente()` ahora DEPRECADA:**
   - Mantiene compatibilidad pero advierte al usuario
   - Ya no intenta calcular bajo demanda; remite a `cargar_coste_pendiente()`
   - Justificación: reproducibilidad (pre-calcular es mejor)

4. **Función `combinar()` implementada COMPLETAMENTE:**
   - Era TODO, ahora implementada con validaciones robustas
   - Pasos:
     1. Valida que todas las capas tienen misma shape
     2. Valida que todos los pesos ≥ 0
     3. Valida que capas solicitadas existen
     4. Suma ponderada: `coste = Σ(capa_i × peso_i)`
     5. Propaga coste prohibido (∞)
   - **Uso:** `coste_multi = combinar(capas_dict, pesos_dict)`
   - Ejemplo incluido en docstring

**Archivo:** [`src/superficie/coste.py`](src/superficie/coste.py) (completamente refactorizado)

---

### ✅ Paso 3: Configuración de Perfiles en `data/config/perfiles.yaml`

**Cambios realizados:**

1. **Ampliación de perfiles (3 → 4 alternativas):**
   - `corto`: Minimiza longitud (pesos: longitud 1.0)
   - `ambiental`: Evita zonas protegidas (pesos: protegida 1.0)
   - `pendiente`: Terreno llano (pesos: pendiente 1.0)
   - **NUEVO** `equilibrio`: Balance recomendado (pesos medianos en todas)

2. **Mejora de estructura:**
   - Cada perfil tiene `id`, `nombre`, `descripcion`, `pesos`, `nota`
   - Pesos ordenados por importancia (arriba primero)
   - Notas explicativas del trade-off

3. **Sección nueva: `parametros_pendiente` (normativa)**
   - Curva por tramos completamente documentada (0°–5°, 5°–15°, 15°–30°, >30°)
   - Rango de coste para cada intervalo
   - Algoritmo: `np.gradient` (MVP 1-4) o `richdem` (futuro)
   - Reproducibilidad garantizada

4. **Sección ampliada: `diferenciacion`**
   - Ahora incluye `metodo: "corridor_masking"` explícito

**Archivo:** [`data/config/perfiles.yaml`](data/config/perfiles.yaml) (estructura expandida y documentada)

---

## Validación de Consistencia

| Aspecto | Estado | Verificación |
|---------|--------|---|
| **Capas en perfiles** | ✅ Consistentes | Todos los perfiles usan: pendiente, uso_suelo, protegida, longitud |
| **Pesos ≥ 0** | ✅ OK | Todos positivos o cero |
| **Suma pesos** | ⚠️ No normalizada | Intencionalmente: cada perfil puede tener Σ distinta (ajusta penalizaciones) |
| **Función combinar()** | ✅ Validada | Suma ponderada + propagación ∞ |
| **Carga de pendiente** | ✅ Implementada | `cargar_coste_pendiente()` lista |
| **Documentación** | ✅ Completa | Docstrings + comentarios inline |

---

## Cómo Usar (Después de Generar DEM Alineado)

### 1. Ejecutar script de pendiente (cuando tengas DEM alineado)

```bash
python scripts/01_pendiente_opcion_B.py
```

Genera: `data/processed/Capas_Coste/pendiente_A.tif` y `pendiente_B.tif`

### 2. Cargar en código

```python
from src.superficie.coste import cargar_coste_pendiente, combinar

# Cargar capa de pendiente
coste_pend = cargar_coste_pendiente('A')

# Cargar otras capas (uso_suelo, protegida, etc.)
# [Implementar P2-P5...]

# Combinar con perfil "equilibrio"
pesos_equilibrio = {
    'pendiente': 0.5,
    'protegida': 0.6,
    'uso_suelo': 0.4,
    'longitud': 0.5
}

coste_multicriterio = combinar(
    {
        'pendiente': coste_pend,
        'protegida': coste_prot,
        'uso_suelo': coste_uso,
        'longitud': coste_long
    },
    pesos_equilibrio
)

# Usar en LCP (A*/Dijkstra)
ruta = buscar_minimo_coste(coste_multicriterio, origen, destino)
```

---

## Estado de Implementación del Reto

### MVP 1-4 Progress

| Componente | P1-Pendiente | P2-Geotecnia | P3-Expropiación | P4-Protegida | P5-Cruces | LCP |
|---|---|---|---|---|---|---|
| **Especificación técnica** | ✅ | — | — | — | — | — |
| **Pre-rasterización** | 🔄 Bloqueado (DEM) | — | — | — | — | — |
| **Integración en código** | ✅ | — | — | — | — | — |
| **Configuración de pesos** | ✅ | — | — | — | — | — |
| **Validación automática** | ✅ | — | — | — | — | — |

---

## Checklist para MVP 1 (Hito 2)

- [x] Análisis técnico de pendiente completado (3 opciones + corrección dirección)
- [x] Especificación P1 (CAPAS_COSTE_P1_Pendiente.md)
- [x] Script 01_pendiente_opcion_B.py implementado
- [x] Integración en src/superficie/coste.py
- [x] Perfiles actualizados con pesos
- [ ] ⏳ DEM alineado a EPSG:25830 (bloqueador)
- [ ] Ejecutar script de pendiente
- [ ] Validar pendiente_A.tif y pendiente_B.tif
- [ ] Implementar P2-P5 (otras capas)

---

## Próximos Pasos

1. **Generar DEM alineado** (fuera de este workflow)
   - Descargar Copernicus GLO-30
   - Reproyectar a EPSG:25830
   - Crear `data/processed/rasters_aoi/dem_aoi_{A,B}.tif`

2. **Ejecutar script**
   ```bash
   python scripts/01_pendiente_opcion_B.py
   ```

3. **Validar salida**
   ```python
   from src.superficie.coste import validar_capa_pendiente
   validar_capa_pendiente('data/processed/Capas_Coste/pendiente_A.tif',
                          'data/processed/rasters_aoi/dem_aoi_A.tif')
   ```

4. **Continuar con P2-P5**
   - Seguir mismo formato y estructura
   - Implementar cargar_coste_*() para cada capa
   - Agregar en perfiles.yaml

---

**Documentos relacionados:**
- [`CAPAS_COSTE_P1_Pendiente.md`](CAPAS_COSTE_P1_Pendiente.md) — Especificación completa
- [`analisis_pendiente_alturas.md`](analisis_pendiente_alturas.md) — Análisis técnico (opciones + justificación)
- [`scripts/01_pendiente_opcion_B.py`](scripts/01_pendiente_opcion_B.py) — Implementación lista
- [`src/superficie/coste.py`](src/superficie/coste.py) — Integración en pipeline
- [`data/config/perfiles.yaml`](data/config/perfiles.yaml) — Configuración de pesos
