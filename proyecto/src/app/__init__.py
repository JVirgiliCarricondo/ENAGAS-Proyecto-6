"""Orquestador e interfaces (CLI / Streamlit).

El orquestador lee el caso de estudio de data/config/ (AOI, origen, destino, perfiles),
ejecuta el pipeline geoespacial para cada perfil (ingesta -> superficie -> LCP ->
diferenciación -> métricas) y compone la salida: tabla comparativa + mapa de las 3-5 rutas.
"""
