"""Motor de camino de mínimo coste (LCP) y diferenciación de rutas.

Sobre cada superficie de coste calcula la ruta origen->destino que minimiza el coste
acumulado (skimage.graph / networkx). Garantiza rutas DIFERENCIADAS combinando perfiles
de prioridad distintos con corridor masking (penalizar la proximidad a rutas ya generadas).
Una ruta solo entra en el abanico si es demostrablemente distinta de las demás.
"""
