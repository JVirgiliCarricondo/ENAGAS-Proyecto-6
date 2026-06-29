# Metodología oficial Enagás — Valoración y comparación de corredores

> Tablas y fórmulas facilitadas por Enagás en las **bases para la ejecución del trabajo**
> (*"Proyectos de ingeniería básica para gasoductos"*). Documento de referencia citable del Grupo 6.
> Análisis del reto en [`reto6_enagas.md`](reto6_enagas.md). Hitos en [`hitos_mvp.md`](hitos_mvp.md).
> Mapeo a nuestras capas de coste: ver §4 y [`../proyecto/data/config/perfiles.yaml`](../proyecto/data/config/perfiles.yaml).

## 1. Para qué sirve

Esta es la metodología que **Enagás usa internamente** para valorar y comparar corredores de gasoducto
en ingeniería básica. Nos da dos cosas que sustituyen a nuestros números "orientativos" por criterios
**defendibles ante el cliente**:

1. **Factores de ponderación (A)** por tipo de condicionante (§2) → calibran las penalizaciones de la
   **superficie de coste** que genera las rutas.
2. **La fórmula de dificultad del corredor `G = E·F`** (§3) → métrica oficial *a posteriori* para
   **rankear las alternativas** ya generadas.

> ⚠️ Igual que el resto del prototipo, todo aquí es **coste/dificultad relativa (índice), nunca €**.
> Los factores A son adimensionales; G se expresa en "metros de dificultad" (ver §3).

## 2. Factores de ponderación (A) por condicionante

Cada condicionante tiene un factor de ponderación **A** (adimensional). A mayor A, más se debe evitar.
Están agrupados por **nivel de sensibilidad**:

### Áreas que deben evitarse (Factor ≥ 30)

| Condicionante | A |
|---|---:|
| Aeródromo | 50.25 |
| Humedales internacionales (RAMSAR) | 39 |
| Árboles monumentales | 39 |
| Minas | 38 |
| Almacenamiento subterráneo | 38 |
| Terrenos inestables (deslizamientos, arcillas expansivas…) | 38 |
| Parque eólico y Estaciones fotovoltaicas | 37.75 |
| Cantera | 31.75 |
| Paredes verticales, Acantilados | 31.75 |

### Áreas muy sensibles (20 ≤ Factor < 30)

| Condicionante | A |
|---|---:|
| Parque Natural Nacional | 29.5 |
| RED NATURA 2000 | 28.5 |
| Sitio arqueológico | 25.5 |
| Área urbana con alta densidad (> 80 hab/ha) | 25.25 |
| Sitio Patrimonio de la Humanidad (UNESCO) | 22 |
| Reserva natural regional | 20.75 |
| Pendiente muy fuerte | 20.5 |
| Roca muy dura y abrasiva | 20.5 |

### Áreas sensibles (13 ≤ Factor < 20)

| Condicionante | A |
|---|---:|
| Área urbana con densidad media (8 < hab/ha ≤ 80) | 17.75 |
| Zona industrial | 17.75 |
| Masa forestal densa | 17.75 |
| Hábitat prioritario | 17.75 |
| Zona natural de interés para la flora y la fauna — tipo 1 | 15.75 |
| Fuerte pendiente | 14.25 |
| Zonas inundables | 14.25 |
| Sobreocupación de terrenos (pista) | 13.25 |
| Curso hídrico con presencia permanente de agua | 13 |
| Zona arqueológica potencial | 13 |
| Roca dura | 13 |
| Viñedos | 13 |

### Áreas de baja sensibilidad (Factor < 13)

| Condicionante | A |
|---|---:|
| Olivar u otros cultivos singulares (de interés económico) | 12 |
| Zona natural de interés para la flora y la fauna — tipo 2 | 11.75 |
| Área sensible natural — Propiedad municipal | 10.75 |
| Curso hídrico sin presencia de agua permanente | 9.75 |
| Montes de Utilidad Pública | 9 |
| Cruce por perforación horizontal | 7 |
| Almendros | 7 |
| Presencia de bancales | 6 |

### Condicionante positivo (D)

| Condicionante | A |
|---|---:|
| **Corredor de infraestructuras existentes** | **−0.5** |

> El único factor **negativo**: pegarse a infraestructuras existentes (líneas eléctricas, carreteras,
> otros gasoductos) **reduce** la dificultad. Es un *premio*, no una penalización.

## 3. Dificultad del corredor: `G = E·F`

La métrica oficial para ordenar alternativas. Se calcula sobre cada corredor **ya trazado**:

1. **Por condicionante:** `C = A × B`
   - `A` = factor de ponderación (§2, adimensional)
   - `B` = longitud que afecta al trazado (m)
2. **Longitud total ponderada:** `D = Σ C` (suma sobre todos los tipos de condicionante, incluido el
   positivo −0.5)
