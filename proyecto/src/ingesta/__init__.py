"""Subpaquete de ingesta: primer bloque del pipeline geoespacial.

Descarga/recorta cada capa GIS (DEM, catastro, OSM, hidrografía IGN, Red Natura
2000, IGME, zonas inundables) al AOI, la reproyecta a EPSG:25830 y la
remuestrea/rasteriza a una REJILLA COMÚN. Sin alineación (mismo CRS y misma
rejilla) las capas no se pueden combinar: la celda (i, j) debe representar el
mismo trozo de terreno en todas — de lo contrario los costes mienten.

Este subpaquete es la única puerta de entrada de datos al proyecto y produce el
recorte alineado del AOI que consumen `superficie/`, `trazados/` y `metricas/`.

Módulos principales:
    * ``descargar_capas``     — descarga los crudos del AOI (WFS/WCS/Overpass)
      hacia ``data/raw/*_{escenario}`` y escribe el manifiesto de estado.
    * ``alinear_capas``       — reproyecta a EPSG:25830, remuestrea a la rejilla
      común y recorta al AOI → ``data/processed/Recorte_AOI/*_{escenario}``.
    * ``convertir_catastro``  — normaliza los ZIP del Catastro (shapefile / GML
      INSPIRE / paquete provincial de la Sede) a ``PARCELA.shp``.
    * ``preparar_escenario``  — orquestador end-to-end (descarga → alinea →
      genera superficies de coste) para un escenario nuevo.

Contrato del manifiesto de estado (``data/raw/manifiesto_estado.json``): lo
escribe ``descargar_capas`` y lo lee ``alinear_capas``. Estados por capa:
``ok`` (datos válidos), ``empty`` (sin cobertura, se alinea vacío legítimamente),
``failed`` (descarga fallida: NO se alinea, para no producir recortes vacíos
engañosos) y ``partial`` (datos escritos pero con alguna subfuente caída).

Librerías: rasterio, geopandas, shapely, pyproj, osmnx.
"""
