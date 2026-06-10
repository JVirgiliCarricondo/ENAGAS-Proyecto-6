# Transferencia — Montar la estructura para el Reto 6 (Enagás, ingeniería de ramales / trazados de H₂)

> **Propósito.** Este documento es el *blueprint* para levantar un workspace **espejo** del Grupo 5 pero aplicado al **Reto 6 de Enagás** (generación automatizada de trazados de H₂). Reutiliza la misma arquitectura de tres dimensiones — **formación**, **coordinación/seguimiento** y **desarrollo de código** — cambiando el contenido técnico de "calidad del gas / normativa" por "GIS / trazados".
>
> Sigue este documento (a mano o con un asistente) para generar el workspace del equipo del Reto 6. El Reto 5 sirve de plantilla: ver [`CLAUDE.md`](CLAUDE.md), [`docs/reto5_enagas.md`](docs/reto5_enagas.md) y [`proyecto/arquitectura.md`](proyecto/arquitectura.md).

---

## 1. El Reto 6 en una frase

Dado un **punto de origen** (planta de H₂) y un **destino** (conexión a red troncal), una herramienta genera automáticamente **3-5 trazados alternativos diferenciados** sobre **GIS público** y los presenta en **comparativa multi-criterio**: longitud, coste *relativo* (índice, no €), nº y tipo de cruces especiales, km en zona protegida, km en zona urbana/periurbana, pendiente máxima y media.

> **El énfasis está en el problema de selección y comparación de trazados, no en estimar costes absolutos.** (Enunciado original en [`docs/retos_alumnos.md`](docs/retos_alumnos.md), sección "Retos 5 y 6 — Enagás".)

Igual que en el Reto 5 hay un rigor que define el reto (trazabilidad + comparabilidad de unidades), aquí el rigor es doble:

- **Rutas realmente diferenciadas**, no variaciones del mismo corredor.
- **Coste relativo (índice), nunca €.** No se promete estimación económica.

---

## 2. Qué cambia del Reto 5 al Reto 6

La **estructura de carpetas y la filosofía de trabajo se reutilizan tal cual**. Solo cambia la sustancia técnica:

| Pieza | Reto 5 (calidad del gas) | Reto 6 (trazados H₂) |
|-------|--------------------------|----------------------|
| Núcleo determinista | Ontología de parámetros (O₂/H₂S/PCS) | **Superficies de coste raster** (multicriterio) |
| Núcleo algorítmico | RAG + normalización de unidades | **Camino de mínimo coste (LCP) + diferenciación de rutas** |
| Fuentes de datos | PDFs normativos (BOE, EUR-Lex) | **Capas GIS públicas** (DEM, CLC, OSM, IGN, Red Natura 2000, IGME) |
| Rigor que define el reto | Trazabilidad + comparabilidad de unidades | Rutas **diferenciadas** + coste **relativo** |
| Salida al usuario | Respuesta con cita + flag de comparabilidad | **3-5 rutas + tabla multicriterio + mapa** |
| Stack | LLMs, RAG, base vectorial, ontologías | **GIS, LCP, raster multicriterio** |
| Interfaz | Streamlit (texto) | **Mapa interactivo** (Streamlit + folium / similar) |
| "Normalizar antes de comparar" | Unidades y condiciones de referencia | **Alinear rasters** (CRS y rejilla común) antes de combinar capas |

Lo común (no tocar): Enagás como patrono; presencia 3 días Enagás + 2 ICAI; calendario 1 jun – 17 jul; sprints semanales; documentación en español y código en inglés; definición de "hecho" exigente.

---

## 3. Estructura objetivo (idéntica a la del Reto 5)

