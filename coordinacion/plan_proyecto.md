# Plan de proyecto — Grupo 6 (Reto 6, Enagás)

> Plan de trabajo del prototipo. Sprints semanales de lunes a viernes. Cierre del programa: **17 jul 2026**.
>
> **Dos lecturas complementarias del avance:**
> - **Hitos semanales (H0-H7)** — la cadencia de este plan, abajo.
> - **Escalera MVP (MVP 1-8)** — la madurez de producto que pide Enagás, en [`../docs/hitos_mvp.md`](../docs/hitos_mvp.md). El núcleo comprometido del verano es **MVP 1-4**; MVP 5-8 son ambición/continuidad.

## Hitos semanales

| # | Hito | Fecha objetivo | MVP que cubre |
|---|------|----------------|----------------|
| H0 | Formación intensiva completada | 29 may ✅ | — |
| H1 | Entorno + catálogo de capas + AOI/origen/destino + **matriz de condicionantes** + validación de calidad de datos | 5 jun | MVP 1 (inicio) |
| H2 | Capas descargadas, reproyectadas (EPSG:25830) y alineadas a rejilla común | 12 jun | MVP 1 |
| H3 | Ráster de coste multicriterio + perfiles + **trazado base** (A\*/Dijkstra) | 19 jun | MVP 2 |
| H4 | Motor LCP consolidado (una ruta por perfil) | 26 jun | MVP 2-3 |
| H5 | Rutas diferenciadas + métricas multicriterio + comparativa + **ranking y recomendación** + mapa | 3 jul | MVP 3-4 |
| H6 | Evaluación (rutas distintas, métricas correctas) + **backtesting con un ramal real** (si disponible) + robustez | 10 jul | MVP 4, 6 |
| H7 | Presentación final + demo (+ EV-500 / herramienta operativa si da tiempo) | 17 jul | MVP 5/7 (reach) |

## Sprints

### S1 (1–5 jun) — Setup + catálogo de capas + AOI · 🟡 en curso · ➡️ MVP 1
- Montar entorno geoespacial (`proyecto/`), repos y dependencias.
- Catalogar las capas GIS públicas en `proyecto/data/raw/FUENTES.md` (URL, fecha, CRS original, resolución).
- Definir AOI, origen (planta H₂) y destino (conexión a red troncal) en `proyecto/data/config/`.
- Esbozar los perfiles de prioridad (vectores de pesos) en `proyecto/data/config/perfiles.yaml`.
- Construir la primera **matriz de condicionantes** (clasificar cada capa/criterio en técnico / ambiental / administrativo).
- **Validación de calidad de datos:** comprobar cobertura y huecos de cada capa sobre el AOI.
- **Entregable:** entorno reproducible + capas catalogadas + AOI/origen/destino fijados + matriz de condicionantes inicial.

### S2 (8–12 jun) — Ingesta y alineación · ➡️ MVP 1
- Pipeline de descarga/recorte de cada capa al AOI.
- Reproyección a **EPSG:25830** y remuestreo a una **rejilla común**.
- Rasterización de capas vectoriales (Red Natura 2000, CLC, OSM) a la rejilla.
- **Entregable:** todas las capas alineadas (mismo CRS y rejilla), verificable superponiéndolas.

### S3 (15–19 jun) — Superficies de coste + trazado base · ➡️ MVP 2
- Función de coste por capa (pendiente, uso de suelo, protección, proximidad a cruces…).
- Combinación multicriterio con pesos → superficie de coste.
- Perfiles de prioridad: distintos pesos → distintas superficies.
- Primer **trazado base** origen→destino por camino de menor coste (**A\* / Dijkstra**), itinerario continuo que evita condicionantes críticos.
- **Entregable:** superficies de coste reproducibles + un trazado base automático.

### S4 (22–26 jun) — Motor LCP · ➡️ MVP 2-3
- Consolidar el camino de mínimo coste origen→destino (`skimage.graph` / `networkx`).
- Una ruta por perfil, con su geometría y coste relativo.
- **Entregable:** motor LCP que devuelve una ruta válida por perfil.

