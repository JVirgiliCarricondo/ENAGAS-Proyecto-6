# Estado — Grupo 6 (Reto 6, Enagás)

> Resumen ejecutivo. Actualizar al cierre de cada sprint semanal. Última actualización: **2026-06-05**.

## Semáforo general

| Dimensión | Estado | Comentario |
|-----------|--------|------------|
| Formación | 🟢 En marcha | Semana 0 de formación completada (25-29 may). Refuerzo continuo (GIS) durante el proyecto. |
| Coordinación | 🟢 En marcha | Plan de proyecto y sprints definidos. Equipo por confirmar nominalmente. |
| Código | 🟡 Setup | Estructura y arquitectura del pipeline geoespacial definidas. Pendiente catalogar capas GIS y fijar AOI/origen/destino. |

## Hito actual

**Sprint 1 (1–5 jun): Setup + catálogo de capas + AOI.** Dejar el entorno geoespacial funcionando, catalogar las capas GIS públicas y definir el área de interés (AOI), el origen (planta H₂) y el destino (conexión a red troncal).

## Riesgos abiertos

- **Alineación de capas (CRS y rejilla):** el mayor riesgo técnico del reto. Si las capas no comparten CRS (EPSG:25830) y rejilla común, combinar superficies de coste produce resultados engañosos. Documentar desde el día 1 el CRS y la resolución original de cada capa.
- **Diferenciación real de rutas:** que las 3-5 rutas no acaben siendo el mismo corredor con ruido. Validar diferenciación (corridor masking + perfiles de prioridad distintos) desde que el motor LCP produzca la primera ruta.
- **Coste relativo, nunca €:** mantener la disciplina de índice normalizado; no prometer estimación económica.
- **Descarga de capas públicas:** confirmar acceso y licencias de DEM Copernicus, CLC, OSM, hidrografía IGN, Red Natura 2000 e IGME.
- **Equipo nominal:** pendiente registrar los 3-4 alumnos asignados en [`coordinacion/equipo.md`](coordinacion/equipo.md).

## Próximos pasos

1. Completar [`coordinacion/equipo.md`](coordinacion/equipo.md) con los alumnos asignados.
2. Definir AOI, origen y destino en `proyecto/data/config/` (escenario y perfiles de prioridad).
3. Catalogar las capas GIS en `proyecto/data/raw/FUENTES.md` (URL, fecha, CRS original, resolución).

## Bitácora de sprints

| Sprint | Fechas | Objetivo | Estado |
|--------|--------|----------|--------|
| S0 | 25-29 may | Formación intensiva | ✅ |
| S1 | 1-5 jun | Setup + catálogo de capas GIS + AOI/origen/destino | 🟡 En curso |
| S2 | 8-12 jun | Ingesta: descarga, reproyección y alineación a rejilla común | ⬜ |
| S3 | 15-19 jun | Superficies de coste multicriterio + perfiles de prioridad | ⬜ |
| S4 | 22-26 jun | Motor LCP (una ruta por perfil) | ⬜ |
| S5 | 29 jun-3 jul | Diferenciación + métricas + comparativa + mapa | ⬜ |
| S6 | 6-10 jul | Evaluación (rutas distintas, métricas correctas) + robustez | ⬜ |
| S7 | 13-17 jul | Pulido + presentación final | ⬜ |
