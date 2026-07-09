"""Verifica que el entorno Python tiene todo lo que el prototipo necesita.

Comprueba la version de Python y que cada dependencia clave se puede importar,
imprimiendo OK/FALTA por linea. Lo invocan setup.ps1 / setup.sh al final de la
instalacion, y puede lanzarse a mano tras un `git pull`:

    Windows:      .venv\\Scripts\\python.exe check_entorno.py
    macOS/Linux:  .venv/bin/python check_entorno.py

Sale con codigo 1 si falta algo (util en scripts).
"""
import importlib
import importlib.metadata
import sys

# modulo importable -> nombre del paquete en pip (requirements.txt)
DEPENDENCIAS = {
    "rasterio": "rasterio",
    "geopandas": "geopandas",
    "shapely": "shapely",
    "pyproj": "pyproj",
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "yaml": "PyYAML",
    "requests": "requests",
    "folium": "folium",
    "streamlit": "streamlit",
    "streamlit_folium": "streamlit-folium",
    "matplotlib": "matplotlib",
    "reportlab": "reportlab",
    "pytest": "pytest",
}


def main() -> int:
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    if sys.version_info[:2] != (3, 10):
        print(
            f"  AVISO: el entorno validado usa Python 3.10 y este es "
            f"{sys.version_info.major}.{sys.version_info.minor}; las versiones "
            "pineadas en requirements.txt podrian no instalar igual."
        )
    if sys.prefix == sys.base_prefix:
        print("  AVISO: no estas dentro de un entorno virtual (.venv).")
    print()

    faltan = []
    for modulo, paquete in DEPENDENCIAS.items():
        try:
            importlib.import_module(modulo)
            try:
                version = importlib.metadata.version(paquete)
            except importlib.metadata.PackageNotFoundError:
                version = "?"
            print(f"  OK     {paquete:<18} {version}")
        except ImportError as exc:
            faltan.append(paquete)
            print(f"  FALTA  {paquete:<18} ({exc})")

    print()
    if faltan:
        print(f"Entorno INCOMPLETO: falta(n) {', '.join(faltan)}.")
        print("Ejecuta setup.ps1 (Windows) o setup.sh (macOS/Linux), o bien:")
        print("  python -m pip install -r requirements.txt")
        return 1
    print("Entorno COMPLETO: todas las dependencias estan instaladas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
