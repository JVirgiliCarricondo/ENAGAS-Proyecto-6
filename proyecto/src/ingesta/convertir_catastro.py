"""Normaliza ZIP catastrales al formato que lee el pipeline (PARCELA.shp).

El motor de alineación (`alinear_capas.py`) descubre las parcelas por
`PARCELA.shp` (formato shapefile del Catastro Inmobiliario) y auto-extrae los
ZIP colocados bajo `data/raw/Catastro/`. Hay dos formatos que el usuario puede
descargar de la Sede Electrónica / portal INSPIRE del Catastro:

  * **Shapefile del Catastro Inmobiliario** (Sede, cl@ve): el ZIP ya contiene
    `PARCELA.shp` → el pipeline lo lee tal cual, no hay nada que convertir.
  * **INSPIRE Cadastral Parcels** (descarga abierta): el ZIP trae
    `A.ES.SDGC.CP.<dgc>.cadastralparcel.gml` (GML), que el pipeline **no**
    reconoce. Este módulo lo convierte a `PARCELA.shp`.

Uso programático:
    from ingesta.convertir_catastro import normalizar_zip_catastro
    res = normalizar_zip_catastro(Path("....zip"), Path("data/raw/Catastro/50074"))

Uso por línea de comandos:
    python -m ingesta.convertir_catastro <zip> <dir_destino>
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd

# Sufijo del GML de parcelas en la descarga INSPIRE (Cadastral Parcels).
_GML_PARCELA_SUFFIX = "cadastralparcel.gml"
# CRS por defecto si el GML no lo declara (INSPIRE España va en EPSG:25830).
_CRS_DEFECTO = "EPSG:25830"


def _nombres_zip(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.namelist()


def _tiene_parcela_shp(nombres: list[str]) -> bool:
    """True si el ZIP ya contiene un PARCELA.shp (formato shapefile Catastro)."""
    return any(Path(n).name.lower() == "parcela.shp" for n in nombres)


def _gml_parcela(nombres: list[str]) -> str | None:
    """Nombre interno del GML de parcelas INSPIRE, o None si no lo hay."""
    for n in nombres:
        if n.lower().endswith(_GML_PARCELA_SUFFIX):
            return n
    return None


def _existe_parcela_legible(dest_dir: Path) -> Path | None:
    """PARCELA.shp ya presente bajo dest_dir (case-insensitive), o None."""
    for p in dest_dir.rglob("*.shp"):
        if p.stem.lower() == "parcela":
            return p
    return None


def _extraer_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)


def _convertir_gml(zip_path: Path, gml_interno: str, dest_dir: Path) -> tuple[Path, int]:
    """Lee el GML de parcelas del ZIP y lo escribe como PARCELA.shp.

    Devuelve (ruta_shp, n_parcelas). Conserva solo la geometría y la referencia
    catastral (renombrada a 'refcat' para no exceder el límite de 10 caracteres
    de los nombres de campo en shapefile).
    """
    # /vsizip/ permite leer el GML sin descomprimirlo a disco.
    src = f"/vsizip/{zip_path}/{gml_interno}"
    gdf = gpd.read_file(src, engine="pyogrio")

    if gdf.crs is None:
        gdf = gdf.set_crs(_CRS_DEFECTO)

    cols = {}
    if "nationalCadastralReference" in gdf.columns:
        cols["nationalCadastralReference"] = "refcat"
    elif "localId" in gdf.columns:
        cols["localId"] = "refcat"
    gdf = gdf.rename(columns=cols)
    conservar = [c for c in ("refcat",) if c in gdf.columns] + ["geometry"]
    gdf = gdf[conservar]

    out_dir = dest_dir / "PARCELA_convertido"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_shp = out_dir / "PARCELA.shp"
    gdf.to_file(out_shp, driver="ESRI Shapefile")
    return out_shp, len(gdf)


def normalizar_zip_catastro(zip_path: Path, dest_dir: Path) -> dict:
    """Deja en dest_dir un PARCELA.shp legible por el pipeline de alineación.

    Estados devueltos en la clave "estado":
      * "shp"        → el ZIP ya traía PARCELA.shp (shapefile Catastro); extraído.
      * "convertido" → era GML INSPIRE y se ha convertido a PARCELA.shp.
      * "no_geom"    → el ZIP no contiene ni PARCELA.shp ni GML de parcelas
                       (p. ej. formato CAT alfanumérico, que no lleva geometría).
      * "error"      → el ZIP está corrupto o la lectura/escritura falló.

    Devuelve {estado, formato, salida (Path|None), n_parcelas (int), mensaje}.
    """
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)

    # Idempotencia: si ya hay un PARCELA.shp legible, no repetimos el trabajo.
    ya = _existe_parcela_legible(dest_dir)
    if ya is not None:
        return {"estado": "shp", "formato": "shapefile Catastro",
                "salida": ya, "n_parcelas": -1,
                "mensaje": f"Ya disponible: {ya.name}"}

    try:
        nombres = _nombres_zip(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        return {"estado": "error", "formato": "?", "salida": None,
                "n_parcelas": 0, "mensaje": f"ZIP ilegible: {exc}"}

    if _tiene_parcela_shp(nombres):
        try:
            _extraer_zip(zip_path, dest_dir)
        except (zipfile.BadZipFile, OSError) as exc:
            return {"estado": "error", "formato": "shapefile Catastro",
                    "salida": None, "n_parcelas": 0,
                    "mensaje": f"No se pudo extraer: {exc}"}
        shp = _existe_parcela_legible(dest_dir)
        # Mensajes de cara al usuario: "shapefile de parcelas" (el nombre técnico
        # del fichero, PARCELA.shp, se queda en código y docstrings).
        return {"estado": "shp", "formato": "shapefile Catastro",
                "salida": shp, "n_parcelas": -1,
                "mensaje": "Shapefile de parcelas listo para el pipeline."}

    gml = _gml_parcela(nombres)
    if gml is not None:
        try:
            out_shp, n = _convertir_gml(zip_path, gml, dest_dir)
        except Exception as exc:  # pyogrio/GDAL pueden lanzar varios tipos
            return {"estado": "error", "formato": "GML INSPIRE",
                    "salida": None, "n_parcelas": 0,
                    "mensaje": f"Conversión GML→SHP falló: {exc}"}
        return {"estado": "convertido", "formato": "GML INSPIRE",
                "salida": out_shp, "n_parcelas": n,
                "mensaje": f"Convertido a shapefile de parcelas ({n} parcelas)."}

    return {"estado": "no_geom", "formato": "desconocido / CAT", "salida": None,
            "n_parcelas": 0,
            "mensaje": ("El ZIP no contiene parcelas con geometría (ni shapefile de "
                        "parcelas ni GML INSPIRE). Descarga el formato SHAPEFILE "
                        "del Catastro.")}


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Uso: python -m ingesta.convertir_catastro <zip> <dir_destino>")
        raise SystemExit(2)
    resultado = normalizar_zip_catastro(Path(sys.argv[1]), Path(sys.argv[2]))
    for k, v in resultado.items():
        print(f"{k:12}: {v}")
