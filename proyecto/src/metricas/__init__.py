"""Métricas multicriterio por ruta.

Para cada ruta calcula: longitud (km), coste relativo (índice), cruces especiales
(nº y tipo: río/carretera/ferrocarril…), km en zona protegida (Red Natura 2000),
km en zona inundable (peligrosidad fluvial T=100, SNCZI), km en zona
urbana/periurbana (catastro) y pendiente máxima y media (del DEM a lo largo de la
ruta). Son las magnitudes que alimentan la comparativa.
"""
