# Notebooks

Exploración geoespacial y ejercicios de formación. Nombrado: `NN_tema.ipynb` (p.ej. `01_dem_pendiente.ipynb`).

Sugeridos:
- `01_dem_pendiente.ipynb` — descargar un DEM, reproyectar a EPSG:25830 y derivar la pendiente.
- `02_alineacion_capas.ipynb` — reproyectar y remuestrear dos capas a una rejilla común y superponerlas.
- `03_superficie_coste.ipynb` — combinar pendiente + uso de suelo con pesos en una superficie de coste.
- `04_lcp.ipynb` — calcular un camino de mínimo coste con `skimage.graph` y pintarlo.
- `05_diferenciacion.ipynb` — corridor masking y validación de que dos rutas son distintas.

> El código que se consolide pasa de los notebooks a `src/`. Los notebooks son banco de pruebas, no producto final.
