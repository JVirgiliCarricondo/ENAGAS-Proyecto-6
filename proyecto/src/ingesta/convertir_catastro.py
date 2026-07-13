"""Normaliza ZIP catastrales al formato que lee el pipeline (PARCELA.shp).

El motor de alineación (`alinear_capas.py`) descubre las parcelas por
`PARCELA.shp` (formato shapefile del Catastro Inmobiliario) y auto-extrae los
ZIP colocados bajo `data/raw/Catastro/`. Hay tres formatos que el usuario puede
descargar de la Sede Electrónica / portal INSPIRE del Catastro:

  * **Shapefile del Catastro Inmobiliario** (Sede, cl@ve): el ZIP ya contiene
    `PARCELA.shp` → el pipeline lo lee tal cual, no hay nada que convertir.
  * **INSPIRE Cadastral Parcels** (descarga abierta): el ZIP trae
    `A.ES.SDGC.CP.<dgc>.cadastralparcel.gml` (GML), que el pipeline **no**
    reconoce. Este módulo lo convierte a `PARCELA.shp`.
  * **Paquete provincial de la Sede** (`*_PETICION_DESCARGA_SHA.zip`): la Sede
    entrega la cartografía de TODA la provincia como un ZIP multiparte dentro
    del envoltorio (`XX_UA_fecha_SHP.z01` + `.z02` + … + `.zip`). Las partes se
    unen reparando los offsets del directorio central (que son relativos a cada
    parte) y se extraen solo las capas `*_PARCELA` del municipio pedido.

Uso programático:
    from ingesta.convertir_catastro import normalizar_zip_catastro
    res = normalizar_zip_catastro(Path("....zip"), Path("data/raw/Catastro/50074"),
                                  dgc="50074")

Uso por línea de comandos:
    python -m ingesta.convertir_catastro <zip> <dir_destino> [dgc]
"""

from __future__ import annotations

import io
import re
import shutil
import struct
import zipfile
from pathlib import Path

import geopandas as gpd

# Sufijo del GML de parcelas en la descarga INSPIRE (Cadastral Parcels).
_GML_PARCELA_SUFFIX = "cadastralparcel.gml"
# CRS por defecto si el GML no lo declara (INSPIRE España va en EPSG:25830).
_CRS_DEFECTO = "EPSG:25830"


