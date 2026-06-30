# Modelo de coste multicriterio — Hitos 2-4

> Documento unificado: **modelo teórico + guía de implementación**.
> Reemplaza `modelo_coste.md` y `coordinacion/Guia_Capas_Coste.docx`.
> Lectura previa: [`arquitectura.md`](arquitectura.md) · [`../docs/hitos_mvp.md`](../docs/hitos_mvp.md).

---

# Parte A — Modelo teórico

## 1. Principio: coste de *tránsito* vs coste de *cruce*

El **camino de mínimo coste** (LCP) se resuelve con **A\* o Dijkstra** sobre un **grafo de la rejilla**: cada celda es un nodo, con aristas a sus 8 vecinos (ver §8.1). El **coste por celda** = lo que cuesta atravesar ese píxel → peso de las aristas. La ruta paga ese coste en **todas** las celdas que recorre. Hay que distinguir dos naturalezas:

- **Coste de tránsito** — propiedad del terreno que se paga en *cada* celda recorrida: pendiente, uso del suelo, zona protegida.
- **Coste de cruce** — penalización **puntual** que se paga *una vez* al atravesar transversalmente una línea: carretera, ferrocarril, río.

| Familia | Variables | Naturaleza | Condicionante | Fuente |
|---|---|---|---|---|
| Tránsito continuo | pendiente | por celda | técnico | DEM |
| Tránsito discreto | expropiación | por celda | administrativo | Catastro |
| Tránsito discreto | Red Natura 2000 | por celda | ambiental | MITECO |
| Tránsito continuo | geotecnia | por celda | técnico/seguridad | IGME |
| Cruce puntual | carreteras, ferrocarril, ríos | al cruzar | técnico | OSM / IGN |

---

## 1.A Las seis dimensiones del trazado y su traducción a coste

| Dimensión | Dir. | Capas | Condicionante | Estado |
|---|---|---|---|---|
| Menor impacto ambiental | ↓ | protegida, hidrografía | ambiental | cubierto |
| Menores afecciones a terceros | ↓ | expropiacion (Catastro) | administrativo | cubierto |
| Menor complejidad técnica | ↓ | pendiente, cruces | técnico | cubierto |
| Menor coste total | ↓ | — (función objetivo) | — | es la salida |
| Mayor viabilidad administrativa | ↑ | suelo urbano consolidado | administrativo | parcial |
| Mayores seguridad y operabilidad | ↑ | geotecnia (IGME) | técnico/operacional | cubierto |

Cada perfil de prioridad (`data/config/perfiles.yaml`) sube el peso de la dimensión que prioriza → rutas diferenciadas (hito 3).

---

## 2. Reglas transversales

1. **Alinear antes de combinar.** Ninguna capa entra sin estar reproyectada a **EPSG:25830** y remuestreada a la **rejilla común**. La celda (i, j) debe representar el mismo trozo de terreno en todas las capas.
2. **Normalizar contra umbrales físicos FIJOS, nunca contra el min/max del AOI.** Si se normaliza con el máximo del AOI, el mismo terreno tendría coste distinto entre escenarios → resultados no comparables.
3. **Toda capa sale en el índice adimensional [0, 1].** El coste es relativo, nunca €.
4. **Barrera dura vs coste alto** son cosas distintas y deben decidirse explícitamente:
   - *Coste alto finito* → la ruta lo cruza si no hay alternativa.
   - *Barrera dura* (`inf` en memoria / `999.0` en disco) → el LCP la rodea siempre.
5. **Coste base de longitud** siempre presente y > 0: garantiza que la distancia cuente y que ninguna celda tenga coste 0.

---

## 3. Resolución y rejilla común

Resolución de trabajo: **30 m** (Copernicus GLO-30 DEM). Definida en `data/config/escenario.yaml`.

`dem_aoi_{s}.tif` es el **raster de referencia**: su `transform`, `width`, `height` y `CRS` son la fuente de verdad para todos los scripts de `src/superficie/`. NUNCA calcular la rejilla manualmente.

---

## 4. Pendiente

### 4.1 Función de coste (curva por tramos)

