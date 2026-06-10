# Generación automatizada de trazados de ramales de H₂

Prototipo del Grupo 6 (CI2 Lab 2026, reto Enagás). Dado un origen (planta de H₂), un destino (conexión a red troncal) y un AOI, genera **3-5 trazados alternativos diferenciados** sobre GIS público y los compara por longitud, coste relativo, cruces, km en zona protegida/urbana y pendiente.

> Contexto del reto: [`../docs/reto6_enagas.md`](../docs/reto6_enagas.md) · Arquitectura: [`arquitectura.md`](arquitectura.md)

## Requisitos

- Python 3.11+
- Dependencias geoespaciales (rasterio, geopandas, shapely, pyproj…). En Windows puede ser más cómodo instalarlas con **conda** (canal `conda-forge`) que con `pip`.
- Acceso a las capas GIS públicas (ver [`data/raw/FUENTES.md`](data/raw/FUENTES.md)). Si alguna descarga requiere clave, configúrala en `.env`.

## Puesta en marcha

```bash
# 1. Crear y activar entorno virtual
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt
# (alternativa recomendada en Windows: conda create -n ramales -c conda-forge --file requirements.txt)

# 3. Configurar variables de entorno (si alguna descarga requiere clave)
copy .env.example .env      # Windows
# cp .env.example .env       # macOS/Linux

# 4. Definir el caso de estudio en data/config/ (AOI, origen, destino, perfiles)
#    y registrar las capas en data/raw/FUENTES.md
```

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