```
CI2 LAB 2026 - Grupo 6 (Ramales)/        # nombre del nuevo workspace
├── CLAUDE.md                 # contexto del workspace (adaptar)
├── README.md                 # intro humana (adaptar)
├── estado.md                 # resumen ejecutivo del avance (adaptar)
├── docs/
│   ├── Descripcion_CI2_Lab.md   # copiar tal cual del Reto 5
│   ├── retos_alumnos.md         # copiar tal cual
│   ├── reto6_enagas.md          # REESCRIBIR (análisis técnico del Reto 6) ← clave
│   └── glosario.md              # REESCRIBIR (términos GIS)
├── formacion/
│   ├── CLAUDE.md                # adaptar (habilidades GIS)
│   ├── plan_formativo.md        # REESCRIBIR (itinerario GIS)
│   └── recursos/README.md       # adaptar
├── coordinacion/
│   ├── CLAUDE.md                # reutilizar casi igual
│   ├── plan_proyecto.md         # adaptar (WBS y sprints de trazados)
│   ├── seguimiento.md           # reutilizar plantilla
│   ├── equipo.md                # reutilizar (cambiar miembros)
│   └── reuniones/README.md      # reutilizar tal cual
└── proyecto/
    ├── CLAUDE.md                # adaptar
    ├── README.md                # adaptar (puesta en marcha GIS)
    ├── arquitectura.md          # REESCRIBIR (pipeline GIS) ← clave
    ├── requirements.txt         # REESCRIBIR (stack geoespacial)
    ├── .env.example             # adaptar (claves de descarga si aplica)
    ├── .gitignore               # reutilizar + ignorar rasters pesados
    ├── data/
    │   ├── raw/FUENTES.md       # REESCRIBIR (catálogo de capas GIS)
    │   ├── processed/.gitkeep   # rasters alineados / superficies de coste
    │   └── config/              # AOI, origen/destino, perfiles de prioridad
    ├── src/
    │   ├── ingesta/             # descarga y preparación de capas
    │   ├── superficie/          # superficies de coste (raster multicriterio)
    │   ├── trazados/            # motor LCP + diferenciación de rutas
    │   ├── metricas/            # métricas multicriterio por ruta
    │   ├── comparacion/         # tabla comparativa + scoring
    │   └── app/                 # orquestador + mapa/UI
    ├── tests/                   # priorizar: alineación de rasters y métricas
    └── notebooks/               # exploración geoespacial
```

**Regla de transferencia:** *reutilizar* todo lo que sea proceso (coordinación, plantillas, convenciones) y *reescribir* solo lo técnico (los 4 ficheros marcados "clave/REESCRIBIR": `docs/reto6_enagas.md`, `docs/glosario.md`, `proyecto/arquitectura.md`, `proyecto/data/raw/FUENTES.md`, más `requirements.txt` y `plan_formativo.md`).

---

## 4. Contenido técnico del Reto 6 (lo que hay que escribir nuevo)

### 4.1 `docs/reto6_enagas.md` — análisis técnico

Cubrir:

- **El problema.** Trazar un ramal de H₂ entre planta y red troncal evitando/penalizando obstáculos y zonas sensibles, ofreciendo varias alternativas para decidir, no una única "óptima".
- **Las "magnitudes" a comparar** (el análogo a los 3 parámetros del Reto 5). Para cada ruta:

  | Criterio | Qué mide | Fuente principal |
  |----------|----------|------------------|
  | Longitud | km totales del trazado | geometría de la ruta |
  | Coste relativo | índice normalizado (0-1 o 0-100), **no €** | suma del coste de las celdas atravesadas |
  | Cruces especiales | nº y tipo (ríos, carreteras, ferrocarril, otras infraestructuras) | OSM, hidrografía IGN |
  | Km en zona protegida | km dentro de Red Natura 2000 | Red Natura 2000 |
  | Km en zona urbana/periurbana | km en suelo urbano/periurbano | Corine Land Cover, OSM |
  | Pendiente máxima y media | derivadas del DEM a lo largo de la ruta | DEM Copernicus |

- **El reto técnico central** (análogo a las "condiciones de referencia"): **alineación de capas** (CRS y rejilla comunes) antes de combinarlas, y **diferenciación real de rutas** (que no sean el mismo corredor con ruido). Si las capas no están alineadas o las rutas no son diferenciadas, los resultados engañan.
- **Arquitectura** (resumen; detalle en `proyecto/arquitectura.md`).
- **Preguntas/casos tipo** que el prototipo debe resolver bien (p.ej. "dame 3 trazados: el más corto, el de menor impacto ambiental y el de menor pendiente").

### 4.2 Fuentes GIS — `proyecto/data/raw/FUENTES.md`

Catálogo de capas públicas (registrar URL, fecha de descarga, CRS original, resolución):

| Capa | Qué aporta | Fuente |
|------|-----------|--------|
| **DEM** | elevación → pendiente | Copernicus DEM (GLO-30) |
| **Corine Land Cover (CLC)** | usos del suelo (urbano, agrícola…) | Copernicus Land Monitoring |
| **OSM** | infraestructuras, viario, hidrografía, núcleos | OpenStreetMap |
| **Hidrografía IGN** | ríos y masas de agua (cruces) | IGN / CNIG |
| **Red Natura 2000** | zonas protegidas | MITECO / Copernicus |
| **Mapa geológico IGME** | litología / cruces geológicos especiales | IGME |

