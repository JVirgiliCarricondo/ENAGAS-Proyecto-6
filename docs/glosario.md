# Glosario — Grupo 6 (Reto 6, Enagás)

Términos de dominio (GIS / análisis geoespacial) y técnicos (algoritmos de rutas). Mantener vivo: si un término te frena, añádelo.

## Dominio: GIS y datos geoespaciales

| Término | Definición |
|---------|------------|
| **GIS / SIG** | Sistema de Información Geográfica: herramientas y datos para capturar, almacenar y analizar información referenciada espacialmente. |
| **Raster** | Datos geográficos como rejilla de celdas (píxeles), cada una con un valor (p.ej. elevación). Formato típico: GeoTIFF. Es el modelo natural para superficies de coste. |
| **Vector** | Datos geográficos como geometrías (puntos, líneas, polígonos) con atributos. Formatos: GeoPackage, shapefile, GeoJSON. Típico para ríos, carreteras, límites de zonas protegidas. |
| **DEM (Modelo Digital de Elevaciones)** | Raster con la altitud del terreno en cada celda. Base para derivar la **pendiente**. En inglés *DEM / DTM*. Fuente por defecto: Copernicus DEM (GLO-30, ~30 m). |
| **Pendiente (slope)** | Inclinación del terreno, derivada del DEM (gradiente de la elevación). En grados o en %. Penaliza el coste de trazado. |
| **CRS (Sistema de Referencia de Coordenadas)** | Define cómo las coordenadas se relacionan con posiciones en la Tierra (geográficas en lat/lon o proyectadas en metros). Comparar/combinar capas exige un CRS común. |
| **EPSG** | Catálogo de códigos numéricos para CRS. Cada CRS tiene un código EPSG (p.ej. EPSG:4326 = WGS84 lat/lon). |
| **EPSG:25830** | **ETRS89 / UTM zona 30N**. CRS proyectado (en metros) de referencia para la **península ibérica**. CRS de trabajo del proyecto: todas las capas se reproyectan aquí. |
| **Reproyección** | Transformar una capa de un CRS a otro. Imprescindible para alinear capas de fuentes distintas. |
| **Remuestreo (resampling)** | Cambiar la resolución/rejilla de un raster (nearest, bilinear…). Necesario para llevar todas las capas a una **rejilla común**. |
| **Rejilla común / alineación de rasters** | Mismo CRS, misma resolución y mismo origen de celda en todas las capas, de modo que la celda (i, j) represente el mismo trozo de terreno en todas. **"Alinear antes de combinar"** — el corazón técnico del reto. |
| **Rasterización** | Convertir capas vectoriales (Red Natura, CLC, OSM) en raster sobre la rejilla común, para poder combinarlas en la superficie de coste. |
| **AOI (Área de Interés)** | *Area Of Interest*. Recorte geográfico (bounding box o polígono) dentro del cual se trabaja: acota descargas y cómputo. |
| **CLC (Corine Land Cover)** | Capa europea de **usos del suelo** (urbano, agrícola, forestal…). Fuente: Copernicus Land Monitoring. Aporta el coste por tipo de suelo. |
| **Red Natura 2000** | Red europea de **espacios protegidos** (ZEC/ZEPA). Define zonas a evitar o penalizar fuertemente. Fuente: MITECO / Copernicus. |
| **OSM (OpenStreetMap)** | Cartografía colaborativa libre: viario, ferrocarril, hidrografía, núcleos urbanos, infraestructuras. Aporta cruces especiales. Descarga vía `osmnx` / Overpass. |
| **IGN / CNIG** | Instituto Geográfico Nacional / Centro Nacional de Información Geográfica (España). Fuente oficial de hidrografía y cartografía base. |
| **IGME** | Instituto Geológico y Minero de España. Mapa geológico (litología) → cruces geológicos especiales. |
| **Copernicus** | Programa europeo de observación de la Tierra. Fuente del DEM (GLO-30) y del Corine Land Cover. |
| **WMS / WFS / WCS** | Servicios web estándar de datos geográficos: **WMS** sirve mapas como imagen, **WFS** sirve vectores, **WCS** sirve coberturas raster. Útiles para descargar capas de IGN/IGME/Copernicus. |
| **GeoTIFF** | Formato raster con georreferencia embebida. Formato por defecto para DEM y superficies de coste. |
| **GeoPackage / shapefile / GeoJSON** | Formatos de datos vectoriales. GeoPackage (.gpkg) es el moderno recomendado; shapefile el clásico; GeoJSON el ligero/web. |

