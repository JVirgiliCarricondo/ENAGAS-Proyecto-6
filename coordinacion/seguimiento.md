# Seguimiento — Grupo 6 (Reto 6, Enagás)

> Bitácora viva. Una entrada por sprint (y notas sueltas cuando haga falta). Lo más reciente, arriba.

## Plantilla de entrada de sprint

```
## Sprint X (fechas) — Título
**Avance:** …
**Hecho:** …
**Bloqueos:** …
**Decisiones:** …
**Para el próximo sprint:** …
**Dudas de formación a reforzar:** …
```

---

## Sprint 1 (1–5 jun) — Setup + catálogo de capas + AOI
**Avance:** workspace creado (estructura, CLAUDE.md, plan, arquitectura del pipeline geoespacial). Pendiente catalogar capas, fijar AOI/origen/destino y montar el entorno geoespacial.
**Hecho:** documentación base y plan de proyecto.
**Bloqueos:**
- Confirmar acceso y licencias de las capas públicas (Copernicus DEM/CLC, OSM, hidrografía IGN, Red Natura 2000, IGME).
- Definir el caso de estudio: AOI, origen (planta H₂) y destino (conexión a red troncal).
- Registrar nominalmente al equipo en [`equipo.md`](equipo.md).
**Decisiones:**
- Pipeline geoespacial confirmado (ingesta+alineación → superficies de coste → LCP → diferenciación → métricas → comparativa). Ver [`../proyecto/arquitectura.md`](../proyecto/arquitectura.md).
- CRS de trabajo: **ETRS89 / UTM 30N (EPSG:25830)**. LCP por defecto con `skimage.graph` (revisable). UI con Streamlit + folium (revisable).
**Para el próximo sprint:** descargar capas a `proyecto/data/raw/`, catalogarlas en `FUENTES.md` (con CRS y resolución), reproyectar y alinear a rejilla común.
**Dudas de formación a reforzar:** reproyección/remuestreo con rasterio; rasterización de vectores; intuición del camino de mínimo coste.

---

## Sprint 0 (25–29 may) — Formación intensiva ✅
**Avance:** campus de vibe coding completado.
**Hecho:** entornos montados, primer contacto con datos geoespaciales (raster vs vector, CRS, abrir un GeoTIFF).
**Para el próximo sprint:** arrancar dominio GIS y la ingesta/alineación de capas.
