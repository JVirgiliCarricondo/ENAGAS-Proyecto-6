"""Tabla comparativa, scoring y mapa de las rutas.

Esqueleto de partida — completar en el Sprint 5. No introduce ningún coste en €:
todo es índice relativo. El scoring sirve para ORDENAR alternativas, no para puntuar
en valor absoluto.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Comparativa:
    rutas: list          # list[MetricasRuta]
    ranking: list[str]   # ids de perfil ordenados (según criterio/agregado)


def tabla_comparativa(metricas_rutas: list) -> "Comparativa":
    """Construye la tabla multicriterio a partir de las métricas de cada ruta.

    TODO(S5): montar un DataFrame (una fila por ruta, una columna por criterio) y
    calcular un ranking (por criterio elegido o por agregado ponderado normalizado).
    """
    raise NotImplementedError("Construir tabla comparativa — Sprint 5")


def mapa_rutas(rutas: list, rejilla, salida_html: str = "rutas.html") -> str:
    """Dibuja las 3-5 rutas diferenciadas sobre un mapa interactivo (folium).

    TODO(S5): una capa por ruta con color distinto + marcadores de origen/destino;
    devuelve la ruta del HTML generado.
    """
    raise NotImplementedError("Generar mapa de rutas — Sprint 5")
