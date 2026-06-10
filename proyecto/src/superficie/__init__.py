"""Superficies de coste (raster multicriterio).

Convierte cada capa alineada en un coste por celda (pendiente -> coste; suelo urbano ->
coste alto; Red Natura 2000 -> coste muy alto o prohibido; proximidad a cruces -> coste)
y las combina con un VECTOR DE PESOS. Cada perfil de prioridad produce una superficie
distinta y, por tanto, una ruta distinta. Todo coste es RELATIVO (índice), nunca €.
"""
