# Arquitectura — Generación automatizada de trazados

> Diseño técnico del prototipo. Lectura previa: [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md).

## Principio de diseño

**Pipeline geoespacial determinista: alinear antes de combinar, diferenciar antes de comparar.**

Todo el cálculo es reproducible y auditable: las capas se alinean a un CRS y rejilla comunes, se convierten en superficies de coste con pesos explícitos (perfiles), y las rutas se obtienen por camino de mínimo coste. No hay estimación económica: el coste es un **índice relativo**. No hay una única "óptima": se generan **varias alternativas diferenciadas** para decidir.

## Diagrama de componentes

```
   origen + destino + AOI
                          │
        ┌─────────────────▼──────────────────┐
        │   1. INGESTA  (src/ingesta/)        │
        │   · descarga / recorte al AOI       │
        │   · reproyección a EPSG:25830       │
        │   · remuestreo a rejilla común      │
        │   · rasterización de vectores       │
        └─────────────────┬──────────────────┘
                          │ capas alineadas (mismo CRS y rejilla)
        ┌─────────────────▼──────────────────┐     ┌───────────────────────┐
        │   2. SUPERFICIES DE COSTE           │◀────│  perfiles de prioridad │
        │      (src/superficie/)              │     │  (vectores de pesos)   │
        │   · capa → coste por celda          │     │  data/config/          │
        │   · combinación multicriterio       │     └───────────────────────┘
        └─────────────────┬──────────────────┘
                          │ una superficie de coste por perfil
        ┌─────────────────▼──────────────────┐
        │   3. MOTOR LCP  (src/trazados/)     │
        │   · camino de mínimo coste          │
        │     (Dijkstra 8-conexo propio)      │
        │   · diferenciación por perfiles +   │
        │     validación de solapamiento      │
        └─────────────────┬──────────────────┘
                          │ 4 rutas diferenciadas (validadas)
        ┌─────────────────▼──────────────────┐
        │   4. MÉTRICAS  (src/metricas/)      │
        │   longitud · coste relativo · cruces│
        │   km protegida · km urbana · pend.  │
        └─────────────────┬──────────────────┘
                          │ métricas por ruta
        ┌─────────────────▼──────────────────┐
        │   5. COMPARATIVA  (src/comparacion/)│
        │   tabla multicriterio + scoring     │
        │   + mapa (folium)                   │
        └─────────────────┬──────────────────┘
                          ▼
        Interfaz (src/app/ — CLI / Streamlit): mapa + tabla de las 3-5 rutas
```

## Componentes

### 1. Ingesta (`src/ingesta/`)
Dado el origen y el destino (≤ 15 km), **descarga automáticamente a `data/raw/` la unidad mínima** de cada fuente que cubre el AOI (DEM Copernicus GLO-30, OSM vía Overpass, hidrografía IGN vía WFS, IGME vía ArcGIS REST, zonas inundables SNCZI vía OGC API Features). **Red Natura 2000 y Catastro no tienen servicio por bbox fiable y se colocan a mano** en `data/raw/RN2000/` y `data/raw/Catastro/`. Un manifiesto de estado por capa (`manifiesto_estado.json`) distingue "descargada", "AOI sin cobertura" y "descarga fallida".

Después **recorta al AOI**, **reproyecta a EPSG:25830** y **remuestrea a la rejilla común** (anclada a una malla global, misma resolución y origen de celda). Cadena de carpetas en `data/processed/`:

- **`Recorte_AOI/`** — el recorte alineado del AOI: capas vectoriales (`.gpkg`, vacías si sin datos) y el DEM (`.tif`).
- **`Capas_Coste/`** — una capa de coste `[0,1]` por criterio (las genera `src/superficie/`).
- **`Trazados/`** — superficies de coste combinadas: la neutral (`superficie_{s}.tif`, pesos iguales, referencia del coste relativo) y una por perfil. **Se regeneran en cada ejecución.**
- **`Rutas/`** — rutas LCP por perfil (`.gpkg`). **Se regeneran en cada ejecución.**

Librerías: `rasterio` (raster, reproyección, remuestreo), `geopandas`/`shapely` (vectores), `pyproj` (CRS), `requests` (Overpass/WFS/REST).

