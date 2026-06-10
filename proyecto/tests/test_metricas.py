"""Pruebas de métricas y de diferenciación de rutas.

Esqueleto de partida. Dos cosas que NO pueden fallar: (1) las métricas por ruta deben ser
correctas y (2) las rutas presentadas deben ser realmente distintas. Activar en el Sprint 5.
"""

import pytest

from src.trazados.lcp import Ruta, solapamiento


@pytest.mark.skip(reason="Implementar en Sprint 5")
def test_rutas_diferenciadas_bajo_umbral():
    # Dos rutas aceptadas en el abanico deben solaparse por debajo del umbral configurado.
    ruta_a = Ruta(perfil="corto", celdas=[(0, 0), (1, 1), (2, 2)], coste_relativo=0.1)
    ruta_b = Ruta(perfil="ambiental", celdas=[(0, 0), (0, 1), (0, 2)], coste_relativo=0.2)
    assert solapamiento(ruta_a, ruta_b) <= 0.3


@pytest.mark.skip(reason="Implementar en Sprint 5")
def test_coste_es_relativo_no_euros():
    # El coste relativo es un índice normalizado en [0, 1]; nunca un valor en euros.
    ruta = Ruta(perfil="corto", celdas=[(0, 0), (1, 1)], coste_relativo=0.42)
    assert 0.0 <= ruta.coste_relativo <= 1.0
