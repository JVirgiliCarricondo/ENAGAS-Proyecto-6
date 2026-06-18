# Modelo de coste multicriterio — superficies de coste (hito 2)

> Diseño del paso 2 del pipeline (`src/superficie/`) y **matriz de condicionantes** del hito 1.
> Lectura previa: [`arquitectura.md`](arquitectura.md) · [`../docs/hitos_mvp.md`](../docs/hitos_mvp.md).
>
> Este documento define **cómo se convierte cada capa GIS alineada en un coste por celda**, cómo
> se combinan en una única superficie de coste por perfil, y los umbrales de transformación.
> Los valores numéricos son **orientativos y calibrables** (ver §9); lo que es norma del grupo es
> la **forma** de cada función y las reglas de §1–§2.

---

## 1. Principio que ordena el modelo: coste de *tránsito* vs coste de *cruce*

El **camino de mínimo coste** (problema LCP) se resuelve con **A\* o Dijkstra** sobre un **grafo de la
rejilla**: cada celda es un nodo, con aristas a sus 8 vecinos (ver §8.1). El **coste por celda** que
define este documento = lo que cuesta atravesar ese píxel, y se traduce en el **peso de las aristas**
del grafo. La ruta paga ese coste en **todas** las celdas que recorre. Hay que distinguir dos
naturalezas distintas de coste:

- **Coste de tránsito** — propiedad del terreno que se paga en *cada* celda recorrida:
  pendiente, terreno roto, uso del suelo, zona protegida.
- **Coste de cruce** — penalización **puntual** que se paga *una vez* al atravesar
  transversalmente una línea: carretera, ferrocarril, río. No es un coste por "estar en una zona".

Mezclar ambos sin cuidado produce artefactos (ver §6). Por eso el modelo se organiza en tres familias,
que se mapean con la **matriz de condicionantes** (técnico / ambiental / administrativo) del hito 1:

| Familia | Variables | Naturaleza | Condicionante | Fuente |
|---|---|---|---|---|
| Tránsito continuo | pendiente, terreno roto | por celda | técnico | DEM |
| Tránsito discreto | uso del suelo | por celda | administrativo / técnico | CLC/SIOSE/Catastro |
| Tránsito discreto | Red Natura 2000 | por celda | ambiental | Red Natura 2000 |
| Tránsito continuo *(reach)* | estabilidad geotécnica, proximidad a población | por celda | seguridad / operabilidad | IGME, núcleos/edificaciones |
| Cruce puntual | carreteras, ferrocarril, ríos | al cruzar la línea | técnico | OSM / IGN |

---

## 1.A Las seis dimensiones del trazado óptimo y su traducción a coste

El trazado óptimo es un **equilibrio multicriterio** entre seis dimensiones de decisión. El modelo de
coste las traduce a una única superficie minimizable por el LCP. Dos principios rigen la traducción:

- **Todo se expresa como coste donde "más = peor"** (índice 0-1). El LCP solo sabe *minimizar*. Las
  dimensiones **"↓ mejor"** se mapean **directas**; las **"↑ mejor"** se **invierten**: no se modela
  la virtud sino su **carencia** (la inviabilidad, el riesgo) como coste. Así las seis quedan en el
  mismo lenguaje "↓ mejor".
- **"Menor coste total" no es una capa: es la función objetivo.** Es el resultado de combinar las
  otras cinco dimensiones con pesos (= el `coste_relativo` de las métricas, §8). El LCP minimiza ese
  agregado; no se añade como capa de entrada.

Crosswalk dimensión ↔ capas ↔ condicionante:

| Dimensión de decisión | Dir. | Cómo se modela (capas) | Mapeo | Condicionante | Estado |
|---|---|---|---|---|---|
| Menor impacto ambiental | ↓ | protegida (Red Natura), hidrografía, forestal (uso_suelo) | directo | ambiental | cubierto |
| Menores afecciones a terceros | ↓ | uso_suelo (expropiación, urbano, regadío), parcelario (Catastro) | directo | administrativo | cubierto |
| Menor complejidad técnica | ↓ | pendiente, terreno roto, cruces | directo | técnico | cubierto |
| Menor coste total | ↓ | — (función objetivo: suma ponderada + base longitud) | — | — | **es la salida** |
| Mayor viabilidad administrativa | ↑ | inviabilidad: prohibición legal (barrera dura), suelo urbano consolidado, nº de municipios afectados | invertido | administrativo | parcial |
| Mayores seguridad y operabilidad | ↑ | riesgo/inoperabilidad: estabilidad geotécnica (IGME), proximidad a población, accesibilidad / co-ubicación con corredores | invertido | técnico / operacional | **nuevo (§6.A)** |

