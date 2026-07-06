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
from shapely.geometry import LineString
from shapely.geometry import box as _shp_box
from shapely.ops import unary_union

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
    "pendiente":  "Relieve (TPI)",
}

# Claves de peso en perfiles.yaml → etiqueta en la UI
_CAPAS_PESO: list[tuple[str, str]] = [
    ("longitud",     "Longitud (distancia)"),
    ("tpi",          "Relieve (TPI)"),
    ("protegida",    "Zonas protegidas"),
    ("inundable",    "Zonas inundables"),
    ("cruces",       "Cruces (vias y rios)"),
    ("expropiacion", "Expropiacion (catastro)"),
    ("geotecnia",    "Geotecnia (litologia)"),
]
_PESO_MIN, _PESO_MAX, _PESO_STEP = 0, 100, 1

try:
    from streamlit_folium import st_folium as _st_folium
    _HAS_ST_FOLIUM = True
except ImportError:
    _HAS_ST_FOLIUM = False

# ── CSS — design system "Enagás Engineering Core" (Stitch) ────────────────────
# Tokens (paleta Material 3 corporativa Enagás), tipografías (Hanken Grotesk /
# Inter / JetBrains Mono) y componentes trasladados del diseño de Stitch.
_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Hanken+Grotesk:wght@600;700;800&family=Lora:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=swap');

  .material-symbols-outlined {
    font-family: 'Material Symbols Outlined';
    font-weight: normal; font-style: normal;
    font-size: 20px; line-height: 1; vertical-align: middle;
    display: inline-block; letter-spacing: normal; text-transform: none;
    white-space: nowrap; direction: ltr;
  }

  :root {
    --primary:            #004e7e;
    --primary-container:  #0067a3;
    --on-primary:         #ffffff;
    --secondary:          #4b6700;
    --secondary-container:#c3f35c;
    --tertiary:           #094f7a;
    --surface:            #f7fafc;
    --surface-lowest:     #ffffff;
    --surface-low:        #f1f4f6;
    --surface-container:  #ebeef0;
    --surface-high:       #e5e9eb;
    --surface-highest:    #e0e3e5;
    --on-surface:         #181c1e;
    --on-surface-variant: #404750;
    --outline:            #717881;
    --outline-variant:    #c0c7d1;
    --error:              #ba1a1a;

    --font-body: 'Inter', 'Segoe UI', Arial, sans-serif;
    --font-head: 'Hanken Grotesk', 'Segoe UI', Arial, sans-serif;
    --font-serif: 'Lora', Georgia, 'Times New Roman', serif;
    --font-mono: 'JetBrains Mono', ui-monospace, monospace;

    --radius-sm: 4px;
    --radius:    8px;
    --radius-xl: 12px;
    --shadow-card: 0 1px 3px rgba(0,75,118,0.06);
    --shadow-pop:  0 4px 24px rgba(0,75,118,0.12);
  }

  /* Quitar el hueco superior por defecto de Streamlit (cabecera oculta) */
  [data-testid="stMainBlockContainer"],
  [data-testid="stAppViewBlockContainer"],
  .block-container {
    padding-top: 1.1rem !important;
    padding-bottom: 1.1rem !important;
  }
  .stApp {
    background-color: var(--surface);
    color: var(--on-surface);
    font-family: var(--font-body);
  }
  .stApp p, .stApp li, .stApp label {
    color: var(--on-surface);
    font-family: var(--font-body);
  }
  .stApp h1, .stApp h2, .stApp h3, .stApp h4 {
    font-family: var(--font-head);
    color: var(--on-surface);
    letter-spacing: -0.01em;
  }
  div[data-testid="stMarkdownContainer"] * { color: var(--on-surface); }
  div[data-testid="stDataFrame"] * { color: var(--on-surface) !important; }

  /* ── Barra superior unificada ─────────────────────────────────────────── */
  .enagas-topnav {
    background: var(--surface-lowest);
    border-bottom: 1px solid var(--outline-variant);
    box-shadow: var(--shadow-card);
    padding: 12px 28px;
    margin: -0.4rem 0 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
  }
  .topnav-left { display: flex; align-items: center; gap: 14px; }
  .topnav-logo { height: 34px; display: block; }
  .topnav-divider {
    width: 1px; height: 26px; background: var(--outline-variant); margin: 0 2px;
  }
  .topnav-title {
    font-family: var(--font-head);
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--primary);
    line-height: 1.15;
  }
  .topnav-badge {
    font-family: var(--font-body);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--on-surface-variant);
    background: var(--surface-container);
    border: 1px solid var(--outline-variant);
    border-radius: 999px;
    padding: 5px 14px;
  }

  /* ── Stepper de progreso ──────────────────────────────────────────────── */
  .enagas-stepper {
    display: flex;
    align-items: center;
    gap: 0;
    background: rgba(247,250,252,0.7);
    border: 1px solid var(--outline-variant);
    border-radius: var(--radius-xl);
    padding: 12px 22px;
    margin-bottom: 16px;
  }
  .step { display: flex; align-items: center; gap: 10px; }
  .step-num {
    width: 30px; height: 30px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-family: var(--font-body); font-weight: 700; font-size: 0.85rem;
    flex-shrink: 0;
  }
  .step.done   .step-num { background: var(--primary); color: #fff; }
  .step.active .step-num { background: var(--secondary); color: #fff;
                           box-shadow: 0 0 0 4px var(--secondary-container); }
  .step.pending .step-num { background: transparent; color: var(--outline);
                            border: 2px solid var(--outline); }
  .step-txt { display: flex; flex-direction: column; line-height: 1.1; }
  .step-kicker {
    font-family: var(--font-body); font-size: 0.62rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.06em; color: var(--outline);
  }
  .step.active .step-kicker { color: var(--secondary); }
  .step.done   .step-kicker { color: var(--primary); }
  .step-name {
    font-family: var(--font-body); font-size: 0.86rem; font-weight: 700;
    color: var(--on-surface);
  }
  .step.pending .step-name { color: var(--on-surface-variant); font-weight: 500; }
  .step-conn { flex: 1; height: 2px; background: var(--outline-variant); margin: 0 18px; }
  .step-conn.done { background: var(--primary); }

  /* ── Tarjetas con borde (container border=True) ───────────────────────── */
  div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--surface-lowest);
    border: 1px solid var(--outline-variant);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-card);
  }
  .scenario-title {
    font-family: var(--font-head);
    color: var(--primary);
    font-size: 1.05rem;
    font-weight: 700;
    margin: 0 0 6px;
    display: flex; align-items: center; gap: 8px;
  }
  .scenario-title::before {
    content: ""; width: 6px; height: 20px;
    background: var(--secondary-container); border-radius: 999px;
  }

  /* ── Badge de restricciones (info) ────────────────────────────────────── */
  .constraints-box {
    background: rgba(0,103,163,0.06);
    border: 1px solid rgba(0,103,163,0.22);
    border-radius: var(--radius);
    padding: 10px 16px;
    margin-bottom: 12px;
    font-size: 0.82rem;
    color: var(--on-surface-variant);
    font-family: var(--font-body);
  }
  .constraints-box b { color: var(--primary); }

  /* ── Etiquetas de sección (label-caps) ────────────────────────────────── */
  .section-label {
    font-family: var(--font-body);
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--on-surface-variant);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 2px;
  }

  /* ── Inputs numéricos / selects: aire técnico + mono en cifras ────────── */
  div[data-testid="stNumberInput"] input {
    font-family: var(--font-mono) !important;
    font-size: 0.85rem !important;
  }
  div[data-testid="stNumberInput"] div[data-baseweb="input"],
  div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
  div[data-testid="stTextInput"] div[data-baseweb="input"] {
    border-radius: var(--radius-sm) !important;
    border-color: var(--outline-variant) !important;
    background: var(--surface-lowest) !important;
  }
  div[data-testid="stNumberInput"] div[data-baseweb="input"]:focus-within,
  div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 1px var(--primary) !important;
  }

  /* ── Sliders con acento primario ──────────────────────────────────────── */
  div[data-testid="stSlider"] div[role="slider"] {
    background: var(--primary) !important;
    border: 2px solid #fff !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.25) !important;
  }
  div[data-testid="stSlider"] div[data-baseweb="slider"] > div > div {
    background: var(--primary) !important;
  }

  /* ── Pestañas: subrayado con acento primario ──────────────────────────── */
  button[data-baseweb="tab"] {
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    color: var(--on-surface-variant) !important;
  }
  button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--primary) !important;
  }
  div[data-baseweb="tab-highlight"] { background: var(--primary) !important; }
  div[data-baseweb="tab-border"]    { background: var(--outline-variant) !important; }

  /* ── Tablas (DataFrame): cabecera en versalitas + celdas mono ─────────── */
  div[data-testid="stDataFrame"] {
    border-radius: var(--radius-xl);
    border: 1px solid var(--outline-variant);
    overflow: hidden;
  }
  div[data-testid="stDataFrame"] thead th {
    background: var(--surface-highest) !important;
    text-transform: uppercase;
    font-family: var(--font-body) !important;
    font-size: 0.68rem !important;
    letter-spacing: 0.05em;
    font-weight: 600 !important;
    color: var(--on-surface-variant) !important;
  }
  div[data-testid="stDataFrame"] tbody td {
    font-family: var(--font-mono) !important;
    font-size: 0.8rem !important;
  }

  /* ── Botones ──────────────────────────────────────────────────────────── */
  div[data-testid="stButton"] > button {
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--primary) !important;
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
    background: var(--surface-lowest) !important;
    transition: background 0.15s, color 0.15s;
  }
  div[data-testid="stButton"] > button p,
  div[data-testid="stButton"] > button span,
  div[data-testid="stButton"] > button div {
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
    background: transparent !important;
    border: none !important;
  }
  div[data-testid="stButton"] > button:hover {
    background: var(--surface-container) !important;
    border-color: var(--primary-container) !important;
  }
  div[data-testid="stButton"] > button:disabled,
  div[data-testid="stButton"] > button:disabled p,
  div[data-testid="stButton"] > button:disabled span,
  div[data-testid="stButton"] > button:disabled div {
    color: var(--outline) !important;
    -webkit-text-fill-color: var(--outline) !important;
    background: var(--surface-container) !important;
    border-color: var(--outline-variant) !important;
    opacity: 1 !important;
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
    background: var(--primary) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.2px !important;
    padding: 12px 28px !important;
    box-shadow: var(--shadow-card);
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: var(--primary-container) !important;
    filter: brightness(1.05);
  }

  /* Botón verde (secundario Enagás) — "Comenzar simulación" en bienvenida */
  .st-key-btn_welcome_start div[data-testid="stButton"] > button {
    background: var(--secondary) !important;
    border: 1px solid var(--secondary) !important;
  }
  .st-key-btn_welcome_start div[data-testid="stButton"] > button,
  .st-key-btn_welcome_start div[data-testid="stButton"] > button * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
  }
  .st-key-btn_welcome_start div[data-testid="stButton"] > button:hover {
    background: #3d5600 !important;
    border-color: #3d5600 !important;
  }

  /* ── Barra superior: zona derecha (iconos + perfil) ───────────────────── */
  .topnav-right { display: flex; align-items: center; gap: 14px; }
  .topnav-icon {
    color: var(--on-surface-variant);
    display: flex; align-items: center; justify-content: center;
    width: 34px; height: 34px; border-radius: 50%;
  }
  /* ── Footer técnico ───────────────────────────────────────────────────── */
  .enagas-footer {
    margin-top: 26px;
    background: var(--surface-lowest);
    border-top: 1px solid var(--outline-variant);
    border-radius: var(--radius) var(--radius) 0 0;
    padding: 12px 28px;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 8px;
  }
  .enagas-footer .foot-left { display: flex; align-items: center; gap: 14px; }
  .enagas-footer .foot-brand {
    font-family: var(--font-body); font-weight: 700; font-size: 0.72rem;
    letter-spacing: 0.05em; text-transform: uppercase; color: var(--on-surface-variant);
  }
  .enagas-footer .foot-mono,
  .enagas-footer .foot-links a {
    font-family: var(--font-mono); font-size: 0.72rem; color: var(--outline);
    text-decoration: none;
  }
  .enagas-footer .foot-links { display: flex; align-items: center; gap: 20px; }
  .enagas-footer .foot-links a:hover { color: var(--primary); }
  .enagas-footer .foot-ver {
    font-family: var(--font-mono); font-size: 0.65rem; color: var(--on-surface-variant);
    background: var(--surface-highest); border-radius: var(--radius-sm); padding: 2px 8px;
  }
  .enagas-footer .foot-green { color: var(--secondary); }

  /* ── Pantalla de bienvenida ───────────────────────────────────────────── */
  .welcome-wrap { max-width: 940px; margin: 6px auto 0; text-align: center; }
  .welcome-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--secondary-container); color: var(--secondary);
    font-family: var(--font-body); font-weight: 700; font-size: 0.72rem;
    letter-spacing: 0.03em; padding: 6px 16px; border-radius: 999px;
  }
  .welcome-title {
    font-family: var(--font-head); font-size: 2.4rem; font-weight: 800;
    color: var(--primary); margin: 18px 0 12px; letter-spacing: -0.02em;
  }
  .welcome-sub {
    font-family: var(--font-body); color: var(--on-surface-variant);
    font-size: 0.98rem; max-width: 640px; margin: 0 auto 6px; line-height: 1.55;
  }
  .welcome-card-head { text-align: left; }
  .welcome-card-icon {
    width: 48px; height: 48px; border-radius: var(--radius);
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 14px;
  }
  .welcome-card-icon .material-symbols-outlined { font-size: 26px; }
  .icon-primary   { background: rgba(0,103,163,0.10); color: var(--primary); }
  .icon-secondary { background: rgba(75,103,0,0.12);  color: var(--secondary); }
  .welcome-card-title {
    font-family: var(--font-head); color: var(--primary);
    font-size: 1.25rem; font-weight: 700; margin: 0 0 8px;
  }
  .welcome-card-txt { color: var(--on-surface-variant); font-size: 0.88rem;
                      margin: 0 0 4px; line-height: 1.5; }

  /* ── Hero de resultados ───────────────────────────────────────────────── */
  .results-back {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--font-body); font-weight: 700; font-size: 0.72rem;
    letter-spacing: 0.05em; text-transform: uppercase; color: var(--primary);
  }
  .results-title {
    font-family: var(--font-head); font-size: 2rem; font-weight: 700;
    color: var(--on-surface); margin: 6px 0 6px; letter-spacing: -0.02em;
  }
  .results-sub { color: var(--on-surface-variant); font-size: 0.9rem; max-width: 640px; }
  .results-actions { display: flex; gap: 12px; }
  .btn-ghost, .btn-solid {
    display: inline-flex; align-items: center; gap: 8px;
    font-family: var(--font-body); font-weight: 700; font-size: 0.82rem;
    padding: 9px 18px; border-radius: var(--radius-sm); cursor: default;
  }
  .btn-ghost { border: 1px solid var(--primary); color: var(--primary); background: var(--surface-lowest); }
  .btn-solid { background: var(--primary); color: #fff; border: 1px solid var(--primary); }

  /* ── Encabezado de sección (Paso 2) ───────────────────────────────────── */
  .section-h1 {
    font-family: var(--font-head); font-size: 1.7rem; font-weight: 700;
    color: var(--primary); margin: 0 0 4px; letter-spacing: -0.02em;
  }
  .section-desc { color: var(--on-surface-variant); font-size: 0.88rem;
                  max-width: 720px; line-height: 1.5; }

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
    """Editor de pesos por capa (tarjeta). Devuelve la lista de perfiles actualizada."""
    _init_perfiles_session()
    perfiles = st.session_state.perfiles_cfg

    with st.container(border=True):
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
        st.markdown(
            f'<p style="font-style:italic;color:var(--on-surface-variant);'
            f'font-size:0.85rem;margin:2px 0 12px;">{perfil.get("descripcion", "")}</p>',
            unsafe_allow_html=True,
        )

        col_a, col_b = st.columns(2, gap="large")
        pesos = perfil.setdefault("pesos", {})
        ver = st.session_state.pesos_version
        suma_pct = 0
        for i, (clave, etiqueta) in enumerate(_CAPAS_PESO):
            col = col_a if i % 2 == 0 else col_b
            with col:
                pct = st.slider(
                    etiqueta,
                    min_value=_PESO_MIN,
                    max_value=_PESO_MAX,
                    value=int(round(float(pesos.get(clave, 0.0)) * 100)),
                    step=_PESO_STEP,
                    format="%d%%",
                    key=f"peso_{pid}_{clave}_v{ver}",
                )
                pesos[clave] = pct / 100
                suma_pct += pct

        suma_color = "var(--secondary)" if suma_pct == 100 else "var(--error)"
        st.markdown(
            f'<p style="font-family:var(--font-mono);font-size:0.82rem;'
            f'color:var(--on-surface-variant);margin-top:10px;">Suma de pesos: '
            f'<b style="color:{suma_color};">{suma_pct}%</b>'
            f'<span style="opacity:0.6;margin-left:6px;">(recomendado: 100%)</span></p>',
            unsafe_allow_html=True,
        )

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

    return perfiles


def _tabla_comparativa_perfiles(perfiles: list[dict]) -> None:
    """Tabla resumen de los pesos por perfil (en %)."""
    filas = []
    for p in perfiles:
        row = {"Perfil": _NOMBRE_PERFIL.get(p["id"], p["id"])}
        for clave, etiqueta in _CAPAS_PESO:
            v = p.get("pesos", {}).get(clave, 0.0)
            row[etiqueta.split(" (")[0]] = f"{round(v * 100)}%"
        filas.append(row)
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)


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
    from ingesta.preparar_escenario import escenario_preparado, preparar

    if not escenarios:
        raise ValueError("No hay escenarios configurados.")

    n = len(escenarios)
    avisos_prep: dict[str, list[str]] = {}
    for i, s in enumerate(escenarios):
        base = 0.05 + 0.75 * i / n
        span = 0.75 / n
        # Un escenario nuevo no tiene capas de coste: se auto-preparan
        # (descarga GIS + alineación + superficies) antes de trazar. Si falla
        # (sin internet, servicio caído), preparar() lanza PreparacionError con
        # un mensaje claro que se muestra en la UI.
        if not escenario_preparado(s):
            progress_cb(base, f"Preparando escenario {s} (descarga + alineación)…")
            res_prep = preparar(
                s,
                progress_cb=lambda pct, msg, b=base, sp=span: progress_cb(
                    b + sp * 0.7 * pct, msg
                ),
            )
            if res_prep.get("avisos"):
                avisos_prep[s] = res_prep["avisos"]
        progress_cb(base + span * 0.72, f"Calculando rutas — Escenario {s}…")
        run_perfiles(s, perfiles_override=perfiles)

    st.session_state["avisos_preparacion"] = avisos_prep

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

    # Cursor de puntería sobre el mapa: al fijar origen/destino el usuario ve una
    # cruz precisa en vez de la manita de arrastre. La marca de mira sigue al raton.
    m.get_root().header.add_child(folium.Element("""
    <style>
      .leaflet-container, .leaflet-grab, .leaflet-interactive,
      .leaflet-container.leaflet-grab { cursor: crosshair !important; }
      .leaflet-container:active { cursor: crosshair !important; }
    </style>
    """))

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
      <span class="c-pendiente" style="font-size:1.3em;">&#9644;</span><span> Relieve (TPI)</span>
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


