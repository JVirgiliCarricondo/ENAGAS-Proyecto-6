# Análisis Técnico: Gestión de Pendientes y Alturas en el Trazado de Ramales

> **Documento de análisis comparativo para el Grupo 6 del CI2 Lab 2026.**  
> Redactado como respuesta al interrogante: *¿conviene trabajar con alturas por tesela + gradientes, o con superficies de pendiente pre-calculadas?*
> 
> **Fecha:** 18 de junio de 2026  
> **Autor:** Análisis geográfico-SIG  
> **Estado:** Análisis fundamentado, recomendaciones con prioridades

---

## Resumen Ejecutivo

**Dos enfoques en competencia:**

| Opción | Almacenamiento | Cálculo en el LCP | Ventaja | Desventaja |
|--------|---|---|---|---|
| **A) Alturas por tesela + gradientes** | DEM nativo (1 raster, ~40 MB) | Calcular gradientes bajo demanda o pre-proceso | Máxima flexibilidad; dirección+magnitud | Costo computacional; dirección innecesaria para tubería |
| **B) Pendientes pre-calculadas** | Raster de pendientes (1 raster, ~40 MB) | Consulta directa en lookup | Rápido; coste directo normalizable | Pierde dirección; requiere curva por tramos coherente |

**Recomendación de este análisis:**

🎯 **Opción B (pendientes pre-calculadas) es la más adecuada para el reto Enagás**, por estas razones:

1. **No necesitas dirección del gradiente:** la tubería es *anisotrópica* respecto a la pendiente, pero *isotrópica* respecto a su dirección en el terreno (igual costo en cualquier azimut mientras la pendiente sea la misma).
2. **Implementación determinista:** la superficie de coste es reproducible; no depende de cálculos en tiempo de búsqueda.
3. **Alineación garantizada:** DEM y pendientes se calculan una sola vez, a rejilla común, al inicio del pipeline.
4. **Coherencia con el modelo:** el modelo de coste especifica una **curva por tramos normativa** (§1.A de este análisis), que requiere umbrales absolutos fijos. Es más fácil implementar con pendientes pre-calculadas.

**Sin embargo**, el **proyecto tiene una deuda técnica:** la pendiente actual se normaliza de forma relativa (al máximo del corredor) en lugar de absoluta (vs. umbrales físicos fijos: 0°, 15°, 30°). Esto hace que el coste de una pendiente de 20° **varíe entre escenarios**, violando reproducibilidad. §6 detalla cómo resolverlo.

---

## 1. Opción A: Alturas por Tesela + Cálculo de Gradientes

### 1.1 Concepto

Se almacena el **DEM nativo** (matriz de elevaciones). En el pipeline, el **motor LCP** calcula en cada paso:
- **Gradientes 2D:** `dh/dx` (E-O) y `dh/dy` (N-S) a partir del DEM.
- **Magnitud de pendiente:** `√((dh/dx)² + (dh/dy)²)` en grados o radines.
- **Dirección (azimut):** `arctan(dh/dy / dh/dx)` (opcional).
- **Coste de la celda:** función de la magnitud y, opcionalmente, de la dirección.

### 1.2 Ventajas

| Ventaja | Descripción | Caso de uso |
|---------|-------------|------------|
| **Máxima flexibilidad** | Derivadas (pendiente, curvatura, aspect) se calculan bajo demanda | Análisis exploratorio; variación de criterios |
| **Dirección disponible** | El azimut del gradiente es información explícita | Infraestructuras direccionales (líneas de tensión, carreteras) |
| **Descubrimiento** | Modificar la función de coste no requiere recalcular DEM | Calibración rápida de pesos y umbrales |

### 1.3 Desventajas

