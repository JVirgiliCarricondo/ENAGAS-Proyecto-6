# Biblioteca SIG — base de conocimiento del agente geógrafo-SIG

> **Propósito.** Bibliografía anotada que conforma la base de conocimiento del futuro **subagente experto en geografía y Sistemas de Información Geográfica (SIG)**, al servicio del Reto 6 (trazado automatizado de ramales de H₂). Complementa —sin duplicar— los dos documentos base ya presentes en esta carpeta.
>
> **Cómo se construyó.** Sobre los dos documentos base, una ronda de *deep research* (búsqueda multi-fuente + verificación adversarial 3-0 por afirmación) localizó y validó las referencias de los temas 1-4; los temas 5-8 (datos, CRS, pendiente, herramientas) se resolvieron con documentación oficial (fuente primaria por naturaleza) cuyos metadatos finos conviene confirmar al usarlos.

## Leyenda

- 📥 **En local** — el documento está descargado en esta carpeta.
- 🔗 **Enlace** — referencia por URL (no descargada).
- 🟢 **Acceso abierto** — PDF gratuito legal disponible.
- 🔴 **Muro de pago** — requiere suscripción o compra; busca versión de autor / repositorio institucional antes de pagar.
- ✅ **Verificado 3-0** — afirmación central confirmada por verificación adversarial unánime en el deep research.
- 📚 **Documentación/obra canónica** — fuente primaria oficial o libro de referencia (no sometida a verificación de afirmaciones individuales).

---

## 0. Referencias base (ya en la biblioteca)

Punto de partida; el resto **complementa** estas dos.

- 📥 📚 **Olaya, V. (2014).** *Sistemas de Información Geográfica.* — `Libro_SIG.pdf`
  Manual de fundamentos en español, exhaustivo y gratuito: modelos de datos (raster/vector), CRS, MDE/pendiente, álgebra de mapas, superficies de coste, evaluación multicriterio, visualización. **Por qué importa:** referencia transversal de fundamentos para todos los MVP; el agente la usa como "libro de texto".

- 📥 📚 **Da Silva, C. J. & Cardozo, O. D. (2015).** *Evaluación multicriterio y SIG aplicados a la definición de espacios potenciales para uso del suelo residencial en Resistencia (Argentina).* GeoFocus nº16, p. 23-40. ISSN 1578-5157. — `evaluacion-multicriterio-y-sistemas-de-informacion-5d7rngyu8y.pdf`
  Caso aplicado de EMC+SIG (criterios ambientales y de accesibilidad → aptitud del suelo). **Por qué importa:** ejemplo trabajado de cómo pasar de criterios a una superficie de aptitud por evaluación multicriterio (MVP 1, MVP 3-4).

---

## 1. Camino de mínimo coste (LCP / cost-distance): fundamentos y problemas conocidos

> El corazón algorítmico del reto (MVP 2). Estas fuentes fundamentan *por qué* se usa una superficie de coste y, sobre todo, *qué trampas* tiene el LCP sobre rejilla raster (sesgo diagonal, escala de los costes, distorsión).

- 🔗 🔴 ✅ **Etherington, T. R. (2016).** *Least-Cost Modelling and Landscape Ecology: Concepts, Applications, and Opportunities.* Current Landscape Ecology Reports. DOI: 10.1007/s40823-016-0006-9.
  Review canónica que define el *least-cost modelling* como técnica que incorpora costes de travesía para medir la distancia de mínimo coste entre puntos, como alternativa a la distancia euclídea cuando la línea recta no refleja el coste real. **Por qué importa:** marco conceptual del motor LCP (MVP 2); justifica usar superficie de coste en vez de distancia recta.
  Acceso: https://link.springer.com/article/10.1007/s40823-016-0006-9

- 🔗 🔴 ✅ **Etherington, T. R. (2012/2013).** *Least-cost modelling on irregular landscape graphs.* Landscape Ecology, vol. ~28. DOI: 10.1007/s10980-012-9747-y.
  Demuestra que los grafos de paisaje **regulares** (rejilla raster) producen resultados con **sesgo direccional** —artefacto conocido de la estructura de la rejilla— y propone un algoritmo (con código Python) para construir un grafo irregular a partir de la superficie de coste, con resultados comparables y menor coste computacional. **Por qué importa:** ataca directamente el sesgo diagonal/conectividad de vecindad del LCP (MVP 2); ofrece una mitigación implementable.
  ⚠️ **Corrección de cita:** el DOI (`s10980-012-`) sitúa la publicación en **2012/2013**, no en 2016 como suele citarse. Usar la fecha correcta.
  Acceso: https://link.springer.com/article/10.1007/s10980-012-9747-y

