# Auditoría del workspace — 13 de julio de 2026

> Auditoría de solo lectura del workspace completo (raíz, `docs/`, `formacion/`, `coordinacion/`, `proyecto/`)
> a 4 días de la **presentación final con demo en vivo (viernes 17-jul)**. Todos los hallazgos están
> verificados leyendo código o ejecutándolo; ninguno es especulativo. Severidad según riesgo para la demo:
> **[CRÍTICO]** rompe la demo o da un dato falso · **[ALTO]** error real con workaround · **[MEDIO]** deuda/mejora · **[BAJO]** cosmético.

## Resumen ejecutivo

El proyecto está en buen estado para la demo: la app arranca (HTTP 200), los 3 tests pasan, todas las
llamadas de red tienen timeout, no hay claves de widget duplicadas, la convención «coste relativo, nunca €»
se cumple en todo el código y no hay ficheros generados colados en git. **No se ha encontrado ningún
hallazgo crítico.** Los dos hallazgos serios son: (1) una **contradicción de entornos** — toda la
documentación y el tooling apuntan a `proyecto/.venv` (Python 3.10, requirements pineados), pero ese
entorno **no existe** en la máquina de la demo y todo corre sobre el `.venv` de la raíz («deprecado» según
el propio README) con Python 3.14.5 y 10 paquetes en versiones distintas a las pineadas; y (2) la **caché
del ZIP de descarga de rutas** no detecta regeneraciones (mismo bug ya corregido en el informe PDF).
Además, `estado.md` está una semana desactualizado y hay 14 enlaces markdown rotos. Al final: 6 quick wins
de <30 min aplicables antes del viernes.

## Tabla de hallazgos