| Desventaja | Descripción | Impacto |
|------------|-------------|--------|
| **Coste computacional** | Calcular gradientes en *cada celda explorada* por el LCP | ~30×40 km, resolución 30 m → ~400k celdas; gradiente 3×3 en cada una = millones de ops |
| **Sensibilidad del algoritmo** | Gradientes discretos (diferencias de celdas contiguas) son ruidosos en DEM suave o con artefactos | Pendientes erráticas en terreno llano → ruido en búsqueda A* |
| **Sin normalización determinista** | Los gradientes se "ven" en tiempo de búsqueda; no hay forma de normalizar previamente contra umbrales fijos | La curva por tramos requiere decisión en vivo |
| **Alineación difícil** | Si se cambia AOI o resolución, hay que recalcular gradientes de nuevo | Ruptura de reproducibilidad entre escenarios |
| **Almacenamiento separado** | DEM + derivadas (aspect, curvatura) crece en número de archivos | No es un problema real (GB, no TB) pero aumenta complejidad |

### 1.4 Implementación Técnica

```python
# En el motor LCP (pseudocódigo):
for cada_celda_en_frontera:
    i, j = celda.coords
    # Ventana 3×3 alrededor de (i, j)
    ventana = dem[i-1:i+2, j-1:j+2]
    
    # Gradientes con Horn o Sobel
    dz_dy, dz_dx = np.gradient(ventana, resolucion_pixel)
    pendiente_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    pendiente_grad = np.degrees(pendiente_rad)
    
    # Azimut (opcional)
    azimut = np.degrees(np.arctan2(dz_dy, dz_dx))
    
    # Función de coste (con curva por tramos)
    coste = f_coste_pendiente(pendiente_grad, azimut)
```

**Algoritmo robusto:** Horn (1981), usado en GDAL, GRASS, QGIS (ver `Copernicus_DEM_Product_Handbook`).

---

## 2. Opción B: Pendientes Pre-Calculadas

### 2.1 Concepto

Se **pre-calcula el raster de pendientes** una sola vez al inicio (fuera del LCP), almacenando coste por celda. El LCP luego **consulta directamente** sin derivadas adicionales.

```
DEM nativo (data/processed/rasters_aoi/dem_aoi.tif)
         ↓ [pre-proceso: scripts/02_pendiente.py]
Raster de pendientes (30 m, EPSG:25830)
         ↓ [curva por tramos + normalización absoluta]
Raster de coste de pendiente (0-1 adimensional)
         ↓ [guardado]
data/processed/rasters_aoi/coste_pendiente.tif
         ↓ [LCP: lectura directa en O(1)]
Coste usado en A*/Dijkstra
```

### 2.2 Ventajas

| Ventaja | Descripción |
|---------|-------------|
| **Determinismo** | Una sola realización de la curva por tramos; no cambia entre ejecuciones |
| **Reproducibilidad** | El coste de una pendiente de 20° es siempre el mismo (no depende de max_pendiente_corredor) |
| **Velocidad** | Lectura de 1 pixel = O(1); no hay cálculo iterativo en tiempo de búsqueda |
| **Alineación garantizada** | DEM + pendiente alineados por construcción; sin sorpresas |
| **Mantenibilidad** | La curva por tramos es editable en un único lugar (§4.1 del modelo de coste) |
| **Traceabilidad** | Auditoría clara: entrada (DEM), transformación (curva), salida (coste); no hay cajas negras en LCP |

### 2.3 Desventajas

| Desventaja | Descripción | Mitigación |
|------------|-------------|-----------|
| **Sin dirección** | El azimut del gradiente no se almacena | Correcto: tubería no es direccional (ver §3) |
| **Calibración lenta** | Cambiar la curva por tramos requiere recalcular todo el raster | Aceptable: decisión de pesos es rara; cambios en perfil sí son frecuentes |
| **Almacenamiento fijo** | Una sola curva por tramos; si quieres dos variantes (p.ej. H₂ vs gas natural), necesitas dos rasters | Solución: versionar escenarios en config; raster se calcula con parámetros |

### 2.4 Implementación Técnica

**Pre-proceso (scripts/02_pendiente.py — **actual, pero defectuoso**):**

