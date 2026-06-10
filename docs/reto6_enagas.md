# Reto 6 — Enagás: Generación automatizada de trazados de ramales de H₂

> Análisis técnico del reto. Documento de referencia para todo el grupo.
> Enunciado original en [`retos_alumnos.md`](retos_alumnos.md) (sección "Retos 5 y 6 — Enagás").

## 1. El problema

Enagás (operador del sistema gasista español, con una apuesta fuerte por el hidrógeno verde) necesita trazar **ramales** que conecten una **planta de H₂** con la **red troncal**. Antes de un estudio de ingeniería de detalle (caro y lento), interesa una herramienta de **prediseño** que, sobre datos geográficos públicos, proponga **varias alternativas de trazado** y las compare de forma objetiva.

El reto **no** es encontrar "la ruta óptima": es ofrecer **3-5 alternativas realmente distintas** —la más corta, la de menor impacto ambiental, la de menor pendiente…— y presentarlas en una **comparativa multi-criterio** para que una persona decida con criterio.

Trazar "a ojo" sobre un mapa es peligroso: ignora pendientes, cruces de ríos y carreteras, zonas protegidas y suelo urbano. Y combinar capas geográficas **sin alinearlas** (mismo CRS, misma rejilla) produce mapas de coste que **mienten**.

### Objetivo

Construir un **prototipo** que, dados origen, destino y un área de interés (AOI), genere **3-5 trazados diferenciados** sobre GIS público y los presente en tabla comparativa + mapa, de modo que:

1. Las rutas sean **demostrablemente diferenciadas** (no el mismo corredor con ruido).
2. Todos los costes sean **relativos (índice 0-1 o 0-100), nunca en €**.
3. Cada métrica sea **reproducible y trazable** a las capas GIS de origen.

> ⚠️ **No es un GIS profesional ni un estudio de ingeniería.** Es una herramienta de **prediseño y comparación** de alternativas. El rigor está en (a) alinear las capas antes de combinarlas y (b) garantizar que las rutas son distintas. Ese rigor es el reto.

## 2. Las magnitudes a comparar

Para cada ruta generada se calculan estas métricas (el análogo a los "3 parámetros" del Reto 5). El objetivo es comparar alternativas, así que importan tanto los valores absolutos por criterio como su posición relativa entre rutas.

| Criterio | Qué mide | Fuente principal |
|----------|----------|------------------|
| **Longitud** | km totales del trazado | geometría de la ruta |
| **Coste relativo** | índice normalizado (0-1 o 0-100), **no €** | suma del coste de las celdas atravesadas en la superficie de coste |
| **Cruces especiales** | nº y tipo (ríos, carreteras, ferrocarril, otras infraestructuras) | OSM, hidrografía IGN |
| **Km en zona protegida** | km dentro de Red Natura 2000 | Red Natura 2000 |
| **Km en zona urbana/periurbana** | km en suelo urbano/periurbano | Corine Land Cover, OSM |
| **Pendiente máxima y media** | derivadas del DEM a lo largo de la ruta | DEM Copernicus |

### Por qué el coste es relativo (índice) y no en euros

Un coste en € exigiría precios de obra, expropiaciones, técnicas de cruce, terreno, permisos… datos que no tenemos y que cambian por proyecto. Lo honesto es un **índice de coste relativo**: cada celda del terreno recibe un coste adimensional (más pendiente → más coste; suelo urbano → más coste; zona protegida → más coste o prohibición), y el coste de una ruta es la suma de las celdas que atraviesa. Sirve para **ordenar alternativas entre sí**, que es justo lo que pide el reto. Prometer € sería falsear la precisión.

## 3. El reto técnico central

Análogo a las "condiciones de referencia" del Reto 5, aquí hay dos exigencias que, si se incumplen, hacen que toda la salida sea engañosa:

### 3.1 Alineación de capas (CRS y rejilla comunes)

Cada capa GIS pública viene en su propio **sistema de referencia (CRS)** y su propia **resolución**. Antes de combinarlas hay que:

- **Recortar** al área de interés (AOI).
- **Reproyectar** todas al CRS de trabajo: **ETRS89 / UTM 30N = EPSG:25830** (península).
- **Remuestrear** a una **rejilla común** (misma resolución y mismo origen de celda), para que la celda (i, j) signifique el mismo trozo de terreno en todas las capas.

Sin esto, sumar la capa de pendiente con la de usos del suelo es sumar peras con manzanas: el resultado parece un mapa de coste pero no lo es. **"Alinear antes de combinar"** es el equivalente al "normalizar antes de comparar" del Reto 5.