def _nombres_zip(zip_path: Path) -> list[str]:
    """Devuelve la lista de nombres internos (rutas) de un ZIP, sin extraerlo."""
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
    """Extrae todo el contenido de un ZIP en dest_dir (creándolo si no existe)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)


def _convertir_gml(zip_path: Path, gml_interno: str, dest_dir: Path) -> tuple[Path, int]:
    """Lee el GML de parcelas del ZIP y lo escribe como PARCELA.shp.

    Conserva solo la geometría y la referencia catastral (renombrada a 'refcat'
    para no exceder el límite de 10 caracteres de los nombres de campo del
    formato shapefile). El shapefile resultante es lo que el pipeline reconoce.

    Args:
        zip_path:    Ruta del ZIP INSPIRE que contiene el GML.
        gml_interno: Nombre interno del GML de parcelas dentro del ZIP.
        dest_dir:    Directorio destino; se crea ``PARCELA_convertido/`` dentro.

    Returns:
        Tupla ``(ruta_shp, n_parcelas)``: ruta del PARCELA.shp escrito y número
        de parcelas convertidas.
    """
    # /vsizip/ es el sistema de ficheros virtual de GDAL: permite leer el GML
    # directamente desde dentro del ZIP, sin descomprimirlo a disco primero.
    src = f"/vsizip/{zip_path}/{gml_interno}"
    gdf = gpd.read_file(src, engine="pyogrio")

    # INSPIRE España va en EPSG:25830; si el GML no declara CRS, se asume ese.
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


# ── Paquete provincial de la Sede (ZIP multiparte) ──────────────────────────

# Partes de un ZIP partido: X.z01, X.z02, … (la última parte es X.zip).
_RE_PARTE_ZIP = re.compile(r"\.z\d+$", re.IGNORECASE)


def _grupos_multiparte(nombres: list[str]) -> dict[str, list[str]]:
    """Agrupa las entradas de un envoltorio de la Sede por ZIP multiparte.

    Devuelve {stem: [partes en orden .z01, .z02, …, .zip]}. Un ZIP interior sin
    partes .zNN forma un grupo de un solo elemento.
    """
    grupos: dict[str, dict[str, str]] = {}
    for n in nombres:
        p = Path(n)
        suf = p.suffix.lower()
        if suf == ".zip" or _RE_PARTE_ZIP.match(suf):
            grupos.setdefault(str(p.parent / p.stem), {})[suf] = n
    orden = {}
    for stem, partes in grupos.items():
        claves = sorted(k for k in partes if k != ".zip") + [".zip"]
        if ".zip" in partes:
            orden[stem] = [partes[k] for k in claves if k in partes]
    return orden


def _fusionar_zip_partido(wrapper: zipfile.ZipFile, partes: list[str],
                          salida: Path) -> None:
    """Une las partes de un ZIP multiparte (streaming desde el envoltorio) y
    repara el resultado para que sea un ZIP válido de un solo fichero.

    En un ZIP partido, los offsets del directorio central son relativos a la
    parte (disco) donde vive cada entrada, así que tras concatenar hay que
    reescribirlos como offsets absolutos (y poner los números de disco a 0).
    Solo se toca el directorio central y el EOCD (~KB), no los datos.

    Nota: es manipulación de bytes del formato ZIP a bajo nivel (EOCD = End Of
    Central Directory, el registro final que indexa el archivo). No requiere
    conocimientos GIS; el objetivo es solo reconstruir un ZIP abrible.

    Args:
        wrapper: ZIP envoltorio abierto que contiene las partes (.z01, .z02, …, .zip).
        partes:  Nombres internos de las partes, ya ordenados.
        salida:  Ruta del ZIP fusionado a escribir.

    Raises:
        zipfile.BadZipFile: si no se encuentra el EOCD, el directorio central
            está corrupto o el ZIP está en formato Zip64 (>4 GB), no soportado.
    """
    tamanos = []
    with open(salida, "wb") as out:
        for parte in partes:
            with wrapper.open(parte) as f:
                shutil.copyfileobj(f, out)
            tamanos.append(wrapper.getinfo(parte).file_size)
    cum = [0]
    for t in tamanos[:-1]:
        cum.append(cum[-1] + t)

    with open(salida, "r+b") as f:
        # EOCD: firma PK\x05\x06 en los últimos 64 KB + 22 bytes.
        f.seek(0, 2)
        total = f.tell()
        cola = min(total, 65558)
        f.seek(total - cola)
        buf = f.read(cola)
        i = buf.rfind(b"PK\x05\x06")
        if i < 0:
            raise zipfile.BadZipFile("EOCD no encontrado en el ZIP multiparte")
        eocd_pos = total - cola + i
        (_, _, _, n_disco, n_total, cd_size, cd_off, _) = struct.unpack(
            "<4s4H2LH", buf[i:i + 22])
        if 0xFFFF in (n_disco, n_total) or 0xFFFFFFFF in (cd_size, cd_off):
            raise zipfile.BadZipFile(
                "ZIP multiparte en formato Zip64 (>4 GB); descomprímelo en tu "
                "equipo con 7-Zip y sube el ZIP *_PARCELA del municipio")
        cd_real = eocd_pos - cd_size

        # Reescribe cada registro del directorio central: disco→0, offset→absoluto.
        f.seek(cd_real)
        cd = bytearray(f.read(cd_size))
        pos = 0
        for _ in range(n_total):
            if cd[pos:pos + 4] != b"PK\x01\x02":
                raise zipfile.BadZipFile("Directorio central corrupto")
            nlen, elen, clen, disco = struct.unpack("<4H", cd[pos + 28:pos + 36])
            (off,) = struct.unpack("<L", cd[pos + 42:pos + 46])
            if off == 0xFFFFFFFF or disco >= len(cum):
                raise zipfile.BadZipFile(
                    "ZIP multiparte con offsets Zip64; descomprímelo con 7-Zip "
                    "y sube el ZIP *_PARCELA del municipio")
            cd[pos + 34:pos + 36] = struct.pack("<H", 0)
            cd[pos + 42:pos + 46] = struct.pack("<L", cum[disco] + off)
            pos += 46 + nlen + elen + clen
        f.seek(cd_real)
        f.write(cd)
        # EOCD: discos a 0, nº de entradas en este disco = total, offset real del CD.
        f.seek(eocd_pos + 4)
        f.write(struct.pack("<4H2L", 0, 0, n_total, n_total, cd_size, cd_real))


def _extraer_parcelas_sede(zip_path: Path, dest_dir: Path,
                           dgc: str | None) -> tuple[int, str | None]:
    """Extrae las capas *_PARCELA del municipio `dgc` desde un paquete
    provincial de la Sede.

    El envoltorio y el ZIP provincial fusionado son temporales y se borran al
    terminar: si quedaran partes .zNN sueltas bajo data/raw/Catastro/, el
    auto-extractor del pipeline (alinear_capas) fallaría al intentar abrirlas.

    Args:
        zip_path: Ruta del paquete provincial de la Sede (envoltorio multiparte).
        dest_dir: Directorio destino donde dejar las capas del municipio.
        dgc:      Código DGC del municipio a extraer, o None para no filtrar.

    Returns:
        Tupla ``(n_capas_extraidas, error)``: número de capas *_PARCELA extraídas
        y un mensaje de error (str) si algo falló, o None si fue bien.
    """
    tmp = dest_dir / "_paquete_sede_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    extraidas = 0
    try:
        with zipfile.ZipFile(zip_path) as wrapper:
            grupos = _grupos_multiparte(wrapper.namelist())
            if not grupos:
                return 0, None
            for stem, partes in grupos.items():
                merged = tmp / f"{Path(stem).name}_completo.zip"
                if len(partes) == 1:
                    with wrapper.open(partes[0]) as f, open(merged, "wb") as out:
                        shutil.copyfileobj(f, out)
                else:
                    _fusionar_zip_partido(wrapper, partes, merged)
                with zipfile.ZipFile(merged) as zprov:
                    for info in zprov.infolist():
                        nombre = Path(info.filename).name
                        if info.is_dir() or "_PARCELA" not in nombre.upper():
                            continue
                        if dgc and not any(c.startswith(dgc) for c in
                                           Path(info.filename).parts):
                            continue
                        datos = zprov.read(info)
                        if nombre.lower().endswith(".zip"):
                            with zipfile.ZipFile(io.BytesIO(datos)) as zcapa:
                                zcapa.extractall(dest_dir / Path(nombre).stem)
                        else:
                            destino = dest_dir / Path(nombre).parent.name / nombre
                            destino.parent.mkdir(parents=True, exist_ok=True)
                            destino.write_bytes(datos)
                        extraidas += 1
                merged.unlink()
        return extraidas, None
    except (zipfile.BadZipFile, OSError, struct.error) as exc:
        return extraidas, str(exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def normalizar_zip_catastro(zip_path: Path, dest_dir: Path,
                            dgc: str | None = None) -> dict:
    """Deja en dest_dir un PARCELA.shp legible por el pipeline de alineación.

    `dgc` (código de municipio del Catastro) hace falta solo para los paquetes
    provinciales de la Sede: dice de qué municipio extraer las parcelas.

    Estados devueltos en la clave "estado":
      * "shp"        → el ZIP ya traía PARCELA.shp (shapefile Catastro); extraído.
      * "convertido" → era GML INSPIRE (convertido a PARCELA.shp) o un paquete
                       provincial de la Sede (extraídas las capas del municipio).
      * "no_geom"    → el ZIP no contiene parcelas con geometría (p. ej. formato
                       CAT alfanumérico, o un paquete provincial sin el municipio).
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

    if _grupos_multiparte(nombres):
        # Paquete provincial de la Sede: ZIP multiparte con toda la provincia.
        extraidas, err = _extraer_parcelas_sede(zip_path, dest_dir, dgc)
        if err:
            return {"estado": "error", "formato": "paquete Sede (provincial)",
                    "salida": None, "n_parcelas": 0,
                    "mensaje": f"No se pudo abrir el paquete provincial: {err}"}
        if extraidas:
            shp = _existe_parcela_legible(dest_dir)
            quien = f"del municipio {dgc} " if dgc else ""
            return {"estado": "convertido", "formato": "paquete Sede (provincial)",
                    "salida": shp, "n_parcelas": -1,
                    "mensaje": (f"Extraídas las parcelas {quien}del paquete "
                                f"provincial de la Sede ({extraidas} capa(s)).")}
        return {"estado": "no_geom", "formato": "paquete Sede (provincial)",
                "salida": None, "n_parcelas": 0,
                "mensaje": (f"El paquete provincial no incluye capa de parcelas "
                            f"del municipio {dgc} (¿es de otra provincia o de "
                            "otro tipo de cartografía?).")}

    return {"estado": "no_geom", "formato": "desconocido / CAT", "salida": None,
            "n_parcelas": 0,
            "mensaje": ("El ZIP no contiene parcelas con geometría (ni shapefile de "
                        "parcelas ni GML INSPIRE). Descarga el formato SHAPEFILE "
                        "del Catastro.")}


if __name__ == "__main__":
    import sys

    if len(sys.argv) not in (3, 4):
        print("Uso: python -m ingesta.convertir_catastro <zip> <dir_destino> [dgc]")
        raise SystemExit(2)
    resultado = normalizar_zip_catastro(
        Path(sys.argv[1]), Path(sys.argv[2]),
        sys.argv[3] if len(sys.argv) == 4 else None)
    for k, v in resultado.items():
        print(f"{k:12}: {v}")
