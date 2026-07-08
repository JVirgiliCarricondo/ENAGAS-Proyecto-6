# Proyecto — Generación automatizada de trazados de ramales de H₂

> Dimensión 3: el prototipo. Volver al [CLAUDE.md raíz](../CLAUDE.md).
> Diseño técnico en [`arquitectura.md`](arquitectura.md). Contexto del reto en [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md).

## Qué es

Prototipo en Python que, dado un **origen** (planta de H₂), un **destino** (conexión a red troncal) y un **AOI**, genera **3-5 trazados alternativos diferenciados** sobre GIS público y los presenta en **comparativa multicriterio** (longitud, coste relativo, cruces, km en zona protegida/urbana, pendiente) + **mapa**.

## Arquitectura (resumen)

Pipeline geoespacial determinista: **ingesta y alineación de capas** → **superficies de coste multicriterio** (con perfiles de prioridad) → **motor de camino de mínimo coste (LCP)** → **diferenciación de rutas** → **métricas** → **comparativa + mapa**. Detalle en [`arquitectura.md`](arquitectura.md).

## Estructura del código

```
proyecto/
├── README.md             # puesta en marcha
├── arquitectura.md       # diseño técnico
├── requirements.txt      # dependencias (stack geoespacial)
├── .env.example          # variables de entorno (claves de descarga si aplica) — copiar a .env
├── data/
│   ├── raw/              # capas GIS descargadas o aportadas a mano (NO se versionan) + FUENTES.md
│   ├── processed/        # salidas del pipeline (NO se versionan)
│   │   ├── Recorte_AOI/  #   recorte alineado del AOI: vectores (.gpkg) + DEM (.tif)
│   │   ├── Capas_Coste/  #   una capa de coste [0,1] por criterio (.tif)
│   │   ├── Trazados/     #   superficies combinadas (neutral + por perfil) — se regeneran por ejecución
│   │   └── Rutas/        #   rutas LCP por perfil (.gpkg) — se regeneran por ejecución
│   └── config/           # origen/destino por escenario y perfiles de prioridad (sí se versionan)
├── src/
│   ├── ingesta/         # descarga, recorte, reproyección, remuestreo, rasterización
│   ├── superficie/      # superficies de coste (raster multicriterio) + perfiles
│   ├── trazados/        # motor LCP + diferenciación de rutas
│   ├── metricas/        # métricas multicriterio por ruta
│   ├── comparacion/     # tabla comparativa + scoring + mapa
│   └── app/             # orquestador + CLI/Streamlit
├── tests/               # pruebas (priorizar alineación de rasters y métricas)
└── notebooks/           # exploración geoespacial y ejercicios de formación
```

## Convenciones de código

- Python 3.11+. Código y nombres en **inglés**; docstrings pueden ir en español.
- Formato con `ruff` (a fijar). Type hints donde aporten.
- **Alineación:** ninguna capa entra en el pipeline sin estar reproyectada a **EPSG:25830** y remuestreada a la **rejilla común**. Sin alineación, los costes mienten.
- **Coste relativo:** todo coste es un índice adimensional; nunca operar ni mostrar costes en €.
- **Diferenciación:** una ruta solo se acepta en el abanico si es demostrablemente distinta de las demás.
- Secretos (si alguna descarga requiere clave) solo en `.env` (nunca commiteado). Ver `.env.example`.

## Estado del código

Operativo end-to-end (ver [`../estado.md`](../estado.md)): dado origen/destino (≤ 15 km), la app Streamlit descarga los datos del AOI, genera las capas de coste, traza 4 rutas por perfil (Dijkstra 8-conexo en `src/trazados/ruta_pendiente.py`), valida su diferenciación (solapamiento, buffer 60 m / umbral 50 %) y presenta métricas + mapa + informe PDF. `Trazados/` y `Rutas/` se regeneran en cada ejecución. Quedan como esqueletos documentados del Sprint 7: `src/comparacion/comparador.py` (scoring formal) y `src/app/cli.py`.

## Cómo empezar

Ver [`README.md`](README.md).
