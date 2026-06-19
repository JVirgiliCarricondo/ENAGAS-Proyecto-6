# Estado — Grupo 6 (Reto 6, Enagás)

> Resumen ejecutivo. Actualizar al cierre de cada sprint semanal. Última actualización: **2026-06-22**.

## Semáforo general

| Dimensión | Estado | Comentario |
|-----------|--------|------------|
| Formación | 🟢 En marcha | Semana 0 de formación completada (25-29 may). Refuerzo continuo (GIS) durante el proyecto. |
| Coordinación | 🟢 En marcha | Plan de proyecto y sprints definidos. Equipo por confirmar nominalmente. |
| Código | 🟢 En marcha | **MVP 1 completado:** 6 capas GIS alineadas (EPSG:25830 · ~30 m) + 5 superficies de coste implementadas. Motor LCP en desarrollo (Sprint 4). |

## Hito actual

**Sprint 4 (22–26 jun): Motor LCP → MVP 2-3.** Con los datos alineados y las superficies de coste listas, implementar el **camino de mínimo coste** (A\*) origen→destino: una ruta válida por perfil, con su geometría y coste asociado. Es el primer resultado tangible que se podrá enseñar sobre mapa.

> **Revisión intermedia con Enagás (22 jun):** presentación ejecutiva en [`proyecto/presentacion.html`](proyecto/presentacion.html). Puntos abiertos para validación con el cliente: **coste por atributo de cada capa** y **pesos por capa** (perfiles de prioridad).

> El avance se sigue por dos ejes: los **sprints semanales** ([`coordinacion/plan_proyecto.md`](coordinacion/plan_proyecto.md)) y la **escalera de 8 hitos MVP** de Enagás ([`docs/hitos_mvp.md`](docs/hitos_mvp.md)). Núcleo comprometido del verano: **MVP 1-4**.

## Riesgos abiertos

- **Alineación de capas (CRS y rejilla):** ✅ **mitigado.** Las 6 capas ya están reproyectadas a EPSG:25830 y alineadas a la rejilla común (~30 m); fuentes y resoluciones originales catalogadas en [`proyecto/data/raw/FUENTES.md`](proyecto/data/raw/FUENTES.md).
- **Diferenciación real de rutas:** que las 3-5 rutas no acaben siendo el mismo corredor con ruido. Validar diferenciación (corridor masking + perfiles de prioridad distintos) desde que el motor LCP produzca la primera ruta (Sprint 4-5).
- **Calibración de costes y pesos:** los valores por defecto son del equipo; pendiente validarlos con Enagás (planteado en la revisión intermedia del 22 jun).
- **Coste relativo, nunca €:** mantener la disciplina de índice normalizado; no prometer estimación económica.
- **Ramal real para backtesting:** pedir a Enagás un ramal de H₂ existente (origen/destino) para validar el modelo (MVP 4/6). Sin él, la validación se queda en interna.
- **Alcance de EV-500:** confirmar con Enagás el contenido exacto del "paquete tipo EV-500" antes de comprometer MVP 5/8.
- **Equipo nominal:** pendiente registrar los 3-4 alumnos asignados en [`coordinacion/equipo.md`](coordinacion/equipo.md).

## Próximos pasos

1. Implementar el **motor LCP** (A\*) en `proyecto/src/trazados/lcp.py`: una ruta por perfil con geometría y coste.
2. Calibrar costes y pesos con el feedback de Enagás de la revisión intermedia.
3. Encadenar **diferenciación + métricas + comparador** (Sprint 5) sobre la primera ruta válida.

## Bitácora de sprints

| Sprint | Fechas | Objetivo | MVP | Estado |
|--------|--------|----------|-----|--------|
| S0 | 25-29 may | Formación intensiva | — | ✅ |
| S1 | 1-5 jun | Setup + catálogo de capas + AOI + matriz de condicionantes | MVP 1 | ✅ |
| S2 | 8-12 jun | Ingesta: descarga, reproyección y alineación a rejilla común | MVP 1 | ✅ |
| S3 | 15-19 jun | Superficies de coste + perfiles + trazado base (A\*/Dijkstra) | MVP 2 | ✅ |
| S4 | 22-26 jun | Motor LCP (una ruta por perfil) | MVP 2-3 | 🟡 En curso |
| S5 | 29 jun-3 jul | Alternativas diferenciadas + métricas + comparador + ranking | MVP 3-4 | ⬜ |
| S6 | 6-10 jul | Evaluación + backtesting con ramal real + robustez | MVP 4, 6 | ⬜ |
| S7 | 13-17 jul | Pulido + presentación (+ EV-500/herramienta si da tiempo) | MVP 5/7 | ⬜ |