### S5 (29 jun–3 jul) — Alternativas + métricas + comparador · ➡️ MVP 3-4
- Diferenciación de rutas: corridor masking + perfiles; validar solapamiento (evitar redundancia).
- Métricas por ruta: longitud, coste relativo, cruces, km protegida/urbana, pendiente máx/media.
- Tabla comparativa + **ponderación + ranking** + **recomendación** preliminar; mapa (folium) y, si da tiempo, UI Streamlit.
- **Entregable:** 3-5 rutas diferenciadas con comparativa, ranking y recomendación.

### S6 (6–10 jul) — Evaluación + backtesting + robustez · ➡️ MVP 4, 6
- Casos tipo (ver [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md) §8).
- Comprobar diferenciación real y corrección de métricas; cazar rutas duplicadas y costes mal combinados.
- **Backtesting:** comparar las alternativas con un **ramal real existente** (si Enagás lo facilita): proximidad, coherencia de corredor, explicación de desviaciones; ajuste iterativo del modelo de costes.
- Robustez ante cambios de AOI/origen/destino.
- **Entregable:** informe de evaluación con resultados (y backtesting si hay ramal real).

### S7 (13–17 jul) — Pulido + presentación (+ reach EV-500 / herramienta) · ➡️ MVP 5/7
- Refinar UI/mapa y mensajes; documentar limitaciones y siguientes pasos.
- *Si el núcleo está sólido (reach):* primer "paquete tipo **EV-500**" de la alternativa elegida (plano, exportable GIS, relación de cruces, afección por términos municipales, narrativa) y/o salidas para terceros (shapefile, Excel comparativo).
- Preparar y ensayar la presentación final tipo mini-consultoría; situar MVP 5-8 como hoja de ruta de continuidad.
- **Entregable:** demo + presentación.

## WBS (desglose de trabajo)

```
1. Datos GIS y condicionantes                                  [MVP 1]
   1.1 Catálogo de capas (FUENTES.md) con CRS y resolución originales
   1.2 Descarga y recorte al AOI
   1.3 Reproyección (EPSG:25830) + remuestreo a rejilla común + rasterización
   1.4 Matriz de condicionantes (técnicos / ambientales / administrativos)
   1.5 Validación de calidad de datos y detección de vacíos
2. Superficies de coste                                        [MVP 2]
   2.1 Función de coste por capa
   2.2 Combinación multicriterio con pesos
   2.3 Perfiles de prioridad
3. Trazados                                                    [MVP 2-3]
   3.1 Trazado base (A* / Dijkstra) origen→destino
   3.2 Motor LCP (una ruta por perfil)
   3.3 Diferenciación (corridor masking + validación de solapamiento)
4. Métricas                                                    [MVP 4]
   4.1 Longitud y coste relativo
   4.2 Cruces especiales (nº y tipo)
   4.3 Km en zona protegida / urbana
   4.4 Pendiente máxima y media
5. Comparativa + decisión                                      [MVP 4]
   5.1 Tabla multicriterio + ponderación + ranking
   5.2 Recomendación preliminar de trazado
   5.3 Mapa (folium / contextily) y UI (Streamlit)
6. Validación                                                  [MVP 4, 6]
   6.1 Pruebas de alineación de rasters
   6.2 Pruebas de métricas y de diferenciación de rutas
   6.3 Backtesting frente a un ramal real (si disponible) + ajuste de costes
7. Comunicación
   7.1 Documentación
   7.2 Presentación final
8. Ambición / continuidad (si el núcleo está sólido)           [MVP 5, 7, 8]
   8.1 Paquete pre-ingeniería tipo EV-500 (plano, exportable GIS, cruces, afección municipal)
   8.2 Herramienta operativa para terceros (selección interactiva, salidas shapefile/Excel)
   8.3 Industrialización (versionado de escenarios, trazabilidad de decisiones)
```

## Definición de "hecho" (DoD)

Una tarea está hecha cuando: el código corre en el entorno del proyecto, **todas las capas comparten CRS (EPSG:25830) y rejilla común**, las rutas generadas son **demostrablemente diferenciadas**, y **todos los costes son relativos (índice), nunca en €**.