> Todas las capas se reproyectan a un **CRS común** (península: **ETRS89 / UTM 30N = EPSG:25830**) y se remuestrean a una **rejilla común** antes de usarse.

### 4.3 Arquitectura — `proyecto/arquitectura.md`

Pipeline geoespacial (sustituye al híbrido ontología+RAG del Reto 5):

```
Entrada: origen (planta H₂) + destino (conexión red troncal) + AOI
   │
   ▼
1. INGESTA de capas GIS  (DEM, CLC, OSM, hidrografía IGN, Red Natura 2000, IGME)
   · recorte al área de interés (AOI) · reproyección a EPSG:25830 · remuestreo a rejilla común
   ▼
2. SUPERFICIES DE COSTE (raster multicriterio)
   · cada capa → coste por celda (pendiente, uso de suelo, protección, proximidad a cruces…)
   · PERFILES DE PRIORIDAD: distintos vectores de pesos → distintas superficies de coste
   ▼
3. MOTOR DE CAMINO DE MÍNIMO COSTE (LCP)
   · por cada perfil: ruta origen→destino (skimage MCP_Geometric / route_through_array, o networkx)
   · DIFERENCIACIÓN: penalizar proximidad a rutas ya generadas (corridor masking) + pesos distintos
   ▼
4. MÉTRICAS multicriterio por ruta
   · longitud · coste relativo (índice) · nº/tipo de cruces · km protegida · km urbana · pendiente máx/media
   ▼
5. COMPARATIVA y VISUALIZACIÓN
   · tabla multicriterio + mapa con las 3-5 rutas diferenciadas
```

Componentes (`src/`): `ingesta/`, `superficie/`, `trazados/`, `metricas/`, `comparacion/`, `app/`.

Lo que el sistema **NO** hace: no estima costes absolutos en €; no entrega una única ruta "óptima" sino un abanico comparable; no garantiza viabilidad jurídica/expropiatoria (es una herramienta de prediseño y comparación).

### 4.4 Stack — `proyecto/requirements.txt`

```
# Geoespacial
rasterio
geopandas
shapely
pyproj
numpy
# Descarga de datos
osmnx          # OSM
requests       # WCS/WFS de Copernicus, IGN, IGME
# Camino de mínimo coste
scikit-image   # skimage.graph (MCP_Geometric / route_through_array)
networkx       # alternativa para LCP sobre grafo
# Visualización / UI
folium
matplotlib
contextily
streamlit
# Calidad
pytest
ruff
```

### 4.5 Glosario — `docs/glosario.md`

Términos GIS a definir: **DEM**, raster vs vector, **CRS / EPSG / EPSG:25830**, reproyección, remuestreo, **rasterización**, **AOI** (área de interés), **superficie de coste**, **LCP / MCP** (least-cost path / minimum cost path), Dijkstra, **pendiente** (slope), **CLC** (Corine Land Cover), **Red Natura 2000**, **IGN/CNIG**, **IGME**, **Copernicus**, **WMS/WFS/WCS**, GeoTIFF, GeoPackage/shapefile, **corridor masking** (diferenciación de rutas), **índice de coste relativo**.

---

## 5. Dimensión 1 — Formación (habilidades del Reto 6)

Reescribir `formacion/plan_formativo.md` con el itinerario *just-in-time* mapeado a los sprints. Habilidades objetivo:

1. **Python geoespacial** — numpy, geopandas, rasterio, shapely, pyproj.
2. **Sistemas de referencia y alineación** — CRS/EPSG, reproyección, remuestreo, alineación de rasters a rejilla común (el "normalizar antes de comparar").
3. **Modelos de elevación y pendiente** — leer un DEM y derivar pendiente.
4. **Vector ↔ raster** — rasterización de capas vectoriales (Red Natura, CLC, OSM) a la rejilla común.
5. **Superficies de coste y análisis multicriterio** — combinar capas con pesos.
6. **Algoritmos de camino de mínimo coste** — Dijkstra/MCP sobre rejilla.
7. **Diferenciación de rutas** — corridor masking, perfiles de prioridad.
8. **Visualización geoespacial** — mapas y comparativa multicriterio.
9. **Fuentes de datos públicas** — descarga de Copernicus, CLC, OSM, IGN, Red Natura 2000, IGME.

