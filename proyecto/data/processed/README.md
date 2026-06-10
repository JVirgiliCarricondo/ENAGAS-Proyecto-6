# Capas procesadas

Esta carpeta contiene las versiones preparadas para combinarse en un unico proyecto GIS de Ciudad Lineal.

Los archivos de datos no se versionan porque pueden ser pesados. Este README si debe mantenerse actualizado para que cada capa procesada sea trazable a su fuente original.

## Convencion de nombres

Usar el formato:

```text
ID_ciudad-lineal_CRS[_resolucion].ext
```

Ejemplos:

- `OSM_ciudad-lineal_25830.gpkg`
- `DEM_ciudad-lineal_25830_30m.tif`
- `RN2000_ciudad-lineal_25830.gpkg`

## Registro de transformaciones

| Archivo procesado | Fuente en `raw/` | CRS final | Resolucion final | Cambios aplicados | Fecha | Responsable |
|-------------------|------------------|-----------|------------------|-------------------|-------|-------------|
| _(pendiente)_ | _(pendiente)_ | EPSG:25830 | _(pendiente)_ | recorte AOI, reproyeccion, limpieza/remuestreo | _(pendiente)_ | _(pendiente)_ |

## Reglas para combinar capas

Antes de combinar varias capas, comprobar que:

1. Todas estan en `EPSG:25830`.
2. Todas estan recortadas al mismo AOI de Ciudad Lineal.
3. Las capas raster usan la misma resolucion y alineacion de celda.
4. Las capas vectoriales no tienen geometria invalida.
5. El ID coincide con una fila documentada en `raw/FUENTES.md`.
