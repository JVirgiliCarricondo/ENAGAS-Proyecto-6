"""Ingesta y alineación de las capas GIS (DEM, CLC, OSM, hidrografía IGN, Red Natura 2000, IGME).

Descarga/recorta cada capa al AOI, la reproyecta a EPSG:25830 y la remuestrea/rasteriza
a una REJILLA COMÚN. Sin alineación (mismo CRS y rejilla) las capas no se pueden combinar:
la celda (i, j) debe representar el mismo trozo de terreno en todas. Librerías: rasterio,
geopandas, shapely, pyproj, osmnx.
"""
