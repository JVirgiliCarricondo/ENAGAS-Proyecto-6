# Estado — Grupo 6 (Reto 6, Enagás)

> Resumen ejecutivo. Actualizar al cierre de cada sprint semanal. Última actualización: **2026-06-05**.

## Semáforo general

| Dimensión | Estado | Comentario |
|-----------|--------|------------|
| Formación | 🟢 En marcha | Semana 0 de formación completada (25-29 may). Refuerzo continuo (GIS) durante el proyecto. |
| Coordinación | 🟢 En marcha | Plan de proyecto y sprints definidos. Equipo por confirmar nominalmente. |
| Código | 🟡 Setup | Estructura y arquitectura del pipeline geoespacial definidas. Pendiente catalogar capas GIS y fijar AOI/origen/destino. |

## Hito actual

**Sprint 1 (1–5 jun): Setup + catálogo de capas + AOI → MVP 1.** Dejar el entorno geoespacial funcionando, catalogar las capas GIS públicas, definir AOI/origen/destino, montar la primera **matriz de condicionantes** (técnicos/ambientales/administrativos) y validar la calidad de los datos.

> El avance se sigue por dos ejes: los **sprints semanales** ([`coordinacion/plan_proyecto.md`](coordinacion/plan_proyecto.md)) y la **escalera de 8 hitos MVP** de Enagás ([`docs/hitos_mvp.md`](docs/hitos_mvp.md)). Núcleo comprometido del verano: **MVP 1-4**.

## Riesgos abiertos

- **Alineación de capas (CRS y rejilla):** el mayor riesgo técnico del reto. Si las capas no comparten CRS (EPSG:25830) y rejilla común, combinar superficies de coste produce resultados engañosos. Documentar desde el día 1 el CRS y la resolución original de cada capa.
- **Diferenciación real de rutas:** que las 3-5 rutas no acaben siendo el mismo corredor con ruido. Validar diferenciación (corridor masking + perfiles de prioridad distintos) desde que el motor LCP produzca la primera ruta.
- **Coste relativo, nunca €:** mantener la disciplina de índice normalizado; no prometer estimación económica.
- **Descarga de capas públicas:** confirmar acceso y licencias de DEM Copernicus, CLC, OSM, hidrografía IGN, Red Natura 2000 e IGME.
- **Ramal real para backtesting:** pedir a Enagás un ramal de H₂ existente (origen/destino) para validar el modelo (MVP 4/6). Sin él, la validación se queda en interna.
- **Alcance de EV-500:** confirmar con Enagás el contenido exacto del "paquete tipo EV-500" antes de comprometer MVP 5/8.
- **Equipo nominal:** pendiente registrar los 3-4 alumnos asignados en [`coordinacion/equipo.md`](coordinacion/equipo.md).

## Próximos pasos

1. Completar [`coordinacion/equipo.md`](coordinacion/equipo.md) con los alumnos asignados.
2. Definir AOI, origen y destino en `proyecto/data/config/` (escenario y perfiles de prioridad).
3. Catalogar las capas GIS en `proyecto/data/raw/FUENTES.md` (URL, fecha, CRS original, resolución).

## Bitácora de sprints

| Sprint | Fechas | Objetivo | MVP | Estado |
|--------|--------|----------|-----|--------|
| S0 | 25-29 may | Formación intensiva | — | ✅ |
| S1 | 1-5 jun | Setup + catálogo de capas + AOI + matriz de condicionantes | MVP 1 | 🟡 En curso |
| S2 | 8-12 jun | Ingesta: descarga, reproyección y alineación a rejilla común | MVP 1 | ⬜ |
| S3 | 15-19 jun | Superficies de coste + perfiles + trazado base (A\*/Dijkstra) | MVP 2 | ⬜ |
| S4 | 22-26 jun | Motor LCP (una ruta por perfil) | MVP 2-3 | ⬜ |
| S5 | 29 jun-3 jul | Alternativas diferenciadas + métricas + comparador + ranking | MVP 3-4 | ⬜ |
| S6 | 6-10 jul | Evaluación + backtesting con ramal real + robustez | MVP 4, 6 | ⬜ |
| S7 | 13-17 jul | Pulido + presentación (+ EV-500/herramienta si da tiempo) | MVP 5/7 | ⬜ |