**Conexión con los perfiles.** Estas seis dimensiones son los **ejes naturales de los perfiles**
(`data/config/perfiles.yaml`): cada perfil sube el peso de la dimensión que prioriza (perfil
ambiental ↑ impacto ambiental; perfil técnico ↑ pendiente/cruces; perfil "mínimos cruces" ↑ cruces…).
Así el abanico de 3-5 trazados (hito 3) recorre el espacio de compromisos entre las seis dimensiones.

---

## 2. Reglas transversales (válidas para todas las variables)

1. **Alinear antes de combinar.** Ninguna capa entra sin estar reproyectada a **EPSG:25830** y
   remuestreada a la **rejilla común** (ver §3). La celda (i, j) debe representar el mismo trozo de
   terreno en todas las capas. Si no, los costes mienten.
2. **Normalizar contra umbrales físicos FIJOS, nunca contra el min/max de los datos del AOI.**
   Si se normaliza con el máximo observado en el AOI, el coste de un mismo terreno cambiaría entre
   escenarios y dejaría de ser reproducible y comparable. Se usan referencias absolutas (p. ej. 15°,
   30°), no `slope.max()`.
3. **Toda capa sale en el índice adimensional [0, 1].** El coste es **relativo, nunca €**.
4. **Barrera dura vs coste alto** son cosas distintas y deben decidirse explícitamente por capa:
   - *Coste alto finito* → la ruta lo cruza si no hay alternativa.
   - *Barrera dura* (`inf` / `nodata`) → el LCP la rodea siempre; si no hay paso, **falla**
     (y ese fallo es información útil: "no existe corredor viable").
5. **Coste base de longitud** siempre presente y > 0 (ver §7): garantiza que la distancia cuente
   y que ninguna celda tenga coste 0.

---

## 3. Resolución y rejilla común

> **Regla del grupo:** la resolución de trabajo será la **menor (más fina) de todas las capas que
> tengamos** — es decir, el menor tamaño de celda disponible. **Pendiente de determinar** hasta
> catalogar todas las capas (hito 1).

Motivación: remuestrear *hacia abajo* (de fina a gruesa) descarta información; remuestrear *hacia
arriba* (de gruesa a fina) no inventa detalle pero **no destruye** el de las capas más finas. Tomar la
resolución más fina como rejilla común preserva el máximo de información de cada fuente.

Implicaciones a vigilar:

- `data/config/escenario.yaml` tiene hoy `resolucion_m: 30` como **placeholder**. Actualizar al valor
  real una vez catalogadas las capas y conocido el menor tamaño de celda.
- **Pendiente y resolución:** la pendiente debe calcularse sobre el **DEM nativo** (lo más fino
  posible) y luego remuestrear el *coste*, no remuestrear el DEM grueso y derivar. A celdas grandes,
  los picos finos de pendiente se suavizan y desaparecen.
- Coste computacional: cuanto más fina la rejilla, más celdas y más pesado el LCP. Vigilar el tamaño
  del AOI × resolución.

---

## 4. Variables continuas — pendiente

Capa base del coste de tránsito técnico. Calcular la pendiente con un algoritmo serio
(**Horn**, el de `gdaldem` / `richdem`), no con diferencias crudas del DEM.

### 4.1 Función de coste (curva por tramos)

El mapeo lineal hasta 45° **subestima la realidad**: a partir de ~15° una zanja para tubería ya es
muy cara, pero una rampa lineal a 45° le asignaría solo ~0.33. Se adopta una **curva por tramos** con
saturación y barrera dura:

```
pendiente (°)      coste
0 – 5              ~0.0            zanja normal, trivial
5 – 15             0.0 → 0.6       rampa lineal (encarece rápido)
15 – 30            0.6 → 1.0       muy caro
> 30 (umbral)      barrera (inf)   constructivamente prohibitivo
```

La **forma** (no lineal + saturación + barrera dura arriba) es la norma; los cortes (5/15) son
calibrables. **Umbral de barrera dura fijado: 30°** (por encima, celda intransitable `inf`).

### 4.2 Terreno roto (capa opcional, separada)

Las variantes "en ventana" **no son alternativas** a la pendiente por celda: miden algo distinto.
La pendiente por celda responde "¿está inclinado este punto?"; la ventana responde "**¿es terreno
quebrado alrededor?**", que encarece la construcción aunque el punto concreto sea llano.

| Opción | Fórmula (ventana 5×5) | Qué capta |
|---|---|---|
| i) máximo | `max(pendiente)` | un pico cercano, aunque la media sea baja |
| ii) **std (recomendada)** | `std(pendiente)` | variabilidad: altos y bajos juntos = terreno roto |
| iii) gradiente de pendiente | `|∂pendiente|` (2ª derivada DEM) | transiciones bruscas; más ruidosa a celda grande |

**Recomendación:** capa base = pendiente por celda (§4.1). Si sobra tiempo, añadir
**Opción ii (std en ventana 5×5)** como capa separada "terreno roto" con su propio peso pequeño.
Fácil con `scipy.ndimage`. **No bloquear el hito 2** por esto: la pendiente por celda sola ya da un
trazado base coherente.

---

## 5. Variables discretas — lookup fijo por categoría

Asignación directa de coste por categoría (cumple §2: tabla fija, no data-driven). El coste 1.0 puede
ser *coste alto finito* o *barrera dura* según §2.4 — decisión marcada en la última columna.

### 5.1 Uso del suelo — dos capas separadas (decisión cerrada)

Se modela en **dos capas independientes, cada una en [0, 1] y con su propio peso**, porque miden cosas
distintas (constructabilidad física vs coste administrativo). Los valores son punto de partida
calibrable (§10).

**(a) Constructabilidad del terreno — fuente CLC / SIOSE.** Dificultad física de construir según la
cobertura del suelo.

| Cobertura | Coste | Justificación |
|---|---|---|
| Improductivo / matorral | 0.1 | Sin vegetación que retirar |
| Agrícola (secano / regadío) | 0.2 | Terreno blando, fácil de excavar |
| Forestal | 0.6 | Retirada de arbolado, acceso difícil |
| Roquedo | 0.7 | Excavación en roca |
| Urbano / industrial | 0.9 | Obstáculos físicos, difícil acceso |

**(b) Expropiación / parcelario — fuente Catastro.** Coste administrativo de ocupar el suelo
(afección a terceros).

| Clase de suelo | Coste | Justificación | Tratamiento |
|---|---|---|---|
| Rústico improductivo | 0.1 | Expropiación trivial | finito |
| Rústico secano | 0.2 | Expropiación simple | finito |
| Rústico regadío | 0.5 | Expropiación cara (infraestructura de riego) | finito |
| Urbanizable / industrial | 0.9 | Muchos permisos | finito |
| Urbano consolidado | 1.0 | Prácticamente prohibitivo — **coste alto finito, NO barrera** (§2.4) | finito |

Ambas capas entran en la combinación (§8) con pesos separados: `w_uso_construccion` y
`w_uso_expropiacion`.

### 5.2 Red Natura 2000

**Variable binaria.** Una celda está dentro de Red Natura o no lo está; la capa no
grada la intensidad. La magnitud de la penalización la pone el **peso** de la capa
en la combinación (§8), que es independiente del resto. Por eso el valor es 1
(dentro) o 0 (fuera), sin escalones intermedios.

| Situación | Valor | Justificación | Tratamiento |
|---|---|---|---|
| Fuera de zona protegida | 0 | Sin restricción | finito |
| Dentro de Red Natura (ZEPA / LIC / ZEC) | 1 | Zona a evitar; transitable con autorización | finito |

