# Catálogo de capas GIS — Fuentes de datos

> Las capas en sí **no se versionan** (ver `.gitignore`); este catálogo sí.
> **CRS de trabajo:** todas las capas se reproyectan a **EPSG:25830** (ETRS89/UTM 30N) y se alinean a la rejilla común (30 m) definida en `config/escenario.yaml` antes de entrar al pipeline.

## Resumen

| ID | Capa | Obtención | Fecha descarga | CRS original | Tipo |
|----|------|-----------|----------------|--------------|------|
| DEM | Copernicus GLO-30 | Automática (`descargar_capas.py`) | 2026-06-16 | EPSG:4326 | Raster |
| OSM | OpenStreetMap | Automática (`descargar_capas.py`) | 2026-06-16 | EPSG:4326 | Vector |
| HID | Hidrografía IGN INSPIRE | Automática (`descargar_capas.py`) | 2026-06-16 | EPSG:25830 | Vector |
| IGME | Mapa Geológico IGME | Automática (`descargar_capas.py`) | 2026-06-16 | EPSG:25830 | Vector |
| INUNDABLES | Zonas inundables peligrosidad fluvial T=100 (SNCZI) | **Manual** (tiles CNIG) + `descargar_capas.py` / WMS fallback | 2026-06-30 | EPSG:25830 | Raster |
| RN2000 | Red Natura 2000 (MITECO) | **Manual** (leer instrucciones) | 2025 (ed. final) | EPSG:25830 | Vector |
| CATASTRO | Catastro INSPIRE (DGC) | **Manual** (leer instrucciones) | 2026-06-16 | EPSG:25830 | Vector |

---

## Capas descargadas automáticamente

Estas cuatro capas se obtienen ejecutando `src/ingesta/descargar_capas.py` con los puntos del `escenario.yaml`. No requieren ninguna acción manual.

### DEM — Modelo Digital de Elevaciones Copernicus GLO-30

- **Qué aporta:** elevación del terreno → cálculo de pendiente en la superficie de coste.
- **Fuente:** Copernicus DEM GLO-30 (tiles COG en S3 de AWS).
  - Tiles usados: `Copernicus_DSM_COG_10_N41_00_W001_00_DEM` y `Copernicus_DSM_COG_10_N41_00_E000_00_DEM`.
- **CRS original:** EPSG:4326 (WGS84 geográfico), reproyectado a EPSG:25830 durante la descarga.
- **Resolución original:** ~1 arc-second (~30 m); resolución en raw tras reproyección: 29.4 × 29.4 m.
- **Archivos en `raw/`:** `DEM_A.tif`, `DEM_B.tif`
- **Salida en `Recorte_AOI/`:** `dem_aoi_A.tif`, `dem_aoi_B.tif`
- **Licencia:** datos abiertos de Copernicus (© DLR e.V. 2010–2011, © Airbus Defence and Space GmbH 2014–2018). Citar la fuente.

---

### OSM — OpenStreetMap (viario e infraestructura)

- **Qué aporta:** red viaria, ferroviaria, puentes, líneas de alta tensión, núcleos urbanos → cruces especiales y zonas urbanas/periurbanas.
- **Fuente:** Overpass API (`https://overpass-api.de/`). Consulta por bbox WGS84 del AOI de cada escenario.
  - Escenario A bbox: `(41.0670, -0.1660) → (41.1747, -0.1099)`
- **CRS original:** EPSG:4326 (WGS84), convertido a EPSG:25830 durante la descarga.
- **Geometría:** LineString (vías, cauces, infraestructuras lineales).
- **Archivos en `raw/`:** `OSM_A.gpkg`, `OSM_B.gpkg`
- **Salida en `Recorte_AOI/`:** `osm_aoi_A.gpkg`, `osm_aoi_B.gpkg`
- **Advertencia:** OSM se actualiza continuamente. Para garantizar reproducibilidad, no borrar los archivos de `raw/` y no re-descargar salvo necesidad justificada.
- **Licencia:** © OpenStreetMap contributors, licencia ODbL. Atribución obligatoria.

---

### HID — Hidrografía IGN (INSPIRE)

- **Qué aporta:** ríos y cursos de agua → cruces hidrológicos especiales en la superficie de coste.
- **Fuente:** WFS INSPIRE del IGN — servicio `hidrografia`, capa `hy-n:WatercourseLink`.
  - Endpoint: `https://servicios.idee.es/wfs-inspire/hidrografia`