- 🔗 🔴 ✅ **Murekatete, R. M. & Shirabe, T. (2020/2021).** *An experimental analysis of least-cost path models on ordinal-scaled raster surfaces.* International Journal of Geographical Information Science, 35(8):1545-1569. DOI: 10.1080/13658816.2020.1753204.
  Muchos análisis LCP usan costes en **escala ordinal** (categorías ordenadas), pero el objetivo estándar de minimizar la suma de costes presupone una escala de razón. El paper compara modelos *minisum* vs *minimax* y muestra que la ruta resultante es sensible a decisiones arbitrarias (rango/incremento entre clases, valor de coste cero), no solo al patrón espacial. **Por qué importa:** advertencia crítica para construir la superficie de coste (MVP 2): *cómo se escalan y normalizan las capas cambia la ruta* — clave dado que el reto usa índice relativo, no €.
  Acceso: https://www.tandfonline.com/doi/full/10.1080/13658816.2020.1753204

- 🔗 🔴 ✅ **Seegmiller, L., Shirabe, T. & Tomlin, C. D. (2021).** *A method for finding least-cost corridors with reduced distortion in raster space.* International Journal of Geographical Information Science, 35(8):1570-1591. DOI: 10.1080/13658816.2020.1850734.
  Los métodos LCP raster estándar sufren distorsión (limitados a ~8 direcciones); el método propuesto, basado en transiciones de octágono, la reduce. Señala que cuando los corredores tienen **anchura no despreciable** deben modelarse como objetos 2D, midiendo coste como **área ponderada** en lugar de longitud. Coautoría de **C. D. Tomlin** (creador del álgebra de mapas). **Por qué importa:** exactitud del LCP (distorsión de rejilla) y paso de ruta-polilínea a **corredor con anchura de servidumbre** (MVP 2-3, EV-500).
  Acceso: https://www.tandfonline.com/doi/full/10.1080/13658816.2020.1850734

---

## 2. Corredores y trazado de infraestructura lineal (tuberías, líneas)

> El análogo directo del reto: trazar infraestructura lineal con SIG. La referencia de Durmaz & Ünal es prácticamente "el reto resuelto" para un gasoducto real.

- 🔗 🟢 ✅ **Durmaz, A. İ., Ünal, E. et al. (2019).** *Automatic Pipeline Route Design with Multi-Criteria Evaluation Based on Least-Cost Path Analysis and Line-Based Cartographic Simplification: A Case Study of the Mus Project in Turkey.* ISPRS International Journal of Geo-Information, 8(4):173. DOI: 10.3390/ijgi8040173.
  Un algoritmo automático determina la ruta óptima de un **gasoducto** evitando obstáculos y ponderando celdas por criterios (geográficos, sociales, económicos, ambientales); valida la ruta generada **contra el gasoducto real de Muş (~156 km, BOTAŞ)**, reportando ~20% de reducción de coste. **Por qué importa:** el espejo más cercano del reto completo — pipeline LCP+MCDA+**backtesting con trazado real** (MVP 2, 4, 6). Modelo de extremo a extremo.
  🟢 **Acceso abierto (CC BY):** página https://www.mdpi.com/2220-9964/8/4/173 · PDF https://www.mdpi.com/2220-9964/8/4/173/pdf
  ⚠️ *No se pudo descargar automáticamente (MDPI bloquea descargas de bots con Cloudflare). Descargar a mano desde un navegador → guardar en esta carpeta.*

- 🔗 🔴 ✅ **Bagli, S., Geneletti, D. & Orsi, F. (2011).** *Routeing of power lines through least-cost path analysis and multicriteria evaluation to minimise environmental impacts.* Environmental Impact Assessment Review, 31(3):234-239. DOI: 10.1016/j.eiar.2010.04.003.
  Plantea el flujo en tres niveles anidados: **mapas de criterios → superficie de coste (fricción) derivada combinando los factores por evaluación multicriterio → camino de mínimo coste.** Señala que el procedimiento se implementa fácilmente en SIG y se ha usado de carreteras a tuberías. **Por qué importa:** plantilla metodológica *exacta* del reto (criterios → superficie de coste MCE → LCP); muy citada (MVP 2-4).
  Acceso: https://www.sciencedirect.com/science/article/abs/pii/S0195925510001393