```
pendiente (°)    coste
0 – 5            0.0          zanja normal, trivial
5 – 15           0.0 → 0.6   rampa lineal
15 – 30          0.6 → 1.0   muy caro
> 30             barrera (inf / 999.0)
```

El **umbral de barrera dura está fijado en 30°**. Los cortes intermedios (5°/15°) son calibrables.

### 4.2 Terreno roto (opcional)

`std(pendiente)` en ventana 5×5 como capa adicional separada. No bloquea el hito 2.

---

## 5. Variables discretas

### 5.1 Expropiación parcelaria — Catastro

Columna `TIPO` de `catastro_aoi_{s}.gpkg`. Coste administrativo de ocupar el suelo.
Valores **estandarizados al factor oficial Enagás** `A / 38` (ver [`../docs/metodologia_enagas.md`](../docs/metodologia_enagas.md); urbano alta densidad A=25.25 → 0.66, periurbano/media densidad A=17.75 → 0.47).

| TIPO | Descripción | Coste | A oficial |
|------|-------------|-------|-----------|
| D | Dominio público | 0.03 | — |
| R | Rústico | 0.10 | — |
| X | Sin clasificar | 0.30 | — |
| R (<500 m²) | Periurbano (refinamiento opcional) | 0.47 | 17.75 |
| U | Urbano | 0.66 | 25.25 |
| Fondo (sin parcela) | Rústico por defecto | 0.10 | — |

### 5.2 Red Natura 2000

Variable binaria. El valor "dentro" está **estandarizado al factor oficial Enagás** RED NATURA 2000 (A=28.5 / 38 = 0.75); la magnitud final la modula además el peso de la capa en la combinación (§8).

| Situación | Valor | Tratamiento |
|-----------|-------|-------------|
| Fuera de zona protegida | 0.0 | finito |
| Dentro de Red Natura (ZEPA / LIC / ZEC) | 0.75 | finito (transitable con autorización; A=28.5) |
| Fondo (sin polígono) | 0.0 | — |

No hay barrera dura. Los km en zona protegida se reportan como métrica (hito 4).

### 5.2b Zonas inundables — SNCZI (MITECO)

Variable binaria. El valor "dentro" está **estandarizado al factor oficial Enagás** Zonas inundables (A=14.25 / 38 = 0.375; ver [`../docs/metodologia_enagas.md`](../docs/metodologia_enagas.md)). Igual patrón que Red Natura 2000 (§5.2): sin barrera dura, sin gradación por periodo de retorno — la capa fuente une T10+T100+T500 en la descarga (`src/ingesta/descargar_capas.py`) porque la tabla oficial solo da un factor para el condicionante "Zonas inundables", no uno por periodo de retorno.

| Situación | Valor | Tratamiento |
|-----------|-------|-------------|
| Fuera de lámina de inundación | 0.0 | finito |
| Dentro de lámina SNCZI (T10 ∪ T100 ∪ T500) | 0.375 | finito (transitable; A=14.25) |
| Fondo (sin polígono) | 0.0 | — |

No hay barrera dura. Los km en zona inundable se reportan como métrica (`src/metricas/zonas_inundables.py`).

---

## 6. Variables de cruce

### 6.1 Coste puntual por tipo

**Viario — OSM, columna `highway`:**

| Tipo | Coste |
|------|-------|
| `path`, `track`, `footway` | 0.2 |
| `service`, `unclassified` | 0.3 |
| `residential` | 0.4 |
| `tertiary` | 0.5 |
| `secondary` | 0.6 |
| `primary` | 0.7 |
| `trunk`, `motorway` | 0.8 |
| `railway` (`rail`) | 0.9 |
| No listado | 0.3 |

**Hidrografía — IGN, columnas `text` y `length`** (estandarizada al factor oficial Enagás `A / 38`: curso permanente A=13 → 0.34, no permanente A=9.75 → 0.26):

| Criterio | Coste | A oficial |
|----------|-------|-----------|
| Sin nombre (rambla / no permanente) | 0.26 | 9.75 |
| Con nombre, length ≤ 2000 m (río menor) | 0.30 | — (interpolado) |
| Con nombre, length > 2000 m (río principal/permanente) | 0.34 | 13 |

Fusión OSM + HID: **máximo por celda**. Líneas rasterizadas a 1 celda (`all_touched=True`). Fondo: 0.0.