```python
# Leer DEM alineado
dem = rioxarray.open_rasterio("dem_aoi.tif")

# Gradientes (Horn sería mejor, pero np.gradient es aceptable aquí)
dz_dy, dz_dx = np.gradient(dem.values[0], resolucion_y, resolucion_x)
pendiente_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
pendiente_grados = np.degrees(pendiente_rad)

# **CORRECCIÓN necesaria: curva por tramos + normalización ABSOLUTA**
def mapeo_coste_pendiente(pend_grados):
    """Mapeo normativo del modelo de coste (§4.1 modelo_coste.md)."""
    if pend_grados < 5:
        return 0.0
    elif pend_grados < 15:
        # Rampa lineal 5°→0, 15°→0.6
        return 0.6 * (pend_grados - 5) / 10
    elif pend_grados < 30:
        # Rampa lineal 15°→0.6, 30°→1.0
        return 0.6 + 0.4 * (pend_grados - 15) / 15
    else:
        # Barrera dura: intransitable
        return np.inf

coste_pendiente = np.vectorize(mapeo_coste_pendiente)(pendiente_grados)

# Guardar
coste_xr = xr.DataArray(coste_pendiente, coords=dem.coords, dims=dem.dims)
coste_xr.rio.to_raster("coste_pendiente_aoi.tif")
```

**Motor LCP (acceso directo):**

```python
# En A*/Dijkstra:
coste_celda_actual = coste_pendiente[i, j]  # ← O(1), directo
```

---

## 3. ¿Necesitas Dirección del Gradiente?

### 3.1 La Pregunta

Tu formulación: *"¿De la pendiente tendríamos que saber la dirección no?"*

### 3.2 Respuesta Corregida

**Sí, tienes razón.** La dirección **sí influye** en la pendiente efectiva. Tu ejemplo es correcto:

```
Tesela: pendiente de 5° de norte a sur (aspecto = norte)

Si tubería va de NORTE a SUR: pendiente efectiva = 5°
Si tubería va de ESTE a OESTE: pendiente efectiva = 0° (perpendicular al gradiente)
Si tubería va diagonal: pendiente efectiva = 5° × cos(ángulo)
```

Esto es **anisotropía real**, no una sutileza matemática.

#### A) Definiciones

- **Magnitud de pendiente:** `|∇h|` = raíz cuadrada de la suma de gradientes en X e Y. Es la **inclinación global** del terreno.
- **Dirección (aspecto/azimut):** `arctan(∂h/∂y / ∂h/∂x)` = **brújula a la que apunta la máxima pendiente**.
- **Pendiente efectiva:** `|∇h| × cos(ángulo_relativo)` = la pendiente que la tubería "siente" en su dirección de avance.

Ejemplo en 2D (malla de terreno):
```
Altura:  10m      8m      5m      (bajada hacia el oeste)
         |        |       |
Pendiente: 2m/30m (rampa suave, aspecto oeste)

- Tubería O→E: pendiente efectiva = 0° (perpendicular)
- Tubería N→S: pendiente efectiva ≈ 0.5° (casi perpendicular)
- Tubería O→E (como gradiente): pendiente efectiva = 5° (paralela)
```

#### B) ¿Cuándo sí necesitas dirección?

| Infraestructura | ¿Dirección importa? | Por qué |
|---|---|---|
| **Línea de transmisión eléctrica** | ✅ SÍ | Anisotropía: "pasar entre dos torres" tiene coste distinto según si subes o bajas |
| **Carretera (vehículos)** | ✅ SÍ | Coches no suben igual que bajan (combustible, seguridad) |
| **Alcantarilla/desagüe** | ✅ SÍ | La gravedad apunta en una dirección; el flujo sigue esa dirección |
| **Tubería de H₂** | ✅ **SÍ** | **La pendiente efectiva depende de la dirección de avance** (ver arriba) |

#### C) Entonces, ¿por qué aún recomendamos ignorar la dirección (por ahora)?

No es que no importe en la *física*, sino que presenta **dos problemas prácticos** en MVP 1-4:

**Problema 1: Chicken-and-egg del LCP**

El algoritmo de camino de mínimo coste no sabe la dirección de la ruta hasta que termina. El coste es lo que *determina* la dirección. Implementar pendiente efectiva requeriría:

```python
Para cada celda (i, j) en la frontera de búsqueda:
  - ¿De dónde vienes? (celda anterior)
  - ¿Hacia dónde vas? (celda candidata)
  - Calcula pendiente relativa a esa dirección
  - Asigna coste
```

