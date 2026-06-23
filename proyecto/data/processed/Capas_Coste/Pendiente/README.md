# Capa de DIRECCIÓN de pendiente (gradiente)

> Generado por [`src/superficie/gradiente.py`](../../../../src/superficie/gradiente.py).
> Respuesta a la reunión con Enagás del **2026-06-22**. **Carpeta nueva**: no pisa
> `pendiente_A.tif` / `pendiente_B.tif` (capa de magnitud), que siguen intactas.

## Qué es y por qué

Enagás pidió **dos capas** para la pendiente:

1. **Magnitud** (escalar, ya existía) → `Capas_Coste/pendiente_{s}.tif`. Coste por
   tramos + barrera a >30°. Se queda **fina** (30 m) para no falsear barreras ni la
   métrica de pendiente máxima.
2. **Dirección** (vectorial, esta carpeta) → línea de máxima pendiente. Para que la
   tubería cruce las laderas **de frente** (perpendicular a las curvas de nivel) y
   no en transversal (riesgo de cizalla ante deslizamientos de terreno).

La dirección se calcula sobre una **copia suavizada** del DEM (Gaussiano, sigma en
metros). El DEM original **no se toca**. Se suaviza porque la dirección es una
derivada y las derivadas amplifican el ruido: a 30 m la línea de máxima pendiente
"tiembla" y "perpendicular a la ladera" pierde sentido. Suavizando se ve la
**ladera real** (cientos de m), no los guijarros.

## Ficheros

Por escenario `s ∈ {A, B}` y sigma `N ∈ {90, 150, 250}` m:

- `gradiente_{s}_sig{N}m.tif` — raster de 4 bandas:
  1. `dz/dx` (Este+)
  2. `dz/dy` (fila+/Sur+)
  3. pendiente suavizada (grados)
  4. azimut de la línea de máxima pendiente, **sentido descenso** (grados, 0=N 90=E)
- `gradiente_{s}_sig{N}m_flechas.gpkg` — flechas **cuesta abajo** para validar el
  sentido en QGIS.

Se generan **3 sigmas** para elegir la escala a la que "se ve la ladera real".
A más sigma, más suave la dirección (y menor la pendiente aparente: A pasa de
48.9° a 15.6° entre sig90 y sig250 — por eso la magnitud NO se suaviza).

## Convenio de signos (EPSG:25830, Este/Norte)

```
ascenso  (cuesta arriba) ∝ ( dz/dx, -dz/dy)
descenso (línea de caída) ∝ (-dz/dx,  dz/dy)   ← la que sigue el agua / la tubería
```

## Verificación "no está invertido"

En cada `.gpkg`, la columna **`dz` debe ser < 0** en todas las flechas: la cota al
final de la flecha (sobre la superficie suavizada, a 1.5 celdas) es menor que al
inicio → la flecha apunta cuesta abajo. Comprobado: **100%** de las flechas con
`dz < 0` en A y B, en los tres sigmas.

## Pendiente (Fase 2, aún no hecho)

Esta capa todavía **no** entra en el motor LCP. El siguiente paso es el LCP
anisótropo: coste de transición `base · long · (1 + λ · S · sinθ)`, con θ = ángulo
del paso respecto a la línea de máxima pendiente. Eso penaliza cruzar en transversal.
Requiere cambiar `src/trazados/lcp.py` (no se puede prehornear en `combinar.py`).
