# Estado — Grupo 6 (Reto 6, Enagás)

> Resumen ejecutivo. Actualizar al cierre de cada sprint semanal. Última actualización: **2026-07-08**.

## Semáforo general

| Dimensión | Estado | Comentario |
|-----------|--------|------------|
| Formación | 🟢 En marcha | Semana 0 de formación completada (25-29 may). Refuerzo continuo (GIS) durante el proyecto. |
| Coordinación | 🟢 En marcha | Plan de proyecto y sprints definidos. Equipo por confirmar nominalmente. |
| Código | 🟢 En marcha | **MVP 1-3 operativos:** 6 capas alineadas (EPSG:25830 · ~30 m), 6 capas de coste, **motor LCP Dijkstra 8-conexo** (`src/trazados/ruta_pendiente.py`), 4 rutas por escenario con validación de diferenciación, métricas multicriterio y **app Streamlit completa** (asistente 3 pasos + informe PDF). |

## Hito actual

**Sprint 6 (6–10 jul): evaluación + robustez → MVP 4.** El pipeline end-to-end funciona (origen/destino → descarga → capas de coste → 4 rutas → métricas → comparativa en la app). Foco actual: robustez de la entrega, calibración de costes/pesos con Enagás y backtesting con un ramal real si se recibe.

> **Revisión intermedia con Enagás (22 jun):** presentación ejecutiva en [`proyecto/presentacion-intermedia-2026-06-22.html`](proyecto/presentacion-intermedia-2026-06-22.html).
> 👉 **Ver renderizada (sin descargar):** [presentación intermedia 22-jun-2026](https://htmlpreview.github.io/?https://github.com/MonicaOlmos2003/ENAGAS-Proyecto-6/blob/main/proyecto/presentacion-intermedia-2026-06-22.html)
> Puntos abiertos para validación con el cliente: **coste por atributo de cada capa** y **pesos por capa** (perfiles de prioridad).

> El avance se sigue por dos ejes: los **sprints semanales** ([`coordinacion/plan_proyecto.md`](coordinacion/plan_proyecto.md)) y la **escalera de 8 hitos MVP** de Enagás ([`docs/hitos_mvp.md`](docs/hitos_mvp.md)). Núcleo comprometido del verano: **MVP 1-4**.

## Riesgos abiertos

- **Alineación de capas (CRS y rejilla):** ✅ **mitigado.** Las 6 capas ya están reproyectadas a EPSG:25830 y alineadas a la rejilla común (~30 m); fuentes y resoluciones originales catalogadas en [`proyecto/data/raw/FUENTES.md`](proyecto/data/raw/FUENTES.md).
- **Diferenciación real de rutas:** ✅ **mitigado.** Las 4 rutas nacen de perfiles de prioridad distintos y se **valida el solapamiento** entre corredores (buffer 60 m, umbral 50 %; matriz visible en la app). Decisión de diseño: **sin penalización algorítmica (corridor masking)** — las rutas por perfil resultan suficientemente distintas; si un par sale redundante, se reporta para revisar pesos.
- **Calibración de costes y pesos:** los valores por defecto son del equipo; pendiente validarlos con Enagás (planteado en la revisión intermedia del 22 jun).
- **Coste relativo, nunca €:** mantener la disciplina de índice normalizado; no prometer estimación económica.
- **Ramal real para backtesting:** pedir a Enagás un ramal de H₂ existente (origen/destino) para validar el modelo (MVP 4/6). Sin él, la validación se queda en interna.
- **Alcance de EV-500:** confirmar con Enagás el contenido exacto del "paquete tipo EV-500" antes de comprometer MVP 5/8.
- **Equipo nominal:** pendiente registrar los 3-4 alumnos asignados en [`coordinacion/equipo.md`](coordinacion/equipo.md).

## Próximos pasos

1. Calibrar costes y pesos con el feedback de Enagás de la revisión intermedia.
2. **Backtesting** con un ramal real (pendiente de Enagás) y robustez del pipeline.
3. Opcional (Sprint 7): **scoring/ranking formal** en `src/comparacion/comparador.py` (hoy la comparativa vive en la página de Resultados de la app) y CLI de orquestación (`src/app/cli.py`).

## Bitácora de sprints

| Sprint | Fechas | Objetivo | MVP | Estado |
|--------|--------|----------|-----|--------|
| S0 | 25-29 may | Formación intensiva | — | ✅ |
| S1 | 1-5 jun | Setup + catálogo de capas + AOI + matriz de condicionantes | MVP 1 | ✅ |
| S2 | 8-12 jun | Ingesta: descarga, reproyección y alineación a rejilla común | MVP 1 | ✅ |
| S3 | 15-19 jun | Superficies de coste + perfiles + trazado base (A\*/Dijkstra) | MVP 2 | ✅ |
| S4 | 22-26 jun | Motor LCP (una ruta por perfil) — Dijkstra en `ruta_pendiente.py` | MVP 2-3 | ✅ |
| S5 | 29 jun-3 jul | Alternativas diferenciadas + métricas + app de resultados | MVP 3-4 | ✅ (comparador formal pospuesto a S7) |
| S6 | 6-10 jul | Evaluación + backtesting con ramal real + robustez | MVP 4, 6 | 🟡 En curso |
| S7 | 13-17 jul | Pulido + presentación (+ EV-500/herramienta si da tiempo) | MVP 5/7 | ⬜ |