3. **Coeficiente de dificultad del pasillo:** `F = (D − E) / E` (adimensional)
   - `E` = longitud física del corredor (m)
4. **Dificultad del corredor:** `G = E · F`

> **Simplificación útil:** como `F = (D − E)/E`, entonces `G = E·F = D − E`.
> Es decir, **la dificultad es la longitud ponderada menos la longitud física** ("metros de dificultad
> en exceso"). Un corredor que solo atravesara terreno trivial (todos los A = 0) tendría `D = E` y `G = 0`.

**Criterio de selección:** la alternativa óptima es la de **menor G**, siempre bajo el juicio final de
los responsables del proyecto. Es un criterio comparativo (qué alternativa tiene menor impacto sobre el
área de estudio), no una valoración absoluta.

### Tabla de resultados por alternativa

| | E (m) — long. física | D (m) — long. ponderada | F — coef. dificultad | G (m) — dificultad |
|---|---|---|---|---|
| Alternativa 1 | | | | G-1 |
| Alternativa 2 | | | | G-2 |
| … | | | | … |
| Alternativa N | | | | G-N |

### Desglose por tipología (las 7 familias de condicionantes)

La toma de decisión se complementa con una tabla de longitudes ponderadas (D) agrupadas en **7 tipologías**.
Cada tipología aporta un % de cada alternativa; los 7 suman el 100% de la dificultad total.

| Aspecto analizado | Alt. 1 | Alt. 2 | … | Alt. N |
|---|---|---|---|---|
| Aspectos ambientales | | | | |
| Aspectos arqueológicos | | | | |
| Condicionantes urbanísticos | | | | |
| Condicionantes constructivos | | | | |
| Cruces y zonas especiales | | | | |
| Cultivos | | | | |
| Aspectos positivos (ponderaciones negativas) | | | | |
| **TOTAL** | **G-1** | **G-2** | **…** | **G-N** |

## 4. Mapeo a nuestro pipeline

Cómo se traduce la metodología oficial a las capas y módulos del prototipo. Pesos actuales en
[`perfiles.yaml`](../proyecto/data/config/perfiles.yaml).

> **Estandarización aplicada (29-jun-2026).** Los valores intra-capa se anclaron al factor oficial mediante `coste = A / 38` (A_REF=38 = terrenos inestables), preservando la jerarquía oficial y manteniendo cada capa en [0, 1]. La pendiente queda fuera (curva por tramos propia). Tablas resultantes en [`../proyecto/Modelo_Coste.md`](../proyecto/Modelo_Coste.md) §5–§6.A y en `perfiles.yaml`.

| Condicionante oficial (A) | Nuestra capa / parámetro | Estado de calibración |
|---|---|---|
| Terrenos inestables (38), Roca muy dura (20.5), Roca dura (13) | `geotecnia` (`parametros_capas.geotecnia`) | **Aplicado**: yeso/inestable A=38 → 1.00 (techo), roca dura A=13 → 0.34. |
| Pendiente muy fuerte (20.5), Fuerte pendiente (14.25) | `pendiente` (curva por tramos) | **Sin tocar** (fuera del anclaje A): curva propia + `umbral_barrera_deg`. |
| RED NATURA 2000 (28.5), Parque Nacional (29.5), Reserva regional (20.75) | `protegida` (`zonas_protegidas`) | **Aplicado**: binaria 0 / 0.75 (A=28.5/38), por debajo de inestabilidad/pendiente extrema. |
| Área urbana alta/media densidad (25.25 / 17.75), Zona industrial (17.75) | `expropiacion` (tipos catastrales U/X) | **Aplicado**: U=0.66 (A=25.25), periurbano=0.47 (A=17.75). |
| Curso hídrico permanente (13) / no permanente (9.75), Cruce perforación horizontal (7) | `cruces` (ríos + viario) | **Aplicado** a ríos: permanente 0.34 (A=13), no permanente 0.26 (A=9.75). Viario/ferrocarril sin factor oficial → calibración constructiva. |
| Sitio/zona arqueológica (25.5 / 13), Patrimonio UNESCO (22) | *(sin capa)* | Pendiente de fuente; tipología "arqueológicos". |
| Viñedos (13), Olivar (12), Almendros (7), Bancales (6) | *(sin capa)* | Tipología "cultivos"; capa de usos agrícolas pendiente. |
| **Corredor de infraestructuras existentes (−0.5)** | *(sin modelar)* | **Falta**: bonus negativo que premia seguir trazas existentes. A añadir. |

> **Dos usos, no confundir:**
> - Los factores **A** calibran la **superficie de coste** (genera rutas) → `perfiles.yaml`.
> - La fórmula **G = D − E** rankea las rutas **ya generadas** → módulo `comparacion/`.