> **Regla de oro:** una capa no avanza al paso 2 si no comparte CRS y rejilla con las demás. La celda (i, j) debe representar el mismo trozo de terreno en todas las capas.

### 2. Superficies de coste (`src/superficie/`)
Convierte cada capa alineada en un **coste por celda** (p.ej. relieve vía TPI → cresta barata / valle caro, con barrera dura de pendiente >70 %; suelo urbano → coste alto; Red Natura 2000 → **variable binaria** dentro/fuera, con su penalización fijada por el peso; proximidad a cruces → coste). Combina las capas con un **vector de pesos** en una única superficie de coste. Cada **perfil de prioridad** (definido en `data/config/perfiles.yaml`) produce una superficie distinta.

> Diseño detallado de las funciones de coste por variable, umbrales y matriz de condicionantes en [`modelo_coste.md`](modelo_coste.md).

### 3. Motor de camino de mínimo coste (`src/trazados/`)
Sobre la superficie de coste de cada perfil calcula el **camino de mínimo coste** origen→destino con **Dijkstra 8-conexo isótropo** (implementación propia con `heapq` en `ruta_pendiente.py`; cada celda = nodo, coste de paso `d · media(C_p, C_q)` con `d` = 1 ortogonal / √2 diagonal). Las celdas nodata (fuera del AOI o barrera dura de pendiente) son intransitables.

La **diferenciación** de las 4 alternativas nace de los **perfiles de prioridad** (pesos distintos → superficies distintas → rutas distintas) y se **valida a posteriori** midiendo el solapamiento entre corredores (`metricas/diversidad_corredores.py`: buffer 60 m, umbral 50 %). **Decisión de diseño:** no se aplica penalización algorítmica (corridor masking) porque las rutas por perfil resultan suficientemente distintas; si un par supera el umbral, se reporta como redundante para que el usuario revise los pesos.

### 4. Métricas (`src/metricas/`)
Para cada ruta calcula: **longitud** (km), **coste relativo** (suma normalizada de celdas atravesadas), **cruces especiales** (nº y tipo: río, carretera, ferrocarril…), **km en zona protegida** (Red Natura 2000), **km en zona urbana/periurbana** (catastro) y **pendiente máxima y media** (del DEM a lo largo de la ruta).

> **Nota histórica — clasificación de suelo urbano:** inicialmente se planteó usar **CLC (Corine Land Cover)** como fuente de los usos del suelo. Al integrarla se vio que el **catastro** ofrece la misma información de forma más rigurosa (parcela a parcela, frente a los polígonos gruesos ≥25 ha de CLC) y con clasificación urbano/rústico directa. Por eso el pipeline usa catastro y la capa CLC se retiró de la ingesta.

### 5. Comparativa (`src/comparacion/`)
Reúne las métricas de las 3-5 rutas en una **tabla multicriterio**, calcula un **scoring/ranking** (por criterio o agregado ponderado) y genera el **mapa** con las rutas diferenciadas (`folium` / `contextily`).

### 6. Orquestador / Interfaz (`src/app/`)
Lee el caso de estudio de `data/config/`, ejecuta el pipeline para cada perfil y compone la salida (tabla + mapa) en **CLI** y/o **Streamlit**.

## Contrato de datos

### Caso de estudio — `data/config/escenario.yaml`
Multi-escenario: la herramienta guarda por defecto los escenarios `A` y `B`, y la app puede crear otros (`C`, …). El AOI no se declara: se deriva de la línea origen→destino con 1 km de semiancho perpendicular (rectángulo orientado).
```yaml
crs_trabajo: EPSG:25830            # CRS común (península)
resolucion_m: 30                   # tamaño de celda de la rejilla común (m)
escenario_A:
  origen:                          # punto de origen
    nombre: A_inicial
    x: 741453
    y: 4561984
  destino:                         # conexión a red troncal
    nombre: A_final
    x: 739098
    y: 4550264
escenario_B:
  # ... misma estructura
```