Esto es lo que hace **`r.walk` de GRASS** (Opción F), pero requiere reformular el LCP como **grafo direccional con costes en las aristas** (no solo en los nodos). Es más complejo que A*/Dijkstra estándar.

**Problema 2: Escala de la rejilla**

Con resolución de 30m, cada celda representa un polígono de 30×30m. Dentro de esa celda, la tubería puede entrar y salir en múltiples ángulos. La pendiente media/máxima dentro de esa celda es una aproximación, pero **la dirección relativa exacta es difusa** a esa escala. A resoluciones mayores (50m, 100m), el error es aún mayor.

**Conclusión:** La dirección **sí importa en la física**, pero **ignorarla en MVP 1-4 es un trade-off entre realismo (95%) y complejidad (medio-alto)**. Equivalente a usar pendiente isotrópica (~70% realismo, baja complejidad) con posibilidad de mejorar después.

---

## 4. Otras Opciones que se te Podrían Haber Pasado

Más allá de A (alturas) y B (pendientes), aquí hay variantes y alternativas que el equipo podría considerar:

### Opción C: Costes Anisótropos (Pendiente + Dirección)

**Concepto:** La tubería pesa diferente al subir que al bajar. La pendiente cuesta más si *subes* que si *bajas*.

```
coste = {
  si ∇h apunta en mi dirección (cuesta arriba):  magnitud_alta
  si ∇h apunta opuesta (cuesta abajo):            magnitud_baja
}
```

**Ventaja:** Modelaría realismo de obra (más caro excavar contra gravedad).

**Desventaja:**
- Complejidad alta: requiere reformular LCP como grafo direccional (r.walk en lugar de A*/Dijkstra).
- Costo computacional mayor (~3-5× más lento).
- A resolución 30m, la dirección relativa exacta es difusa dentro de cada celda.

**Recomendación:** **Viable pero posponer para MVP 1-4.** Mantener isotrópico en MVP 1-3. Si el backtesting (MVP 4/6) muestra desviaciones sistemáticas (p.ej. rutas reales evitan pendientes suaves), reconsiderar para MVP 5-8 usando `r.walk` de GRASS o implementación propia.

---

### Opción D: Terreno Roto (Variabilidad Local de Pendientes)

**Concepto:** No solo la pendiente de la celda, sino cuánto *varía* la pendiente alrededor. Detecta:
- Fondos de valle (abrupto)
- Crestas (abrupto)
- Llanuras suaves (homogéneo)

**Métodos:**

| Métodos | Cálculo | Detecta |
|---|---|---|
| **(i) Máximo en ventana 5×5** | `max(pendiente[i-2:i+3, j-2:j+3])` | Un pico cercano (fragante) |
| **(ii) Desv. Est. en ventana 5×5** (recomendado) | `std(pendiente[i-2:i+3, j-2:j+3])` | Variabilidad: abrupto = alto σ |
| **(iii) Gradiente de gradientes** | `∂²h/∂x² + ∂²h/∂y²` (curvatura) | Transiciones bruscas (2ª derivada) |

**Uso en modelo de coste:** Capa separada con peso pequeño (p.ej. 10% del peso de pendiente).

```
coste_total = w_pendiente × coste_pendiente 
            + w_terreno_roto × coste_terreno_roto
            + w_uso_suelo × coste_uso_suelo
            + ...
```

**Ventaja:** Captura dificultad adicional de obra en terreno quebrado.

**Desventaja:** Añade complejidad; requiere decisión de parámetros (tamaño de ventana, peso).

**Recomendación para MVP:** **Posponer.** El modelo actual sin terreno roto ya ofrece diferenciación entre rutas. Si MVP 1-4 sale bien y sobra tiempo, añadir como mejora. El script está listo pero sin integración.

---

### Opción E: Curvatura Gauss (Cambio de Aspecto Local)

**Concepto:** Detecta si el terreno es "abovedado" (curvo hacia arriba) o "deprimido" (curvo hacia abajo). Más sofisticado que desv. est.

