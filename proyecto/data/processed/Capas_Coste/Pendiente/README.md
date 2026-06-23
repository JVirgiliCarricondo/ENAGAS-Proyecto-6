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

## Fase 2 — Ruta con LCP anisótropo (hecho)

Generada por [`src/trazados/ruta_pendiente.py`](../../../../src/trazados/ruta_pendiente.py).
La capa de dirección entra ahora en un LCP anisótropo (Dijkstra 8-conexo) cuyo coste
de transición penaliza cruzar la pendiente en transversal:

```
coste(p→q) = d · C_celda · (1 + λ · S · sinθ)
```
- `C_celda` = superficie escalar combinada (Trazados/superficie_{s}.tif, que ya
  incluye la pendiente-MAGNITUD y el resto de capas: geotecnia, cruces, protegida…)
- `S` = pendiente normalizada [0,1] (capa de dirección) · `θ` = ángulo del paso
  respecto a la línea de máxima pendiente · `λ` = peso (def. 4.0, calibrable).

**Ficheros** (por escenario `s ∈ {A, B}`):
- `ruta_{s}_anisotropa.gpkg` — la propuesta, con la consideración de Enagás.
- `ruta_{s}_isotropa.gpkg`   — baseline sin anisotropía, para comparar.

Cada `.gpkg` lleva `exposicion_transversal` = media de `S·sinθ` por la ruta
(0 = siempre de frente a la ladera). Resultado (λ=4):

| Escenario | exposición isótropa | exposición anisótropa | mejora |
|---|---|---|---|
| A | 0.0377 | 0.0233 | −38% |
| B | 0.0352 | 0.0185 | −47% |

Las rutas comparten solo ~21% de celdas con la isótropa: el corredor cambia para
cruzar las laderas de frente, sin alargarse. `λ` es el parámetro de calibración
(`--lambda`); su valor final se fijará con el backtesting contra un ramal real.