- 🔗 🔴 ✅ **Scaparra, M. P., Church, R. L. et al. (2014).** *Corridor location: the multi-gateway shortest path model.* Journal of Geographical Systems. DOI: 10.1007/s10109-014-0197-8.
  Formaliza el **problema de localización de corredores** (colocar una servidumbre origen→destino), que abarca tuberías, líneas eléctricas y carreteras; subraya la necesidad de **generar alternativas competitivas pero diferentes** y propone el modelo multi-gateway para hacerlo sin la explosión exponencial del k-shortest path. **Por qué importa:** encuadra el reto en una clase de problema bien definida y aporta un método para las **3-5 rutas diferenciadas** (MVP 3).
  Acceso: https://link.springer.com/article/10.1007/s10109-014-0197-8

---

## 3. Decisión multicriterio (MCDA / EMC) en SIG

> Cómo derivar pesos y combinar capas en la superficie de coste (MVP 1-4: matriz de condicionantes, perfiles de prioridad, ranking).

- 🔗 🔴 ✅ **Malczewski, J. (2006).** *GIS-based multicriteria decision analysis: a survey of the literature.* International Journal of Geographical Information Science, 20(7):703-726. DOI: 10.1080/13658810600661508.
  Survey que revisa y clasifica >300 artículos de GIS-MCDA (1990-2004), con taxonomía y tendencias; estructura la elección de reglas de decisión (WLC, AHP, OWA) para combinar capas en una superficie de aptitud/coste. **Por qué importa:** referencia estructurante para los perfiles de prioridad y la combinación de capas (MVP 3); mapa del campo.
  Acceso: https://www.tandfonline.com/doi/pdf/10.1080/13658810600661508

- 🔗 🔴 ✅ **Malczewski, J. (2006).** *Ordered weighted averaging with fuzzy quantifiers: GIS-based multicriteria evaluation for land-use suitability analysis.* International Journal of Applied Earth Observation and Geoinformation, 8(4):270-277. DOI: 10.1016/j.jag.2006.01.003.
  Aplica el operador **OWA** con cuantificadores lingüísticos difusos a la evaluación multicriterio en SIG, permitiendo controlar el nivel de compensación/riesgo entre criterios. **Por qué importa:** alternativa/complemento a WLC y AHP al combinar capas en la superficie de coste (MVP 3).
  ⚠️ **Corrección de cita:** citar con el DOI de Elsevier de arriba; **no** con `tandfonline 10.1080/13658810500433453` (esa URL es de otro artículo y una afirmación que la usaba fue **refutada 0-3**).
  Acceso: https://doi.org/10.1016/j.jag.2006.01.003

- 🔗 🔴 📚 **Malczewski, J. (1999).** *GIS and Multicriteria Decision Analysis.* John Wiley & Sons. ISBN 978-0-471-32944-2.
  La obra de referencia del campo (libro completo). **Por qué importa:** tratamiento sistemático de WLC/AHP/OWA y su integración con SIG; manual de cabecera para el componente MCDA del agente.
  Acceso: https://www.wiley.com/en-us/GIS+and+Multicriteria+Decision+Analysis-p-9780471329442

- 🔗 🔴 📚 **Saaty, T. L. (1980 / 1987).** *The Analytic Hierarchy Process* (McGraw-Hill, 1980) y *"The analytic hierarchy process—what it is and how it is used"* (Mathematical Modelling, 9(3-5):161-176, 1987).
  Origen del **AHP**: derivación de pesos por comparación por pares y razón de consistencia. **Por qué importa:** método para fijar de forma defendible los pesos de la matriz de condicionantes / perfiles de prioridad (MVP 1, 3).
  *Referencia fundacional conocida; no verificada en esta ronda de deep research.*

---

## 4. Generación de rutas alternativas diferenciadas

> El requisito de **3-5 corredores realmente distintos** (MVP 3). Ver también Scaparra et al. 2014 (Tema 2), que aporta el modelo multi-gateway.

- 🔗 🟢 ✅ **"Transmission Corridor Location: Multi-Path Alternative Generation Using the K-Shortest Path Method".** (Disponible en academia.edu, id 87382835.)
  Muestra que aplicar **k-shortest path** a localización de corredores hace crecer **exponencialmente** el número de rutas y el tiempo de cómputo ("overwhelming" en memoria y procesamiento). **Por qué importa:** advertencia práctica para generar las 3-5 alternativas (MVP 3) — el k-shortest puro escala mal; motiva **corridor masking / penalización de proximidad / multi-gateway**.
  ⚠️ *Menor autoridad: no arbitrado en revista como las demás. Usar como apoyo, no como fuente principal. Una afirmación más fuerte sobre k-shortest en rejillas densas fue **refutada 0-3**.*
  Acceso: https://www.academia.edu/87382835/

