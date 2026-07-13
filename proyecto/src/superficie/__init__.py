"""Superficies de coste (raster multicriterio).

Convierte cada capa alineada en un coste por celda (pendiente -> coste; suelo urbano ->
coste alto; Red Natura 2000 -> coste muy alto o prohibido; proximidad a cruces -> coste)
y las combina con un VECTOR DE PESOS. Cada perfil de prioridad produce una superficie
distinta y, por tanto, una ruta distinta. Todo coste es RELATIVO (índice), nunca €.

Módulos del subpaquete
----------------------
Cada módulo de criterio lee sus entradas de ``data/processed/Recorte_AOI/`` (DEM
alineado + vectores/rasters ya reproyectados a EPSG:25830) y escribe una capa de
coste normalizada en ``data/processed/Capas_Coste/`` (GeoTIFF float32, nodata
-9999, LZW) junto a un ``.qml`` de leyenda para QGIS:

  - ``geotecnia``          — coste por litología IGME (columna DLO).
  - ``zonas_protegidas``   — Red Natura 2000 (binaria estandarizada).
  - ``zonas_inundables``   — láminas de inundación SNCZI (binaria estandarizada).
  - ``expropiacion``       — coste catastral por tipo de parcela (TIPO).
  - ``cruces_viario_rios`` — coste de cruce de viario OSM + hidrografía.
  - ``tpi``                — posición topográfica (cresta barata / valle caro) +
                             barrera dura de pendiente.

Y dos módulos transversales:

  - ``config``   — cargador cacheado de ``data/config/perfiles.yaml`` (pesos y
                   parámetros de cada capa).
  - ``combinar`` — suma ponderada de las capas por perfil → superficie única en
                   ``data/processed/Trazados/superficie_{s}.tif`` para el LCP.

Todas las capas se alinean a la MISMA rejilla (la del DEM), premisa para que la
combinación ponderada sea coherente celda a celda.
"""