### 6.2 Cómo entra un cruce en la superficie

La ruta paga al atravesar **perpendicularmente** la línea (≈ 1 celda). No se bufferiza: bufferizar penalizaría la proximidad, no el cruce.

---

## 6.A Geotecnia y seguridad

**IGME MAGNA 50, campo `DLO` (descripción litológica).** Valores **estandarizados al factor oficial Enagás** `A / 38` (terrenos inestables A=38 → 1.00 fija el techo; roca dura A=13 → 0.34):

| Litología (DLO contiene...) | Coste | A oficial |
|-----------------------------|-------|-----------|
| Aluvial / terrazas recientes (fácil) | 0.05 | — |
| Sedimento fino (limos, margas) | 0.10 | — |
| Arcillas blandas | 0.15 | — |
| Arenisca compacta | 0.22 | — |
| Conglomerados | 0.28 | — |
| Calizas, dolomías, roca dura | 0.34 | 13 |
| Yeso (inestable / expansivo) | 1.00 | 38 |
| No clasificado / sin dato | 0.15 | — (defecto) |
| Fondo (sin polígono IGME) | 0.15 | — (defecto) |

---

## 7. Coste base de longitud

`BASE_LONG = 1.0` — constante en todas las celdas. Sin él, una zona de coste 0 dejaría al solver serpentear "gratis". Sumarlo **siempre** a la superficie combinada.

---

## 8. Combinación y perfiles

Para cada perfil *p* (`data/config/perfiles.yaml`):

```
coste_total(i,j) = BASE_LONG        · w_longitud
                 + pendiente(i,j)    · w_pendiente
                 + expropiacion(i,j) · w_expropiacion
                 + protegida(i,j)    · w_protegida
                 + inundable(i,j)    · w_inundable
                 + cruces(i,j)       · w_cruces
                 + geotecnia(i,j)    · w_geotecnia
```

**Primera iteración (pesos iguales):** `w = 1/n` para cada capa + `BASE_LONG = 1.0`.
Generada por `src/superficie/combinar.py` → `Trazados/superficie_{s}.tif`. Rango típico: [1.06, 1.73] *(medido antes de la recalibración A de §5–§6.A; recalcular tras regenerar las capas)*.

### 8.1 Del raster al grafo (A\*)

- **Nodos:** una celda = un nodo. Celdas barrera (`999.0`) no generan nodo.
- **Aristas:** 8 vecinos. Distancia × `resolucion_m`.
- **Peso de arista** = distancia × **media del coste** de las dos celdas.
- **Heurística A\*** (admisible): distancia euclídea × coste mínimo de celda.

---

## 9. Decisiones cerradas

| Tema | Decisión |
|------|----------|
| Barrera de pendiente | 30° → `inf` en memoria, `999.0` en disco |
| Red Natura | Variable binaria transitable (0 / 0.75; A=28.5/38). No barrera. |
| Zonas inundables | Variable binaria transitable (0 / 0.375; A=14.25/38). No barrera; sin gradación por periodo de retorno. |
| Urbano consolidado | Coste 0.66 finito (A=25.25/38). No barrera. |
| Cruces | Rasterización fina 1 celda (`all_touched=True`) + conteo en métricas |
| Doble conteo urbano | No hay en MVP: solo lo lleva Catastro |
| Solver | A\* (Dijkstra solo como respaldo) |
| Peso de arista | Media del coste de las dos celdas |
| Conectividad | 8 vecinos |
| Barreras en disco | `999.0`; nodata fuera del AOI: `-9999.0` |

---

## 10. Calibración

Los valores intra-capa de §5–§6.A están **anclados a los factores de ponderación oficiales de Enagás** (`coste = A / 38`, con A_REF=38 = terrenos inestables; ver [`../docs/metodologia_enagas.md`](../docs/metodologia_enagas.md)), de modo que se preserva la jerarquía oficial entre condicionantes y toda capa queda en [0, 1]. La pendiente queda fuera de este anclaje (curva por tramos propia, §4). Siguen siendo calibrables con el caso real: cuando Enagás facilite un ramal existente → **backtesting** (hito 4/6). Registrar cambios en [`../coordinacion/seguimiento.md`](../coordinacion/seguimiento.md).

