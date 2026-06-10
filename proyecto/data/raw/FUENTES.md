# Catalogo de capas GIS

> Registro de las capas geograficas publicas usadas. Las capas en si **no se versionan** (ver `../../.gitignore`); este catalogo si.
> Para cada capa: identificador, que aporta, fuente, URL, fecha de descarga, **CRS original** y **resolucion original**.

## Criterio de carpetas

- `raw/`: mapas y capas originales, tal como se descargan. No editar estos archivos.
- `processed/`: las mismas capas despues de aplicar los cambios necesarios para combinarlas: recorte al area de Ciudad Lineal, reproyeccion, limpieza geometrica, rasterizacion o remuestreo.
- `config/`: parametros comunes del escenario: CRS de trabajo, resolucion de la rejilla, AOI, origen y destino.

Para mantener la trazabilidad, cada capa procesada debe conservar el ID de su fuente original. Ejemplo:

| Original en `raw/` | Procesado en `processed/` | Cambio aplicado |
|--------------------|---------------------------|-----------------|
| `OSM.gpkg` | `OSM_ciudad-lineal_25830.gpkg` | recorte AOI + reproyeccion |
| `DEM.tif` | `DEM_ciudad-lineal_25830_30m.tif` | recorte AOI + remuestreo |
| `GEO-IGME.gpkg` | `GEO-IGME_ciudad-lineal_25830.gpkg` | recorte AOI + limpieza |

## Capas

| ID | Capa | Que aporta | Fuente | URL | Fecha descarga | CRS original | Resolucion |
|----|------|------------|--------|-----|----------------|--------------|------------|
| DEM | Modelo Digital de Elevaciones | elevacion -> pendiente | Copernicus DEM (GLO-30) | _(pendiente)_ | _(pendiente)_ | _(pendiente)_ | ~30 m |
| CLC | Corine Land Cover | usos del suelo (urbano, agricola, etc.) | Copernicus Land Monitoring | _(pendiente)_ | _(pendiente)_ | _(pendiente)_ | 100 m |
| OSM | OpenStreetMap | viario, ferrocarril, hidrografia, nucleos, infraestructuras | OpenStreetMap (osmnx / Overpass) | _(pendiente)_ | _(pendiente)_ | EPSG:4326 | vector |
| HID-IGN | Hidrografia IGN | rios y masas de agua | IGN / CNIG | _(pendiente)_ | _(pendiente)_ | _(pendiente)_ | vector |
| RN2000 | Red Natura 2000 | zonas protegidas (ZEC/ZEPA) | MITECO / Copernicus | _(pendiente)_ | _(pendiente)_ | _(pendiente)_ | vector |
| GEO-IGME | Mapa geologico | litologia / cruces geologicos especiales | IGME | _(pendiente)_ | _(pendiente)_ | _(pendiente)_ | vector |

> **CRS de trabajo:** todas las capas se reproyectan a **ETRS89 / UTM 30N = EPSG:25830** (peninsula) y se remuestrean a una **rejilla comun** antes de usarse.

## Procedimiento

1. Localizar la capa publica oficial (Copernicus, OSM, IGN/CNIG, MITECO, IGME).
2. Descargarla a `raw/` con nombre = `ID.<ext>`; por ejemplo, `DEM.tif` o `RN2000.gpkg`.
3. Rellenar la fila correspondiente en este catalogo: URL, fecha de descarga, CRS original y resolucion original.
4. Crear una version en `processed/` con los cambios necesarios para combinarla:
   - recorte al area de interes de Ciudad Lineal;
   - reproyeccion a `EPSG:25830`;
   - limpieza de geometria si es vectorial;
   - remuestreo o rasterizacion si debe entrar en una rejilla comun.
5. Documentar en `processed/README.md` el archivo generado, su fuente `raw`, el CRS final y las transformaciones aplicadas.

## Notas de licencias

- **OpenStreetMap:** OpenStreetMap contributors, licencia ODbL; citar la atribucion.
- **Copernicus (DEM, CLC):** datos abiertos de Copernicus; revisar y citar las condiciones de uso.
- **IGN / CNIG, MITECO, IGME:** datos publicos; revisar la licencia especifica de cada producto y citar la fuente.
