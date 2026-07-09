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
| INUND | Zonas inundables SNCZI (MITECO) | Automática (`descargar_capas.py`) | 2026-06-29 | EPSG:4326 | Vector |
| RN2000 | Red Natura 2000 (MITECO) | Automática (`descargar_capas.py`) | 2026-07-09 | EPSG:4326 | Vector |
| CATASTRO | Catastro INSPIRE (DGC) | **Manual** (leer instrucciones) | 2026-06-16 | EPSG:25830 | Vector |

---

## Capas descargadas automáticamente

Estas capas se obtienen ejecutando `src/ingesta/descargar_capas.py` con los puntos del `escenario.yaml`. No requieren ninguna acción manual.

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

### INUND — Zonas inundables SNCZI (MITECO)

- **Qué aporta:** láminas de inundación fluvial (periodos de retorno T10, T100 y T500, unidas en una sola capa binaria) → penalización de zonas inundables en la superficie de coste.
- **Fuente:** OGC API Features de MITECO — colecciones `agua:Zi_laminas_q10`, `agua:Zi_laminas_q100` y `agua:Zi_laminas_q500`.
  - Endpoint: `https://wmts.mapama.gob.es/sig-api/ogc/features/v1`
  - Referencia oficial: `https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/agua/mapas-peligrosidad-por-inundacion-fluvial.html`
- **CRS original:** EPSG:4326 (WGS84), reproyectado a EPSG:25830 durante la descarga.
- **Geometría:** Polygon (láminas de inundación).
- **Archivos en `raw/`:** `INUND_A.gpkg`, `INUND_B.gpkg`
- **Salida en `Recorte_AOI/`:** `inundable_aoi_A.gpkg`, `inundable_aoi_B.gpkg`
- **Licencia:** datos públicos MITECO, reutilización libre con atribución.

---

### RN2000 — Red Natura 2000 (MITECO)

- **Qué aporta:** espacios protegidos ZEC y ZEPA → penalización alta en la superficie de coste (mínima afección a áreas protegidas).
- **Fuente:** OGC API Features de MITECO — colección `biodiversidad:RedNatura` (mismo servicio que las zonas inundables).
  - Endpoint: `https://wmts.mapama.gob.es/sig-api/ogc/features/v1`
  - Referencia oficial: `https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/biodiversidad/rn2000.html`
  - Nota: hasta jul-2026 se usaba el WFS INSPIRE del IGN (`redes-ecologicas`, capa `PS.ProtectedSite`), pero ese servicio está caído/inestable de forma recurrente y se sustituyó por el de MITECO.
- **CRS original:** EPSG:4326 (WGS84), reproyectado a EPSG:25830 durante la descarga.
- **Geometría:** Polygon (áreas ZEC/ZEPA).
- **Archivos en `raw/`:** `RN2000_A.gpkg`, `RN2000_B.gpkg`
- **Salida en `Recorte_AOI/`:** `natura2000_aoi_A.gpkg`, `natura2000_aoi_B.gpkg`
- **Alternativa manual (fallback):** si el servicio no responde, se puede descargar el dataset nacional (Península e Islas Baleares, edición final 2025 `end25`) desde el portal de MITECO y guardarlo en `data/raw/RN2000/` (o como `data/raw/RN2000.gpkg`); `alinear_capas.py` lo detecta automáticamente.
- **Licencia:** datos públicos MITECO, reutilización libre con atribución.

---

## Capas de obtención manual

Esta capa **no se descarga automáticamente** por el pipeline (no hay servicio por bbox fiable). Debe obtenerse manualmente y colocarse en la ruta indicada antes de ejecutar `alinear_capas.py`.

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
# 1. Descargar capas automáticas (DEM, OSM, HID, IGME, INUND, RN2000)
python src/ingesta/descargar_capas.py --escenario A
python src/ingesta/descargar_capas.py --escenario B

# 2. Colocar manualmente CATASTRO en la ruta indicada arriba

# 3. Alinear y recortar al AOI (genera Recorte_AOI/)
python src/ingesta/alinear_capas.py --escenario A
python src/ingesta/alinear_capas.py --escenario B
```

> Los archivos de `Recorte_AOI/` **sí están versionados** en git. Si solo se quiere usar el pipeline a partir de las capas ya procesadas (sin re-ejecutar la ingesta), hacer `git pull` es suficiente.
