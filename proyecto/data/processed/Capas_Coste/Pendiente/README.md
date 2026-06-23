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

Cada `.gpkg` lleva `exposicion_transversal` = media de `S·sinθ` por la ruta
(0 = siempre de frente a la ladera).

### Demo del efecto (pesos iguales, `--modo demo`)

- `ruta_{s}_anisotropa.gpkg` y `ruta_{s}_isotropa.gpkg` — misma superficie, λ=4 vs λ=0.
  Aísla el efecto de la anisotropía:

  | Escenario | exposición isótropa | exposición anisótropa | mejora |
  |---|---|---|---|
  | A | 0.0377 | 0.0233 | −38% |
  | B | 0.0352 | 0.0185 | −47% |

  Las rutas comparten solo ~21% de celdas: el corredor cambia para cruzar las
  laderas de frente, sin alargarse.

### Rutas por perfil (`--modo perfiles`) — versión anisótropa para comparar

> Contexto: `main` (commit c783166) ya resuelve este encargo de Enagás con OTRO
> método (capa escalar `traversal_{s}.tif` = `pendiente·|sin(aspecto − azimut_OD)|`,
> con el azimut **global** O→D, + LCP isótropo). Esta carpeta es la versión
> **alternativa** para comparar: dirección **suavizada** + transversalidad por la
> dirección **local** real (LCP anisótropo). El equipo / backtesting decidirá cuál.

Para una comparación justa se adoptan los **mismos pesos por perfil que main**
(`perfiles.yaml`). Única diferencia entre ambos métodos:

- **main**: `traversal` es una capa escalar (peso normal) + LCP isótropo.
- **aquí**: NO hay capa `traversal`; su peso por perfil **escala λ** (fuerza del
  cruce perpendicular en el LCP anisótropo). λ_perfil = λ_base(4.0) · peso_traversal.

Capas escalares combinadas (1:1): `pendiente, protegida, cruces, expropiacion,
geotecnia`; `longitud` = coste base por celda.

Ficheros: `ruta_{s}_{corto,ambiental,pendiente,equilibrio}.gpkg`.

**Diferenciación** (solape de trazado, buffer 60 m; menor = más distintas):

| | corto·ambiental | corto·pendiente | corto·equil. | amb·pend | amb·equil | pend·equil |
|---|---|---|---|---|---|---|
| A | 46% | 45% | 65% | 43% | 53% | 62% |
| B | 35% | 34% | 91% | 81% | 40% | 38% |

(Antes, con los pesos viejos de la rama, salían 88–100%: prácticamente iguales.)

`λ_base` se ajusta con `--lambda` (def. 4.0); su valor final se fija con el
backtesting contra un ramal real.

### Superficies de coste que originan cada ruta

- `superficie_{s}_{corto,ambiental,pendiente,equilibrio}.tif` — superficie escalar
  ponderada de cada perfil (la que entra en el LCP). Alineadas al DEM, nodata=-9999.
- `superficie_{s}_demo.tif` — superficie de pesos iguales que origina el par
  iso/aniso (copia de `Trazados/superficie_{s}.tif`).

**Ojo:** en esta versión anisótropa, cada ruta NO sale solo de su raster escalar.
La ruta = **`superficie_{s}_{perfil}.tif` (coste escalar) + `gradiente_{s}_sig150m.tif`
(dirección) + λ_perfil**. El término direccional `λ·S·sinθ` se aplica en las
transiciones del LCP, no se puede prehornear en el raster escalar. El raster escalar
es, por tanto, una parte de lo que origina la ruta; la dirección es la otra.