- **CRS original:** EPSG:25830 (devuelto directamente en UTM 30N).
- **Geometría:** LineString (cursos de agua).
- **Archivos en `raw/`:** `HID_A.gpkg`, `HID_B.gpkg`
- **Salida en `Recorte_AOI/`:** `hidrografia_aoi_A.gpkg`, `hidrografia_aoi_B.gpkg`
- **Licencia:** datos públicos IGN/CNIG, Reutilización de la Información del Sector Público (CC BY 4.0 con condiciones IGN).

---

### IGME — Mapa Geológico MAGNA 50

- **Qué aporta:** litología y geología → corredor de menor resistencia geomecánica, identificación de cruces geológicos especiales.
- **Fuente:** ArcGIS REST del IGME — servicio `IGME_MAGNA_50`, capa 11 (Litologías color).
  - Endpoint consultado por `descargar_capas.py` vía query espacial al bbox del AOI.
- **CRS original:** EPSG:25830.
- **Geometría:** Polygon (unidades litológicas).
- **Archivos en `raw/`:** `IGME_A.gpkg`, `IGME_B.gpkg`
- **Salida en `Recorte_AOI/`:** `igme_aoi_A.gpkg`, `igme_aoi_B.gpkg`
- **Licencia:** datos públicos IGME. Citar como: "Mapa Geológico de España a escala 1:50.000 (MAGNA), IGME-CSIC."

---

### INUNDABLES — Zonas inundables, peligrosidad fluvial T=100 (SNCZI)

- **Qué aporta:** lámina de inundación de periodo de retorno T=100 años (probabilidad media) → condicionante "Zonas inundables" (factor oficial Enagás A=14.25) en la superficie de coste.
- **Fuente PRIMARIA (manual):** GeoTIFF oficial de peligrosidad del **Centro de Descargas del CNIG / SNCZI**, por hoja, calado (profundidad) en metros, **1 m**, EPSG:25830, `nodata = -3.0`.
  - Portal: `https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/agua/mapas-peligrosidad-por-inundacion-fluvial.html` (filtrar por municipio).
  - Ficheros `ESNZSNCZIMPF**T100**<hoja>.tif`; descargar y dejar en `data/raw/INUNDABLES/`.
- **Fuente FALLBACK (automática):** WMS INSPIRE `NZ.Flood.FluvialT100` (`https://servicios.idee.es/wms-inspire/riesgos-naturales/inundaciones`). Se usa solo si no hay tiles locales (el SNCZI no expone WFS vectorial; es la única capa por WMS).
- **Obtención:** `descargar_capas.py` detecta los tiles locales, **mosaica** las hojas que intersectan cada AOI, las remuestrea a 30 m con `Resampling.max` (bloque inundable si alguna subcelda de 1 m tiene calado) y produce una **máscara binaria uint8** (1 = inundable, 0 = fuera).
- **Geometría:** Raster (máscara binaria 0/1).
- **Tiles usados (hojas que tocan cada corredor):**
  - Escenario A: `ESNZSNCZIMPFT100AB111.tif`
  - Escenario B: `ESNZSNCZIMPFT100X108.tif` + `ESNZSNCZIMPFT100Y108.tif`
- **Archivos en `raw/`:** `INUNDABLES_A.tif`, `INUNDABLES_B.tif` (+ tiles en `raw/INUNDABLES/`)
- **Salida en `Recorte_AOI/`:** `inundables_aoi_A.tif`, `inundables_aoi_B.tif`
- **⚠️ Nota de cobertura (importante):** en los corredores actuales (1 km de ancho) la lámina T=100 da **0 % de celdas inundables** dentro del AOI de A y B, confirmado por las **dos** fuentes (GeoTIFF oficial 1 m y WMS). La llanura de inundación del Ebro (hasta ~18 m de calado en la hoja X108) queda **fuera del pasillo**. El dato es correcto y la capa está bien alineada; simplemente **no condiciona el trazado actual**. Pasaría a ser relevante si se ensancha el AOI o se mueven origen/destino.
- **Licencia:** datos públicos MITECO/SNCZI, reutilización con atribución.

---

## Capas de obtención manual

Estas dos capas **no se descargan automáticamente** por el pipeline. Deben obtenerse manualmente y colocarse en las rutas indicadas antes de ejecutar `alinear_capas.py`.

### RN2000 — Red Natura 2000 (MITECO)