**Cálculo:** Curvatura de Gauss = `(∂²h/∂x²) × (∂²h/∂y²) - (∂²h/∂x∂y)²`

**Uso:** Modificar coste local (fuerte curvatura → difícil excavación).

**Recomendación:** **Descartar por ahora.** Es tercera derivada; ruido en datos de 30m. Mantenerlo como idea para futuro (MVP 6-8).

---

### Opción F: "Coste de transición" (Cost-Distance Anisotrópica, r.walk de GRASS)

**Concepto:** No es solo el coste de *estar* en una celda, sino el coste de *mover* desde una celda a otra, considerando dirección relativa.

Formulación:
```
coste_transicion(A → B) = f(h_A, h_B, dirección_A_B)
```

**Ejemplo GRASS `r.walk`:** Usa "friction" isotrópica (sin dirección) pero velocidad de recorrido anisotrópica.

**Ventaja:** Muy realista; captura que cuesta distinto subir +2m que bajar -2m.

**Desventaja:**
- Complejidad alta; requiere reformular el LCP (no es A* sino cálculo de distancia de fricción).
- Necesita dos cestas: coste de salida + coste de llegada.
- Bibliotecas Python limitadas (GRASS sí lo hace, `scipy.sparse` no).

**Recomendación:** **Muy interesante para MVP 5-8 (pre-ingeniería avanzada).** Para MVP 1-4 es overkill. Mantener en backlog.

---

### Opción G: Equivalencia "Energy"—Tobler & Vertical Equivalence Distance

**Concepto:** Convertir pendiente en "distancia equivalente horizontal" más cara. Formulación histórica de Tobler (1993):

```
v = 6 × exp(-3.5 × |pendiente + 0.05|)  [km/h a pie]
tiempo_celda = resolucion_m / (v × 1000 / 3600)
```

**Uso:** En lugar de coste abstracto, usar "distancia equivalente horizontal" (más intuitiva).

**Ventaja:** Muy usada en ecología de paisaje y modelos de viaje a pie.

**Desventaja:**
- Calibrada para **caminante humano**, no para obra de tubería.
- Pierde la curva por tramos especificada en modelo de coste.

**Recomendación:** **Descartar.** No es relevante para ingeniería de tuberías. Mantener solo como curiosidad científica.

---

## 5. Matriz de Decisión: Comparativa de Todas las Opciones

| Opción | Determinismo | Velocidad | Reproducibilidad | Complejidad | Implementación | Para MVP 1-4 |
|--------|---|---|---|---|---|---|
| **A) Alturas + gradientes bajo demanda** | ⚠️ Ruidoso | ❌ Lento (~10-100s/búsqueda) | ❌ Depende ejecución | Media | 3-4 semanas | ❌ No |
| **B) Pendientes pre-calc isotrópicas** | ✅ Determinista | ✅ Rápido (< 1s) | ✅ 100% reproducible | Baja | 1-2 semanas | ✅ **RECOMENDADO** |
| **C) Anisotropía (dirección-relativa, r.walk)** | ✅ Determinista | ⚠️ Lento (3-5× B) | ✅ Reproducible | Media-Alta | 3-4 semanas | ⚠️ **Viable-opcional** |
| **D) Terreno roto (std ventana)** | ✅ Determinista | ✅ Rápido | ✅ Reproducible | Baja | 1 semana | ⚠️ Posponer |
| **E) Curvatura Gauss** | ⚠️ Ruidosa | ✅ Rápido | ⚠️ Inestable | Alta | 3-4 semanas | ❌ No |
| **F) r.walk (fricción anisotrópica mejorada)** | ✅ Determinista | ❌ Muy lento | ✅ Reproducible | **Muy alta** | 4-6 semanas | ❌ Futuro |
| **G) Tobler (distancia equiv.)** | ✅ Determinista | ✅ Rápido | ✅ Reproducible | Baja | 1-2 semanas | ❌ No (fuera de dominio) |

---

## 6. Recomendaciones para el Grupo

### 6.1 Corto Plazo (Hito 2: Trazado Base MVP) — **PRIORITARIO**

🎯 **Usar Opción B (pendientes pre-calculadas)** con estas acciones:

**Acción 1: Arreglar la normalización actual** (deuda técnica crítica)

El código actual en `scripts/02_pendiente.py` normaliza al máximo de pendiente del corredor:

```python
# ❌ INCORRECTO (actual):
coste_pendiente = pendiente_grados / pendiente_grados.max()

# ✅ CORRECTO (propuesto):
def mapeo_coste_pendiente(pend_grados):
    if pend_grados < 5:
        return 0.0
    elif pend_grados < 15:
        return 0.6 * (pend_grados - 5) / 10
    elif pend_grados < 30:
        return 0.6 + 0.4 * (pend_grados - 15) / 15
    else:
        return np.inf

coste_pendiente = np.vectorize(mapeo_coste_pendiente)(pendiente_grados)
```

**Por qué:** Sin esto, el coste de una pendiente de 20° **varía entre escenarios** (dependiendo de si hay un pico a 45° en otra zona). Viola reproducibilidad y hace que el backtesting sea imposible.

**Estimación:** 2-4 horas de implementación + testing.

---

**Acción 2: Considerar usar Horn en lugar de np.gradient** (mejora, no bloqueador)

Horn (1981) es más robusto frente a ruido de DEM. Pero `np.gradient` es aceptable para una primera iteración. Decidir:
- Si presupuesto permite: implementar Horn vía `richdem` o GDAL (mejor prácticas).
- Si no: mantener `np.gradient` y anotar como **deuda técnica para MVP 5-6**.

---

**Acción 3: Documentar la curva en perfiles.yaml**

```yaml
perfiles:
  tecnico:
    pesos:
      pendiente: 0.4         # 40% del coste
      uso_suelo: 0.3
      cruces: 0.3
      
  ambiental:
    pesos:
      pendiente: 0.1         # Solo 10%
      natura2000: 0.5        # 50% ambiental
      uso_suelo: 0.4

# NUEVO: parámetros de la curva por tramos (normativa)
parametros_pendiente:
  rango1_max_grados: 5      # 0-5°: coste 0
  rango2_max_grados: 15     # 5-15°: rampa lineal
  rango2_coste_final: 0.6
  rango3_max_grados: 30     # 15-30°: rampa lineal
  rango3_coste_final: 1.0
  barrera_dura_grados: 30   # >30°: ∞ (intransitable)
```

---

### 6.2 Decisiones que Pueden Activar Anisotropía (Opción C): Cuándo Reconsiderar

**A) Durante backtesting (MVP 4/6):**

Si proporcionan un ramal real y el modelo isotrópico (Opción B) lo encuentra pero **sistemáticamente desplazado** hacia las pendientes menores, eso sugiere que la anisotropía (dirección relativa) es importante. Señales de alerta:

- La ruta real sube/baja pendientes a propósito en ciertas direcciones.
- El modelo isotrópico penaliza más los tramos que suben que los que bajan (o viceversa).
- El índice de acierto del backtesting cae por debajo del 70% cuando debería estar > 85%.

**B) Si Enagás lo solicita explícitamente:**

- *"Necesitamos que el modelo capture el coste diferente de subida vs bajada (realismo de obra)"* → Implementar Opción C con `r.walk` de GRASS o implementación propia.

**C) Si sobra presupuesto en MVP 1-4:**

Opción C es **factible en 3-4 semanas** si hay recursos. No es trivial pero tampoco bloqueador.

**Recomendación:** Mantener **Opción B para MVP 1-3** (rápido, determinista, cumple requisitos). Evaluar necesidad de Opción C en MVP 4 (backtesting).

---

### 6.3 Medio Plazo (Hito 3-4: Alternativas + Comparativa)

Mantener Opción B sin cambios. Usar la curva fija documentada en todos los perfiles.

**Opciones adicionales que pueden sumarse sin cambiar B:**

- **Opción D (terreno roto):** Si MVP 1-3 sale bien y sobra tiempo, es ganancia rápida (1 semana). Recomendable.
- Otros: descartar por ahora.

---

### 6.4 Largo Plazo (MVP 5-8: Pre-ingeniería)

