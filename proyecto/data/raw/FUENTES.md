# Catálogo de capas GIS

> Registro de las capas geográficas públicas usadas. Las capas en sí **no se versionan** (ver `.gitignore`); este catálogo sí.
> Para cada capa: identificador, qué aporta, fuente, URL, fecha de descarga, **CRS original** y **resolución original**.

## Capas

| ID | Capa | Qué aporta | Fuente | Portal oficial | Fecha descarga | CRS original | Resolución |
|----|------|-----------|--------|----------------|----------------|--------------|------------|
| DEM | Modelo Digital de Elevaciones | elevación → pendiente | Copernicus DEM (GLO-30) | https://dataspace.copernicus.eu/ | _(pendiente)_ | _(pendiente)_ | ~30 m |
| CLC | Corine Land Cover | usos del suelo (urbano, agrícola…) | Copernicus Land Monitoring (EEA) | https://land.copernicus.eu/ | _(pendiente)_ | _(pendiente)_ | 100 m |
| OSM | OpenStreetMap | viario, ferrocarril, hidrografía, núcleos, infraestructuras (cruces) | OpenStreetMap (Geofabrik / osmnx / Overpass) | https://download.geofabrik.de/europe/spain.html | _(pendiente)_ | EPSG:4326 | vector |
| HID-IGN | Hidrografía IGN | ríos y masas de agua (cruces) | IGN / CNIG | https://centrodedescargas.cnig.es/ | _(pendiente)_ | _(pendiente)_ | vector |
| RN2000 | Red Natura 2000 | zonas protegidas (ZEC/ZEPA) | MITECO | https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/biodiversidad/rn2000.html | _(pendiente)_ | _(pendiente)_ | vector |
| GEO-IGME | Mapa geológico | litología / cruces geológicos especiales | IGME | https://www.igme.es/ _(portal de descargas a confirmar)_ | _(pendiente)_ | _(pendiente)_ | vector |

> Portales oficiales localizados en la ronda de investigación; los metadatos finos (CRS original, resolución exacta, licencia) se confirman al descargar cada capa. Fundamento bibliográfico y documentación de cada fuente en [`../../../docs/referencias_sig/biblioteca_sig.md`](../../../docs/referencias_sig/biblioteca_sig.md) (Tema 5).

> **CRS de trabajo:** todas las capas se reproyectan a **ETRS89 / UTM 30N = EPSG:25830** (península) y se remuestrean a una **rejilla común** (resolución y origen de celda definidos en `../config/escenario.yaml`) antes de usarse.

## Procedimiento

1. Localizar la capa pública oficial (Copernicus, OSM, IGN/CNIG, MITECO, IGME).
2. Descargarla a esta carpeta con nombre = `ID.<ext>` (p.ej. `DEM.tif`, `RN2000.gpkg`).
3. Rellenar la fila correspondiente arriba (URL, fecha de descarga, **CRS original** y **resolución original**).
4. En la ingesta: recortar al AOI, reproyectar a **EPSG:25830** y remuestrear/rasterizar a la rejilla común → `../processed/`.
5. Documentar cualquier transformación aplicada para que el resultado sea reproducible y trazable a la fuente.

## Notas de licencias

- **OpenStreetMap:** © OpenStreetMap contributors, licencia ODbL — citar la atribución.
- **Copernicus (DEM, CLC):** datos abiertos de Copernicus — revisar y citar las condiciones de uso.
- **IGN / CNIG, MITECO, IGME:** datos públicos — revisar la licencia específica de cada producto y citar la fuente.
