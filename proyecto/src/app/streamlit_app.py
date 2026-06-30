"""Interfaz web — Generador de trazados de ramales de H2 (Enagás / CI2 Lab 2026).

Ejecutar desde proyecto/:
    streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import copy
import math
import re
import sys
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import streamlit as st
import yaml
from pyproj import Transformer

# Page config — DEBE ser la primera llamada a Streamlit
st.set_page_config(
    page_title="Enagás — Trazados de Ramales H₂",
    page_icon=":large_blue_circle:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Paths del proyecto
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

_CONFIG_PATH = _ROOT / "data" / "config" / "escenario.yaml"
_PERFILES_PATH = _ROOT / "data" / "config" / "perfiles.yaml"
_RUTAS_DIR   = _ROOT / "data" / "processed" / "Rutas"

# Constantes
MAX_DIST_M = 15_000.0
BUFFER_M   = 2_000.0
PERFILES   = ["corto", "equilibrio", "ambiental", "pendiente"]

_to_wgs84 = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
_to_utm   = Transformer.from_crs("EPSG:4326",  "EPSG:25830", always_xy=True)

_COLORES = {
    "corto":      "#1f78b4",
    "equilibrio": "#ff7f00",
    "ambiental":  "#33a02c",
    "pendiente":  "#e31a1c",
}
_NOMBRE_PERFIL = {
    "corto":      "Ruta Corta",
    "equilibrio": "Equilibrio",
    "ambiental":  "Ambiental",
    "pendiente":  "Min. Pendiente",
}

# Claves de peso en perfiles.yaml → etiqueta en la UI
_CAPAS_PESO: list[tuple[str, str]] = [
    ("longitud",     "Longitud (distancia)"),
    ("pendiente",    "Pendiente"),
    ("protegida",    "Zonas protegidas"),
    ("inundable",    "Zonas inundables"),
    ("cruces",       "Cruces (vias y rios)"),
    ("expropiacion", "Expropiacion (catastro)"),
    ("geotecnia",    "Geotecnia (litologia)"),
    ("traversal",    "Traversalidad (direccion pendiente)"),
]
_PESO_MIN, _PESO_MAX, _PESO_STEP = 0.0, 1.0, 0.01

try:
    from streamlit_folium import st_folium as _st_folium
    _HAS_ST_FOLIUM = True
except ImportError:
    _HAS_ST_FOLIUM = False

# ── CSS estilo Enagás ─────────────────────────────────────────────────────────
_CSS = """
<style>
  .stApp {
    background-color: #f4f6f9;
    color: #1f2937;
  }
  .stApp p, .stApp li, .stApp label {
    color: #1f2937;
  }
  div[data-testid="stMarkdownContainer"] * {
    color: #1f2937;
  }
  div[data-baseweb="tab"] {
    color: #1f2937 !important;
  }
  div[data-testid="stDataFrame"] * {
    color: #1f2937 !important;
  }

  .enagas-page-header {
    background: white;
    border-top: 4px solid #76B82A;
    border-bottom: 1px solid #dde6ef;
    padding: 14px 28px;
    margin-bottom: 18px;
    display: flex;
    align-items: center;
    gap: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
  }
  .header-divider {
    width: 2px;
    height: 38px;
    background: #0066B2;
    border-radius: 2px;
    flex-shrink: 0;
  }
  .header-title {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 1.38rem;
    font-weight: 700;
    color: #002B5C;
    margin: 0;
    line-height: 1.2;
  }
  .header-subtitle {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 0.81rem;
    color: #6B7D8E;
    margin: 3px 0 0;
  }

  .scenario-card {
    background: white;
    border-radius: 8px;
    padding: 18px 20px 14px;
    margin-bottom: 14px;
    border-top: 4px solid #00AEEF;
    box-shadow: 0 2px 6px rgba(0,0,0,0.07);
  }
  .scenario-card h3 {
    color: #002B5C;
    font-size: 1rem;
    font-weight: 700;
    margin: 0 0 10px;
    font-family: 'Segoe UI', Arial, sans-serif;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .constraints-box {
    background: #ddeef8;
    border-left: 4px solid #00AEEF;
    border-radius: 0 6px 6px 0;
    padding: 10px 16px;
    margin-bottom: 18px;
    font-size: 0.87rem;
    color: #002B5C;
    font-family: 'Segoe UI', Arial, sans-serif;
  }

  .section-label {
    font-size: 0.75rem;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 2px;
    font-family: 'Segoe UI', Arial, sans-serif;
  }

  div[data-testid="stButton"] > button {
    font-weight: 600 !important;
    border: 1px solid #9aa9b8 !important;
    color: #0b1f33 !important;
    -webkit-text-fill-color: #0b1f33 !important;
  }
  div[data-testid="stButton"] > button p,
  div[data-testid="stButton"] > button span,
  div[data-testid="stButton"] > button div {
    color: #0b1f33 !important;
    -webkit-text-fill-color: #0b1f33 !important;
    border: none !important;
    background: transparent !important;
  }
  div[data-testid="stButton"] > button:hover {
    color: #071523 !important;
    -webkit-text-fill-color: #071523 !important;
    border-color: #6d7f91 !important;
  }
  div[data-testid="stButton"] > button:hover p,
  div[data-testid="stButton"] > button:hover span,
  div[data-testid="stButton"] > button:hover div {
    color: #071523 !important;
    -webkit-text-fill-color: #071523 !important;
  }
  div[data-testid="stButton"] > button:disabled {
    color: #4b5d70 !important;
    -webkit-text-fill-color: #4b5d70 !important;
    background: #dbe4ec !important;
    border-color: #b4c2cf !important;
    opacity: 1 !important;
  }
  div[data-testid="stButton"] > button:disabled p,
  div[data-testid="stButton"] > button:disabled span,
  div[data-testid="stButton"] > button:disabled div {
    color: #4b5d70 !important;
    -webkit-text-fill-color: #4b5d70 !important;
  }

  div[data-testid="stButton"] > button[kind="primary"],
  div[data-testid="stButton"] > button[kind="primary"] p,
  div[data-testid="stButton"] > button[kind="primary"] span,
  div[data-testid="stButton"] > button[kind="primary"] div,
  div[data-testid="stButton"] > button[kind="primary"] * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    border: none !important;
  }
  div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #002B5C 0%, #005BAA 100%) !important;
    border-radius: 6px !important;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
    font-size: 1rem !important;
    letter-spacing: 0.3px !important;
    padding: 12px 28px !important;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover,
  div[data-testid="stButton"] > button[kind="primary"]:hover p,
  div[data-testid="stButton"] > button[kind="primary"]:hover span,
  div[data-testid="stButton"] > button[kind="primary"]:hover div,
  div[data-testid="stButton"] > button[kind="primary"]:hover * {
    background: transparent !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #001f45 0%, #004f95 100%) !important;
  }

  footer { display: none; }
  #MainMenu { display: none; }
  header[data-testid="stHeader"] { display: none; }
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utm_to_latlon(x: float, y: float) -> tuple[float, float]:
    lon, lat = _to_wgs84.transform(x, y)
    return lat, lon


