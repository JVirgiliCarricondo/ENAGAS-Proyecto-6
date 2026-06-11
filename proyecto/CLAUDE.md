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
│   ├── raw/              # capas GIS originales (NO se versionan) + FUENTES.md
│   ├── processed/        # salidas del pipeline (NO se versionan)
│   │   ├── Recorte_AOI/  #   vectores recortados al AOI (.gpkg); vacíos si sin datos
│   │   └── Rasters_AOI/  #   rasters alineados (.tif): DEM de ingesta + rasters de superficie/
│   └── config/           # AOI, origen/destino y perfiles de prioridad (sí se versionan)
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

Setup. Estructura y arquitectura del pipeline definidas; pendiente catalogar capas, fijar AOI/origen/destino y alinear (ver [`../estado.md`](../estado.md)). Los módulos de `src/` son por ahora esqueletos con su responsabilidad documentada.

## Cómo empezar

Ver [`README.md`](README.md).
