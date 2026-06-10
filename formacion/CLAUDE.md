# Formación — Grupo 6 (Reto 6, Enagás)

> Dimensión 1: formar a los alumnos en las habilidades técnicas que necesitan para resolver el reto.
> Volver al [CLAUDE.md raíz](../CLAUDE.md).

## Objetivo

Llevar a los 3-4 alumnos del grupo desde su punto de partida hasta poder construir, entender y defender un **pipeline geoespacial** que genera y compara trazados de ramales de H₂: ingesta y alineación de capas GIS, superficies de coste multicriterio, camino de mínimo coste (LCP) y diferenciación de rutas. La formación no es un bloque previo y cerrado: arranca en la Semana 0 (campus de vibe coding) y **continúa en paralelo al proyecto**, con refuerzos puntuales (*just-in-time*) cuando cada técnica se necesita.

## Habilidades objetivo

1. **Python geoespacial** — numpy, geopandas, rasterio, shapely, pyproj.
2. **Sistemas de referencia y alineación** — CRS/EPSG, reproyección, remuestreo, alineación de rasters a una rejilla común (el "normalizar antes de comparar" de este reto).
3. **Modelos de elevación y pendiente** — leer un DEM y derivar la pendiente.
4. **Vector ↔ raster** — rasterización de capas vectoriales (Red Natura 2000, CLC, OSM) a la rejilla común.
5. **Superficies de coste y análisis multicriterio** — combinar capas con pesos en un índice de coste.
6. **Algoritmos de camino de mínimo coste** — Dijkstra / MCP sobre la rejilla (skimage.graph, networkx).
7. **Diferenciación de rutas** — corridor masking y perfiles de prioridad.
8. **Visualización geoespacial** — mapas (folium/contextily) y comparativa multicriterio.
9. **Fuentes de datos públicas** — descarga de Copernicus (DEM, CLC), OSM, IGN, Red Natura 2000, IGME.

## Plan

El itinerario semana a semana, con recursos y criterios de "hecho", está en [`plan_formativo.md`](plan_formativo.md).

## Materiales

Los materiales, ejercicios y enlaces se guardan en [`recursos/`](recursos/). Cada recurso se enlaza desde el plan formativo.

## Principio

> Se aprende construyendo el reto. Cada técnica se introduce **cuando el proyecto la pide** y se consolida aplicándola al prototipo, no con ejercicios desconectados.