def _latlon_to_utm(lat: float, lon: float) -> tuple[float, float]:
    x, y = _to_utm.transform(lon, lat)
    return x, y


def _dist_m(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _leer_cfg() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))


def _guardar_cfg(cfg: dict) -> None:
    txt = yaml.dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False)
    _CONFIG_PATH.write_text(txt, encoding="utf-8")


def _ids_escenarios(cfg: dict) -> list[str]:
    ids = [k.removeprefix("escenario_").upper() for k in cfg if k.startswith("escenario_")]
    return sorted(ids, key=lambda x: (len(x), x))


def _coords_desde_cfg(cfg: dict) -> dict[str, dict[str, dict[str, float]]]:
    coords: dict[str, dict[str, dict[str, float]]] = {}
    for sid in _ids_escenarios(cfg):
        block = cfg[f"escenario_{sid}"]
        coords[sid] = {
            rol: {"x": float(block[rol]["x"]), "y": float(block[rol]["y"])}
            for rol in ("origen", "destino")
        }
    return coords


def _aplicar_coords_a_cfg(cfg: dict, coords: dict[str, dict[str, dict[str, float]]]) -> dict:
    for sid, pts in coords.items():
        key = f"escenario_{sid}"
        if key not in cfg:
            cfg[key] = {
                "origen": {"nombre": f"{sid}_inicial"},
                "destino": {"nombre": f"{sid}_final"},
            }
        for rol in ("origen", "destino"):
            cfg[key][rol]["x"] = int(round(pts[rol]["x"]))
            cfg[key][rol]["y"] = int(round(pts[rol]["y"]))
            cfg[key][rol].setdefault(
                "nombre", f"{sid}_{'inicial' if rol == 'origen' else 'final'}"
            )
    return cfg


def _siguiente_id_escenario(ids: list[str]) -> str:
    for code in range(ord("A"), ord("Z") + 1):
        sid = chr(code)
        if sid not in ids:
            return sid
    n = 1
    while f"E{n}" in ids:
        n += 1
    return f"E{n}"