> No hay barrera dura (`inf`) en esta capa: es transitable y su km se reporta como
> métrica (hito 4). La *zona núcleo* legalmente intransitable no viene en los datos
> (solo hay `TIPO` a nivel de espacio completo); si llegara, se modelaría como una
> capa de barrera aparte, no como un valor de esta.

---

## 6. Variables de cruce — carreteras, ferrocarril, ríos

### 6.1 Coste puntual por tipo

**Viario — OSM, columna `highway`** (el ferrocarril va en su propia columna `railway`):

| Tipo de cruce (`highway`) | Coste | Justificación |
|---|---|---|
| Camino / pista / senda (`path`, `track`, `footway`) | 0.2 | Cruce simple, poco tráfico |
| Vía de servicio / sin clasificar (`service`, `unclassified`) | 0.3 | Cruce sencillo |
| Calle urbana (`residential`) | 0.4 | Tráfico local, algún permiso |
| Carretera local (`tertiary`) | 0.5 | Requiere corte o perforación horizontal |
| Carretera comarcal (`secondary`) | 0.6 | Perforación horizontal probable |
| Carretera nacional (`primary`) | 0.7 | Perforación horizontal, cara |
| Autovía / autopista (`trunk`, `motorway`) | 0.8 | Perforación horizontal obligatoria |
| Ferrocarril (columna `railway`, p.ej. `rail`) | 0.9 | ADIF, permisos especiales |
| Vía en obra (`construction`) | 0.4 | Estado temporal, no clase; ~`residential` (dictamen geógrafo-SIG) |
| Cualquier `highway` no listado | 0.3 | Default prudente (~`unclassified`) |

**Hidrografía — IGN, columnas `text` (nombre) y `length` (longitud en m).** El dato IGN no
trae anchura de cauce, así que se usa nombre + longitud como proxy de entidad del río:

| Criterio | Coste | Justificación |
|---|---|---|
| Sin nombre (`text` nulo/vacío) | 0.3 | Rambla / val estacional, cruce sencillo |
| Con nombre y `length` ≤ 2000 m | 0.5 | Río menor, cruce subfluvial sencillo |
| Con nombre y `length` > 2000 m | 0.8 | Río principal, cruce subfluvial complejo |

> **Fusión de las dos fuentes** en `cruces_{s}.tif`: **máximo por celda** (gana el cruce más
> restrictivo). Líneas rasterizadas finas (`all_touched=True`, sin buffer). Rango [0.0, 0.9],
> fondo 0.0. Implementado en `src/superficie/cruces_viario_rios.py`.

### 6.2 Cómo entra un cruce en la superficie de coste

El reto es que el grafo solo entiende coste **por celda / arista**, pero un cruce es una penalización
**puntual**. Tres formas, de peor a mejor para el MVP:

- ❌ **Bufferizar la línea** (darle anchura) → penaliza la *proximidad*, no el *cruce*: una ruta que
  pasa cerca paga sin cruzar. Incorrecto.
- ⚠️ **Solo contarlos en métricas** (post-proceso) → el trazado no los *evita*, solo se reportan.
  Enagás quiere que la ruta esquive los cruces caros, así que se queda corto.
- ✅ **Rasterizar la línea fina (1 celda, `all_touched=True`) y asignar el coste puntual a esas
  celdas.** Al cruzar **perpendicularmente** una línea de 1 celda de ancho, la ruta paga ≈ una celda
  de ese coste → aproxima bien la penalización puntual. Si intentara ir *paralela* sobre la
  infraestructura, acumularía coste en cada celda → la disuade sola.

**Decisión adoptada:** opción ✅ (rasterización fina como coste de superficie) **+ conteo en métricas**.

Avisos:

1. **Mantener la línea fina** (no bufferizar): solo así se paga por cruzar, no por acercarse.
2. **Ríos:** si es línea fina, se trata como los demás cruces; si es polígono ancho (lámina de agua),
   tratar como cruce *y* posible barrera.

---

## 6.A Seguridad y operabilidad (familia nueva — *reach*, fuera del MVP)

> **Estado:** esta familia **no entra en el MVP del hito 2** (decisión §9). Se documenta como
> *reach* / continuidad; el dato de geotecnia (IGME) ya está disponible para cuando se incorpore.