Mapa habilidad ↔ sprint (análogo al del Reto 5): dominio+ingesta (S1-S2) → superficies de coste (S2-S3) → LCP (S3-S4) → diferenciación + métricas (S4-S5) → comparativa + mapa (S5) → evaluación (S6) → presentación (S7).

---

## 6. Dimensión 2 — Coordinación (sprints del Reto 6)

Reutilizar `coordinacion/CLAUDE.md`, `seguimiento.md`, `equipo.md` y `reuniones/` casi tal cual. Reescribir solo los hitos y el WBS de `plan_proyecto.md`:

| Sprint | Fechas | Objetivo |
|--------|--------|----------|
| S1 | 1-5 jun | Setup + catálogo de capas GIS + definir AOI, origen y destino |
| S2 | 8-12 jun | Ingesta: descarga, reproyección y alineación de todas las capas a rejilla común |
| S3 | 15-19 jun | Superficies de coste multicriterio + perfiles de prioridad |
| S4 | 22-26 jun | Motor LCP funcionando (una ruta por perfil) |
| S5 | 29 jun-3 jul | Diferenciación de rutas + métricas multicriterio + comparativa + mapa |
| S6 | 6-10 jul | Evaluación (¿son rutas realmente distintas? ¿métricas correctas?) + robustez |
| S7 | 13-17 jul | Pulido + presentación final |

**WBS:** 1. Datos GIS (catálogo, descarga, alineación) · 2. Superficies de coste (capas→coste, perfiles) · 3. Trazados (LCP, diferenciación) · 4. Métricas (longitud, coste relativo, cruces, km protegida/urbana, pendiente) · 5. Comparativa + mapa · 6. Calidad (alineación, métricas) · 7. Comunicación.

**Definición de "hecho":** las capas comparten CRS y rejilla; las rutas generadas son **demostrablemente diferenciadas**; todos los costes son **relativos (índice)**, nunca €.

---

## 7. Checklist de transferencia

Para levantar el workspace del Reto 6:

- [ ] Crear la carpeta del workspace (p.ej. `CI2 LAB 2026 - Grupo 6 (Ramales)`).
- [ ] Copiar `docs/Descripcion_CI2_Lab.md` y `docs/retos_alumnos.md` tal cual.
- [ ] Reescribir `docs/reto6_enagas.md` (§4.1) y `docs/glosario.md` (§4.5).
- [ ] Adaptar `CLAUDE.md`, `README.md`, `estado.md` (cambiar reto, dimensiones intactas).
- [ ] Reescribir `proyecto/arquitectura.md` (§4.3) y `proyecto/requirements.txt` (§4.4).
- [ ] Crear el esqueleto `src/{ingesta,superficie,trazados,metricas,comparacion,app}` con responsabilidades documentadas.
- [ ] Reescribir `proyecto/data/raw/FUENTES.md` con el catálogo de capas (§4.2) y crear `data/config/` para AOI/origen/destino/perfiles.
- [ ] Reescribir `formacion/plan_formativo.md` (§5) y adaptar `coordinacion/plan_proyecto.md` (§6).
- [ ] Reutilizar plantillas de `coordinacion/` (seguimiento, equipo, reuniones) y `.gitignore` (añadir ignorar rasters pesados de `data/raw/` y `data/processed/`).
- [ ] Registrar los alumnos del equipo en `coordinacion/equipo.md`.

> Atajo: este mismo documento puede entregarse a un asistente con la instrucción *"genera el workspace del Reto 6 siguiendo `transferencia.md`, usando el del Reto 5 como plantilla"*.

---

## 8. Decisiones de stack por defecto (revisables)

| Pieza | Opción por defecto | Alternativas |
|-------|--------------------|--------------|
| Lenguaje | Python 3.11+ | — |
| Geoespacial | rasterio + geopandas + shapely + pyproj | — |
| CRS de trabajo | ETRS89 / UTM 30N (EPSG:25830) | según zona del trazado |
| LCP | scikit-image `MCP_Geometric` | networkx (Dijkstra sobre grafo) |
| Descarga OSM | osmnx | overpass directo |
| Visualización | folium + contextily | matplotlib, kepler.gl |
| UI | Streamlit con mapa | mapa estático + tabla |

Cualquier cambio de stack se registra en el `seguimiento.md` del nuevo workspace, igual que en el Reto 5.