def _normalizar_id_escenario(raw: str) -> str | None:
    s = re.sub(r"[^A-Za-z0-9_-]", "", raw.strip()).upper().replace("-", "_")
    return s[:20] or None


def _plantilla_nuevo_escenario(
    cfg: dict, ref_id: str | None = None, desplazamiento_m: float = 500.0
) -> dict[str, dict[str, float]]:
    if ref_id and ref_id in _coords_desde_cfg(cfg):
        ref = _coords_desde_cfg(cfg)[ref_id]
    elif _ids_escenarios(cfg):
        ref = _coords_desde_cfg(cfg)[_ids_escenarios(cfg)[0]]
    else:
        ref = {
            "origen": {"x": 740_000.0, "y": 4_560_000.0},
            "destino": {"x": 741_000.0, "y": 4_561_000.0},
        }
    return {
        "origen": {
            "x": ref["origen"]["x"] + desplazamiento_m,
            "y": ref["origen"]["y"] + desplazamiento_m,
        },
        "destino": {
            "x": ref["destino"]["x"] + desplazamiento_m,
            "y": ref["destino"]["y"] + desplazamiento_m,
        },
    }


def _cargar_perfiles_defecto() -> list[dict]:
    data = yaml.safe_load(_PERFILES_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(data["perfiles"])


def _perfil_por_id(perfiles: list[dict], pid: str) -> dict:
    for p in perfiles:
        if p["id"] == pid:
            return p
    raise KeyError(pid)


def _init_perfiles_session() -> None:
    if "perfiles_cfg" not in st.session_state:
        st.session_state.perfiles_cfg = _cargar_perfiles_defecto()
    if "perfil_pesos_activo" not in st.session_state:
        st.session_state.perfil_pesos_activo = PERFILES[0]
    if "pesos_version" not in st.session_state:
        st.session_state.pesos_version = 0


def _render_editor_pesos() -> list[dict]:
    """Editor de pesos por capa; devuelve la lista de perfiles actualizada."""
    _init_perfiles_session()
    perfiles = st.session_state.perfiles_cfg

    with st.expander("Pesos de capas (perfiles de prioridad)", expanded=False):
        st.caption(
            "Cada perfil combina las capas como: "
            "**coste = peso_longitud + Σ (peso_capa × capa)**. "
            "Los valores son indices relativos, no euros. "
            "Cada peso está acotado a [0, 1]; lo ideal es que la suma de los "
            "pesos de un perfil sea 1.00 (100%)."
        )

        pid = st.selectbox(
            "Perfil a ajustar",
            options=PERFILES,
            index=PERFILES.index(st.session_state.perfil_pesos_activo)
            if st.session_state.perfil_pesos_activo in PERFILES else 0,
            format_func=lambda p: _NOMBRE_PERFIL.get(p, p),
            key="select_perfil_pesos",
        )
        st.session_state.perfil_pesos_activo = pid
        perfil = _perfil_por_id(perfiles, pid)
        st.markdown(f"*{perfil.get('descripcion', '')}*")

        col_a, col_b = st.columns(2)
        pesos = perfil.setdefault("pesos", {})
        ver = st.session_state.pesos_version
        for i, (clave, etiqueta) in enumerate(_CAPAS_PESO):
            col = col_a if i % 2 == 0 else col_b
            with col:
                pesos[clave] = st.slider(
                    etiqueta,
                    min_value=_PESO_MIN,
                    max_value=_PESO_MAX,
                    value=float(pesos.get(clave, 0.0)),
                    step=_PESO_STEP,
                    key=f"peso_{pid}_{clave}_v{ver}",
                )

        suma_pesos = sum(pesos.values())
        if abs(suma_pesos - 1.0) > 0.01:
            st.caption(f"Suma de pesos: {suma_pesos:.2f} (recomendado: 1.00)")
        else:
            st.caption(f"Suma de pesos: {suma_pesos:.2f} (correcto)")

        btn_r, btn_a = st.columns(2)
        with btn_r:
            if st.button("Restaurar este perfil", use_container_width=True, key="btn_reset_perfil"):
                defecto = _perfil_por_id(_cargar_perfiles_defecto(), pid)
                perfil["pesos"] = copy.deepcopy(defecto["pesos"])
                st.session_state.pesos_version += 1
                st.rerun()
        with btn_a:
            if st.button("Restaurar todos", use_container_width=True, key="btn_reset_todos"):
                st.session_state.perfiles_cfg = _cargar_perfiles_defecto()
                st.session_state.pesos_version += 1
                st.rerun()

        # Resumen compacto de los 4 perfiles
        filas = []
        for p in perfiles:
            row = {"Perfil": _NOMBRE_PERFIL.get(p["id"], p["id"])}
            for clave, etiqueta in _CAPAS_PESO:
                row[etiqueta.split(" (")[0]] = p.get("pesos", {}).get(clave, 0.0)
            filas.append(row)
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    return perfiles


def _crear_escenario(cfg: dict, coords: dict, nuevo_id: str, ref_id: str | None) -> str:
    sid = _normalizar_id_escenario(nuevo_id)
    if not sid:
        raise ValueError("Indica un identificador valido (letras, numeros, guion o guion bajo).")
    if sid in coords:
        raise ValueError(f"El escenario '{sid}' ya existe.")
    coords[sid] = _plantilla_nuevo_escenario(cfg, ref_id)
    cfg = _aplicar_coords_a_cfg(cfg, {sid: coords[sid]})
    _guardar_cfg(cfg)
    return sid


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _ejecutar_pipeline(
    progress_cb,
    escenarios: list[str],
    perfiles: list[dict] | None = None,
) -> dict:
    import importlib
    import logging as _logging
    _logging.basicConfig(level=_logging.WARNING)

    for _mod in list(sys.modules.keys()):
        if _mod.startswith(("trazados.", "metricas.", "superficie.", "ingesta.")):
            del sys.modules[_mod]

    from trazados.ruta_pendiente import run_perfiles
    from metricas.calculo import calcular_todas

    if not escenarios:
        raise ValueError("No hay escenarios configurados.")

    for i, s in enumerate(escenarios):
        pct = 0.05 + (0.75 * i / len(escenarios))
        progress_cb(pct, f"Calculando rutas — Escenario {s}...")
        run_perfiles(s, lam=4.0, perfiles_override=perfiles)

    progress_cb(0.85, "Calculando metricas...")
    resultados = calcular_todas(escenarios=escenarios)

    progress_cb(1.0, "Listo")
    return resultados


# ── Mapas Folium ──────────────────────────────────────────────────────────────

_COLORES_ESCENARIO = {
    "A": "#0066B2",
    "B": "#76B82A",
    "C": "#E31A1C",
    "D": "#FF7F00",
}


def _color_escenario(sid: str) -> str:
    if sid in _COLORES_ESCENARIO:
        return _COLORES_ESCENARIO[sid]
    idx = sum(ord(c) for c in sid) % 5
    return ["#6A3D9A", "#B15928", "#FB9A99", "#CAB2D6", "#FFFF99"][idx]


def _marcador_punto(
    m: folium.Map,
    lat: float,
    lon: float,
    rol: str,
    escenario: str,
    activo: bool,
    coords: dict,
) -> None:
    """Marca origen/destino con circulo visible y etiqueta O/D."""
    es_origen = rol == "origen"
    fill = "#27ae60" if es_origen else "#e74c3c"
    letra = "O" if es_origen else "D"
    radio = 14 if activo else 9
    opacidad = 1.0 if activo else 0.45
    tooltip = f"Escenario {escenario} — {rol.capitalize()}"
    popup_html = (
        f"<b style='color:#002B5C'>{tooltip}</b><br>"
        f"X: {coords[escenario][rol]['x']:.0f} m<br>"
        f"Y: {coords[escenario][rol]['y']:.0f} m<br>"
        f"<small>({lat:.5f}, {lon:.5f})</small>"
    )
    folium.CircleMarker(
        location=[lat, lon],
        radius=radio,
        color="#ffffff",
        weight=3 if activo else 2,
        fill=True,
        fill_color=fill,
        fill_opacity=opacidad,
        tooltip=tooltip,
        popup=folium.Popup(popup_html, max_width=240),
    ).add_to(m)
    if activo:
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-family:Segoe UI,sans-serif;font-size:13px;'
                    f"font-weight:700;color:#fff;background:{fill};"
                    f'width:22px;height:22px;line-height:22px;text-align:center;'
                    f'border-radius:50%;border:2px solid #fff;'
                    f'box-shadow:0 1px 4px rgba(0,0,0,0.45);">{letra}</div>'
                ),
                icon_size=(22, 22),
                icon_anchor=(11, 11),
            ),
            tooltip=tooltip,
        ).add_to(m)