| Sev. | Fichero:línea | Hallazgo | Propuesta mínima |
|------|---------------|----------|------------------|
| **ALTO** | `proyecto/README.md:43` · `proyecto/setup.ps1:11` · `.vscode/settings.json:4` · `proyecto/.python-version` | **Doble verdad de entornos.** README, setup, VS Code y el hook post-merge apuntan a `proyecto/.venv` (Python 3.10 + requirements pineados) y declaran «deprecado» el `.venv` de la raíz. Verificado: `proyecto/.venv` **no existe**; todo (app, tests, pipeline) corre en el `.venv` raíz con **Python 3.14.5**. Contra `requirements.txt`: 10 paquetes en versión distinta (p. ej. `pandas 3.0.3` vs `2.3.3` pineado, `numpy 2.5.0` vs `2.2.6`, `rasterio 1.5.0` vs `1.4.4`) y 5 pineados ausentes (`ruff`, `pytz`… `pytest` faltaba y se instaló pineado durante esta auditoría para poder ejecutar la suite). | **Antes del viernes: no tocar el entorno del portátil de la demo** (funciona y está probado). Riesgo real: que alguien «arregle» el entorno el jueves ejecutando `setup.ps1` (estrenaría un venv 3.10 nunca probado con el código actual) o que la demo se haga desde otro portátil tras un setup limpio. Congelar la decisión por escrito (aviso en README). Tras la demo: elegir UNA verdad — o `pip freeze` desde el venv real y actualizar README/setup/.vscode, o validar de verdad `proyecto/.venv` 3.10. |
| **ALTO** | `proyecto/src/app/streamlit_app.py:3383` | **ZIP de rutas obsoleto.** La firma de `_zip_rutas_cache` es solo `tuple((s, perfil))` — nombres, sin mtimes. Si en la misma sesión se regeneran las rutas de los mismos escenarios/perfiles (p. ej. tras mover coordenadas y reprocesar), «Descargar rutas (.gpkg)» sirve el ZIP viejo de la caché de sesión. Es la misma clase de bug que ya se corrigió en el informe PDF (`_firma_pdf_informe` sí incluye mtimes). | Añadir los `st_mtime` de cada `.gpkg` a la firma, espejo del fix del PDF (~10 min). |
| **MEDIO** | `estado.md:3,50` | **Estado desactualizado.** «Última actualización: 2026-07-08»; la bitácora tiene S6 «🟡 En curso» (venció el 10-jul) y S7 sin abrir, y el semáforo no recoge lo entregado desde el 8-jul: informe PDF por escenario, validación de puntos en el mar, catastro provincial de la Sede (ZIP multiparte), catastro foral Navarra/País Vasco, limpieza de escenarios efímeros. El propio fichero exige actualización al cierre de cada sprint. | Cerrar S6, abrir S7 y refrescar el párrafo de «Código» del semáforo (~15 min). |
| **MEDIO** | `proyecto/tests/` | **Cobertura mínima.** Un solo fichero (`test_common_transform.py`, 3 tests, pasan) que cubre la transformación de coordenadas. Nada de métricas, diferenciación de rutas ni contratos de nombres de fichero, pese a que `proyecto/CLAUDE.md` pide «priorizar alineación de rasters y métricas». | No montar una suite a 4 días de la demo. Si acaso, un smoke test que verifique los contratos de nombres (`superficie_{s}_{p}.tif`, `ruta_{s}_{p}.gpkg`) contra los datos existentes. Dejar el resto como deuda para la hoja de ruta. |
| **MEDIO** | 14 enlaces markdown rotos | Ver sección «Documentación desactualizada» — la mayoría en documentos heredados de otro workspace. | Arreglar los 4 de `geografo-gis.md` (rutas relativas mal); anotar los heredados. |
| **BAJO** | `proyecto/src/ingesta/alinear_capas.py:376` | Comentario obsoleto: «…no proviene de la descarga automática (RN2000, Catastro… se colocan a mano y no tienen manifiesto)». Contradice el propio código 30 líneas más arriba (`_SCENARIO_FILES:92` incluye `RN2000_{s}.gpkg` como automática) y `FUENTES.md:15` (RN2000 automática desde el 09-jul). | Reescribir el paréntesis: solo el Catastro de régimen común es manual (2 min). |
| **BAJO** | `proyecto/src/metricas/cruces.py:17` | El ejemplo de uso del docstring (`from src.metricas.cruces import…`) solo funciona con cwd=`proyecto/`; desde la app (que mete `src/` en `sys.path`) fallaría. Es el único `from src.` sin contexto de los 7 revisados — los otros 6 tienen fallback `try/except ImportError` correcto. | Cambiar el ejemplo a `from metricas.cruces import…` o anotar el contexto (2 min). |
| **BAJO** | `proyecto/src/agents/geografo-gis.md:33-36` | Los 4 enlaces relativos están mal calculados desde su ubicación (`docs/reto6_enagas.md` → debería ser `../../../docs/reto6_enagas.md`, etc.). Los destinos SÍ existen (incluido `docs/glosario.md`). | Corregir las 4 rutas relativas (5 min). |

## Ficheros redundantes u obsoletos

- **`transferencia.md` (raíz)** — *blueprint* histórico para montar este workspace a partir del del Grupo 5.
  Ya cumplió su función; sus enlaces (`docs/reto5_enagas.md`) apuntan a ficheros del otro workspace y están
  rotos aquí. No estorba, pero es el candidato natural a archivar (p. ej. `docs/` con nota de histórico) —
  decisión del equipo, no urge.
- **`docs/Descripcion_CI2_Lab.md`** — copiado del workspace general de la iniciativa: 7 de sus enlaces
  (`call_for_challenges/`, `alumnos_candidatos/`, `estado.md` relativo a docs/) no existen en este repo.
  El contenido sigue siendo útil como contexto; solo los enlaces son basura heredada.
- **`proyecto/src/comparacion/comparador.py` y `proyecto/src/app/cli.py`** — verificado: siguen siendo
  esqueletos y **nada los importa** (grep de usos reales: 0 imports; solo una mención en un docstring de
  `calculo.py`). NO son redundantes: están documentados como pendientes del Sprint 7 en `proyecto/CLAUDE.md`
  y `estado.md`, y encajan como «hoja de ruta» en la presentación. Coherentes — no tocar.
- **Git limpio** — verificado `git ls-files` contra los `.gitignore`: no hay `.qml`, logs, rasters, capas ni
  `__pycache__` versionados. Los únicos binarios son legítimos: `Logo.png` (asset), `img/coste_ramal_[AB].png`
  (los usa `presentacion-intermedia-2026-06-22.html`) y `espana_tierra_25830.geojson` (asset con su excepción).