---

# Parte B — Guía de implementación

## 11. Flujo de trabajo común (5 pasos)

Todos los scripts de `src/superficie/` siguen exactamente este patrón.

**Paso 1 — Leer la rejilla de referencia**

```python
import rasterio
with rasterio.open(f"data/processed/Recorte_AOI/dem_aoi_{s}.tif") as src:
    transform = src.transform
    width, height = src.width, src.height
    profile = src.profile.copy()
```

**Paso 2 — Asignar coste por atributo**

Añadir columna `cost` al GeoDataFrame según la tabla de lookup de §5–§6.A.

**Paso 3 — Rasterizar sobre la rejilla**

```python
from rasterio.features import rasterize
arr = rasterize(
    shapes=((geom, cost) for geom, cost in zip(gdf.geometry, gdf["cost"])),
    out_shape=(height, width),
    transform=transform,
    fill=0.0,
    dtype="float32",
    all_touched=False,   # polígonos
    # all_touched=True,  # líneas (OSM, HID)
)
```

**Paso 4 — Rellenar fondo**

```python
arr = np.where(arr == 0.0, FONDO, arr)
```

**Paso 5 — Guardar**

```python
profile.update(driver="GTiff", dtype="float32", count=1,
               nodata=-9999.0, compress="lzw", tiled=False)
for key in ("blockxsize", "blockysize"):
    profile.pop(key, None)
with rasterio.open(out_path, "w", **profile) as dst:
    dst.write(arr, 1)
```

---

## 12. Detalle por capa

| Capa | Script | Fuente | Columna | all_touched | Fondo |
|------|--------|--------|---------|-------------|-------|
| `pendiente_{s}.tif` | `pendiente.py` | `dem_aoi_{s}.tif` | — (array) | — | no aplica |
| `geotecnia_{s}.tif` | `geotecnia.py` | `igme_aoi_{s}.gpkg` | `DLO` | False | 0.15 |
| `expropiacion_{s}.tif` | `expropiacion.py` | `catastro_aoi_{s}.gpkg` | `TIPO` | False | 0.10 |
| `protegida_{s}.tif` | `zonas_protegidas.py` | `natura2000_aoi_{s}.gpkg` | `TIPO` | False | 0.0 |
| `inundable_{s}.tif` | `zonas_inundables.py` | `inundable_aoi_{s}.gpkg` | — (geometría) | False | 0.0 |
| `cruces_{s}.tif` | `cruces_viario_rios.py` | `osm_aoi_{s}.gpkg` + `hidrografia_aoi_{s}.gpkg` | `highway` / `text`+`length` | True | 0.0 |
| `superficie_{s}.tif` | `combinar.py` | todas las anteriores | — | — | — |

---

## 13. Contrato de salida obligatorio

| Parámetro | Capas individuales | Superficie combinada |
|-----------|-------------------|----------------------|
| CRS | EPSG:25830 | EPSG:25830 |
| Transform | = `dem_aoi_{s}.tif` | = `dem_aoi_{s}.tif` |
| Shape | = `dem_aoi_{s}.tif` | = `dem_aoi_{s}.tif` |
| dtype | float32 | float32 |
| nodata (fuera AOI) | -9999.0 | -9999.0 |
| Rango válido | [0.0, 1.0] | [BASE_LONG, BASE_LONG + n] |
| Barrera dura | 999.0 | 999.0 |
| compress | lzw | lzw |
| Acompañamiento | `.qml` en misma carpeta | `.qml` en misma carpeta |

Si la capa no tiene datos en el AOI: guardar igualmente el raster de fondo completo.

---

## 14. Regla crítica: normalización por umbrales fijos

**Incorrecto (data-driven):**
```python
cost = (slope - slope.min()) / (slope.max() - slope.min())
# El mismo terreno de 20° tendría coste diferente en A que en B.
```

**Correcto (umbrales fijos):**
```python
cost = np.clip((slope - 5) / 10 * 0.6, 0, 0.6)   # tramo 5–15°
# Los 20° siempre cuestan lo mismo, independientemente del AOI.
```

Esta regla aplica a todas las tablas de lookup (§5, §6, §6.A).