def _mapa_entrada(coords: dict, escenario_activo: str) -> folium.Map:
    activo_pts = coords[escenario_activo]
    lat_o, lon_o = _utm_to_latlon(activo_pts["origen"]["x"], activo_pts["origen"]["y"])
    lat_d, lon_d = _utm_to_latlon(activo_pts["destino"]["x"], activo_pts["destino"]["y"])

    m = folium.Map(
        location=[(lat_o + lat_d) / 2, (lon_o + lon_d) / 2],
        zoom_start=12,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri WorldImagery",
    )

    for s in coords:
        activo = s == escenario_activo
        color = _color_escenario(s)
        for rol in ("origen", "destino"):
            lat, lon = _utm_to_latlon(coords[s][rol]["x"], coords[s][rol]["y"])
            _marcador_punto(m, lat, lon, rol, s, activo, coords)

        lat_o_s, lon_o_s = _utm_to_latlon(coords[s]["origen"]["x"], coords[s]["origen"]["y"])
        lat_d_s, lon_d_s = _utm_to_latlon(coords[s]["destino"]["x"], coords[s]["destino"]["y"])
        folium.PolyLine(
            locations=[[lat_o_s, lon_o_s], [lat_d_s, lon_d_s]],
            color=color,
            weight=4.0 if activo else 1.5,
            dash_array=None if activo else "6 4",
            opacity=0.95 if activo else 0.35,
            tooltip=f"Escenario {s} — linea directa",
        ).add_to(m)

    # Encuadrar el escenario activo (origen + destino)
    pad = 0.08
    lat_min, lat_max = min(lat_o, lat_d), max(lat_o, lat_d)
    lon_min, lon_max = min(lon_o, lon_d), max(lon_o, lon_d)
    dlat = max((lat_max - lat_min) * pad, 0.01)
    dlon = max((lon_max - lon_min) * pad, 0.01)
    m.fit_bounds([
        [lat_min - dlat, lon_min - dlon],
        [lat_max + dlat, lon_max + dlon],
    ])

    leyenda = f"""
    <div style="position:fixed;top:12px;right:12px;z-index:1000;background:#fff;
                padding:10px 14px;border-radius:8px;font-family:'Segoe UI',sans-serif;
                font-size:12px;color:#1f2937;box-shadow:0 2px 8px rgba(0,0,0,0.2);
                border-top:3px solid {_color_escenario(escenario_activo)};">
      <b style="color:#002B5C;">Escenario {escenario_activo}</b><br>
      <span style="color:#27ae60;font-weight:700;">&#9679;</span> Origen (O)<br>
      <span style="color:#e74c3c;font-weight:700;">&#9679;</span> Destino (D)
    </div>
    """
    m.get_root().html.add_child(folium.Element(leyenda))

    return m


