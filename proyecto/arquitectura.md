# Arquitectura — Generación automatizada de trazados de ramales de H₂

> Diseño técnico del prototipo. Lectura previa: [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md).

## Principio de diseño

**Pipeline geoespacial determinista: alinear antes de combinar, diferenciar antes de comparar.**

Todo el cálculo es reproducible y auditable: las capas se alinean a un CRS y rejilla comunes, se convierten en superficies de coste con pesos explícitos (perfiles), y las rutas se obtienen por camino de mínimo coste. No hay estimación económica: el coste es un **índice relativo**. No hay una única "óptima": se generan **varias alternativas diferenciadas** para decidir.

## Diagrama de componentes

```
   origen (planta H₂) + destino (conexión red troncal) + AOI
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
        │     (skimage.graph / networkx)      │
        │   · DIFERENCIACIÓN: corridor masking│
        └─────────────────┬──────────────────┘
                          │ 3-5 rutas diferenciadas
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
Descarga/lee las capas de `data/raw/` (DEM, CLC, OSM, hidrografía IGN, Red Natura 2000, IGME), las **recorta al AOI**, las **reproyecta a EPSG:25830** y las **remuestrea a una rejilla común** (misma resolución y origen de celda). Rasteriza las capas vectoriales a esa rejilla. Salida: un conjunto de rasters **alineados** en `data/processed/`.

Librerías: `rasterio` (raster, reproyección, remuestreo), `geopandas`/`shapely` (vectores), `pyproj` (CRS), `osmnx` (OSM).

> **Regla de oro:** una capa no avanza al paso 2 si no comparte CRS y rejilla con las demás. La celda (i, j) debe representar el mismo trozo de terreno en todas las capas.

### 2. Superficies de coste (`src/superficie/`)
Convierte cada capa alineada en un **coste por celda** (p.ej. pendiente → coste creciente; suelo urbano → coste alto; Red Natura 2000 → coste muy alto o celda prohibida; proximidad a cruces → coste). Combina las capas con un **vector de pesos** en una única superficie de coste. Cada **perfil de prioridad** (definido en `data/config/perfiles.yaml`) produce una superficie distinta.

### 3. Motor LCP (`src/trazados/`)
Sobre cada superficie de coste calcula el **camino de mínimo coste** origen→destino (`skimage.graph.MCP_Geometric` / `route_through_array`; alternativa `networkx`). Para garantizar **rutas diferenciadas**, aplica **corridor masking**: tras generar una ruta, penaliza la proximidad a ella antes de generar la siguiente, y descarta rutas con solapamiento por encima de un umbral.

### 4. Métricas (`src/metricas/`)
Para cada ruta calcula: **longitud** (km), **coste relativo** (suma normalizada de celdas atravesadas), **cruces especiales** (nº y tipo: río, carretera, ferrocarril…), **km en zona protegida** (Red Natura 2000), **km en zona urbana/periurbana** (CLC/OSM) y **pendiente máxima y media** (del DEM a lo largo de la ruta).

### 5. Comparativa (`src/comparacion/`)
Reúne las métricas de las 3-5 rutas en una **tabla multicriterio**, calcula un **scoring/ranking** (por criterio o agregado ponderado) y genera el **mapa** con las rutas diferenciadas (`folium` / `contextily`).

### 6. Orquestador / Interfaz (`src/app/`)
Lee el caso de estudio de `data/config/`, ejecuta el pipeline para cada perfil y compone la salida (tabla + mapa) en **CLI** y/o **Streamlit**.

## Contrato de datos

### Caso de estudio — `data/config/escenario.yaml`
```yaml
crs_trabajo: "EPSG:25830"          # CRS común (península)
resolucion_m: 30                    # tamaño de celda de la rejilla común (m)
aoi:                                # bounding box en crs_trabajo (o ruta a un .geojson)
  xmin: 0
  ymin: 0
  xmax: 0
  ymax: 0
origen:                             # planta de H₂
  x: 0
  y: 0
destino:                            # conexión a red troncal
  x: 0
  y: 0
```

### Perfil de prioridad — `data/config/perfiles.yaml`
```yaml
- id: corto
  nombre: "Más corto"
  pesos:                            # peso por capa de coste (adimensional)
    pendiente: 0.2
    uso_suelo: 0.2
    protegida: 0.3
    longitud: 1.0
- id: ambiental
  nombre: "Menor impacto ambiental"
  pesos:
    pendiente: 0.2
    uso_suelo: 0.5
    protegida: 1.0
    longitud: 0.3
- id: pendiente
  nombre: "Menor pendiente"
  pesos:
    pendiente: 1.0
    uso_suelo: 0.3
    protegida: 0.4
    longitud: 0.3
```

### Métricas por ruta (salida)
```python
{
  "perfil": "ambiental",
  "longitud_km": 0.0,
  "coste_relativo": 0.0,          # índice normalizado 0-1, NUNCA €
  "cruces": {"rio": 0, "carretera": 0, "ferrocarril": 0},
  "km_protegida": 0.0,
  "km_urbana": 0.0,
  "pendiente_max_pct": 0.0,
  "pendiente_media_pct": 0.0,
}
```

## Decisiones de stack (revisables)

| Pieza | Opción por defecto | Alternativas |
|-------|--------------------|--------------|
| Lenguaje | Python 3.11+ | — |
| Geoespacial | rasterio + geopandas + shapely + pyproj | — |
| CRS de trabajo | ETRS89 / UTM 30N (EPSG:25830) | según zona del trazado |
| Descarga OSM | osmnx | Overpass directo |
| LCP | scikit-image `MCP_Geometric` | networkx (Dijkstra sobre grafo) |
| Visualización | folium + contextily | matplotlib, kepler.gl |
| UI | Streamlit con mapa | mapa estático + tabla |

Registrar cualquier cambio de stack en [`../coordinacion/seguimiento.md`](../coordinacion/seguimiento.md).

## Lo que este sistema NO hace

- No estima costes absolutos en € (solo índice de coste relativo).
- No entrega una única ruta "óptima", sino un abanico comparable de alternativas.
- No garantiza viabilidad jurídica, expropiatoria ni constructiva: es prediseño y comparación.
