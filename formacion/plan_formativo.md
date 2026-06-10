# Plan formativo — Grupo 6 (Reto 6, Enagás)

> Itinerario *just-in-time*: cada técnica se introduce cuando el sprint la necesita. Alineado con [`../coordinacion/plan_proyecto.md`](../coordinacion/plan_proyecto.md).

## Mapa habilidad ↔ sprint

| Habilidad | Se introduce en | Se aplica en (proyecto) |
|-----------|-----------------|--------------------------|
| Python + entorno + git | S0 (formación) | Todo el proyecto |
| Dominio GIS + fuentes de datos públicas | S1 | Catálogo de capas, AOI, ingesta |
| Python geoespacial (rasterio, geopandas, shapely, pyproj) | S1–S2 | `src/ingesta/` |
| CRS, reproyección, remuestreo y alineación de rasters | S2 | Alineación a rejilla común |
| Vector ↔ raster (rasterización) | S2–S3 | Rasterizar Red Natura, CLC, OSM |
| Superficies de coste y análisis multicriterio | S3 | `src/superficie/` |
| Camino de mínimo coste (LCP / Dijkstra / MCP) | S3–S4 | `src/trazados/` |
| Diferenciación de rutas (corridor masking, perfiles) | S4–S5 | `src/trazados/` |
| Métricas geoespaciales por ruta | S5 | `src/metricas/` |
| Visualización geoespacial (folium / contextily) y UI | S5 | `src/comparacion/`, `src/app/` |
| Evaluación (¿rutas distintas? ¿métricas correctas?) | S6 | Pruebas y validación |
| Comunicación / presentación | S7 | Presentación final |

## Semana 0 (25–29 may) — Campus de vibe coding · ✅

Formación intensiva común del CI2 Lab. Objetivos para este grupo:

- Entorno de trabajo: Python, venv/conda, VS Code, git, uso de un asistente de código.
- Primer contacto con datos geoespaciales: la diferencia raster vs vector, qué es un CRS, abrir un GeoTIFF.
- Idea intuitiva del reto: "convertir el terreno en un mapa de coste y buscar caminos baratos y distintos".
- **Hecho cuando:** cada alumno tiene su entorno montado y ha abierto y pintado una capa GIS desde Python.

## Bloque 1 (S1–S2) — Dominio GIS + ingesta y alineación

**Objetivo:** entender las capas y saber dejarlas alineadas (CRS y rejilla comunes).

- Lectura guiada de [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md) y [`../docs/glosario.md`](../docs/glosario.md).
- Sesión de dominio: qué aporta cada capa (DEM, CLC, OSM, hidrografía IGN, Red Natura 2000, IGME) y de dónde se descarga. (Apoyarse en Enagás durante los días presenciales.)
- Organizar los criterios en una **matriz de condicionantes** (técnicos / ambientales / administrativos) y **validar la calidad de los datos** (cobertura sobre el AOI, huecos).
- Python geoespacial: leer rasters con `rasterio`, vectores con `geopandas`, geometrías con `shapely`, reproyectar con `pyproj`.
- CRS, reproyección y remuestreo: llevar todas las capas a **EPSG:25830** sobre una **rejilla común**.
- **Ejercicio:** descargar un DEM de la AOI, reproyectarlo a EPSG:25830 y derivar un raster de pendiente.
- **Hecho cuando:** el grupo deja dos capas distintas alineadas en la misma rejilla y lo demuestra superponiéndolas.

## Bloque 2 (S2–S3) — Vector ↔ raster y superficies de coste

**Objetivo:** convertir capas en coste por celda y combinarlas.

- Rasterización de capas vectoriales (Red Natura 2000, CLC, OSM) a la rejilla común.
- Diseño de la función de coste por capa (pendiente → coste; suelo urbano → coste alto; zona protegida → coste muy alto o prohibido).
- Análisis multicriterio: combinar capas con pesos en una única superficie de coste.
- **Ejercicio:** construir una superficie de coste mínima con dos capas (pendiente + uso de suelo) y visualizarla.
- **Hecho cuando:** existe una superficie de coste reproducible a partir de capas alineadas.

## Bloque 3 (S3–S4) — Camino de mínimo coste (LCP)

**Objetivo:** obtener una ruta origen→destino sobre la superficie de coste.

- La rejilla como grafo; intuición de Dijkstra / MCP.
- `skimage.graph` (`MCP_Geometric` / `route_through_array`); alternativa con `networkx`.
- Extraer la geometría de la ruta y su coste acumulado.
- **Ejercicio:** calcular el LCP entre origen y destino sobre la superficie de coste del bloque anterior.
- **Hecho cuando:** el motor devuelve una ruta válida (una por perfil) con su coste relativo.

## Bloque 4 (S4–S5) — Diferenciación de rutas y métricas

**Objetivo:** generar 3-5 rutas distintas y medirlas.

- Perfiles de prioridad: distintos vectores de pesos → distintas superficies → distintas rutas.
- Corridor masking: penalizar la proximidad a rutas ya generadas.
- Validar diferenciación: medir el solapamiento entre rutas y descartar las casi idénticas.
- Métricas por ruta: longitud, coste relativo, cruces (tipo y nº), km en zona protegida, km urbana, pendiente máx/media.
- **Ejercicio:** generar 3 rutas (corta / menor impacto / menor pendiente) y comprobar que son distintas.
- **Hecho cuando:** las rutas son demostrablemente diferenciadas y todas las métricas se calculan correctamente.

## Bloque 5 (S5) — Comparativa, mapa e interfaz

- Tabla comparativa multicriterio + scoring/ranking de alternativas.
- Visualización con `folium` (mapa interactivo) / `contextily` (mapa estático).
- Streamlit: entrada (origen/destino/perfil) → salida (mapa + tabla).
- **Hecho cuando:** un usuario no técnico ve las 3-5 rutas en un mapa y entiende la comparativa.

## Bloque 6 (S6) — Evaluación

- Casos tipo (ver [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md) §8).
- Comprobar que las rutas son realmente distintas y que las métricas son correctas (cruces, km en cada zona, pendiente).
- **Backtesting:** comparar las alternativas con un ramal real existente (si Enagás lo facilita) y explicar las desviaciones vía pesos/condicionantes.
- Robustez: cambiar AOI/origen/destino y ver que el pipeline aguanta.
- **Hecho cuando:** se pasan los casos sin rutas duplicadas ni métricas erróneas, todo coste es relativo (nunca €), y (si hay ramal real) el backtesting es coherente.

## Bloque 7 (S7) — Comunicación

- Construir la presentación final tipo mini-consultoría: problema, solución, demo, limitaciones, siguientes pasos.
- **Hecho cuando:** la demo (genera y compara rutas en vivo) funciona y la narrativa es clara para Enagás y la Cátedra.

## Seguimiento de la formación

Anotar dudas recurrentes y temas a reforzar en el seguimiento semanal de [`../coordinacion/seguimiento.md`](../coordinacion/seguimiento.md).
