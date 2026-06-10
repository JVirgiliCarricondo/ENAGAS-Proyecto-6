# Plan de proyecto — Grupo 6 (Reto 6, Enagás)

> Plan de trabajo del prototipo. Sprints semanales de lunes a viernes. Cierre del programa: **17 jul 2026**.

## Hitos

| # | Hito | Fecha objetivo |
|---|------|----------------|
| H0 | Formación intensiva completada | 29 may ✅ |
| H1 | Entorno listo + catálogo de capas GIS + AOI/origen/destino definidos | 5 jun |
| H2 | Todas las capas descargadas, reproyectadas (EPSG:25830) y alineadas a rejilla común | 12 jun |
| H3 | Superficies de coste multicriterio + perfiles de prioridad | 19 jun |
| H4 | Motor LCP funcionando (una ruta por perfil) | 26 jun |
| H5 | Rutas diferenciadas + métricas multicriterio + comparativa + mapa | 3 jul |
| H6 | Evaluación pasada (rutas distintas, métricas correctas) + robustez | 10 jul |
| H7 | Presentación final + demo | 17 jul |

## Sprints

### S1 (1–5 jun) — Setup + catálogo de capas + AOI · 🟡 en curso
- Montar entorno geoespacial (`proyecto/`), repos y dependencias.
- Catalogar las capas GIS públicas en `proyecto/data/raw/FUENTES.md` (URL, fecha, CRS original, resolución).
- Definir AOI, origen (planta H₂) y destino (conexión a red troncal) en `proyecto/data/config/`.
- Esbozar los perfiles de prioridad (vectores de pesos) en `proyecto/data/config/perfiles.yaml`.
- **Entregable:** entorno reproducible + capas catalogadas + AOI/origen/destino fijados.

### S2 (8–12 jun) — Ingesta y alineación
- Pipeline de descarga/recorte de cada capa al AOI.
- Reproyección a **EPSG:25830** y remuestreo a una **rejilla común**.
- Rasterización de capas vectoriales (Red Natura 2000, CLC, OSM) a la rejilla.
- **Entregable:** todas las capas alineadas (mismo CRS y rejilla), verificable superponiéndolas.

### S3 (15–19 jun) — Superficies de coste
- Función de coste por capa (pendiente, uso de suelo, protección, proximidad a cruces…).
- Combinación multicriterio con pesos → superficie de coste.
- Perfiles de prioridad: distintos pesos → distintas superficies.
- **Entregable:** superficies de coste reproducibles, una por perfil.

### S4 (22–26 jun) — Motor LCP
- Camino de mínimo coste origen→destino (`skimage.graph` / `networkx`).
- Una ruta por perfil, con su geometría y coste relativo.
- **Entregable:** motor LCP que devuelve una ruta válida por perfil.

### S5 (29 jun–3 jul) — Diferenciación + métricas + comparativa
- Diferenciación de rutas: corridor masking + perfiles; validar solapamiento.
- Métricas por ruta: longitud, coste relativo, cruces, km protegida/urbana, pendiente máx/media.
- Tabla comparativa + mapa (folium) y, si da tiempo, UI Streamlit.
- **Entregable:** 3-5 rutas diferenciadas con comparativa y mapa.

### S6 (6–10 jul) — Evaluación + robustez
- Casos tipo (ver [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md) §7).
- Comprobar diferenciación real y corrección de métricas; cazar rutas duplicadas y costes mal combinados.
- Robustez ante cambios de AOI/origen/destino.
- **Entregable:** informe de evaluación con resultados.

### S7 (13–17 jul) — Pulido + presentación
- Refinar UI/mapa y mensajes; documentar limitaciones y siguientes pasos.
- Preparar y ensayar la presentación final tipo mini-consultoría.
- **Entregable:** demo + presentación.

## WBS (desglose de trabajo)

```
1. Datos GIS
   1.1 Catálogo de capas (FUENTES.md) con CRS y resolución originales
   1.2 Descarga y recorte al AOI
   1.3 Reproyección (EPSG:25830) + remuestreo a rejilla común + rasterización
2. Superficies de coste
   2.1 Función de coste por capa
   2.2 Combinación multicriterio con pesos
   2.3 Perfiles de prioridad
3. Trazados
   3.1 Motor LCP (una ruta por perfil)
   3.2 Diferenciación (corridor masking + validación de solapamiento)
4. Métricas
   4.1 Longitud y coste relativo
   4.2 Cruces especiales (nº y tipo)
   4.3 Km en zona protegida / urbana
   4.4 Pendiente máxima y media
5. Comparativa + mapa
   5.1 Tabla multicriterio + scoring
   5.2 Mapa (folium / contextily) y UI (Streamlit)
6. Calidad
   6.1 Pruebas de alineación de rasters
   6.2 Pruebas de métricas y de diferenciación de rutas
7. Comunicación
   7.1 Documentación
   7.2 Presentación final
```

## Definición de "hecho" (DoD)

Una tarea está hecha cuando: el código corre en el entorno del proyecto, **todas las capas comparten CRS (EPSG:25830) y rejilla común**, las rutas generadas son **demostrablemente diferenciadas**, y **todos los costes son relativos (índice), nunca en €**.
