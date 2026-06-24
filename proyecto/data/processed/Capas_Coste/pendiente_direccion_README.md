# Capa de DIRECCIÓN de pendiente (`pendiente_direccion_{s}`)

> Generada por [`src/superficie/gradiente.py`](../../../src/superficie/gradiente.py).
> Respuesta a la reunión con Enagás del **2026-06-22**. Vive en `Capas_Coste/`, junto
> a la capa de **magnitud** `pendiente_{s}.tif`: son dos capas distintas y
> complementarias (magnitud vs dirección), ninguna pisa a la otra.

## Qué es y por qué

Enagás pidió **dos capas** para la pendiente:

1. **Magnitud** (escalar) → `Capas_Coste/pendiente_{s}.tif`. Coste por tramos +
   barrera a >30°. Se queda **fina** (30 m) para no falsear barreras ni la métrica
   de pendiente máxima.
2. **Dirección** (vectorial, esta capa) → `Capas_Coste/pendiente_direccion_{s}.tif`.
   Línea de máxima pendiente, para que la tubería cruce las laderas **de frente**
   (perpendicular a las curvas de nivel) y no en transversal (riesgo de cizalla ante
   deslizamientos de terreno).

La dirección se calcula sobre una **copia suavizada** del DEM (Gaussiano, sigma en
metros). El DEM original **no se toca**. Se suaviza porque la dirección es una
derivada y las derivadas amplifican el ruido: a 30 m la línea de máxima pendiente
"tiembla" y "perpendicular a la ladera" pierde sentido. Suavizando se ve la
**ladera real** (cientos de m), no los guijarros.

## Ficheros (en `Capas_Coste/`)

Por escenario `s ∈ {A, B}`, a la escala elegida (sigma = 150 m):

- `pendiente_direccion_{s}.tif` — raster de 4 bandas:
  1. `dz/dx` (Este+)
  2. `dz/dy` (fila+/Sur+)
  3. pendiente suavizada (grados)
  4. azimut de la línea de máxima pendiente, **sentido descenso** (grados, 0=N 90=E)
- `pendiente_direccion_{s}_flechas.gpkg` — flechas **cuesta abajo** para validar el
  sentido en QGIS.

La escala se eligió comparando sigma = 90 / 150 / 250 m (a más sigma, más suave la
dirección y menor la pendiente aparente: A pasa de 48.9° a 15.6° entre sig90 y
sig250 — por eso la MAGNITUD no se suaviza). Se fijó **150 m**, cuya salida es la capa
**canónica** (sin sufijo). Para regenerar otras escalas de comparación:
`python -m src.superficie.gradiente --escenario A --sigmas 90 150 250` (escriben con
sufijo `_sig{N}m` para no pisar la canónica).

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

Generada por [`src/trazados/ruta_pendiente.py`](../../../src/trazados/ruta_pendiente.py).
La capa de dirección entra en un LCP anisótropo (Dijkstra 8-conexo) cuyo coste de
transición penaliza cruzar la pendiente en transversal:

```
coste(p→q) = d · C_celda · (1 + λ · S · sinθ)
```
- `C_celda` = superficie escalar combinada (`Trazados/superficie_{s}.tif`, que ya
  incluye la pendiente-MAGNITUD y el resto de capas: geotecnia, cruces, protegida…)
- `S` = pendiente normalizada [0,1] (capa de dirección) · `θ` = ángulo del paso
  respecto a la línea de máxima pendiente · `λ` = peso (def. 4.0, calibrable).

Cada `.gpkg` lleva `exposicion_transversal` = media de `S·sinθ` por la ruta
(0 = siempre de frente a la ladera).

### Demo del efecto (pesos iguales, `--modo demo`)

Genera `ruta_{s}_anisotropa.gpkg` y `ruta_{s}_isotropa.gpkg` (misma superficie, λ=4 vs
λ=0) para aislar el efecto de la anisotropía. Son artefactos **regenerables** (no se
guardan en bruto); la evidencia queda aquí:

  | Escenario | exposición isótropa | exposición anisótropa | mejora |
  |---|---|---|---|
  | A | 0.0377 | 0.0233 | −38% |
  | B | 0.0352 | 0.0185 | −47% |

Las rutas comparten solo ~21% de celdas: el corredor cambia para cruzar las laderas
de frente, sin alargarse.

### Rutas por perfil (`--modo perfiles`) — versión anisótropa para comparar

> Contexto: `main` (commit c783166) ya resuelve este encargo de Enagás con OTRO
> método (capa escalar `traversal_{s}.tif` = `pendiente·|sin(aspecto − azimut_OD)|`,
> con el azimut **global** O→D, + LCP isótropo). Esta es la versión **alternativa**
> para comparar: dirección **suavizada** + transversalidad por la dirección **local**
> real (LCP anisótropo). El equipo / backtesting decidirá cuál.

Para una comparación justa se adoptan los **mismos pesos por perfil que main**
(`perfiles.yaml`). Única diferencia entre ambos métodos:

- **main**: `traversal` es una capa escalar (peso normal) + LCP isótropo.
- **aquí**: NO hay capa `traversal`; su peso por perfil **escala λ** (fuerza del cruce
  perpendicular en el LCP anisótropo). λ_perfil = λ_base(4.0) · peso_traversal.

Capas escalares combinadas (1:1): `pendiente, protegida, cruces, expropiacion,
geotecnia`; `longitud` = coste base por celda.

**Salidas** (ya reubicadas en sus carpetas canónicas):

- Rutas por perfil → `Rutas/ruta_{s}_{corto,ambiental,pendiente,equilibrio}.gpkg`.
- Superficies de coste de cada perfil → `Trazados/superficie_{s}_{corto,ambiental,pendiente,equilibrio}.tif`.

**Diferenciación** (solape de trazado, buffer 60 m; menor = más distintas):

| | corto·ambiental | corto·pendiente | corto·equil. | amb·pend | amb·equil | pend·equil |
|---|---|---|---|---|---|---|
| A | 46% | 45% | 65% | 43% | 53% | 62% |
| B | 35% | 34% | 91% | 81% | 40% | 38% |

(Antes, con los pesos viejos de la rama, salían 88–100%: prácticamente iguales.)

`λ_base` se ajusta con `--lambda` (def. 4.0); su valor final se fija con el
backtesting contra un ramal real.

### Qué origina cada ruta

En esta versión anisótropa, cada ruta NO sale solo de su raster escalar. La ruta =
**`Trazados/superficie_{s}_{perfil}.tif` (coste escalar) + `Capas_Coste/pendiente_direccion_{s}.tif`
(dirección) + λ_perfil**. El término direccional `λ·S·sinθ` se aplica en las
transiciones del LCP, no se puede prehornear en el raster escalar: el raster escalar
es una parte de lo que origina la ruta; la dirección es la otra.