# ── Disponibilidad de capas para el AOI elegido ────────────────────────────────
#
# Al mover origen/destino el AOI se recalcula (mismo criterio que la ingesta:
# corredor de 1 km a cada lado de la linea origen-destino). Casi todas las capas
# se obtienen automaticamente por bbox (DEM, hidrografia, geologia, viario, RN2000
# via WFS, inundables SNCZI). La excepcion es CATASTRO: se descarga por municipios
# a mano (Sede Catastro INSPIRE), asi que aqui comprobamos de verdad si el AOI
# nuevo cae dentro de lo ya preparado (recortes catastro_aoi_*.gpkg).

_AOI_BUFFER_M = 1000.0  # 1 km a cada lado — mismo valor que src.ingesta.descargar_capas


def _aoi_bounds(coords_esc: dict) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) del corredor actual en EPSG:25830."""
    line = LineString([
        (coords_esc["origen"]["x"], coords_esc["origen"]["y"]),
        (coords_esc["destino"]["x"], coords_esc["destino"]["y"]),
    ])
    return line.buffer(_AOI_BUFFER_M, cap_style=2).bounds


@st.cache_data(show_spinner=False)
def _catastro_cobertura_wkt(recorte_dir: str) -> str | None:
    """Envolvente (WKT) de la cobertura de catastro ya preparada (recortes A/B, …).

    Se cachea porque implica leer los GPKG. Devolvemos WKT para que el valor sea
    hasheable/serializable por st.cache_data.
    """
    cajas = []
    for p in sorted(Path(recorte_dir).glob("catastro_aoi_*.gpkg")):
        try:
            b = gpd.read_file(p).total_bounds  # xmin, ymin, xmax, ymax
        except Exception:
            continue
        if b is not None and not any(np.isnan(b)):
            cajas.append(_shp_box(*b))
    if not cajas:
        return None
    return unary_union(cajas).wkt


def _estado_datos_aoi(coords_esc: dict) -> list[dict]:
    """Estado por capa para el corredor actual.

    Cada item: {nombre, estado ∈ {ok, warn, rec}, detalle}. 'ok' verde (se tiene
    o se descarga sola), 'warn' ambar (verificar / aportar a mano), 'rec' azul
    (recomendado incluir).
    """
    from shapely import wkt as _wkt

    xmin, ymin, xmax, ymax = _aoi_bounds(coords_esc)
    aoi = _shp_box(xmin, ymin, xmax, ymax)

    # Catastro — comprobacion real de cobertura contra lo ya descargado/preparado
    cob_wkt = _catastro_cobertura_wkt(str(_ROOT / "data" / "processed" / "Recorte_AOI"))
    frac = 0.0
    if cob_wkt and aoi.area > 0:
        try:
            frac = aoi.intersection(_wkt.loads(cob_wkt)).area / aoi.area
        except Exception:
            frac = 0.0
    if frac >= 0.99:
        cat = ("ok", "Cubierto por lo ya descargado")
    elif frac > 0.01:
        cat = ("warn", f"Cobertura parcial (~{frac * 100:.0f}%) · completar en Sede Catastro INSPIRE")
    else:
        cat = ("warn", "Fuera de lo descargado · aportar a mano (Sede Catastro INSPIRE)")

    return [
        {"nombre": "Catastro (expropiación)", "estado": cat[0], "detalle": cat[1]},
        {"nombre": "Red Natura 2000", "estado": "warn",
         "detalle": "Obtenible por zona (WFS IDEE); recomendado fichero nacional MITECO"},
        {"nombre": "Zonas inundables (SNCZI)", "estado": "rec",
         "detalle": "Obtenibles por zona · se recomienda incluirlas en el coste"},
        {"nombre": "DEM · Hidrografía · Geología · Viario (OSM)", "estado": "ok",
         "detalle": "Se descargan automáticamente por zona (bbox)"},
    ]


def _render_estado_datos(coords_esc: dict) -> None:
    """Tarjeta de disponibilidad de capas para el corredor origen-destino actual."""
    try:
        items = _estado_datos_aoi(coords_esc)
    except Exception:
        return  # ante cualquier fallo (ficheros/shapely) no romper el Paso 1

    _ICONO = {
        "ok":   ("check_circle", "var(--secondary)"),
        "warn": ("warning",      "#b26a00"),
        "rec":  ("lightbulb",    "var(--primary)"),
    }
    filas = ""
    for it in items:
        icono, color = _ICONO[it["estado"]]
        filas += (
            f'<div style="display:flex;align-items:flex-start;gap:9px;padding:6px 0;'
            f'border-top:1px solid var(--surface-high);">'
            f'<span class="material-symbols-outlined" style="font-size:18px;color:{color};'
            f'line-height:1.15;flex:none;">{icono}</span>'
            f'<div style="line-height:1.25;">'
            f'<span style="font-family:var(--font-body);font-weight:700;font-size:0.78rem;'
            f'color:var(--on-surface);">{it["nombre"]}</span><br>'
            f'<span style="font-family:var(--font-body);font-size:0.7rem;'
            f'color:var(--on-surface-variant);">{it["detalle"]}</span></div></div>'
        )
    st.markdown(
        f'<div style="background:var(--surface-lowest);border:1px solid var(--outline-variant);'
        f'border-radius:14px;box-shadow:var(--shadow-card);padding:12px 16px 8px;margin-top:10px;">'
        f'<div style="display:flex;align-items:center;gap:6px;color:var(--primary);'
        f'font-weight:700;margin-bottom:2px;">'
        f'<span class="material-symbols-outlined" style="font-size:18px;">dataset</span>'
        f'<span style="font-size:0.68rem;letter-spacing:0.05em;text-transform:uppercase;">'
        f'Datos para esta zona</span></div>'
        f'{filas}</div>',
        unsafe_allow_html=True,
    )


# ── Paso 1: Origen y Destino ───────────────────────────────────────────────────

def _init_estado_entrada(cfg: dict) -> None:
    ids_cfg = _ids_escenarios(cfg)
    if "coords" not in st.session_state:
        st.session_state.coords = _coords_desde_cfg(cfg)
    else:
        for sid in ids_cfg:
            if sid not in st.session_state.coords:
                st.session_state.coords[sid] = _coords_desde_cfg(cfg)[sid]
    if ("escenario_activo" not in st.session_state
            or st.session_state.escenario_activo not in st.session_state.coords):
        st.session_state.escenario_activo = ids_cfg[0] if ids_cfg else "A"
    if "punto_activo_rol" not in st.session_state:
        st.session_state.punto_activo_rol = "origen"
    if "_last_click" not in st.session_state:
        st.session_state._last_click = None


def _render_paso1():
    cfg = _leer_cfg()
    _init_estado_entrada(cfg)

    coords = st.session_state.coords
    escenarios = sorted(coords.keys(), key=lambda x: (len(x), x))
    esc_activo = st.session_state.escenario_activo

    col_panel, col_map = st.columns([1, 2], gap="large")

    with col_panel:
        with st.container(border=True):
            st.markdown(
                '<div class="constraints-box">'
                '<div style="display:flex;align-items:center;gap:6px;color:var(--primary);'
                'font-weight:700;margin-bottom:5px;">'
                '<span class="material-symbols-outlined" style="font-size:18px;">info</span>'
                '<span style="font-size:0.68rem;letter-spacing:0.05em;text-transform:uppercase;">'
                'Restricciones del modelo</span></div>'
                'Corredor de referencia: <b>2 km de ancho</b> (&plusmn;1 km a cada lado).<br>'
                'Distancia máxima origen&ndash;destino: <b>15 km</b>.'
                '</div>',
                unsafe_allow_html=True,
            )

            esc_activo = st.selectbox(
                "Escenario",
                options=escenarios,
                index=escenarios.index(st.session_state.escenario_activo)
                if st.session_state.escenario_activo in escenarios else 0,
                format_func=lambda s: f"Escenario {s}",
                key="select_escenario",
            )
            st.session_state.escenario_activo = esc_activo

            with st.expander("＋ Crear nuevo escenario", expanded=False):
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
                f'<div class="scenario-title">Escenario {esc_activo}</div>',
                unsafe_allow_html=True,
            )
            # Sembrar el estado de cada widget una sola vez desde coords. A partir
            # de aqui el session_state del widget (clave f"{esc}_{rol}_{eje}") es la
            # fuente de verdad: asi el clic en el mapa puede escribir en el sin que
            # el number_input revierta al valor previo en el siguiente rerun.
            for rol in ("origen", "destino"):
                for eje in ("x", "y"):
                    k = f"{esc_activo}_{rol}_{eje}"
                    if k not in st.session_state:
                        st.session_state[k] = int(coords[esc_activo][rol][eje])

            # Aplicar un clic pendiente del mapa ANTES de instanciar los number_input
            # (Streamlit prohibe modificar la clave de un widget ya instanciado).
            pend = st.session_state.pop("_pending_click", None)
            if pend is not None:
                st.session_state[f"{pend['esc']}_{pend['rol']}_x"] = pend["x"]
                st.session_state[f"{pend['esc']}_{pend['rol']}_y"] = pend["y"]

            for rol in ("origen", "destino"):
                punto = "#4b6700" if rol == "origen" else "#004e7e"
                st.markdown(
                    f'<p class="section-label" style="display:flex;align-items:center;gap:6px;">'
                    f'<span style="width:8px;height:8px;border-radius:50%;background:{punto};'
                    f'display:inline-block;"></span>{rol.capitalize()}</p>',
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2)
                with c1:
                    st.number_input(
                        "X (m)", step=1, format="%d", key=f"{esc_activo}_{rol}_x",
                    )
                with c2:
                    st.number_input(
                        "Y (m)", step=1, format="%d", key=f"{esc_activo}_{rol}_y",
                    )
                coords[esc_activo][rol]["x"] = st.session_state[f"{esc_activo}_{rol}_x"]
                coords[esc_activo][rol]["y"] = st.session_state[f"{esc_activo}_{rol}_y"]

            dist = _dist_m(
                coords[esc_activo]["origen"]["x"], coords[esc_activo]["origen"]["y"],
                coords[esc_activo]["destino"]["x"], coords[esc_activo]["destino"]["y"],
            )
            km_txt = f"{dist / 1000:.1f}".replace(".", ",")
            supera = dist > MAX_DIST_M
            acento = "var(--error)" if supera else "var(--primary)"
            nota = (
                f'<span style="color:var(--error);font-weight:700;font-size:0.62rem;'
                f'letter-spacing:0;text-transform:none;margin-left:8px;">'
                f'· supera {MAX_DIST_M / 1000:.0f} km</span>'
            ) if supera else ""
            st.markdown(
                f'<div style="display:flex;align-items:stretch;gap:14px;'
                f'background:var(--surface-lowest);border:1px solid var(--outline-variant);'
                f'border-radius:14px;box-shadow:var(--shadow-card);'
                f'padding:15px 20px;margin-top:8px;">'
                f'<div style="width:5px;flex:none;border-radius:99px;background:{acento};"></div>'
                f'<div style="flex:1;display:flex;align-items:center;justify-content:space-between;gap:10px;">'
                f'<span style="font-family:var(--font-body);color:var(--outline);font-weight:700;'
                f'font-size:0.72rem;letter-spacing:0.07em;text-transform:uppercase;">'
                f'Distancia total{nota}</span>'
                f'<span style="font-family:var(--font-serif);font-weight:700;color:{acento};'
                f'font-size:1.35rem;line-height:1;font-variant-numeric:tabular-nums;'
                f'display:inline-flex;align-items:baseline;gap:6px;white-space:nowrap;">'
                f'{km_txt}<span style="font-family:var(--font-serif);font-size:0.85rem;'
                f'font-weight:500;color:var(--outline);font-style:italic;">km</span>'
                f'</span></div></div>',
                unsafe_allow_html=True,
            )

            # Comprobacion de disponibilidad de capas para el corredor elegido
            _render_estado_datos(coords[esc_activo])

            if _HAS_ST_FOLIUM:
                st.markdown(
                    f'<p class="section-label" style="margin-top:12px;">'
                    f'Siguiente clic en el mapa fija ({esc_activo}):</p>',
                    unsafe_allow_html=True,
                )
                st.session_state.punto_activo_rol = st.radio(
                    "Punto activo",
                    options=["origen", "destino"],
                    format_func=str.capitalize,
                    index=0 if st.session_state.punto_activo_rol == "origen" else 1,
                    label_visibility="collapsed",
                    horizontal=True,
                    key="radio_punto_rol",
                )

        st.markdown(
            '<div style="display:flex;gap:16px;margin-top:10px;font-size:0.78rem;">'
            '<span style="display:flex;align-items:center;gap:6px;font-weight:600;">'
            '<span style="width:11px;height:11px;border-radius:50%;background:#4b6700;'
            'display:inline-block;"></span>Origen (O)</span>'
            '<span style="display:flex;align-items:center;gap:6px;font-weight:600;">'
            '<span style="width:11px;height:11px;border-radius:50%;background:#004e7e;'
            'display:inline-block;"></span>Destino (D)</span></div>',
            unsafe_allow_html=True,
        )

    with col_map:
        m = _mapa_entrada(coords, esc_activo)
        if _HAS_ST_FOLIUM:
            map_data = _st_folium(
                m,
                key="mapa_entrada",
                height=480,
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
                    # Guardar el clic como pendiente: se aplica al estado de los
                    # widgets al inicio del proximo run, antes de instanciarlos.
                    st.session_state._pending_click = {
                        "esc": esc_activo, "rol": rol,
                        "x": round(x_utm), "y": round(y_utm),
                    }
                    st.rerun()
        else:
            from streamlit.components.v1 import html as _html
            _html(m._repr_html_(), height=560)

    # ── Navegación ────────────────────────────────────────────────────────────
    distancias = {
        s: _dist_m(
            coords[s]["origen"]["x"], coords[s]["origen"]["y"],
            coords[s]["destino"]["x"], coords[s]["destino"]["y"],
        )
        for s in escenarios
    }
    can_next = all(d <= MAX_DIST_M for d in distancias.values())

    st.markdown("---")
    c_back, _, c_next = st.columns([1.2, 2, 1.4])
    with c_back:
        if st.button("← Inicio", use_container_width=True, key="btn_p1_inicio"):
            st.session_state.pantalla = "bienvenida"
            st.rerun()
    with c_next:
        if st.button("Siguiente: Pesos y Perfiles  →", type="primary",
                     disabled=not can_next, use_container_width=True, key="btn_p1_next"):
            cfg = _aplicar_coords_a_cfg(cfg, coords)
            _guardar_cfg(cfg)
            st.session_state.pantalla = "paso2"
            st.rerun()

    if not can_next:
        invalidos = [s for s, d in distancias.items() if d > MAX_DIST_M]
        st.warning(
            "Corrige las distancias antes de continuar. "
            f"Escenarios fuera de limite: {', '.join(invalidos)}"
        )


# ── Paso 2: Pesos y Perfiles ───────────────────────────────────────────────────

def _render_paso2():
    coords = st.session_state.get("coords") or _coords_desde_cfg(_leer_cfg())
    escenarios = sorted(coords.keys(), key=lambda x: (len(x), x))

    top = st.container()  # cabecera (título + botón "Generar rutas"), rellenada al final

    col_izq, col_der = st.columns([3, 2], gap="large")
    with col_izq:
        perfiles_cfg = _render_editor_pesos()
    with col_der:
        st.markdown(
            '<h3 style="font-family:var(--font-head);color:var(--on-surface);'
            'font-size:1.05rem;font-weight:700;margin:0 0 8px;">Comparativa de Perfiles</h3>',
            unsafe_allow_html=True,
        )
        _tabla_comparativa_perfiles(perfiles_cfg)

    generar = False
    with top:
        h_txt, h_btn = st.columns([3, 1])
        with h_txt:
            st.markdown(
                '<div class="section-h1">Paso 2: Pesos y Perfiles</div>'
                '<p class="section-desc">Cada perfil combina los pesos de coste, longitud, '
                'zonas protegidas, relieve y otros criterios. Los valores son índices relativos. '
                'Cada peso está acotado entre 0 y 1; la suma debe ser 1 (100%).</p>',
                unsafe_allow_html=True,
            )
        with h_btn:
            generar = st.button("Generar rutas", type="primary",
                                use_container_width=True, key="btn_generar_rutas")
        c_back, _ = st.columns([1.2, 3])
        with c_back:
            if st.button("← Origen y Destino", use_container_width=True, key="btn_p2_back"):
                st.session_state.pantalla = "paso1"
                st.rerun()

    if generar:
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


# ── Página de resultados ──────────────────────────────────────────────────────

def _kpis_resumen(resultados: dict, escenarios: list[str]) -> list[tuple[str, str, str]]:
    """KPIs agregados del escenario primario. Coste como índice relativo (nunca €)."""
    if not escenarios:
        return []
    res = resultados.get(escenarios[0], {})
    rutas = [r.to_dict() for r in res.get("rutas", [])]
    if not rutas:
        return []
    long_media = sum(r.get("longitud_km", 0.0) for r in rutas) / len(rutas)
    coste_medio = sum(r.get("coste_relativo", 0.0) for r in rutas) / len(rutas)
    pend_max = max((r.get("pendiente_max_pct", 0.0) for r in rutas), default=0.0)
    km_prot = sum(r.get("km_protegida", 0.0) for r in rutas)
    impacto = "Bajo" if km_prot < 0.5 else ("Medio" if km_prot < 2.0 else "Alto")
    return [
        ("route", "Longitud media", f"{long_media:.2f} km".replace(".", ",")),
        ("stacked_line_chart", "Coste relativo (índice)", f"{coste_medio:.3f}".replace(".", ",")),
        ("trending_up", "Pendiente máxima", f"{pend_max:.0f} %"),
        ("eco", "Impacto ambiental", impacto),
    ]


def _render_kpis(resultados: dict, escenarios: list[str]) -> None:
    kpis = _kpis_resumen(resultados, escenarios)
    if not kpis:
        return
    cols = st.columns(len(kpis), gap="medium")
    for col, (icon, label, value) in zip(cols, kpis):
        with col:
            with st.container(border=True):
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;">'
                    f'<span class="material-symbols-outlined" style="color:var(--primary);'
                    f'font-size:22px;background:rgba(0,103,163,0.10);border-radius:8px;'
                    f'padding:6px;">{icon}</span>'
                    f'<span style="font-size:0.8rem;color:var(--on-surface-variant);">{label}</span>'
                    f'</div>'
                    f'<div style="font-family:var(--font-head);font-size:1.6rem;font-weight:700;'
                    f'color:var(--on-surface);margin-top:8px;">{value}</div>',
                    unsafe_allow_html=True,
                )


def _render_results():
    resultados = st.session_state.get("resultados", {})
    escenarios = st.session_state.get(
        "escenarios_procesados", sorted(resultados.keys(), key=lambda x: (len(x), x))
    )

    if st.button("← Volver a configuración", key="btn_back_results"):
        st.session_state.pantalla = "paso2"
        st.rerun()

    st.markdown(
        '<div style="display:flex;justify-content:space-between;align-items:flex-end;'
        'gap:16px;flex-wrap:wrap;margin:2px 0 10px;">'
        '<div>'
        '<div class="results-title">Comparativa de Trazados de Ramales H₂</div>'
        '<p class="results-sub">Visualización métrica de indicadores de rendimiento para la red '
        'de transporte de hidrógeno renovable. Proyecto H2 Lab 2026.</p>'
        '</div>'
        '<div class="results-actions">'
        '<span class="btn-ghost"><span class="material-symbols-outlined" '
        'style="font-size:16px;">share</span>Compartir</span>'
        '<span class="btn-solid"><span class="material-symbols-outlined" '
        'style="font-size:16px;">download</span>Generar informe PDF</span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Avisos de preparación: capas de coste que no se pudieron generar para
    # algún escenario nuevo (p. ej. sin cobertura o sin fuente de datos). Se
    # muestran para que el usuario sepa que ese criterio no entró en el coste.
    avisos_prep = st.session_state.get("avisos_preparacion", {})
    if avisos_prep:
        detalle = "\n".join(
            f"- **Escenario {s}**: " + "; ".join(a for a in avisos)
            for s, avisos in avisos_prep.items()
        )
        st.warning(
            "Algunas capas de coste no se generaron y **no entraron en el "
            "cálculo** de las rutas de estos escenarios:\n" + detalle
        )

    perfiles_usados = st.session_state.get("perfiles_procesados")
    if perfiles_usados:
        with st.expander("Pesos de capas usados en este procesamiento", expanded=False):
            filas = []
            for p in perfiles_usados:
                row = {"Perfil": _NOMBRE_PERFIL.get(p["id"], p["id"])}
                for clave, etiqueta in _CAPAS_PESO:
                    v = p.get("pesos", {}).get(clave, 0.0)
                    row[etiqueta.split(" (")[0]] = f"{round(v * 100)}%"
                filas.append(row)
            st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    tab_labels = ["Mapa de rutas"] + [f"Métricas — Escenario {s}" for s in escenarios] + [
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

            st.write("")
            _render_kpis(resultados, [s])

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


# ── Stepper de progreso ───────────────────────────────────────────────────────

def _stepper(paso: int) -> None:
    """Barra de pasos (1: Origen y Destino · 2: Pesos y Perfiles · 3: Resultados)."""
    nombres = ["Origen y Destino", "Pesos y Perfiles", "Resultados"]
    kicker = {"done": "Completado", "active": "Paso actual", "pending": "Siguiente"}
    partes = ['<div class="enagas-stepper">']
    for i, nombre in enumerate(nombres, start=1):
        estado = "done" if i < paso else ("active" if i == paso else "pending")
        partes.append(
            f'<div class="step {estado}">'
            f'<div class="step-num">{i}</div>'
            f'<div class="step-txt">'
            f'<span class="step-kicker">{kicker[estado]}</span>'
            f'<span class="step-name">{nombre}</span>'
            f'</div></div>'
        )
        if i < len(nombres):
            partes.append(f'<div class="step-conn {"done" if paso > i else ""}"></div>')
    partes.append("</div>")
    st.markdown("".join(partes), unsafe_allow_html=True)


def _footer() -> None:
    """Footer técnico corporativo."""
    st.markdown(
        '<div class="enagas-footer">'
        '<div class="foot-left">'
        '<span class="foot-brand">2026 Enagás</span>'
        '</div>'
        '<div class="foot-links">'
        '<span class="foot-green foot-mono">Technical Infrastructure Division</span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ── Pantalla de bienvenida ─────────────────────────────────────────────────────

def _hero_visual() -> str:
    """Panel visual derecho de la bienvenida (imagen assets/hero.jpg si existe)."""
    import base64
    for nombre in ("hero.jpg", "hero.png", "hero.jpeg"):
        ruta = Path(__file__).parent / "assets" / nombre
        if ruta.exists():
            mime = "jpeg" if ruta.suffix != ".png" else "png"
            b64 = base64.b64encode(ruta.read_bytes()).decode()
            return (
                f'<div style="height:100%;min-height:420px;border-radius:var(--radius-xl);'
                f'background-image:url(\'data:image/{mime};base64,{b64}\');'
                f'background-size:cover;background-position:center;'
                f'border:1px solid var(--outline-variant);"></div>'
            )
    # Sin imagen: panel degradado con motivo de red H₂
    return (
        '<div style="height:100%;min-height:420px;border-radius:var(--radius-xl);'
        'border:1px solid var(--outline-variant);overflow:hidden;position:relative;'
        'background:linear-gradient(135deg,#004e7e 0%,#0067a3 55%,#4b6700 130%);'
        'display:flex;align-items:center;justify-content:center;">'
        '<div style="position:absolute;inset:0;opacity:0.15;background-image:'
        'linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px);'
        'background-size:32px 32px;"></div>'
        '<span class="material-symbols-outlined" style="color:rgba(255,255,255,0.92);'
        'font-size:120px;position:relative;">valve</span>'
        '</div>'
    )


def _render_bienvenida() -> None:
    col_left, col_right = st.columns([1.15, 1], gap="large")
    with col_left:
        st.markdown(
            '<div style="font-family:var(--font-body);font-weight:700;font-size:0.72rem;'
            'letter-spacing:0.08em;text-transform:uppercase;color:var(--secondary);'
            'margin-bottom:6px;">Hydrogen Infrastructure Tool v2.4</div>'
            '<div style="font-family:var(--font-head);font-size:2.3rem;font-weight:800;'
            'color:var(--primary);line-height:1.1;letter-spacing:-0.02em;margin-bottom:14px;">'
            'Generador de Trazados<br>de Ramales de H₂</div>'
            '<p class="welcome-sub" style="text-align:justify;">Herramienta avanzada '
            'para la optimización y diseño de infraestructuras de hidrógeno. Utilice algoritmos '
            'de última generación para calcular las rutas más eficientes basadas en criterios '
            'geográficos, ambientales y de coste.</p>',
            unsafe_allow_html=True,
        )
        st.write("")
        cc1, cc2 = st.columns(2, gap="medium")
        with cc1:
            with st.container(border=True):
                st.markdown(
                    '<div class="welcome-card-head">'
                    '<div class="welcome-card-icon icon-primary">'
                    '<span class="material-symbols-outlined">play_arrow</span></div>'
                    '<div class="welcome-card-title">Nueva simulación</div>'
                    '<p class="welcome-card-txt">Inicie una nueva sesión de diseño. Defina puntos '
                    'de origen, destino y parámetros para obtener el trazado óptimo.</p>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Comenzar simulación  →", type="secondary",
                             use_container_width=True, key="btn_welcome_start"):
                    st.session_state.pantalla = "paso1"
                    st.rerun()
        with cc2:
            with st.container(border=True):
                st.markdown(
                    '<div class="welcome-card-head">'
                    '<div class="welcome-card-icon icon-secondary">'
                    '<span class="material-symbols-outlined">insights</span></div>'
                    '<div class="welcome-card-title">Documentación técnica</div>'
                    '<p class="welcome-card-txt">Explore la metodología técnica, algoritmos de '
                    'cálculo y detalles de implementación de la herramienta.</p>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Ver documentación  📖", use_container_width=True,
                             key="btn_welcome_docs"):
                    st.toast("Documentación técnica — próximamente.")
    with col_right:
        st.markdown(_hero_visual(), unsafe_allow_html=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def _main():
    import logging
    logging.disable(logging.WARNING)

    import base64
    _LOGO_PATH = Path(__file__).parent / "assets" / "Logo.png"
    _logo_tag = (
        f'<img class="topnav-logo" src="data:image/png;base64,'
        f'{base64.b64encode(_LOGO_PATH.read_bytes()).decode()}">'
        if _LOGO_PATH.exists() else ""
    )

    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="enagas-topnav">'
        f'<div class="topnav-left">{_logo_tag}</div>'
        f'<div class="topnav-right">'
        f'<span class="topnav-icon"><span class="material-symbols-outlined">notifications</span></span>'
        f'<span class="topnav-icon"><span class="material-symbols-outlined">settings</span></span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if "pantalla" not in st.session_state:
        st.session_state.pantalla = "bienvenida"

    pantalla = st.session_state.pantalla
    if pantalla == "bienvenida":
        _render_bienvenida()
    elif pantalla == "paso2":
        _stepper(2)
        _render_paso2()
    elif pantalla == "resultados":
        _stepper(3)
        _render_results()
    else:  # paso1
        _stepper(1)
        _render_paso1()

    _footer()


_main()