## Técnico: rutas, coste y diferenciación

| Término | Definición |
|---------|------------|
| **Superficie de coste (cost surface)** | Raster donde cada celda tiene un **coste de atravesarla**, resultado de combinar varias capas (pendiente, uso de suelo, protección, proximidad a cruces…) con pesos. Base para el cálculo de rutas. |
| **Análisis multicriterio** | Combinar varias capas/criterios (con pesos) en un único índice de coste. Cambiar los pesos cambia la ruta resultante. |
| **Perfil de prioridad** | Un vector de **pesos** que expresa una prioridad (p.ej. "minimizar impacto ambiental" pesa mucho Red Natura y CLC urbano). Cada perfil produce una superficie de coste y, por tanto, una ruta distinta. |
| **LCP (Least-Cost Path) / MCP (Minimum Cost Path)** | **Camino de mínimo coste**: la ruta entre origen y destino que minimiza la suma del coste de las celdas atravesadas sobre la superficie de coste. Núcleo algorítmico del reto. |
| **Dijkstra** | Algoritmo clásico de camino más corto en un grafo con pesos no negativos. Base conceptual del LCP (la rejilla se trata como un grafo donde cada celda es un nodo). |
| **`skimage.graph` (MCP_Geometric / route_through_array)** | Utilidades de scikit-image para calcular caminos de mínimo coste sobre un array 2D (la rejilla de coste). Opción por defecto para el LCP. |
| **Corridor masking** | Mecanismo de **diferenciación de rutas**: tras generar una ruta, se penaliza (enmascara) la proximidad a ella en la superficie de coste, forzando a las siguientes rutas a explorar corredores distintos. |
| **Diferenciación de rutas** | Garantía de que las 3-5 alternativas son **realmente distintas** (no el mismo corredor con ruido). Se logra con perfiles de prioridad distintos + corridor masking, y se valida midiendo el solapamiento entre rutas. |
| **Cruce especial** | Punto donde la ruta atraviesa una infraestructura o elemento natural relevante (río, carretera, ferrocarril, otra tubería). Se cuenta y clasifica como métrica. |
| **Índice de coste relativo** | Coste de una ruta expresado como **número adimensional normalizado** (0-1 o 0-100), **nunca en €**. Sirve para ordenar alternativas entre sí, no para presupuestar. |
| **Scoring / ranking de rutas** | Ordenar las alternativas según uno o varios criterios (o un agregado ponderado) para presentar la comparativa. |

## Técnico: stack y herramientas

| Término | Definición |
|---------|------------|
| **rasterio** | Librería de Python para leer/escribir y procesar rasters (GeoTIFF), reproyectar y remuestrear. |
| **geopandas** | Pandas para datos vectoriales: DataFrames con geometría, lectura de GeoPackage/shapefile, operaciones espaciales. |
| **shapely** | Geometrías y operaciones geométricas (intersección, buffer, longitud) sobre vectores. |
| **pyproj** | Transformaciones entre CRS (reproyección de coordenadas). Motor que usan rasterio/geopandas por debajo. |
| **osmnx** | Descarga y manejo de datos de OpenStreetMap como grafos/geometrías. |
| **scikit-image** | Procesamiento de imágenes; aquí, `skimage.graph` para el camino de mínimo coste sobre la rejilla. |
| **networkx** | Grafos en Python. Alternativa para el LCP modelando la rejilla como grafo (Dijkstra). |
| **folium** | Mapas interactivos (Leaflet) en Python. Candidato para visualizar las rutas. |
| **contextily** | Añade mapas base (teselas) a figuras de matplotlib/geopandas. |
| **Streamlit** | Framework de Python para interfaces web sencillas. Candidato para la UI con mapa interactivo. |