---

## 5. Fuentes de datos GIS públicas (España / Europa)

> 📚 Documentación oficial de las capas del reto (MVP 1). Cruza con [`../../proyecto/data/raw/FUENTES.md`](../../proyecto/data/raw/FUENTES.md), que es el catálogo operativo. *Metadatos finos (CRS/resolución/licencia exactos) a confirmar en cada ficha al descargar.*

- 📥 🟢 📚 **Copernicus DEM — Product Handbook (GLO-30 / GLO-90).** — `Copernicus_DEM_Product_Handbook_v5.0_2024.pdf`
  Manual oficial del modelo digital de elevaciones de Copernicus (GLO-30 ≈ 30 m, GLO-90 ≈ 90 m; datos públicos). **Por qué importa:** fuente del DEM → pendiente (MVP 1-2); documenta CRS, resolución y especificaciones del producto.
  Origen: https://dataspace.copernicus.eu/ (Copernicus Data Space Ecosystem).

- 🔗 🟢 📚 **CORINE Land Cover (CLC) — Product User Manual.** Copernicus Land Monitoring Service (EEA).
  Usos del suelo europeos (raster, típicamente 100 m / MMU 25 ha; gratuito). **Por qué importa:** coste por tipo de suelo, km en zona urbana (MVP 1, 4).
  Acceso: https://land.copernicus.eu/en/technical-library/clc-product-user-manual

- 🔗 🟢 📚 **OpenStreetMap — descargas regionales (Geofabrik: España).**
  Viario, ferrocarril, hidrografía, núcleos e infraestructuras (vector; ODbL — requiere atribución). **Por qué importa:** cruces especiales y red de infraestructuras (MVP 1, 4).
  Acceso: https://download.geofabrik.de/europe/spain.html

- 🔗 🟢 📚 **IGN / CNIG — Centro de Descargas.**
  Cartografía base oficial de España e hidrografía. **Por qué importa:** ríos y masas de agua para cruces, cartografía de referencia (MVP 1).
  Acceso: https://centrodedescargas.cnig.es/

- 🔗 🟢 📚 **Red Natura 2000 — descargas (MITECO).**
  Espacios protegidos (ZEC/ZEPA; vector). **Por qué importa:** zonas a evitar/penalizar y km en zona protegida (MVP 1, 4).
  Acceso: https://www.miteco.gob.es/en/cartografia-y-sig/ide/descargas/biodiversidad/rn2000.html

- 🔗 🟢 📚 **IGME — cartografía geológica.** *(Hueco: portal pendiente de confirmar.)*
  Litología / cruces geológicos especiales. **Por qué importa:** condicionante técnico (MVP 1). Confirmar el portal de descargas del IGME (p.ej. mapa geológico continuo / serie MAGNA).

---

## 6. CRS y proyecciones

- 🔗 🟢 📚 **EPSG:25830 — ETRS89 / UTM zone 30N (ficha oficial del EPSG Geodetic Registry).**
  Definición autoritativa del CRS de trabajo del proyecto (península; metros). **Por qué importa:** todas las capas se reproyectan aquí; "alinear antes de combinar" (MVP 1).
  Acceso: https://epsg.org/crs_25830/ETRS89-UTM-zone-30N.html
  *(Hueco complementario: Iliffe, J. & Lott, R. — "Datums and Map Projections" — como referencia de libro sobre datums/proyecciones; no verificada en esta ronda.)*

---

## 7. DEM y derivación de pendiente

- 📥 🟢 ✅ **Horn, B. K. P. (1981).** *Hill Shading and the Reflectance Map.* Proceedings of the IEEE, 69(1):14-47. — `Horn_1981_Hill-Shading-and-the-Reflectance-Map.pdf`
  Fuente del **algoritmo de pendiente de Horn** (ventana 3×3 ponderada), el más usado por defecto en SIG (GDAL/GRASS/QGIS). **Por qué importa:** cálculo de pendiente a partir del DEM, criterio del reto y capa de coste (MVP 1-2).
  Origen del PDF: https://people.csail.mit.edu/bkph/papers/Hill-Shading.pdf