- **Qué aporta:** espacios protegidos ZEC y ZEPA → penalización alta en la superficie de coste (mínima afección a áreas protegidas).
- **Fuente:** Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO), sección Biodiversidad → Redes y áreas protegidas → Red Natura 2000 → Descargas SIG.
  - Portal: `https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/biodiversidad/rn2000.html`
- **Fichero a descargar:** dataset espacial para **Península e Islas Baleares**, proyección ETRS89 (EPSG:25830). Edición de final de 2025 (`end25`).
- **CRS original:** EPSG:25830.
- **Geometría:** Polygon (áreas ZEC/ZEPA).
- **Ruta esperada en `raw/`:**
  ```
  data/raw/RN2000/
      n2000_spatial_es_pibal_proy_end25.geojson   ← usado por el pipeline
      n2000_spatial_es_can_proy_end25.geojson     ← Canarias (no usado)
  ```
- **Fecha de los datos:** edición final 2025 (nombre de archivo `end25`).
- **Licencia:** datos públicos MITECO, reutilización libre con atribución.

---

### CATASTRO — Catastro INSPIRE (Dirección General del Catastro)

- **Qué aporta:** usos del suelo parcelario (urbano/rústico) → diferenciación de zonas urbanas, periurbanas y agrícolas en la superficie de coste; reemplaza a CLC con mayor resolución y detalle espacial.
- **Fuente:** Sede Electrónica del Catastro — descarga INSPIRE de parcelas en formato Shapefile.
  - Portal: `https://www.sedecatastro.gob.es/` → Descargas INSPIRE → Parcelas
- **CRS original:** EPSG:25830.
- **Geometría:** Polygon (parcelas catastrales).
- **Fecha de referencia catastral:** 23 de enero de 2026 (codificada en los nombres de carpeta como `23012026`).
- **Fecha de descarga:** 2026-06-16.

**Municipios descargados:**

| Municipio | Código INE | Provincia | Ramal(es) cubiertos | Tipo |
|-----------|-----------|-----------|---------------------|------|
| Alcañiz | 44013 | Teruel | A (origen) | RURAL + URBANO |
| Caspe | 50074 | Zaragoza | A (norte) + B (oeste) | RURAL + URBANO |
| Fuentes de Ebro | 50116 | Zaragoza | B | RURAL + URBANO |
| Mediana de Aragón | 50165 | Zaragoza | B | RURAL + URBANO |
| Zaragoza | 50900 | Zaragoza | B (destino) | RURAL + URBANO |

> Caspe (Zaragoza) se descargó en la carpeta RamalB pero cubre geográficamente el extremo norte del AOI del Escenario A. El pipeline usa **todos los municipios sin filtrar** y deja que el recorte espacial al AOI decida qué parcelas son relevantes para cada escenario.

**Estructura en `raw/`:**
```
data/raw/CATASTRO/
    RURAL/
        2026061610140168574_PETICION_DESCARGA_SHA(RamalB)/   ← Caspe, F.Ebro, Mediana, Zgz
        2026061610225320379_PETICION_DESCARGA_SHA(RamalA)/   ← Alcañiz
    URBANO/
        2026061610183402957_PETICION_DESCARGA_SHA(RamalB)/   ← Caspe, F.Ebro, Mediana, Zgz
        2026061610240207173_PETICION_DESCARGA_SHA(RamalA)/   ← Alcañiz
```

- **Salida en `Recorte_AOI/`:** `catastro_aoi_A.gpkg` (1 221 parcelas), `catastro_aoi_B.gpkg` (160 parcelas).
- **Licencia:** datos públicos de la Dirección General del Catastro, Ministerio de Hacienda. Reutilización sujeta a condiciones INSPIRE.

---

## Procedimiento para reproducir la ingesta

```bash
# 1. Descargar capas automáticas (DEM, OSM, HID, IGME)
python src/ingesta/descargar_capas.py --escenario A
python src/ingesta/descargar_capas.py --escenario B

# 2. Colocar manualmente RN2000 y CATASTRO en las rutas indicadas arriba

# 3. Alinear y recortar al AOI (genera Recorte_AOI/)
python src/ingesta/alinear_capas.py --escenario A
python src/ingesta/alinear_capas.py --escenario B
```

> Los archivos de `Recorte_AOI/` **sí están versionados** en git. Si solo se quiere usar el pipeline a partir de las capas ya procesadas (sin re-ejecutar la ingesta), hacer `git pull` es suficiente.
