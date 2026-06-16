# Agente de Ingesta y Alineación de Capas GIS

> Documentación del script `src/ingesta/alinear_capas.py`.
> Proyecto: Reto 6 Enagás — Generación automatizada de trazados de ramales de H₂.

## Qué hace este agente

Toma las capas GIS brutas de `data/raw/` y las prepara para el pipeline de
routing. Las capas de origen tienen CRS, resoluciones y extensiones distintas.
Este agente las deja todas **recortadas, reproyectadas y alineadas** en
`data/processed/`, listas para combinarse en la superficie de coste.

**Regla de oro:** nunca modifica `data/raw/`. Solo lee de ahí y escribe en
`data/processed/`.

---

## Pasos que ejecuta (en orden)

### Paso 1 — Recorte al AOI
Construye el Área de Interés (AOI) como un buffer de **1 km a cada lado**
de la línea recta entre el origen y el destino definidos en
`data/config/escenario.yaml`. Recorta todas las capas a ese rectángulo.

- Entrada: coordenadas `origen` y `destino` de `escenario.yaml`
- Salida: capas recortadas en `data/processed/`
- Librería: `shapely` (buffer + clip), `geopandas` (vectores),
  `rasterio.mask` (rasters)

### Paso 2 — Reproyección a EPSG:25830
Reproyecta todas las capas al CRS de trabajo del proyecto:
**ETRS89 / UTM zona 30N (EPSG:25830)**.

- Capas vectoriales: `geopandas.to_crs(epsg=25830)`
- Capas raster: `rasterio.warp.reproject`
- El CRS original de cada capa queda registrado en el log

### Paso 3 — Alineación de rejilla
Identifica la resolución más fina entre todos los rasters (normalmente el
DEM Copernicus a 30 m) y remuestrea el resto a esa resolución con **celdas
espacialmente coincidentes** (mismo origen de celda). Las capas vectoriales
se rasterizan también a esa rejilla.

Tras este paso, la celda (i, j) representa el **mismo trozo de terreno**
en todas las capas — condición imprescindible para construir la superficie
de coste.

- Librería: `rasterio.warp.reproject` con `Resampling.bilinear`
- Referencia de rejilla: la capa raster con resolución más fina

### Paso 4 — Detección de duplicados
Compara las capas vectoriales entre sí (especialmente OSM frente a
hidrografía IGN u otras fuentes). Si dos capas tienen más de un **70% de
solapamiento espacial**, imprime un aviso y pregunta al usuario cuál
conservar antes de guardar.

---

## Capas esperadas en `data/raw/`

| Capa | Tipo | Fuente | CRS original típico |
|------|------|--------|---------------------|
| DEM Copernicus | Raster `.tif` | Copernicus GLO-30 AWS S3 | EPSG:25830 (reproyectado en descarga) |
| Corine Land Cover | Vector `.gpkg` / `.shp` | Copernicus | EPSG:3035 |
| Red Natura 2000 | Vector `.geojson` | MITECO | EPSG:4326 |
| OSM | Vector `.gpkg` | OpenStreetMap | EPSG:4326 |
| Hidrografía IGN | Vector `.gpkg` / `.shp` | IGN/CNIG | EPSG:25830 |
| IGME geológico | Vector `.gpkg` / `.shp` | IGME | EPSG:25830 |

---

## Salidas en `data/processed/`

Las capas se guardan en dos subcarpetas según su tipo de salida:

### `data/processed/Recorte_AOI/` — capas vectoriales recortadas

| Archivo | Contenido |
|---------|-----------|
| `clc_aoi.gpkg` | Corine Land Cover recortado y reproyectado |
| `natura2000_aoi.gpkg` | Red Natura 2000 recortada y reproyectada |
| `osm_aoi.gpkg` | Datos OSM recortados y reproyectados |
| `hidrografia_aoi.gpkg` | Hidrografía IGN recortada |
| `igme_aoi.gpkg` | Mapa geológico recortado |

> Si una capa vectorial no tiene geometrías dentro del AOI, se guarda igualmente un `.gpkg` vacío para registrar que la capa fue procesada.