### 3.2 Diferenciación real de rutas

Generar 5 veces el mismo camino con ruido no es ofrecer alternativas. La diferenciación se consigue combinando dos mecanismos:

- **Perfiles de prioridad:** distintos vectores de pesos sobre las capas (p.ej. "minimizar longitud", "minimizar impacto ambiental", "minimizar pendiente") → distintas superficies de coste → distintas rutas.
- **Corridor masking:** al generar una nueva ruta, penalizar la proximidad a las rutas ya generadas, forzando que explore corredores distintos.

Una ruta solo se acepta en el abanico final si es **demostrablemente distinta** de las demás (p.ej. solapamiento espacial por debajo de un umbral).

## 4. Arquitectura (resumen)

Pipeline geoespacial determinista (el detalle, con diagrama y contratos de datos, en [`../proyecto/arquitectura.md`](../proyecto/arquitectura.md)):

```
Entrada: origen (planta H₂) + destino (conexión red troncal) + AOI
   ▼
1. INGESTA de capas GIS (DEM, CLC, OSM, hidrografía IGN, Red Natura 2000, IGME)
   · recorte al AOI · reproyección a EPSG:25830 · remuestreo a rejilla común
   ▼
2. SUPERFICIES DE COSTE (raster multicriterio)
   · cada capa → coste por celda · PERFILES DE PRIORIDAD (vectores de pesos distintos)
   ▼
3. MOTOR LCP (camino de mínimo coste)
   · una ruta por perfil · DIFERENCIACIÓN (corridor masking + pesos distintos)
   ▼
4. MÉTRICAS multicriterio por ruta
   · longitud · coste relativo · cruces · km protegida · km urbana · pendiente máx/media
   ▼
5. COMPARATIVA y VISUALIZACIÓN
   · tabla multicriterio + mapa con las 3-5 rutas diferenciadas
```

Componentes en `src/`: `ingesta/`, `superficie/`, `trazados/`, `metricas/`, `comparacion/`, `app/`.

### Lo que el sistema NO hace

- No estima costes absolutos en € (solo índice relativo).
- No entrega una única ruta "óptima", sino un abanico comparable de alternativas.
- No garantiza viabilidad jurídica, expropiatoria ni constructiva: es prediseño y comparación, no ingeniería de detalle.

## 5. Fuentes de datos GIS

Capas públicas a catalogar (URL, fecha de descarga, CRS original, resolución) en [`../proyecto/data/raw/FUENTES.md`](../proyecto/data/raw/FUENTES.md):

| Capa | Qué aporta | Fuente |
|------|-----------|--------|
| **DEM** | elevación → pendiente | Copernicus DEM (GLO-30) |
| **Corine Land Cover (CLC)** | usos del suelo (urbano, agrícola…) | Copernicus Land Monitoring |
| **OSM** | infraestructuras, viario, hidrografía, núcleos | OpenStreetMap |
| **Hidrografía IGN** | ríos y masas de agua (cruces) | IGN / CNIG |
| **Red Natura 2000** | zonas protegidas | MITECO / Copernicus |
| **Mapa geológico IGME** | litología / cruces geológicos especiales | IGME |

> 📌 **Tarea de fuentes:** localizar las capas públicas, descargarlas a `proyecto/data/raw/`, registrarlas en `FUENTES.md` (con CRS y resolución originales) y reproyectarlas a **EPSG:25830** sobre una rejilla común antes de usarlas.

## 6. Entregables

- **Prototipo funcional** que, dado origen/destino/AOI, genera 3-5 rutas diferenciadas con tabla comparativa y mapa.
- **Catálogo de capas GIS** alineadas (CRS y rejilla comunes), trazables a su fuente.
- **Documentación** de la arquitectura, las fuentes y las decisiones de pesos/perfiles.
- **Presentación final** (17 jul) tipo mini-consultoría.

## 7. Casos tipo que el prototipo debe resolver bien

- "Dame 3 trazados: el más corto, el de menor impacto ambiental y el de menor pendiente." → tres perfiles de prioridad, tres rutas distintas, tabla comparativa.
- "¿Cuántos cruces de río y de carretera tiene cada alternativa?" → métricas de cruces por ruta.
- "¿Qué ruta minimiza los km en Red Natura 2000 sin disparar la longitud?" → trade-off visible en la comparativa.
- "Enséñame las rutas en un mapa para decidir." → mapa con las 3-5 rutas diferenciadas y su tabla.

## 8. Glosario

Términos GIS (DEM, CRS/EPSG, raster vs vector, superficie de coste, LCP, corridor masking…) en [`glosario.md`](glosario.md).