Dimensión **"↑ mejor"** → se modela su **carencia** como coste (riesgo / inoperabilidad), según el
principio de inversión de §1.A. Tres componentes (de más a menos prioritario al incorporarla):

- **Estabilidad geotécnica (IGME).** `data/processed/igme_aoi.gpkg` ya está disponible. Litologías
  desfavorables, zonas inestables, fallas o riesgo de deslizamiento → coste alto. Afecta a la
  seguridad y operabilidad del ducto a largo plazo. *Coste de tránsito (por celda).*
- **Proximidad a población (seguridad).** Distancia a núcleos urbanos / edificaciones: cuanto más
  cerca, mayor riesgo ante una fuga → coste creciente por proximidad. *Coste de tránsito (por celda).*
  ⚠️ **Solapa con "afecciones a terceros"** (§5.1): ambos penalizan lo urbano, pero por motivos
  distintos (expropiación vs riesgo). Decidir si se modela como una sola capa o dos, para **evitar el
  doble conteo** (§9).
- **Accesibilidad / co-ubicación (operabilidad).** *Reach.* Ir paralelo a corredores de infraestructura
  existentes (gasoductos, líneas, viario de servicio) mejora el acceso de mantenimiento y reduce la
  afección nueva → **bonificación** (coste menor) en una franja. Es lo **contrario** del coste de
  cruce: cruzar una infraestructura es caro, pero **compartir corredor** con ella es bueno.

---

## 7. Coste base de longitud

`longitud` (en `perfiles.yaml`) **no es una capa GIS**: es un **coste base constante > 0 en toda
celda**. Es imprescindible:

- Sin él, una zona de coste 0 dejaría al solver (A\*/Dijkstra) serpentear "gratis" → rutas absurdas.
- Garantiza que **la distancia siempre cuente** y que el coste total nunca sea 0.

Sumarlo **siempre** a la superficie combinada.

---

## 8. Combinación y contrato con los perfiles

Para cada perfil *p* (de `data/config/perfiles.yaml`):

```
coste_total(i,j) = base_longitud      · w_longitud
                 + pendiente(i,j)      · w_pendiente
                 + uso_construccion(i,j)· w_uso_construccion   (CLC/SIOSE; §5.1a)
                 + uso_expropiacion(i,j)· w_uso_expropiacion   (Catastro; §5.1b)
                 + protegida(i,j)      · w_protegida
                 + cruces(i,j)         · w_cruces
                 [ + terreno_roto(i,j) · w_terreno     ]   opcional (§4.2)
                 [ + seguridad(i,j)    · w_seguridad   ]   reach (§6.A)
                 [ − coubicacion(i,j)  · w_coubicacion ]   reach, bonificación (§6.A)
```

**Capas del MVP:** las seis primeras (longitud, pendiente, uso_construccion, uso_expropiacion,
protegida, cruces). Las tres entre corchetes son opcional/reach según las decisiones de §9.

Cada capa ∈ [0, 1] y las celdas barrera valen `inf`. Si se añade la co-ubicación, **resta** (es una
bonificación), cuidando que `coste_total` nunca quede ≤ 0 (la base de longitud lo garantiza). Cada
perfil = un vector de pesos distinto → una superficie de coste distinta → rutas diferenciadas
(hito 3). Los pesos son los **ejes de las seis dimensiones** de §1.A.

> **Cambio pendiente en la config:** `perfiles.yaml` hoy define pesos para
> `pendiente / uso_suelo / protegida / longitud`. Hay que **partir `uso_suelo` en `uso_construccion` +
> `uso_expropiacion`** y **añadir `cruces`**. Si más adelante entran las capas opcional/reach, sumar
> también `terreno_roto`, `seguridad` y `coubicacion`.

### 8.1 De la superficie de coste al grafo (A\* / Dijkstra)

El camino de mínimo coste (problema **LCP**) se calcula con **A\*** — los algoritmos que nombra el
hito 2 son A\* o Dijkstra, y **se elige A\***: para un único par origen→destino explora muchos menos
nodos que Dijkstra y, con heurística admisible, **garantiza el mismo óptimo** (Dijkstra es A\* con
heurística 0; solo se usaría como respaldo de verificación). No es una alternativa al LCP: es la forma
de resolverlo. La superficie de coste de §8 se convierte en un **grafo de la rejilla**:

- **Nodos:** una celda = un nodo. Las celdas barrera (`inf`) **no** generan nodo.
- **Aristas:** a los **8 vecinos** (conectividad reina). Distancia = 1 (ortogonal) o √2 (diagonal),
  en celdas; ×`resolucion_m` para metros reales.
- **Peso de arista** = distancia × **media del coste de las dos celdas** (origen y destino) que une.
  La media es simétrica y más estable que tomar solo la celda destino (decisión cerrada).
- **Heurística de A\* (admisible):** distancia euclídea origen→destino × **coste mínimo** de celda de
  la superficie. Al no sobreestimar nunca el coste real, A\* mantiene la garantía de óptimo y solo
  acelera la búsqueda.
- **Stack:** `networkx` (`astar_path`) o implementación propia de A\* sobre la matriz. El cruce, la
  pendiente, etc. entran exactamente igual: como peso de las aristas que tocan esas celdas.

> El modelo de coste (§1–§7) es **independiente del solver**: cambiar de `MCP_Geometric` a A\*/Dijkstra
> solo cambia la *representación* (grafo) y la *convención de peso de arista*, no las funciones de coste.

---

## 9. Decisiones

### 9.1 Cerradas

| Tema | Decisión |
|---|---|
| Pendiente (§4.1) | **Curva por tramos** (no lineal), con saturación; cortes 5°/15° calibrables. |
| Barrera de pendiente (§4.1) | **30°**: por encima, celda intransitable (`inf`). |
| Barreras duras (§5) | Única barrera dura implementada: **pendiente >30°**. Red Natura es **variable binaria transitable** (§5.2), NO barrera. Urbano consolidado = **coste 1.0 finito**, NO barrera (evita infactibilidad si origen/destino están cerca de zona urbana). La *zona núcleo* Red Natura sería barrera, pero no viene en los datos; se modelaría como capa aparte. |
| Cruces (§6.2) | **Rasterización fina** (1 celda, `all_touched`) como coste de superficie **+ conteo en métricas**. |
| Uso del suelo (§5.1) | **Dos capas separadas**: constructabilidad (CLC/SIOSE) + expropiación (Catastro), con pesos propios. |
| Doble conteo urbano | En el MVP no hay: lo urbano lo lleva solo Catastro (`uso_expropiacion`); la proximidad a población es *reach*. A revisar si entra seguridad. |
| Municipios afectados | **Solo métrica** de comparación (hito 4), no capa de coste (es propiedad de la ruta entera, no por celda). |
| Solver (§8.1) | **A\*** (Dijkstra solo como respaldo de verificación). |
| Peso de arista (§8.1) | **Media** del coste de las dos celdas que une la arista. |
| Conectividad (§8.1) | **8 vecinos** (reina). |

### 9.2 Pendientes

1. **Resolución de trabajo (§3):** la *regla* está fija (el menor tamaño de celda disponible); falta
   **rellenar el número** y actualizar `escenario.yaml` una vez catalogadas todas las capas (hito 1).
2. **Capas opcional / reach al MVP:** decisión de alcance, aún sin cerrar. ¿Entran ya, o se dejan para
   continuidad?
   - `terreno_roto` (std en ventana, §4.2) — derivada del DEM, fácil.
   - `seguridad` (geotecnia IGME, §6.A) — dato ya ingerido (`igme_aoi.gpkg`).
   - `proximidad a población` y `coubicacion` (§6.A) — requieren capas aún no confirmadas; las más
     claramente *reach*.

---

## 10. Calibración

Los valores numéricos de este documento son un **punto de partida razonado**, no definitivo. Se
calibran contra el caso real y, cuando Enagás facilite un ramal existente, con **backtesting**
(hito 4/6): ¿el trazado real cae entre las alternativas generadas? Las desviaciones se explican
ajustando pesos y umbrales. Registrar cada cambio de calibración en
[`../coordinacion/seguimiento.md`](../coordinacion/seguimiento.md).