### `data/processed/Rasters_AOI/` — rasters alineados

| Archivo | Contenido |
|---------|-----------|
| `dem_aoi.tif` | DEM recortado, reproyectado y alineado a la rejilla común |

> Aquí irán también los rasters derivados que genere `src/superficie/` (pendiente, coste por celda, superficie combinada).

### Raíz de `data/processed/`

| Archivo | Contenido |
|---------|-----------|
| `log_alineacion.txt` | Log completo del proceso de ingesta |

---

## Flujo de dos pasos (nuevo)

La ingesta se divide en dos scripts independientes:

### Paso 0 — Descarga automática (`src/ingesta/descargar_capas.py`)

Nuevo script que descarga automáticamente la unidad mínima de cada fuente
que contiene el AOI. Para todas las fuentes utiliza servicios WFS, WCS u
Overpass que permiten consultas por bbox: la "unidad mínima" es el propio
recorte del AOI (no hace falta descargar capas regionales).

```bash
python -m src.ingesta.descargar_capas              # ambos escenarios A y B
python -m src.ingesta.descargar_capas --escenario A
python -m src.ingesta.descargar_capas --escenario B
```

Archivos generados en `data/raw/` (sufijo `_A` o `_B`):

| Archivo          | Fuente                          | Servicio       |
|------------------|---------------------------------|----------------|
| `DEM_{s}.tif`    | Copernicus GLO-30 (30 m)        | AWS S3 COG (`/vsicurl/`) |
| `CLC_{s}.gpkg`   | Corine Land Cover IGN INSPIRE   | WFS            |
| `RN2000_{s}.gpkg`| Red Natura 2000 IGN INSPIRE     | WFS            |
| `OSM_{s}.gpkg`   | OpenStreetMap (carreteras)      | Overpass API   |
| `HID_{s}.gpkg`   | Hidrografía IGN INSPIRE         | WFS            |
| `IGME_{s}.gpkg`  | IGME MAGNA50                    | WFS / REST     |

### Paso 1 — Alineación (`src/ingesta/alinear_capas.py`)

```bash
python -m src.ingesta.alinear_capas --escenario A
python -m src.ingesta.alinear_capas --escenario B
```

Cuando se indica `--escenario`, el script busca primero los archivos con
sufijo (`DEM_A.tif`, `CLC_A.gpkg`…) antes de recurrir a los patrones glob.
Si la descarga automática no está disponible, puede funcionar igualmente con
los archivos descargados manualmente con los nombres anteriores.

---

## Cómo ejecutarlo (flujo completo)

```bash
# Desde la raíz del proyecto (proyecto/)
python -m src.ingesta.descargar_capas   # descarga ambos escenarios
python -m src.ingesta.alinear_capas --escenario A
python -m src.ingesta.alinear_capas --escenario B
```

Si `data/processed/` ya contiene archivos, el script pregunta antes de
sobreescribir. Usar `-y` para omitir la pregunta.

---

## Requisitos previos

1. `data/config/escenario.yaml` con `escenario_A` y `escenario_B` rellenos
2. Entorno Python con: `rasterio`, `geopandas`, `shapely`, `pyproj`, `numpy`, `requests`

---

## Log generado

Cada ejecución genera `data/processed/log_alineacion.txt` con:
- Fecha y hora de ejecución
- Lista de capas encontradas en `data/raw/`
- CRS original y resolución de cada capa
- Resultado de cada paso (✓ éxito / ✗ error)
- Avisos de duplicados detectados

---

## Decisiones de diseño

- **Resolución de referencia:** la más fina entre los rasters disponibles
  (no se degrada información innecesariamente).
- **Remuestreo:** bilineal para capas continuas (DEM, pendiente);
  nearest-neighbor para capas categóricas (CLC, Natura 2000).
- **Umbral de duplicados:** 70% de solapamiento espacial. Ajustable en
  el propio script.
- **Buffer del AOI:** 1 km por defecto. Configurable en `escenario.yaml`.
