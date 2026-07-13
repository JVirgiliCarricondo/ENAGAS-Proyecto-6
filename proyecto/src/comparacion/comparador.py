"""Tabla comparativa, scoring y mapa de las rutas (esqueleto — Sprint 7).

Papel en el pipeline: última etapa. Reúne las métricas multicriterio de las 3-5
rutas alternativas en una tabla comparativa, calcula un scoring/ranking para
ORDENARLAS y genera un mapa que las muestra diferenciadas. Es la salida que
permite a una persona DECIDIR entre alternativas.

Estado: esqueleto documentado pendiente de implementación en el Sprint 7 (el
scoring formal aún no está definido). Las funciones declaran su contrato pero
lanzan ``NotImplementedError``.

Coste relativo: no introduce ningún coste en €; todo es índice adimensional. El
scoring sirve para ORDENAR alternativas entre sí, nunca para puntuar en valor
absoluto.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Comparativa:
    """Resultado de la comparación multicriterio de un conjunto de rutas.

    Attributes:
        rutas: Métricas de cada ruta alternativa (``list[MetricasRuta]``), una
            entrada por ruta comparada.
        ranking: Ids de perfil ordenados de mejor a peor según el criterio (o el
            agregado ponderado) elegido.
    """

    rutas: list          # list[MetricasRuta]
    ranking: list[str]   # ids de perfil ordenados (según criterio/agregado)


def tabla_comparativa(metricas_rutas: list) -> "Comparativa":
    """Construye la tabla multicriterio a partir de las métricas de cada ruta.

    Pendiente de implementación (Sprint 7): montar un DataFrame (una fila por
    ruta, una columna por criterio) y calcular un ranking, ya sea por el criterio
    elegido o por un agregado ponderado normalizado.

    Args:
        metricas_rutas: Métricas multicriterio de cada ruta alternativa
            (``list[MetricasRuta]``).

    Returns:
        Comparativa: Tabla comparativa con las rutas y su ranking.

    Raises:
        NotImplementedError: Siempre; función aún no implementada (Sprint 7).
    """
    raise NotImplementedError("Construir tabla comparativa — Sprint 5")


def mapa_rutas(rutas: list, rejilla, salida_html: str = "rutas.html") -> str:
    """Dibuja las 3-5 rutas diferenciadas sobre un mapa interactivo (folium).

    Pendiente de implementación (Sprint 7): una capa por ruta con un color
    distinto más los marcadores de origen y destino.

    Args:
        rutas: Rutas alternativas a representar.
        rejilla: Rejilla común (CRS/extensión) de referencia del pipeline.
        salida_html: Ruta del fichero HTML a generar.

    Returns:
        str: Ruta del HTML generado.

    Raises:
        NotImplementedError: Siempre; función aún no implementada (Sprint 7).
    """
    raise NotImplementedError("Generar mapa de rutas — Sprint 5")