def _mapa_resultados(escenarios: list[str] | None = None) -> folium.Map | None:
    ess = escenarios or _ids_escenarios(_leer_cfg())
    rutas = [
        (s, perfil, _RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg")
        for s in ess
        for perfil in PERFILES
        if (_RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg").exists()
    ]
    if not rutas:
        return None

    gdf0 = gpd.read_file(rutas[0][2]).to_crs("EPSG:4326")
    c = gdf0.geometry.iloc[0].centroid
    m = folium.Map(
        location=[c.y, c.x],
        zoom_start=12,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri WorldImagery",
    )

    esc_en_rutas = sorted({s for s, _, _ in rutas})
    grupos = {s: folium.FeatureGroup(name=f"Escenario {s}", show=True) for s in esc_en_rutas}

    all_bounds = []
    for s, perfil, path in rutas:
        gdf = gpd.read_file(path).to_crs("EPSG:4326")
        color = _COLORES[perfil]
        folium.GeoJson(
            gdf.__geo_interface__,
            style_function=lambda _f, c=color: {"color": c, "weight": 3.5, "opacity": 0.9},
            tooltip=f"Esc. {s} — {_NOMBRE_PERFIL[perfil]}",
        ).add_to(grupos[s])
        b = gdf.total_bounds
        all_bounds.append(b)

    for fg in grupos.values():
        fg.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    legend = """
    <style>
      .perfiles-legend, .perfiles-legend span { color: #1f2937 !important; }
      .perfiles-legend b { color: #002B5C !important; }
      .perfiles-legend .c-corto { color: #1f78b4 !important; }
      .perfiles-legend .c-equilibrio { color: #ff7f00 !important; }
      .perfiles-legend .c-ambiental { color: #33a02c !important; }
      .perfiles-legend .c-pendiente { color: #e31a1c !important; }
    </style>
    <div class="perfiles-legend" style="position:fixed;bottom:28px;left:28px;z-index:1000;background:#ffffff;
                padding:12px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.18);font-family:'Segoe UI',sans-serif;
                font-size:13px;border-top:3px solid #002B5C;">
      <b>Perfiles</b><br>
      <span class="c-corto" style="font-size:1.3em;">&#9644;</span><span> Ruta Corta</span><br>
      <span class="c-equilibrio" style="font-size:1.3em;">&#9644;</span><span> Equilibrio</span><br>
      <span class="c-ambiental" style="font-size:1.3em;">&#9644;</span><span> Ambiental</span><br>
      <span class="c-pendiente" style="font-size:1.3em;">&#9644;</span><span> Min. Pendiente</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    if all_bounds:
        bounds = np.array(all_bounds)
        m.fit_bounds([
            [bounds[:, 1].min(), bounds[:, 0].min()],
            [bounds[:, 3].max(), bounds[:, 2].max()],
        ])

    return m


# ── Página de entrada ─────────────────────────────────────────────────────────

def _render_input():
    cfg = _leer_cfg()
    ids_cfg = _ids_escenarios(cfg)

    if "coords" not in st.session_state:
        st.session_state.coords = _coords_desde_cfg(cfg)
    else:
        for sid in ids_cfg:
            if sid not in st.session_state.coords:
                st.session_state.coords[sid] = _coords_desde_cfg(cfg)[sid]

    if "escenario_activo" not in st.session_state or st.session_state.escenario_activo not in st.session_state.coords:
        st.session_state.escenario_activo = ids_cfg[0] if ids_cfg else "A"
    if "punto_activo_rol" not in st.session_state:
        st.session_state.punto_activo_rol = "origen"
    if "_last_click" not in st.session_state:
        st.session_state._last_click = None

    coords = st.session_state.coords
    escenarios = sorted(coords.keys(), key=lambda x: (len(x), x))
    esc_activo = st.session_state.escenario_activo

    st.markdown(
        '<div class="constraints-box">'
        "<b>Restricciones del modelo:</b>"
        "&nbsp;&nbsp;&middot;&nbsp; Corredor de referencia: <b>2 km de ancho</b> (&plusmn;1 km a cada lado)"
        "&nbsp;&nbsp;&middot;&nbsp; Distancia maxima origen&ndash;destino: <b>15 km</b>"
        "</div>",
        unsafe_allow_html=True,
    )

    col_inputs, col_map = st.columns([1, 2], gap="large")

    with col_inputs:
        sel_col, _ = st.columns([2, 1])
        with sel_col:
            esc_activo = st.selectbox(
                "Escenario",
                options=escenarios,
                index=escenarios.index(st.session_state.escenario_activo)
                if st.session_state.escenario_activo in escenarios else 0,
                format_func=lambda s: f"Escenario {s}",
                key="select_escenario",
            )
            st.session_state.escenario_activo = esc_activo

        with st.expander("Crear nuevo escenario", expanded=False):
            propuesto = _siguiente_id_escenario(escenarios)
            nuevo_id = st.text_input(
                "Identificador",
                value=propuesto,
                help="Letras, numeros, guion o guion bajo. Ej.: C, NORTE, RAMAL_3",
                key="nuevo_escenario_id",
            )
            if st.button("Crear escenario", use_container_width=True, key="btn_crear_escenario"):
                try:
                    nuevo = _crear_escenario(cfg, coords, nuevo_id, esc_activo)
                    st.session_state.escenario_activo = nuevo
                    st.session_state.punto_activo_rol = "origen"
                    st.success(f"Escenario {nuevo} creado.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        st.markdown(
            f'<div class="scenario-card"><h3>Escenario {esc_activo}</h3>',
            unsafe_allow_html=True,
        )
        for rol in ("origen", "destino"):
            st.markdown(
                f'<p class="section-label">{rol.capitalize()}</p>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                coords[esc_activo][rol]["x"] = st.number_input(
                    "X (m)", value=coords[esc_activo][rol]["x"],
                    step=1.0, format="%.0f", key=f"{esc_activo}_{rol}_x",
                )
            with c2:
                coords[esc_activo][rol]["y"] = st.number_input(
                    "Y (m)", value=coords[esc_activo][rol]["y"],
                    step=1.0, format="%.0f", key=f"{esc_activo}_{rol}_y",
                )

        dist = _dist_m(
            coords[esc_activo]["origen"]["x"], coords[esc_activo]["origen"]["y"],
            coords[esc_activo]["destino"]["x"], coords[esc_activo]["destino"]["y"],
        )
        if dist > MAX_DIST_M:
            st.error(f"Distancia: {dist / 1000:.1f} km — supera los {MAX_DIST_M / 1000:.0f} km")
        else:
            st.success(f"Distancia: {dist / 1000:.1f} km")

        st.markdown("</div>", unsafe_allow_html=True)

        if len(escenarios) > 1:
            st.caption(
                f"{len(escenarios)} escenarios configurados. "
                f"El mapa muestra todos; el activo ({esc_activo}) resalta en color."
            )

        if _HAS_ST_FOLIUM:
            st.markdown("---")
            st.markdown(f"**Siguiente clic en el mapa establece ({esc_activo}):**")
            st.session_state.punto_activo_rol = st.radio(
                "Punto activo",
                options=["origen", "destino"],
                format_func=str.capitalize,
                index=0 if st.session_state.punto_activo_rol == "origen" else 1,
                label_visibility="collapsed",
                horizontal=True,
                key="radio_punto_rol",
            )
        else:
            st.info("Instala `streamlit-folium` para activar el clic en mapa.")

    with col_map:
        st.markdown(
            f"**Mapa — Escenario {esc_activo}**  "
            f"<span style='color:#27ae60;font-weight:600;'>● Origen</span> &nbsp; "
            f"<span style='color:#e74c3c;font-weight:600;'>● Destino</span>",
            unsafe_allow_html=True,
        )
        m = _mapa_entrada(coords, esc_activo)
        if _HAS_ST_FOLIUM:
            map_data = _st_folium(
                m,
                key="mapa_entrada",
                height=420,
                use_container_width=True,
                returned_objects=["last_clicked"],
            )
            if map_data and map_data.get("last_clicked"):
                click = map_data["last_clicked"]
                click_key = f"{click['lat']:.7f},{click['lng']:.7f}"
                if click_key != st.session_state._last_click:
                    st.session_state._last_click = click_key
                    rol = st.session_state.punto_activo_rol
                    x_utm, y_utm = _latlon_to_utm(click["lat"], click["lng"])
                    coords[esc_activo][rol]["x"] = round(x_utm)
                    coords[esc_activo][rol]["y"] = round(y_utm)
                    st.rerun()
        else:
            from streamlit.components.v1 import html as _html
            _html(m._repr_html_(), height=560)

    perfiles_cfg = _render_editor_pesos()

    # ── Botón ─────────────────────────────────────────────────────────────────
    st.markdown("---")
    distancias = {
        s: _dist_m(
            coords[s]["origen"]["x"], coords[s]["origen"]["y"],
            coords[s]["destino"]["x"], coords[s]["destino"]["y"],
        )
        for s in escenarios
    }
    can_run = all(d <= MAX_DIST_M for d in distancias.values())

    btn_col, _ = st.columns([1, 3])
    with btn_col:
        if st.button("Procesamiento", type="primary", disabled=not can_run,
                     use_container_width=True):
            cfg = _aplicar_coords_a_cfg(cfg, coords)
            _guardar_cfg(cfg)

            bar = st.progress(0, text="Iniciando pipeline...")

            try:
                resultados = _ejecutar_pipeline(
                    lambda pct, msg: bar.progress(pct, text=msg),
                    escenarios=escenarios,
                    perfiles=copy.deepcopy(perfiles_cfg),
                )
                st.session_state.resultados = resultados
                st.session_state.escenarios_procesados = escenarios
                st.session_state.perfiles_procesados = copy.deepcopy(perfiles_cfg)
                st.session_state.pantalla = "resultados"
                st.rerun()
            except Exception as exc:
                st.error(f"Error durante el procesamiento: {exc}")

    if not can_run:
        invalidos = [s for s, d in distancias.items() if d > MAX_DIST_M]
        st.warning(
            "Corrige las distancias antes de lanzar el procesamiento. "
            f"Escenarios fuera de limite: {', '.join(invalidos)}"
        )


# ── Página de resultados ──────────────────────────────────────────────────────

def _render_results():
    resultados = st.session_state.get("resultados", {})
    escenarios = st.session_state.get(
        "escenarios_procesados", sorted(resultados.keys(), key=lambda x: (len(x), x))
    )

    if st.button("← Volver a configuracion"):
        st.session_state.pantalla = "input"
        st.rerun()

    perfiles_usados = st.session_state.get("perfiles_procesados")
    if perfiles_usados:
        with st.expander("Pesos de capas usados en este procesamiento", expanded=False):
            filas = []
            for p in perfiles_usados:
                row = {"Perfil": _NOMBRE_PERFIL.get(p["id"], p["id"])}
                for clave, etiqueta in _CAPAS_PESO:
                    row[etiqueta.split(" (")[0]] = p.get("pesos", {}).get(clave, 0.0)
                filas.append(row)
            st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    tab_labels = ["Mapa de rutas"] + [f"Metricas — Escenario {s}" for s in escenarios] + [
        "Diversidad de corredores"
    ]
    tabs = st.tabs(tab_labels)
    tab_mapa = tabs[0]
    tabs_metricas = {s: tabs[i + 1] for i, s in enumerate(escenarios)}
    tab_div = tabs[-1]

    # ── Tab mapa ──────────────────────────────────────────────────────────────
    with tab_mapa:
        m = _mapa_resultados(escenarios)
        if m is None:
            st.warning("No se encontraron archivos de rutas en Rutas/")
        elif _HAS_ST_FOLIUM:
            _st_folium(m, key="mapa_resultados", height=460,
                       use_container_width=True, returned_objects=[])
        else:
            from streamlit.components.v1 import html as _html
            _html(m._repr_html_(), height=640)

    # ── Tabs métricas ─────────────────────────────────────────────────────────
    col_rename = {
        "perfil":                "Perfil",
        "longitud_km":           "km",
        "coste_relativo":        "Coste rel.",
        "pendiente_max_pct":     "Pend.max %",
        "pendiente_media_pct":   "Pend.med %",
        "km_protegida":          "km prot.",
        "km_inundable":          "km inund.",
        "km_suelo_urbano":       "km urbano",
        "n_cruces_rios":         "Rios",
        "n_cruces_carreteras":   "Carreteras",
        "n_cruces_ferrocarril":  "FFCC",
    }

    for s in escenarios:
        tab = tabs_metricas[s]
        with tab:
            res = resultados.get(s, {})
            rutas = res.get("rutas", [])
            if not rutas:
                st.info("Sin rutas calculadas para este escenario.")
                continue

            rows = [r.to_dict() for r in rutas]
            df = pd.DataFrame(rows)
            cols = [c for c in col_rename if c in df.columns]
            df_show = df[cols].rename(columns=col_rename)
            df_show["Perfil"] = df_show["Perfil"].map(
                lambda p: _NOMBRE_PERFIL.get(p, p)
            )

            st.dataframe(
                df_show.style.format({
                    "km":          "{:.2f}",
                    "Coste rel.":  "{:.3f}",
                    "Pend.max %":  "{:.1f}",
                    "Pend.med %":  "{:.2f}",
                    "km prot.":    "{:.3f}",
                    "km urbano":   "{:.3f}",
                }),
                use_container_width=True,
                hide_index=True,
            )

    # ── Tab diversidad ────────────────────────────────────────────────────────
    with tab_div:
        for s in escenarios:
            res = resultados.get(s, {})
            div = res.get("diversidad", {})
            st.markdown(f"#### Escenario {s}")

            if not div:
                st.info("Diversidad no calculada.")
                continue

            perfiles_div = div.get("perfiles", [])
            buf = div.get("buffer_m", 60)
            st.caption(
                f"Solapamiento dirigido (%) — buffer corredor: {buf:.0f} m. "
                f"Celda (fila i, col j): % de la longitud de la ruta i que discurre "
                f"dentro del corredor de j."
            )

            if len(perfiles_div) < 2:
                st.info("Se necesitan al menos 2 rutas para comparar.")
            else:
                matriz = div.get("matriz", {})
                nombres = [_NOMBRE_PERFIL.get(p, p) for p in perfiles_div]
                data = []
                for pi in perfiles_div:
                    row = []
                    for pj in perfiles_div:
                        if pi == pj:
                            row.append("-")
                        else:
                            val = matriz.get(pi, {}).get(pj, 0.0)
                            row.append(f"{val:.1f}%")
                    data.append(row)
                df_matriz = pd.DataFrame(data, index=nombres, columns=nombres)
                st.dataframe(df_matriz, use_container_width=True)

            st.markdown("---")


# ── Entry point ───────────────────────────────────────────────────────────────

def _main():
    import logging
    logging.disable(logging.WARNING)

    import base64
    _LOGO_PATH = Path(__file__).parent / "assets" / "Logo.png"
    _logo_tag = (
        f'<img src="data:image/png;base64,{base64.b64encode(_LOGO_PATH.read_bytes()).decode()}"'
        f' height="52" style="display:block;">'
        if _LOGO_PATH.exists() else ""
    )

    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="enagas-page-header">'
        f'<div>{_logo_tag}</div>'
        f'<div class="header-divider"></div>'
        f'<div>'
        f'<div class="header-title">Generador de Trazados de Ramales H₂</div>'
        f'<div class="header-subtitle">CI2 Lab 2026 &nbsp;&middot;&nbsp; Enagás</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if "pantalla" not in st.session_state:
        st.session_state.pantalla = "input"

    if st.session_state.pantalla == "resultados":
        _render_results()
    else:
        _render_input()


_main()
