"""Configuración de pytest: añade la raíz del proyecto (proyecto/) al path.

Permite importar el paquete `src` en las pruebas cuando pytest se ejecuta
desde cualquier directorio.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
