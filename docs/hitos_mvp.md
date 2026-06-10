# Hitos MVP — escalera de objetivos progresivos (Enagás)

> Fuente oficial: [`Reto6 - Resumen_Objetivos.pdf`](Reto6%20-%20Resumen_Objetivos.pdf) (Enagás). Este documento analiza esa tabla y la integra en el plan del grupo.
>
> **Qué es esta escalera.** Ocho **MVP entregables** ordenados por **madurez de producto**: cada hito es una versión usable y más completa que la anterior. No son semanas: son *niveles de producto*. La cadencia semanal vive en [`../coordinacion/plan_proyecto.md`](../coordinacion/plan_proyecto.md); aquí está **hacia dónde** escala el producto.

## La escalera de 8 hitos

| Hito | MVP entregado | Qué incluye |
|------|---------------|-------------|
| **1** | **Datos y condicionantes** | Caso de estudio completo: origen y destino; recopilación de capas GIS públicas (DEM, uso del suelo, hidrografía, infraestructuras, Red Natura…); **normalización de CRS y resolución**; primera **matriz de condicionantes** (técnicos, ambientales, administrativos); **validación de calidad de datos y detección de vacíos**. |
| **2** | **Trazado base automático** | Primer **ráster de coste multicriterio** (pendiente, uso del suelo, zonas protegidas, cruces…) y cálculo de **un** trazado óptimo por **camino de menor coste (A\* o Dijkstra)**. Itinerario continuo origen→destino, coherente con el territorio y que evita condicionantes críticos. |
| **3** | **Alternativas de trazado** | **3-5 trazados diferenciados** variando **pesos y perfiles** (mínima distancia, mínimo impacto ambiental, mínimos cruces, equilibrio global). Mecanismos para **evitar redundancia** y asegurar **diversidad real de corredores**. Cartografía comparada. |
| **4** | **Comparador multicriterio (decisión)** | Caracterización automática de cada alternativa: longitud, pendiente media/máxima, km en zona protegida, km en entorno urbano, nº y tipo de cruces, **índice de coste relativo**. Tabla comparativa + **ponderación + ranking**. **Recomendación** preliminar. **Backtesting con un ramal real** (¿está entre las soluciones generadas?). |
| **5** | **Pre-ingeniería básica (parcial)** | "Paquete tipo **EV-500**" de la alternativa elegida: plano del trazado, **exportable GIS**, relación preliminar de **cruces especiales**, **afección por términos municipales** (si hay capa), conclusiones técnicas y **narrativa justificativa** de la elección. |
| **6** | **Validado (backtesting extendido)** | Comparación de las alternativas frente a un **trazado real existente**: análisis de proximidad, coherencia de corredor, explicación de **desviaciones** vía pesos y condicionantes. **Ajuste iterativo** del modelo de costes. |
| **7** | **Herramienta operativa** | Prototipo **usable por terceros**: selección **interactiva** de origen/destino, ejecución automática, salidas (**mapas, shapefiles, Excel comparativo**), parametrización básica de pesos y documentación de uso. |
| **8** | **Piloto industrializable** | Solución **replicable**: arquitectura de datos estable, **versionado de escenarios**, **trazabilidad de decisiones**, **alineación completa con EV-500** (entrada a fases posteriores: geotecnia, ambiental, presupuesto…) y preparación para **integración corporativa**. |

## Lectura para el programa (1 jun – 17 jul)

La escalera describe **toda la ambición** del reto, más allá del verano. Para el programa fijamos el alcance así:

- **Núcleo comprometido (MVP 1-4):** es lo que el prototipo **debe** lograr — de los datos alineados al comparador multicriterio con ranking y recomendación. Es justo el problema central del reto: *seleccionar y comparar trazados*.
- **Validación (parte de MVP 4 y MVP 6):** **backtesting** frente a un ramal real, **si Enagás facilita uno**. Aunque sea parcial, es el mejor argumento de credibilidad de la demo.
- **Ambición / continuidad (MVP 5, 7, 8):** pre-ingeniería EV-500, herramienta para terceros e industrialización. Se abordan **si el núcleo está sólido**; si no, son la hoja de ruta de "siguientes pasos" de la presentación final.

### Mapa hito MVP ↔ sprint

| MVP | Sprint(s) | Estado de compromiso |
|-----|-----------|----------------------|
| MVP 1 — Datos y condicionantes | S1-S2 | Núcleo |
| MVP 2 — Trazado base (A\*/Dijkstra) | S3-S4 | Núcleo |
| MVP 3 — Alternativas diferenciadas | S4-S5 | Núcleo |
| MVP 4 — Comparador + ranking + backtesting | S5-S6 | Núcleo |
| MVP 6 — Backtesting extendido | S6 | Si hay ramal real |
| MVP 5 — Pre-ingeniería EV-500 (parcial) | S7 | Ambición / reach |
| MVP 7 — Herramienta operativa | S7 | Ambición / reach |
| MVP 8 — Piloto industrializable | (post-programa) | Continuidad |

> Detalle por semana en [`../coordinacion/plan_proyecto.md`](../coordinacion/plan_proyecto.md).

## Conceptos nuevos que introduce la escalera

La tabla añade vocabulario y requisitos que no estaban en el enunciado breve. Los integramos en el resto del workspace (ver [`reto6_enagas.md`](reto6_enagas.md) y [`glosario.md`](glosario.md)):

- **Matriz de condicionantes** — clasificación de cada capa/criterio en **técnico**, **ambiental** o **administrativo**. Es la organización conceptual de las capas antes de convertirlas en coste.
- **Validación de calidad de datos / detección de vacíos** — comprobar cobertura, consistencia y huecos de las capas **antes** de combinarlas. Un vacío silencioso de datos también hace que los costes mientan.
- **A\* / Dijkstra** — la fuente nombra explícitamente el algoritmo de camino de menor coste. Encaja con el motor LCP del proyecto (`skimage.graph` / `networkx`).
- **Backtesting de trazados** — contrastar las alternativas generadas con un **ramal real existente** para validar el modelo y explicar desviaciones. Validación empírica, no solo interna.
- **Paquete tipo EV-500** — formato de **pre-ingeniería** de Enagás para empaquetar la alternativa elegida (plano, exportable GIS, cruces, afección municipal, narrativa). *Confirmar con Enagás el contenido exacto del estándar EV-500.*
- **Afección por términos municipales** — km/impacto del trazado desglosado por municipio atravesado (criterio administrativo).
- **Herramienta operativa para terceros** — UI interactiva + salidas estándar (shapefile, Excel) + parametrización de pesos + documentación de uso.
- **Industrialización** — versionado de escenarios, trazabilidad de decisiones y arquitectura replicable para integración corporativa.

> ⚠️ **EV-500:** es un estándar interno de Enagás. El grupo debe **confirmar su alcance exacto** en los días presenciales antes de comprometer el MVP 5/8.