### Perfil de prioridad — `data/config/perfiles.yaml`
```yaml
- id: corto
  nombre: "Más corto"
  pesos:                            # peso por capa de coste (adimensional)
    tpi: 0.2                        # relieve (posición topográfica)
    expropiacion: 0.2              # usos del suelo (catastro)
    protegida: 0.3
    longitud: 1.5
- id: ambiental
  nombre: "Menor impacto ambiental"
  pesos:
    tpi: 0.3
    expropiacion: 0.5
    protegida: 1.5
    longitud: 0.3
- id: pendiente
  nombre: "Por relieve (divisorias / TPI)"
  pesos:
    tpi: 1.5                        # sigue crestas/divisorias; barrera >70% dentro del TPI
    geotecnia: 0.8
    protegida: 0.4
    longitud: 0.3
```

### Métricas por ruta (salida — `metricas.calculo.MetricasRuta.to_dict()`)
```python
{
  "escenario": "A",
  "perfil": "ambiental",
  "longitud_km": 0.0,
  "coste_relativo": 0.0,           # índice [0,1] sobre la superficie neutral, NUNCA €
  "pendiente_max_pct": 0.0,
  "pendiente_media_pct": 0.0,
  "km_protegida": 0.0, "pct_protegida": 0.0,
  "km_inundable": 0.0, "pct_inundable": 0.0,
  "km_suelo_urbano": 0.0, "km_suelo_diseminado": 0.0,
  "km_suelo_rustico": 0.0, "km_suelo_especial": 0.0,
  "n_cruces_rios": 0, "n_cruces_carreteras": 0,
  "n_cruces_ferrocarril": 0,       # None = no comprobable (≠ 0 = "comprobado, no cruza")
}
```
Un módulo de métrica que falla no aborta el cálculo: sus campos se serializan
como `None` («sin dato», mostrado como «—» en tabla y PDF) y el motivo queda en
`MetricasRuta.errores`, que la app muestra como aviso.

## Decisiones de stack (revisables)

| Pieza | Opción en uso | Alternativas |
|-------|---------------|--------------|
| Lenguaje | Python 3.11+ | — |
| Geoespacial | rasterio + geopandas + shapely + pyproj + scipy | — |
| CRS de trabajo | ETRS89 / UTM 30N (EPSG:25830) | según zona del trazado |
| Descarga OSM | Overpass directo (`requests`) | osmnx |
| Camino mínimo coste | Dijkstra 8-conexo propio (`heapq`) | A\* (misma garantía de óptimo, más rápido para un solo par) |
| Visualización | folium (+ matplotlib en el informe PDF) | contextily, kepler.gl |
| UI | Streamlit con mapa (+ informe PDF vía reportlab) | CLI (esqueleto, Sprint 5) |

Registrar cualquier cambio de stack en [`../coordinacion/seguimiento.md`](../coordinacion/seguimiento.md).

## Encaje con la escalera MVP

Los componentes de arriba cubren el **núcleo comprometido (MVP 1-4)** de la escalera de objetivos de Enagás ([`../docs/hitos_mvp.md`](../docs/hitos_mvp.md)): ingesta+alineación (MVP 1), superficies de coste + trazado base por **A\*/Dijkstra** (MVP 2), diferenciación (MVP 3) y métricas+comparativa+ranking (MVP 4). Sobre esa base se apoyan, como **reach/continuidad**:

- **MVP 4/6 — backtesting:** un módulo de validación que compara las rutas generadas con un ramal real y explica desviaciones (puede vivir en `src/comparacion/` o en `tests/`).
- **MVP 5/7 — salidas EV-500 / herramienta operativa:** exportación de la alternativa elegida a **GIS (shapefile/GeoPackage)** y **Excel comparativo**, relación de cruces y afección municipal. Encaja como nuevos formatos de salida de `src/comparacion/` y `src/app/`.
- **MVP 8 — industrialización:** versionado de escenarios (`data/config/`) y trazabilidad de decisiones; no requiere rediseño, sí disciplina.

## Lo que este sistema NO hace

- No estima costes absolutos en € (solo índice de coste relativo).
- No entrega una única ruta "óptima", sino un abanico comparable de alternativas.
- No garantiza viabilidad jurídica, expropiatoria ni constructiva: es prediseño y comparación.
