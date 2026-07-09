# Generación automatizada de trazados

Prototipo del Grupo 6 (CI2 Lab 2026, reto Enagás). Dado un origen, un destino y un AOI, genera **3-5 trazados alternativos diferenciados** sobre GIS público y los compara por longitud, coste relativo, cruces, km en zona protegida/urbana y pendiente.

> Contexto del reto: [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md) · Arquitectura: [`arquitectura.md`](arquitectura.md)

## Requisitos

- **Python 3.10** (versión del entorno validado; ver [`.python-version`](.python-version)). Las versiones de `requirements.txt` están congeladas contra 3.10 — con otro Python la instalación puede diferir.
- Dependencias geoespaciales (rasterio, geopandas, shapely, pyproj…). Se instalan con `pip` desde [`requirements.txt`](requirements.txt); si en Windows algún paquete geoespacial fallara, la alternativa es **conda** (canal `conda-forge`).
- Acceso a las capas GIS públicas (ver [`data/raw/FUENTES.md`](data/raw/FUENTES.md)). Si alguna descarga requiere clave, configúrala en `.env`.

## Puesta en marcha

Un solo comando, desde la carpeta `proyecto/`. Crea el entorno virtual `proyecto/.venv`, instala las versiones exactas de `requirements.txt` y verifica que todas las dependencias importan (OK/FALTA):

```powershell
# Windows (PowerShell)
.\setup.ps1
# si PowerShell bloquea el script por política de ejecución:
# powershell -ExecutionPolicy Bypass -File setup.ps1
```

```bash
# macOS/Linux
bash setup.sh
```

Repítelo tras cada `git pull`: es idempotente y deja el entorno igual que el del resto del equipo. Para comprobar el entorno en cualquier momento sin instalar nada:

```powershell
.venv\Scripts\python.exe check_entorno.py
```

Después, si alguna descarga requiere clave:

```bash
copy .env.example .env      # Windows  (cp en macOS/Linux)
```

Y define el caso de estudio en `data/config/` (AOI, origen, destino, perfiles), registrando las capas en `data/raw/FUENTES.md`.

> **Un único entorno:** el entorno oficial es **`proyecto/.venv`** (el que crean los scripts). Si tienes un `.venv` en la **raíz del repositorio**, no se usa y conviene borrarlo para no confundir al IDE.

### Todo esto es automático si usas VS Code

El repositorio incluye configuración compartida que hace el setup por ti:

- **Intérprete:** `.vscode/settings.json` fija `proyecto/.venv` como intérprete por defecto del workspace. (Si en algún momento seleccionaste otro a mano, cámbialo una vez con `Ctrl+Shift+P → Python: Select Interpreter → proyecto/.venv`; a partir de ahí se queda.)
- **Setup al abrir:** `.vscode/tasks.json` ejecuta `setup.ps1`/`setup.sh` automáticamente al abrir la carpeta. La **primera vez** VS Code pregunta *"Allow Automatic Tasks?"* → responde **Allow**. Desde entonces, abrir VS Code tras un `git pull` deja el entorno al día sin hacer nada.
- **Actualización tras cada pull:** el hook versionado [`.githooks/post-merge`](../.githooks/post-merge) (activado por el propio setup) detecta si un `git pull` cambió `requirements.txt` y reinstala el entorno al momento, incluso con VS Code ya abierto.

## Flujo de trabajo (a medida que se implemente)

1. **Ingesta:** descargar/recortar las capas de `data/raw/` al AOI, reproyectar a EPSG:25830 y alinear a la rejilla común → `data/processed/`.
2. **Superficies de coste:** combinar las capas con pesos por perfil de prioridad.
3. **Trazados:** calcular el LCP por perfil y diferenciar las rutas (corridor masking).
4. **Métricas + comparativa:** medir cada ruta y presentar tabla + mapa (CLI o Streamlit).

> Los comandos concretos (`python -m src.app …`) se documentarán aquí según se implementen los módulos.

## Estructura

Ver [`CLAUDE.md`](CLAUDE.md) para el árbol completo y las convenciones.

## Reglas no negociables

- Toda capa usada debe estar **alineada** (mismo CRS EPSG:25830 y misma rejilla) antes de combinarse.
- Las rutas presentadas deben ser **demostrablemente diferenciadas**, no el mismo corredor con ruido.
- Todo coste es **relativo (índice)**, nunca en €.
- Las claves de descarga (si las hay) van solo en `.env` (nunca se versiona).