## Documentación desactualizada (texto actual vs. realidad)

| Dónde | Dice | Realidad |
|-------|------|----------|
| `proyecto/README.md:9,43` · `proyecto/CLAUDE.md:46` · `.python-version` | «Python 3.10 … el entorno oficial es `proyecto/.venv` … si tienes un `.venv` en la raíz, bórralo» | `proyecto/.venv` no existe; todo corre en el `.venv` raíz con Python 3.14.5 (ver hallazgo ALTO). |
| `estado.md:3` | «Última actualización: 2026-07-08», S6 en curso | Es S7; lo entregado del 9 al 13-jul no aparece. |
| `alinear_capas.py:376` | RN2000 «se coloca a mano» | Descarga automática desde PR #80 (el mapa `_SCENARIO_FILES` del mismo fichero ya lo refleja). |
| `docs/hitos_mvp.md:3` | Enlaza `Reto6 - Resumen_Objetivos.pdf` | El PDF no está versionado en el repo (probablemente intencional por tamaño; si es así, convertir en texto plano sin enlace). |

**Documentación verificada como AL DÍA** (para no repasarla el jueves): `FUENTES.md` (incluye RN2000
automática, catastro foral 13-jul), `check_entorno.py` (incluye reportlab y pytest, avisa si Python ≠ 3.10),
docstrings de `informe.py` (organización por escenario), `convertir_catastro.py` (los 3 formatos, incluido el
paquete provincial multiparte) y `preparar_escenario.py`. Los árboles de carpetas de ambos `CLAUDE.md`
citan solo ficheros existentes.

## Verificaciones positivas (ejecutadas hoy)

- Suite de tests: **3/3 pasan** (6,4 s) con el venv real.
- La app arranca y responde (HTTP 200) tras el arranque con limpieza de efímeros.
- **Cero** llamadas de red sin `timeout` (revisados `descargar_capas.py`, `catastro_foral.py` y los 3
  `urlopen` de la app: 6–120 s). El catastro foral es best-effort con `try/except` que nunca tumba la descarga.
- Imports de doble prefijo: los 7 `from src.` del código tienen fallback `ImportError` (el único sin él es un
  ejemplo de docstring, ver [BAJO]).
- Sin claves de widget de Streamlit duplicadas (grep de `key="…"`).
- Convención «nunca €»: las únicas menciones a € en `src/` son comentarios que refuerzan la regla.
- La limpieza de escenarios efímeros (`_restaurar_escenarios_fabrica`) se revisó contra colisiones de
  prefijos de id y patrones glob: los patrones exigen `_{sid}.` o `ruta_{sid}_` literales y los ids
  normalizados no pueden colisionar con sufijos de perfil ni con A/B (probado además con test real el 11-jul).

## Quick wins (<30 min cada uno, aplicables antes del viernes)

1. **Firma con mtimes en `_zip_rutas_cache`** (`streamlit_app.py:3383`) — espejo del fix del PDF. ~10 min.
2. **Aviso de entorno en `proyecto/README.md`**: una línea «⚠️ hasta después de la demo del 17-jul, el
   entorno validado es el `.venv` de la raíz (Python 3.14); NO ejecutar `setup.ps1` en el portátil de la
   demo». Evita el peor escenario del hallazgo ALTO. ~5 min.
3. **Actualizar `estado.md`**: cerrar S6, abrir S7, refrescar semáforo con lo entregado 9–13 jul. ~15 min.
4. **Comentario RN2000** en `alinear_capas.py:376`. ~2 min.
5. **Rutas relativas de `geografo-gis.md`** (4 enlaces). ~5 min.
6. **Ensayo completo de la demo** con el escenario elegido, en el portátil de la demo y con su red, cronometrado
   — no es un fix pero es el mejor «test» disponible; cualquier fallo que aparezca el miércoles aún tiene arreglo.

---
*Auditoría realizada el 13-jul-2026 sobre `main` (`7f8603d`). Único cambio en disco durante la auditoría:
instalación de `pytest==9.1.1` (versión exacta pineada en `requirements.txt`) en el `.venv` raíz para poder
ejecutar la suite.*