- 🔗 🔴 📚 **Zevenbergen, L. W. & Thorne, C. R. (1987).** *Quantitative analysis of land surface topography.* Earth Surface Processes and Landforms, 12(1):47-56. DOI: 10.1002/esp.3290120107.
  Método alternativo de derivación de pendiente/curvatura (ajuste polinómico). **Por qué importa:** alternativa al método de Horn; el agente debe saber que la elección de algoritmo cambia ligeramente la pendiente (MVP 1).
  Acceso: https://onlinelibrary.wiley.com/doi/abs/10.1002/esp.3290120107

---

## 8. Herramientas geoespaciales (SIG libre / Python)

> 📚 Documentación oficial citable de las herramientas del pipeline (MVP 2-5).

- 🔗 🟢 ✅ **GRASS GIS — `r.walk` (manual oficial).**
  Coste acumulado de movimiento **anisótropo** (distinta velocidad cuesta arriba/abajo), con función tipo **Naismith/Langmuir** dependiente de pendiente y combinación con una superficie de fricción (`coste = tiempo de movimiento + λ · fricción · ΔS`). **Por qué importa:** herramienta clásica de coste-distancia que modela anisotropía por pendiente y fricción multicriterio — alternativa directa a `skimage.graph` (MVP 2).
  Acceso: https://grass.osgeo.org/grass78/manuals/r.walk.html

- 🔗 🟢 📚 **GRASS GIS — `r.cost` (manual oficial).**
  Coste acumulado **isótropo** sobre superficie de coste (el LCP "clásico"). **Por qué importa:** referencia conceptual del motor de mínimo coste (MVP 2).
  Acceso: https://grass.osgeo.org/grass-stable/manuals/r.cost.html

- 🔗 🟢 📚 **scikit-image — `skimage.graph` (MCP, MCP_Geometric, route_through_array).**
  API de camino de mínimo coste sobre array 2D. **Por qué importa:** motor LCP por defecto del prototipo (MVP 2).
  Acceso: https://scikit-image.org/docs/stable/api/skimage.graph.html

- 🔗 🟢 📚 **rasterio — Reproyección (`reproject`, warp).**
  Documentación de reproyección/remuestreo de rasters. **Por qué importa:** alinear capas a EPSG:25830 y a la rejilla común (MVP 1).
  Acceso: https://rasterio.readthedocs.io/en/stable/topics/reproject.html

- 🔗 🟢 📚 **GeoPandas — Managing Projections.**
  Reproyección de capas vectoriales y manejo de CRS. **Por qué importa:** alinear vectores (Red Natura, OSM) antes de rasterizar (MVP 1).
  Acceso: https://geopandas.org/en/stable/docs/user_guide/projections.html

---

## Notas de calidad, correcciones y huecos

**Verificación.** Las 13 referencias marcadas ✅ (temas 1-4 y `r.walk`) pasaron verificación adversarial unánime (3-0) sobre fuentes primarias revisadas por pares o documentación oficial. Las marcadas 📚 son documentación/obra canónica (fuente primaria por naturaleza), no sometida a verificación de afirmaciones individuales.

**Correcciones de cita detectadas:**
1. *Etherington — "irregular landscape graphs"* es **2012/2013** (DOI `s10980-012-…`), no 2016.
2. *Malczewski — OWA* debe citarse con **DOI Elsevier `10.1016/j.jag.2006.01.003`**, no con la URL `tandfonline …500433453`.

**Afirmaciones refutadas (0-3) — NO repetir:**
1. Que el artículo en `tandfonline …500433453` sea el de OWA de Malczewski (es otro paper).
2. Que el k-shortest path se extienda directamente a redes raster densas como técnica recomendada (la propia literatura advierte del coste exponencial; preferir multi-gateway / corridor masking).

**Huecos pendientes (segunda ronda):**
- Portal oficial del **IGME** (mapa geológico) con metadatos.
- Libro **Iliffe & Lott, "Datums and Map Projections"** (CRS/proyecciones).
- Documentación oficial de **Shapely**, **NetworkX** y **QGIS/PyQGIS**.
- Versiones de autor / repositorio institucional (PDF abierto legal) de las canónicas tras muro de pago: Etherington 2012/2016, Murekatete & Shirabe 2020, Seegmiller 2021, Bagli 2011, ambos Malczewski 2006, Scaparra 2014.

**Descargas en local (4 PDF):** Olaya 2014, Da Silva & Cardozo 2015 (base) + Copernicus DEM Handbook, Horn 1981 (nuevos). El resto son enlaces; MDPI (Durmaz & Ünal) es abierto pero requiere descarga manual por bloqueo anti-bot.