**Opción C (anisotropía con r.walk)** pasa a ser **recomendada** si el backtesting falla o Enagás lo pide. Los otros (D, E, F, G) siguen siendo opcionales o descartables.

---

## 7. Checklist Técnico (Antes de Hito 2)

- [ ] Normalización de pendiente **pasada a absoluta** (curva por tramos con umbrales fijos)
- [ ] Barrera dura a 30° implementada (`np.inf` para pendiente > 30°)
- [ ] Parámetros documentados en `perfiles.yaml` y código comentado
- [ ] Tests: verificar que `coste_pendiente(20°)` es **siempre 0.8**, no depende de otros píxeles
- [ ] Raster de coste_pendiente guardado y versionado (reproducibilidad)
- [ ] Verificación: dos ejecuciones con mismo AOI producen **idéntica superficie de coste**

---

## 8. Análisis de Fuentes y Referencias

**Fundamentación de la propuesta:**

1. **Horn, B. K. P. (1981).** "Hill Shading and the Reflectance Map." *Proc. IEEE*. Clásico; algoritmo robusto para cálculo de pendiente desde DEM.
   - ✅ Disponible en `docs/referencias_sig/Horn_1981_Hill-Shading...pdf`

2. **Olaya, V. (2014).** *Sistemas de Información Geográfica* (Manual completo en español).
   - ✅ Disponible en `docs/referencias_sig/Libro_SIG.pdf` §§ Modelado de costes, LCP.

3. **Copernicus DEM Product Handbook (v5.0, 2024).**
   - ✅ Disponible en `docs/referencias_sig/Copernicus_DEM...pdf`
   - Recomendaciones de procesamiento, cuidados con artefactos de DEM.

4. **Da Silva & Cardozo (2015).** "Evaluación multicriterio y sistemas de información" (caso de estudio EMC+SIG).
   - ✅ Disponible en `docs/referencias_sig/evaluacion-multicriterio...pdf`

5. **Etherington, T. R. (2012-2013).** Mínimo coste en grafos irregulares y errores de alineación en rejillas raster.
   - ✅ Referencia verificada en `docs/referencias_sig/biblioteca_sig.md`

---

## 9. Conclusión

**La mejor opción para MVP 1-4 del Reto Enagás es Opción B: Pendientes pre-calculadas (isotrópicas).**

Con esta aclaración importante: **Tu pregunta era correcta.** La dirección del gradiente **sí influye** en la pendiente efectiva. La tubería "siente" distinta pendiente según su ángulo de avance. Pero es un trade-off:

| Aspecto | Opción B (Isotrópica) | Opción C (Anisotrópica) |
|--------|---|---|
| **Realismo** | ~70% | ~95% |
| **Velocidad LCP** | < 1s | 3-5s |
| **Complejidad** | Baja | Media-Alta (r.walk) |
| **Apto MVP 1-4** | ✅ **SÍ** | ⚠️ Viable si sobra presupuesto |
| **Para backtesting** | ⚠️ Limitado | ✅ Mejor si falla B |

**Razones para B en MVP 1-4:**
1. ✅ Determinismo y reproducibilidad garantizados.
2. ✅ Velocidad de búsqueda (crítica en rejilla densa de 30m, 400k+ celdas).
3. ✅ Alineación automática con el DEM.
4. ✅ Consonancia directa con el modelo de coste normativo.
5. ✅ Si el backtesting falla, puedes mejorar a C en MVP 5-8 sin rehacer todo.

**Acción inmediata:** Arreglar la normalización actual de pendiente (pasar de relativa a absoluta). Esto es **bloqueador de Hito 2**. 

**Decisión a tomar en MVP 4 (backtesting):** Si proporcionan un ramal real y B produce desviaciones sistemáticas, investiga migrar a Opción C (r.walk anisotrópico). No es demasiado tarde para cambiar.

---

**Documento redactado:** 18 de junio de 2026  
**Revisión:** Corregido 18 jun 2026 — Dirección **sí importa**, es un trade-off de complejidad  
**Próximas revisiones:** Tras implementación de correcciones de Hito 2 y backtesting (MVP 4)
