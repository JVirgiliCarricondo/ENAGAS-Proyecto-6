"""Interfaz web — Generador de trazados (Enagás / CI2 Lab 2026).

Ejecutar desde proyecto/:
    streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import copy
import json
import math
import re
import shutil
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import streamlit as st
import yaml
from pyproj import Transformer
from shapely import wkt as _shp_wkt
from shapely.geometry import LineString, Point
from shapely.geometry import box as _shp_box
from shapely.geometry import shape as _shp_shape
from shapely.ops import unary_union

# Page config — DEBE ser la primera llamada a Streamlit
_ICON_PATH = Path(__file__).resolve().parent / "assets" / "Logo.png"
st.set_page_config(
    page_title="Generador de Trazados",
    page_icon=str(_ICON_PATH) if _ICON_PATH.exists() else ":droplet:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Paths del proyecto
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

_CONFIG_PATH = _ROOT / "data" / "config" / "escenario.yaml"
_CONFIG_BASE_PATH = _ROOT / "data" / "config" / "escenario_base.yaml"
_PERFILES_PATH = _ROOT / "data" / "config" / "perfiles.yaml"
_RUTAS_DIR     = _ROOT / "data" / "processed" / "Rutas"
_TRAZADOS_DIR  = _ROOT / "data" / "processed" / "Trazados"

# Restaurar la configuración canónica de escenarios al abrir la app: los
# cambios de origen/destino y los escenarios creados en la interfaz duran solo
# la sesión (escenario.yaml es efímero; los valores "de fábrica" viven en
# escenario_base.yaml). El flag de session_state limita la copia al primer
# rerun de cada sesión del navegador.
if "_config_escenarios_restaurada" not in st.session_state:
    if _CONFIG_BASE_PATH.exists():
        shutil.copyfile(_CONFIG_BASE_PATH, _CONFIG_PATH)
    st.session_state["_config_escenarios_restaurada"] = True

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

# ── Relleno bicolor de los sliders (azul a la izquierda del pulgar, claro a
# la derecha) ───────────────────────────────────────────────────────────────
# Baseweb no genera un div de "relleno" proporcional al valor (solo la pista
# completa + el pulgar posicionado con transform), así que el degradado no es
# expresable en CSS puro sin conocer el valor de cada slider. Este script,
# inyectado vía components.html (iframe same-origin: puede tocar
# window.parent.document), lee aria-valuenow/min/max de cada pulgar y pinta
# la pista con un linear-gradient partido en ese punto. Se reevalúa con un
# MutationObserver (arrastre en vivo) + un intervalo de respaldo (nuevos
# sliders tras un rerun de Streamlit).
_SLIDER_FILL_JS = """
<script>
(function () {
  function paintSliders() {
    var doc = window.parent.document;
    var sliders = doc.querySelectorAll('div[data-testid="stSlider"]');
    sliders.forEach(function (sliderEl) {
      var thumb = sliderEl.querySelector('div[role="slider"]');
      var track = sliderEl.querySelector(
        'div[data-baseweb="slider"] > div:not([data-testid="stSliderTickBar"]) > div > div:last-child'
      );
      if (!thumb || !track) return;
      var min = parseFloat(thumb.getAttribute('aria-valuemin'));
      var max = parseFloat(thumb.getAttribute('aria-valuemax'));
      var val = parseFloat(thumb.getAttribute('aria-valuenow'));
      if (isNaN(min) || isNaN(max) || isNaN(val) || max === min) return;
      var pct = ((val - min) / (max - min)) * 100;
      var grad = 'linear-gradient(to right, var(--primary) ' + pct +
        '%, var(--outline-variant) ' + pct + '%)';
      if (track.style.background !== grad) {
        track.style.setProperty('background', grad, 'important');
      }
    });
  }
  try {
    paintSliders();
    new MutationObserver(paintSliders).observe(window.parent.document.body, {
      attributes: true, attributeFilter: ['aria-valuenow'], subtree: true, childList: true,
    });
    setInterval(paintSliders, 400);
  } catch (e) { /* iframe sin acceso al padre: la pista se queda en el tono claro base */ }
})();
</script>
"""

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
  div[class*="st-key-topnav"] {
    background: var(--surface-lowest);
    border-bottom: 1px solid var(--outline-variant);
    box-shadow: var(--shadow-card);
    padding: 0 28px;
    margin: -0.4rem 0 14px;
    min-height: 52px;
    display: flex;
    flex-direction: row !important;
    align-items: center !important;
  }
  div[class*="st-key-topnav"] > * { width: 100%; }
  div[class*="st-key-topnav"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
  div[class*="st-key-topnav"] * { margin-top: 0 !important; margin-bottom: 0 !important; }
  div[class*="st-key-topnav"] [data-testid="stHorizontalBlock"] {
    align-items: center;
  }
  .topnav-left { display: flex; align-items: center; gap: 14px; min-height: 40px; }
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
  /* Sticky: la barra de pasos queda pegada arriba al hacer scroll. Streamlit
     envuelve CADA elemento de nivel superior (incluido nuestro contenedor con
     clave) en un stLayoutWrapper que mide justo lo que su contenido: un sticky
     dentro de ese envoltorio tiene recorrido cero y se va con el scroll. El que
     SÍ tiene un padre alto (el stack vertical de toda la página) es ese propio
     stLayoutWrapper, así que es ÉL quien debe ser sticky. Lo seleccionamos por
     ser el que contiene directamente nuestro contenedor 'stepper_wrap'. */
  div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-stepper_wrap"]) {
    position: sticky;
    top: 0;
    z-index: 50;
    background: var(--surface);
  }
  /* Anular padding/gap propios del contenedor para que la barra quede pegada al
     borde superior sin franja de fondo por encima. */
  div[class*="st-key-stepper_wrap"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
  div[class*="st-key-stepper_wrap"] [data-testid="stElementContainer"] { margin: 0 !important; }
  .enagas-stepper {
    display: flex;
    align-items: center;
    gap: 0;
    background: var(--surface);
    border: 1px solid var(--outline-variant);
    border-radius: var(--radius-xl);
    padding: 12px 22px;
    margin-bottom: 16px;
    box-shadow: 0 2px 12px rgba(0,75,118,0.07);
  }
  .step { display: flex; align-items: center; gap: 10px; }
  .step-num {
    width: 30px; height: 30px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-family: var(--font-body); font-weight: 700; font-size: 0.85rem;
    flex-shrink: 0;
    transition: background 0.4s ease, color 0.4s ease, box-shadow 0.4s ease;
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
  /* Conector: barra base gris con un relleno primario interior que se anima de
     izquierda a derecha (scaleX) cuando el paso acaba de completarse. */
  .step-conn {
    position: relative; flex: 1; height: 2px; margin: 0 18px;
    background: var(--outline-variant); overflow: hidden;
  }
  .step-conn-fill {
    position: absolute; inset: 0; background: var(--primary);
    transform: scaleX(0); transform-origin: left;
  }
  .step-conn.done .step-conn-fill { transform: scaleX(1); }
  .step-conn.just-done .step-conn-fill { animation: connFill 0.6s ease-out both; }

  /* ── Animaciones del avance del stepper ───────────────────────────────── */
  @keyframes connFill {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
  }
  /* Paso recién activado: pulso de escala + anillo que "late" una vez. */
  @keyframes stepPop {
    0%   { transform: scale(0.7);  box-shadow: 0 0 0 0 var(--secondary-container); }
    55%  { transform: scale(1.14); box-shadow: 0 0 0 9px rgba(195,243,92,0.55); }
    100% { transform: scale(1);    box-shadow: 0 0 0 4px var(--secondary-container); }
  }
  .step.just-active .step-num { animation: stepPop 0.5s ease-out; }
  /* Paso recién completado: pequeño rebote al pasar a azul. */
  @keyframes stepDone {
    0%   { transform: scale(1); }
    50%  { transform: scale(1.16); }
    100% { transform: scale(1); }
  }
  .step.just-done .step-num { animation: stepDone 0.5s ease; }

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
  /* Desplegable de escenario (popover): el disparador actúa como cabecero, con
     tipografía grande en acento primario, texto a la izquierda y el símbolo de
     desplegable a la derecha. */
  .st-key-esc_dropdown [data-testid="stPopover"] button {
    justify-content: space-between !important;
    font-family: var(--font-head) !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
    border: 1px solid var(--outline-variant) !important;
    background: var(--surface-lowest) !important;
  }
  .st-key-esc_dropdown [data-testid="stPopover"] button * {
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
  }
  /* Filas del desplegable: botón de selección alineado a la izquierda, sin borde,
     y papelera compacta. Se estilan por sus claves (están en la capa del popover).
     Especificidad extra (div[data-testid=stButton] > button) para ganar a la regla
     global de botones. */
  div[class*="st-key-sel_esc_"] div[data-testid="stButton"] > button {
    justify-content: flex-start !important;
    border: none !important;
    background: transparent !important;
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    text-align: left !important;
  }
  div[class*="st-key-sel_esc_"] div[data-testid="stButton"] > button:hover {
    background: var(--surface-container) !important;
  }
  /* Iconos de acción de cada fila (lápiz, papelera, confirmar/cancelar): sin
     borde, fondo transparente y compactos. */
  div[class*="st-key-edit_esc_"] div[data-testid="stButton"] > button,
  div[class*="st-key-del_esc_"] div[data-testid="stButton"] > button,
  div[class*="st-key-rename_ok_"] div[data-testid="stButton"] > button,
  div[class*="st-key-rename_no_"] div[data-testid="stButton"] > button {
    border: none !important;
    background: transparent !important;
    padding: 4px !important;
  }
  div[class*="st-key-edit_esc_"] div[data-testid="stButton"] > button:hover,
  div[class*="st-key-del_esc_"] div[data-testid="stButton"] > button:hover,
  div[class*="st-key-rename_ok_"] div[data-testid="stButton"] > button:hover,
  div[class*="st-key-rename_no_"] div[data-testid="stButton"] > button:hover {
    background: var(--surface-container) !important;
  }
  /* Iconos Material de las filas: silueta monocroma en azul oscuro (acento
     primario), nunca emoji multicolor. Se pinta todo el contenido del botón
     (incl. el glifo dentro del envoltorio de tooltip) forzando también
     -webkit-text-fill-color, que es quien decide el color real del glifo. */
  div[class*="st-key-edit_esc_"] *,
  div[class*="st-key-del_esc_"] *,
  div[class*="st-key-rename_ok_"] *,
  div[class*="st-key-rename_no_"] * {
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
  }
  /* Compactar el desplegable: menos separación vertical entre filas. */
  [data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] {
    gap: 0.2rem !important;
  }
  [data-testid="stPopoverBody"] [data-testid="stElementContainer"] {
    margin: 0 !important;
  }

  /* ── Badge de restricciones (info) ────────────────────────────────────── */
  .constraints-box {
    background: rgba(0,103,163,0.06);
    border: 1px solid rgba(0,103,163,0.22);
    border-radius: var(--radius);
    padding: 10px 14px;
    margin-bottom: 12px;
    font-size: 0.76rem;
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
  /* Pista del slider: único elemento visual del track (baseweb no genera un
     div de "relleno" aparte aquí). Color base claro ANTES de que el JS de
     _SLIDER_FILL_JS calcule el degradado real (azul a la izquierda del
     pulgar, claro a la derecha); evita un parpadeo de color sólido al
     pintar. Es el ÚLTIMO div de los dos que cuelgan del contenedor del
     pulgar; el primero es el área de arrastre del pulgar y no debe
     colorearse (si no, tapa la pista con el mismo azul). */
  div[data-testid="stSlider"] div[data-baseweb="slider"]
    > div:not([data-testid="stSliderTickBar"]) > div > div:last-child {
    background: var(--outline-variant) !important;
  }
  /* Etiquetas de extremos del slider (0% / 100%): sin fondo y en negro, siempre
     visibles. Alta especificidad para ganar a la regla de relleno de arriba. */
  div[data-testid="stSlider"] div[data-baseweb="slider"] div[data-testid="stSliderTickBar"],
  div[data-testid="stSlider"] div[data-baseweb="slider"] div[data-testid="stSliderTickBarMin"],
  div[data-testid="stSlider"] div[data-baseweb="slider"] div[data-testid="stSliderTickBarMax"] {
    color: var(--on-surface) !important;
    -webkit-text-fill-color: var(--on-surface) !important;
    background: transparent !important;
    background-color: transparent !important;
    opacity: 1 !important;
    font-weight: 600 !important;
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
    transition: background 0.15s, color 0.15s, border-color 0.15s,
                transform 0.1s ease, box-shadow 0.15s ease;
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
    transform: translateY(-1px);
    box-shadow: var(--shadow-card);
  }
  div[data-testid="stButton"] > button:active {
    transform: translateY(0);
    box-shadow: none;
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
    transform: translateY(-1px);
    box-shadow: var(--shadow-pop) !important;
  }
  div[data-testid="stButton"] > button[kind="primary"]:active {
    transform: translateY(0);
    box-shadow: var(--shadow-card) !important;
  }
  /* Primario deshabilitado: mismo azul y texto blanco legible (sin la caja
     clara que hereda de la regla generica de :disabled). Se distingue del
     activo por el cursor y la ausencia de sombra/hover. */
  div[data-testid="stButton"] > button[kind="primary"]:disabled {
    background: var(--primary) !important;
    border: none !important;
    box-shadow: none !important;
    cursor: not-allowed !important;
  }
  div[data-testid="stButton"] > button[kind="primary"]:disabled p,
  div[data-testid="stButton"] > button[kind="primary"]:disabled span,
  div[data-testid="stButton"] > button[kind="primary"]:disabled div {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    background: transparent !important;
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

  /* ── Botones "atrás" al mismo tamaño que el primario contiguo ──────────── */
  /* Paso 1 (← Inicio / Pesos y Perfiles) y Paso 2 (← Origen y Destino / Generar rutas) */
  .st-key-btn_p1_inicio div[data-testid="stButton"] > button,
  .st-key-btn_p2_back div[data-testid="stButton"] > button {
    padding: 12px 28px !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.2px !important;
  }

  /* ── Botones "Generar informe PDF" y "Descargar rutas" — mismo azul,
     texto e icono en blanco ───────────────────────────────────────────── */
  .st-key-btn_pdf_informe div[data-testid="stDownloadButton"] > button,
  .st-key-btn_pdf_informe div[data-testid="stDownloadButton"] > button *,
  .st-key-btn_dl_rutas div[data-testid="stDownloadButton"] > button,
  .st-key-btn_dl_rutas div[data-testid="stDownloadButton"] > button *,
  .st-key-btn_dl_rutas div[data-testid="stButton"] > button,
  .st-key-btn_dl_rutas div[data-testid="stButton"] > button * {
    color: #ffffff !important;
    fill: #ffffff !important;
  }

  /* ── Paso 1: selector de punto bajo el mapa (etiqueta + segmentos) ──────── */
  /* La etiqueta "El próximo clic fija:" es la propia etiqueta del control
     segmentado. Disponemos el grupo (etiqueta + botones) como una fila flex
     centrada bajo el mapa; align-items:center alinea el centro del texto con el
     centro de los botones sin depender de columnas de Streamlit. */
  /* Contenedor del control encogido a su contenido y centrado horizontalmente
     bajo el mapa mediante márgenes automáticos. */
  .st-key-p1_map_selector [data-testid="stElementContainer"] {
    width: fit-content !important;
    margin: 0 auto !important;
  }
  /* Grupo (etiqueta + botones) en fila flex. */
  .st-key-p1_map_selector div[data-testid="stButtonGroup"] {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: 14px !important;
    width: fit-content !important;
    margin: 0 !important;
  }
  /* Etiqueta del control como texto inline a la izquierda de los botones. */
  .st-key-p1_map_selector div[data-testid="stButtonGroup"] label[data-testid="stWidgetLabel"] {
    margin: 0 !important;
    padding: 0 !important;
    white-space: nowrap;
  }
  .st-key-p1_map_selector div[data-testid="stButtonGroup"] label[data-testid="stWidgetLabel"] p {
    margin: 0 !important;
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    color: var(--on-surface-variant) !important;
  }
  .st-key-p1_map_selector div[data-testid="stButtonGroup"] button {
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
  }
  /* Segmento seleccionado: fondo y texto en verde (acento Enagás). El fondo se
     aplica SOLO al botón; los hijos van transparentes para que el tono verde sea
     uniforme (si se tiñen también los hijos, la opacidad se acumula y el icono
     y el texto se ven más oscuros que el resto de la caja). */
  .st-key-p1_map_selector button[data-testid="stBaseButton-segmented_controlActive"] {
    background: rgba(75,103,0,0.12) !important;
    border-color: var(--secondary) !important;
    color: var(--secondary) !important;
    -webkit-text-fill-color: var(--secondary) !important;
  }
  .st-key-p1_map_selector button[data-testid="stBaseButton-segmented_controlActive"] * {
    background: transparent !important;
    color: var(--secondary) !important;
    -webkit-text-fill-color: var(--secondary) !important;
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

  /* ── Bienvenida: tarjetas de igual altura ─────────────────────────────── */
  /* Suelo común (por encima de la caja más alta) + estirado flex robusto: la
     fila estira ambas columnas a la más alta y las tarjetas la rellenan. */
  div[data-testid="stHorizontalBlock"]:has(.st-key-wcard_sim) { align-items: stretch; }
  div[data-testid="stColumn"]:has(.st-key-wcard_sim),
  div[data-testid="stColumn"]:has(.st-key-wcard_docs) {
    display: flex;
  }
  div[data-testid="stColumn"]:has(.st-key-wcard_sim) > div,
  div[data-testid="stColumn"]:has(.st-key-wcard_docs) > div {
    width: 100%;
    height: 100%;
  }
  .st-key-wcard_sim,
  .st-key-wcard_docs {
    height: 100%;
  }

  /* ── Bienvenida: hero derecho a toda la altura (con centrado de reserva) ── */
  div[data-testid="stHorizontalBlock"]:has(.st-key-hero_col) { align-items: stretch; }
  div[data-testid="stColumn"]:has(.st-key-hero_col) > div[data-testid="stVerticalBlock"] {
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .st-key-hero_col,
  .st-key-hero_col > div[data-testid="stVerticalBlock"],
  .st-key-hero_col div[data-testid="stElementContainer"],
  .st-key-hero_col div[data-testid="stMarkdownContainer"],
  .st-key-hero_col div[data-testid="stMarkdownContainer"] > div {
    height: 100%;
    width: 100%;
  }

  /* ── Tarjeta de Catastro (Datos para esta zona) ───────────────────────── */
  .st-key-cat_card {
    background: var(--surface-lowest);
    border: 1px solid var(--outline-variant);
    border-radius: 14px;
    padding: 13px 16px 15px 16px;
    box-shadow: var(--shadow-card);
  }
  .cat-title { display: flex; align-items: center; gap: 8px; }
  .cat-title .material-symbols-outlined { font-size: 19px; }
  .cat-title .txt { font-family: var(--font-body); font-weight: 700;
    font-size: 0.78rem; color: var(--on-surface); line-height: 1.2; }
  .cat-sub { font-family: var(--font-body); font-size: 0.68rem;
    color: var(--on-surface-variant); margin: 4px 0 0 27px; line-height: 1.3; }
  hr.cat-div { border: none; border-top: 1px solid var(--surface-high);
    margin: 12px 0 2px 0; }

  /* Botones "Ver municipios" / "Reintentar" — pastilla clara (azul suave),
     letra pequeña como el cuerpo de las tarjetas */
  .st-key-btn_cat_reintentar div[data-testid="stButton"] > button,
  .st-key-btn_cat_municipios div[data-testid="stButton"] > button {
    background: #eef5fb !important;
    border: 1px solid #d9e7f2 !important;
    border-radius: 9px !important;
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
    padding: 4px 12px !important;
    min-height: 0 !important;
    font-size: 0.6rem !important;
    box-shadow: none !important;
  }
  .st-key-btn_cat_reintentar div[data-testid="stButton"] > button *,
  .st-key-btn_cat_municipios div[data-testid="stButton"] > button * {
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
    font-size: 0.6rem !important;
  }
  .st-key-btn_cat_reintentar div[data-testid="stButton"] > button:hover,
  .st-key-btn_cat_municipios div[data-testid="stButton"] > button:hover {
    background: #e2eef8 !important;
    border-color: #c4dbec !important;
  }

  /* Spinner "Localizando municipios…" — texto pequeño como el subtítulo del card */
  .st-key-cat_muni_spinner div[data-testid="stSpinner"] {
    font-size: 0.68rem !important;
  }
  .st-key-cat_muni_spinner div[data-testid="stSpinner"] * {
    font-size: 0.68rem !important;
    color: var(--on-surface-variant) !important;
  }
  .st-key-cat_muni_spinner div[data-testid="stSpinner"] i,
  .st-key-cat_muni_spinner div[data-testid="stSpinner"] svg {
    width: 0.9rem !important; height: 0.9rem !important;
  }

  /* Caja gris que agrupa los municipios del corredor — compacta y acotada */
  .st-key-cat_muni_box {
    background: var(--surface-low);
    border: 1px solid var(--surface-high);
    border-radius: 13px;
    padding: 9px 11px 1px 11px;
    margin-top: 12px;
  }
  .cat-count { display: flex; align-items: center; gap: 6px;
    font-family: var(--font-body); font-weight: 700; font-size: 0.68rem;
    margin: 2px 2px 8px 2px; }

  /* Cada municipio como expander → tarjeta blanca redondeada, compacta */
  .st-key-cat_muni_box div[data-testid="stExpander"] {
    background: var(--surface-lowest);
    border: 1px solid var(--surface-high) !important;
    border-radius: 10px !important;
    margin-bottom: 7px;
    box-shadow: var(--shadow-card);
    overflow: hidden;
  }
  .st-key-cat_muni_box div[data-testid="stExpander"] details,
  .st-key-cat_muni_box div[data-testid="stExpander"] summary {
    border: none !important; background: transparent !important;
  }
  .st-key-cat_muni_box div[data-testid="stExpander"] summary {
    padding: 7px 12px !important;
  }
  /* Mismo tipo de letra que el título de "Red Natura 2000" en la tabla */
  .st-key-cat_muni_box div[data-testid="stExpander"] summary p {
    font-family: var(--font-body) !important; font-weight: 700 !important;
    font-size: 0.78rem !important; color: var(--on-surface) !important;
  }
  /* Enlaces Urbana/Rústica en AZUL, como el enlace a la API en RN2000 */
  .st-key-cat_muni_box div[data-testid="stLinkButton"] > a {
    border: 1px solid var(--outline-variant) !important;
    border-radius: 8px !important;
    min-height: 0 !important;
    align-items: center !important;
    justify-content: center !important;
    white-space: normal !important;
    line-height: 1.2 !important;
    padding: 7px 10px !important;
    background: var(--surface-lowest) !important;
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
    font-family: var(--font-body) !important;
    font-weight: 400 !important;
    font-size: 0.64rem !important;
  }
  .st-key-cat_muni_box div[data-testid="stLinkButton"] > a * {
    color: var(--primary) !important;
    -webkit-text-fill-color: var(--primary) !important;
    font-family: var(--font-body) !important;
    font-weight: 400 !important;
    font-size: 0.64rem !important;
  }
  .st-key-cat_muni_box div[data-testid="stLinkButton"] > a:hover {
    background: var(--surface-low) !important;
    border-color: var(--primary) !important;
  }
  /* Zona de subida como caja blanca redondeada */
  .st-key-cat_muni_box div[data-testid="stFileUploaderDropzone"] {
    border-radius: 10px !important;
    background: var(--surface-lowest) !important;
  }
  /* Botón "Upload" y texto del límite por fichero: pequeños y sin negrita */
  .st-key-cat_muni_box div[data-testid="stFileUploaderDropzone"] button,
  .st-key-cat_muni_box div[data-testid="stFileUploaderDropzone"] button * {
    font-family: var(--font-body) !important;
    font-size: 0.64rem !important;
    font-weight: 400 !important;
  }
  .st-key-cat_muni_box [data-testid="stFileUploaderDropzoneInstructions"],
  .st-key-cat_muni_box [data-testid="stFileUploaderDropzoneInstructions"] * {
    font-family: var(--font-body) !important;
    font-size: 0.68rem !important;
    font-weight: 400 !important;
  }
  /* Ficheros subidos (nombre + tamaño), caption "✓ Listo…" y avisos de error:
     mismo cuerpo que el subtítulo "Cubierto por lo ya descargado" (.cat-sub) */
  .st-key-cat_muni_box [data-testid="stFileUploaderFile"],
  .st-key-cat_muni_box [data-testid="stFileUploaderFile"] *,
  .st-key-cat_muni_box [data-testid="stCaptionContainer"],
  .st-key-cat_muni_box [data-testid="stCaptionContainer"] * {
    font-family: var(--font-body) !important;
    font-size: 0.68rem !important;
  }
  .st-key-cat_muni_box [data-testid="stAlert"] p,
  .st-key-cat_muni_box [data-testid="stAlert"] div[data-testid="stMarkdownContainer"] * {
    font-family: var(--font-body) !important;
    font-size: 0.68rem !important;
    line-height: 1.35 !important;
  }

  footer { display: none; }
  #MainMenu { display: none; }
  header[data-testid="stHeader"] { display: none; }

  /* ── Accesibilidad: sin movimiento si el sistema lo pide ───────────────── */
  @media (prefers-reduced-motion: reduce) {
    .step-num, .step-conn-fill,
    div[data-testid="stButton"] > button {
      transition: none !important;
      animation: none !important;
    }
    .step.just-active .step-num,
    .step.just-done .step-num,
    .step-conn.just-done .step-conn-fill { animation: none !important; }
    .step-conn.just-done .step-conn-fill { transform: scaleX(1); }
    div[data-testid="stButton"] > button:hover,
    div[data-testid="stButton"] > button[kind="primary"]:hover { transform: none; }
  }
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


# Barrera dura de pendiente (%): pendiente Horn > este valor → celda intransitable.
# Vive en perfiles.yaml → parametros_capas.tpi.umbral_barrera_pct (por defecto 70).
_BARRERA_PENDIENTE_DEFECTO = 70


def _barrera_pendiente_actual() -> int:
    try:
        data = yaml.safe_load(_PERFILES_PATH.read_text(encoding="utf-8"))
        val = data["parametros_capas"]["tpi"]["umbral_barrera_pct"]
        return int(round(float(val)))
    except (KeyError, TypeError, ValueError, OSError):
        return _BARRERA_PENDIENTE_DEFECTO


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
        st.markdown(
            '<div class="scenario-title">Perfil a ajustar</div>',
            unsafe_allow_html=True,
        )
        pid = st.selectbox(
            "Perfil a ajustar",
            options=PERFILES,
            index=PERFILES.index(st.session_state.perfil_pesos_activo)
            if st.session_state.perfil_pesos_activo in PERFILES else 0,
            format_func=lambda p: _NOMBRE_PERFIL.get(p, p),
            key="select_perfil_pesos",
            label_visibility="collapsed",
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


def _borrar_escenario(cfg: dict, coords: dict, sid: str) -> None:
    """Elimina un escenario de la config y de coords. Exige que quede al menos uno."""
    if sid not in coords:
        raise ValueError(f"El escenario '{sid}' no existe.")
    if len(coords) <= 1:
        raise ValueError("Debe quedar al menos un escenario; no se puede borrar el último.")
    coords.pop(sid, None)
    cfg.pop(f"escenario_{sid}", None)
    _guardar_cfg(cfg)
    # Limpiar el estado de los number_input de ese escenario para que no reviva.
    for rol in ("origen", "destino"):
        for eje in ("x", "y"):
            st.session_state.pop(f"{sid}_{rol}_{eje}", None)


def _renombrar_escenario(cfg: dict, coords: dict, old: str, nuevo_id: str) -> str:
    """Cambia el identificador de un escenario (su nombre visible). El id se usa como
    clave en toda la app, así que renombrar propaga el nombre a mapa, métricas, etc."""
    sid = _normalizar_id_escenario(nuevo_id)
    if not sid:
        raise ValueError("Indica un nombre valido (letras, numeros, guion o guion bajo).")
    if sid == old:
        return old  # sin cambios
    if sid in coords:
        raise ValueError(f"El escenario '{sid}' ya existe.")
    old_key, new_key = f"escenario_{old}", f"escenario_{sid}"
    if old_key in cfg:
        block = cfg.pop(old_key)
        block.setdefault("origen", {})["nombre"] = f"{sid}_inicial"
        block.setdefault("destino", {})["nombre"] = f"{sid}_final"
        cfg[new_key] = block
    coords[sid] = coords.pop(old)
    _guardar_cfg(cfg)
    # Migrar el estado de los number_input del escenario renombrado.
    for rol in ("origen", "destino"):
        for eje in ("x", "y"):
            ok = f"{old}_{rol}_{eje}"
            if ok in st.session_state:
                st.session_state[f"{sid}_{rol}_{eje}"] = st.session_state.pop(ok)
    return sid


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _ejecutar_pipeline(
    progress_cb,
    escenarios: list[str],
    perfiles: list[dict] | None = None,
    umbral_barrera_pct: float | None = None,
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
    from superficie.combinar import run as combinar_run

    if not escenarios:
        raise ValueError("No hay escenarios configurados.")

    # Barrera dura de pendiente: si el usuario la cambió respecto al valor por
    # defecto, se sobreescribe el global de la capa TPI y se regenera esa capa
    # (donde vive la barrera) para los escenarios ya preparados.
    _tpimod = None
    if umbral_barrera_pct is not None:
        import superficie.tpi as _tpimod
        _tpimod.UMBRAL_BARRERA_PCT = float(umbral_barrera_pct)

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
        if _tpimod is not None:
            # Regenerar la capa TPI (donde vive la barrera) con el umbral de la
            # UI. También tras preparar un escenario nuevo: la preparación corre
            # en subproceso con el umbral por defecto del YAML, así que sin este
            # paso el valor elegido por el usuario se ignoraría.
            progress_cb(base + span * 0.70, f"Aplicando barrera de pendiente "
                              f"({umbral_barrera_pct:.0f}%) — Escenario {s}…")
            _tpimod.procesar_escenario(s)
        # Superficie neutral (pesos iguales) del escenario: es la referencia
        # contra la que se normaliza coste_relativo en las métricas. Se
        # regenera en cada ejecución, junto con las superficies por perfil
        # y las rutas (Trazados/ y Rutas/ nunca se reutilizan de otra sesión).
        progress_cb(base + span * 0.71, f"Superficie de referencia — Escenario {s}…")
        combinar_run(s)
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


# CSS corporativo para los controles nativos de Leaflet (zoom +/- y atribución).
# Se inyecta DENTRO del HTML del mapa (el iframe), donde no llega el CSS de la app.
_MAPA_CSS_CORP = """
<style>
  /* ── Control de zoom (+/-) : tarjeta corporativa ─────────────────────── */
  .leaflet-control-zoom.leaflet-bar {
    border: none !important;
    border-radius: 10px !important;
    box-shadow: 0 2px 10px rgba(0,75,118,0.20) !important;
    overflow: hidden !important;
  }
  .leaflet-control-zoom a {
    width: 32px !important; height: 32px !important; line-height: 32px !important;
    background: #ffffff !important;
    color: #004e7e !important;
    font-family: 'Inter','Segoe UI',Arial,sans-serif !important;
    font-size: 18px !important; font-weight: 700 !important;
    border: none !important;
    border-bottom: 1px solid #e5e9eb !important;
    transition: background .15s ease, color .15s ease !important;
  }
  .leaflet-control-zoom a.leaflet-control-zoom-out { border-bottom: none !important; }
  .leaflet-control-zoom a:hover {
    background: #004e7e !important;
    color: #ffffff !important;
  }
  .leaflet-control-zoom a.leaflet-disabled {
    background: #f1f4f6 !important; color: #b0b7bd !important;
  }

  /* ── Atribución (fuente) : píldora corporativa, sin bandera ──────────── */
  .leaflet-control-attribution {
    background: rgba(255,255,255,0.94) !important;
    color: #404750 !important;
    font-family: 'Inter','Segoe UI',Arial,sans-serif !important;
    font-size: 10.5px !important;
    line-height: 1.4 !important;
    padding: 3px 9px !important;
    border-radius: 8px 0 0 0 !important;
    border-top: 2px solid #004e7e !important;
    box-shadow: 0 1px 6px rgba(0,75,118,0.14) !important;
  }
  .leaflet-control-attribution a {
    color: #004e7e !important; font-weight: 600 !important; text-decoration: none !important;
  }
  .leaflet-control-attribution a:hover { text-decoration: underline !important; }
  /* Ocultar la bandera de Leaflet en el prefijo. Especificidad alta a propósito:
     leaflet.css trae `.leaflet-attribution-flag{display:inline!important}` y se
     carga después, así que hay que ganarle con un selector más específico. */
  .leaflet-control-attribution svg.leaflet-attribution-flag,
  .leaflet-container svg.leaflet-attribution-flag { display: none !important; }
</style>
"""


def _estilo_corporativo_mapa(m: folium.Map) -> None:
    """Inyecta el CSS corporativo de los controles Leaflet en el HTML del mapa."""
    m.get_root().header.add_child(folium.Element(_MAPA_CSS_CORP))


def _marcador_punto(
    m: folium.Map,
    lat: float,
    lon: float,
    rol: str,
    escenario: str,
    activo: bool,
    coords: dict,
) -> None:
    """Marca origen/destino con un badge; el color identifica el escenario."""
    es_origen = rol == "origen"
    # Mismo tipo de punto para origen y destino: lo que distingue los escenarios
    # es el color (cada escenario tiene el suyo). La letra O/D marca el rol.
    fill = _color_escenario(escenario)
    letra = "O" if es_origen else "D"
    tooltip = f"Escenario {escenario} — {rol.capitalize()}"
    popup_html = (
        f"<b style='color:{fill}'>{tooltip}</b><br>"
        f"X: {coords[escenario][rol]['x']:.0f} m<br>"
        f"Y: {coords[escenario][rol]['y']:.0f} m<br>"
        f"<small>({lat:.5f}, {lon:.5f})</small>"
    )
    if activo:
        size = 28
        # Letra O/D perfectamente centrada (flexbox) y estilo corporativo:
        # tipografía de titulares Enagás, anillo blanco y sombra sutil.
        badge = (
            f'<div style="font-family:\'Hanken Grotesk\',Inter,\'Segoe UI\',sans-serif;'
            f'font-size:14px;font-weight:800;letter-spacing:0.02em;color:#fff;'
            f'background:{fill};width:{size}px;height:{size}px;'
            f'display:flex;align-items:center;justify-content:center;'
            f'border-radius:50%;border:2.5px solid #fff;'
            f'box-shadow:0 2px 6px rgba(0,0,0,0.35);">{letra}</div>'
        )
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=badge,
                icon_size=(size, size),
                icon_anchor=(size // 2, size // 2),
            ),
            tooltip=tooltip,
            popup=folium.Popup(popup_html, max_width=240),
        ).add_to(m)
    else:
        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color=fill,
            fill_opacity=0.55,
            tooltip=tooltip,
            popup=folium.Popup(popup_html, max_width=240),
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

    filas_leyenda = "".join(
        f'<span style="color:{_color_escenario(s)};font-weight:700;'
        f'font-size:1.15em;">&#9679;</span> '
        f'{"<b>" if s == escenario_activo else ""}Escenario {s}'
        f'{" (activo)</b>" if s == escenario_activo else ""}<br>'
        for s in sorted(coords, key=lambda x: (len(x), x))
    )
    leyenda = f"""
    <div style="position:fixed;top:12px;right:12px;z-index:1000;background:#fff;
                padding:10px 14px;border-radius:8px;font-family:'Segoe UI',sans-serif;
                font-size:12px;color:#1f2937;box-shadow:0 2px 8px rgba(0,0,0,0.2);
                border-top:3px solid {_color_escenario(escenario_activo)};">
      <b style="color:#004e7e;">Escenarios</b><br>
      {filas_leyenda}
    </div>
    """
    m.get_root().html.add_child(folium.Element(leyenda))

    _estilo_corporativo_mapa(m)
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
    m = folium.Map(location=[c.y, c.x], zoom_start=12, tiles=None)
    # Capa base con nombre propio y control=False: así el LayerControl no muestra
    # la URL cruda del teselado (el "hiperenlace" que se veía en el selector).
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri WorldImagery",
        name="Ortofoto (Esri)",
        overlay=False,
        control=False,
    ).add_to(m)

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

    # Ambas cajas arriba a la derecha: la leyenda de Perfiles (estática, altura
    # fija) arriba, y debajo la caja de Escenarios (el LayerControl, con sus
    # toggles). El LayerControl se re-estiliza como tarjeta corporativa y se
    # empuja hacia abajo con margin-top para que quede bajo la leyenda.
    legend = """
    <style>
      /* ── Leyenda de perfiles: tarjeta corporativa (arriba a la derecha) ── */
      .perfiles-legend {
        position: fixed; top: 12px; right: 12px; z-index: 1000;
        box-sizing: border-box; width: 190px;
        background: #ffffff; padding: 10px 14px; border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,75,118,0.18);
        font-family: 'Inter','Segoe UI',Arial,sans-serif; font-size: 13px;
        border-top: 3px solid #004e7e;
      }
      .perfiles-legend, .perfiles-legend span { color: #1f2937 !important; }
      .perfiles-legend b { color: #004e7e !important; }
      .perfiles-legend .c-corto { color: #1f78b4 !important; }
      .perfiles-legend .c-equilibrio { color: #ff7f00 !important; }
      .perfiles-legend .c-ambiental { color: #33a02c !important; }
      .perfiles-legend .c-pendiente { color: #e31a1c !important; }

      /* ── Caja de escenarios (LayerControl): misma tarjeta corporativa, ────
         empujada bajo la leyenda de perfiles. */
      .leaflet-control-layers {
        margin-top: 152px !important;
        box-sizing: border-box !important; width: 190px !important;
        border: none !important; border-radius: 8px !important;
        box-shadow: 0 2px 8px rgba(0,75,118,0.18) !important;
        border-top: 3px solid #004e7e !important;
        background: #ffffff !important; padding: 10px 14px !important;
        font-family: 'Inter','Segoe UI',Arial,sans-serif !important;
      }
      .leaflet-control-layers-toggle { display: none !important; }
      .leaflet-control-layers-separator { display: none !important; }
      .leaflet-control-layers-overlays::before {
        content: "Escenarios"; display: block;
        color: #004e7e; font-weight: 700; font-size: 13px; margin-bottom: 6px;
      }
      .leaflet-control-layers-overlays label {
        color: #1f2937 !important; font-size: 13px !important;
        margin-bottom: 2px !important; font-weight: 400 !important;
      }
    </style>
    <div class="perfiles-legend">
      <b>Perfiles</b><br>
      <span class="c-corto" style="font-size:1.3em;">&#9644;</span><span> Corto</span><br>
      <span class="c-equilibrio" style="font-size:1.3em;">&#9644;</span><span> Equilibrio</span><br>
      <span class="c-ambiental" style="font-size:1.3em;">&#9644;</span><span> Ambiental</span><br>
      <span class="c-pendiente" style="font-size:1.3em;">&#9644;</span><span> Relieve (TPI)</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    _estilo_corporativo_mapa(m)

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


@st.cache_data(show_spinner=False)
def _recorte_bbox_wkt(path_str: str, mtime: float) -> str | None:
    """BBox (WKT) de los datos de un recorte alineado (.gpkg o .tif) del AOI.

    None si el fichero no se puede leer o el vector no tiene geometrías (recorte
    vacío legítimo: ausencia confirmada de la capa en la zona). mtime forma parte
    de la clave de caché: si la ingesta regenera el fichero, se relee.
    """
    p = Path(path_str)
    try:
        if p.suffix == ".tif":
            import rasterio
            with rasterio.open(p) as src:
                b = src.bounds  # left, bottom, right, top
            return _shp_box(b.left, b.bottom, b.right, b.top).wkt
        b = gpd.read_file(p).total_bounds
        if b is None or any(np.isnan(b)):
            return None
        return _shp_box(*b).wkt
    except Exception:
        return None


# ── Acceso directo a las descargas manuales (Catastro INSPIRE, RN2000, SNCZI) ──
#
# La capa realmente manual es CATASTRO: se descarga por municipio en la Sede del
# Catastro (servicio INSPIRE). Para que el usuario no tenga que averiguar qué
# municipio le toca, resolvemos con las coordenadas del corredor:
#   1) OVC Consulta_RCCOOR → referencia catastral del punto; sus 5 primeros dígitos
#      son el código DGC del municipio (provincia[2] + municipio[3]).
#   2) Feed ATOM provincial de "Cadastral Parcels" → enlace directo (enclosure) al
#      ZIP INSPIRE de parcelas de ese municipio.
# Todo cacheado y tolerante a fallos: sin red, se cae al portal general.

# HTTPS: el HTTP plano del Catastro está deprecado y algunas redes corporativas
# lo bloquean (lo que se manifestaba como falso "sin conexión").
_OVC_RCCOOR = ("https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/"
               "OVCCoordenadas.asmx/Consulta_RCCOOR")
_CAT_INSPIRE_CP = "https://www.catastro.hacienda.gob.es/INSPIRE/CadastralParcels"
# Portales de descarga (fallback / fuentes recomendadas que se aportan a mano)
_URL_CATASTRO_PORTAL = "https://www.catastro.hacienda.gob.es/webinspire/index.html"
# Sede Electronica del Catastro — descarga de datos (urbana/rustica por municipio).
# Requiere identificacion con cl@ve o certificado; es un portal con formulario, no
# admite deep-link por municipio, asi que enlazamos al portal y mostramos el codigo
# DGC + nombre para que el usuario seleccione alli provincia → municipio → urbana/rustica.
_CAT_SEDE_DESCARGA = "https://www.sedecatastro.gob.es/Accesos/SECAccDescargaDatos.aspx"
# Carpeta donde aterrizan los ZIP catastrales subidos en la app (uno por municipio).
_CAT_RAW_DIR = _ROOT / "data" / "raw" / "Catastro"
# Fuentes oficiales de las capas que el pipeline descarga solo (mismos endpoints
# que usa src.ingesta.descargar_capas). El .html del portal MITECO de zonas
# inundables devolvía 404, así que apuntamos al servicio real (OGC API Features).
# RN2000 usa el mismo OGC API Features de MITECO que SNCZI (el WFS del IGN
# redes-ecologicas está caído/inestable de forma recurrente).
_URL_RN2000 = "https://wmts.mapama.gob.es/sig-api/ogc/features/v1"
_URL_SNCZI = "https://wmts.mapama.gob.es/sig-api/ogc/features/v1"


def _xml_localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@lru_cache(maxsize=4096)
def _ovc_parcela(xq: int, yq: int) -> tuple[str, str] | None:
    """(dgc5, refcat14) de la parcela en (xq, yq) EPSG:25830 vía OVC.

    dgc5 = código DGC del municipio (provincia[2]+municipio[3]); refcat14 = pc1+pc2,
    referencia catastral con la que se centra el visor del Catastro. Se consulta con
    coordenadas redondeadas a rejilla gruesa (500 m) para reaprovechar la caché.

    Caché en proceso (lru_cache, no st.cache_data) para poder consultar en paralelo
    desde varios hilos sin ScriptRunContext. IMPORTANTE: si hay fallo de red, la
    excepción se PROPAGA a propósito — lru_cache no memoriza llamadas que lanzan,
    así que un corte puntual no envenena la caché (el bug del falso "sin conexión"
    persistente). Solo se cachea None cuando el servicio responde de verdad pero
    no hay parcela en esas coordenadas.
    """
    q = urllib.parse.urlencode({
        "SRS": "EPSG:25830", "Coordenada_X": str(xq), "Coordenada_Y": str(yq),
    })
    with urllib.request.urlopen(f"{_OVC_RCCOOR}?{q}", timeout=6) as r:
        root = ET.fromstring(r.read())
    pc1 = pc2 = ""
    for el in root.iter():
        name = _xml_localname(el.tag)
        if name == "pc1" and el.text:
            pc1 = el.text.strip()
        elif name == "pc2" and el.text:
            pc2 = el.text.strip()
    dgc = pc1[:5]
    if len(dgc) != 5 or not dgc.isdigit():
        return None
    return dgc, (pc1 + pc2)


@st.cache_data(show_spinner=False, ttl=86400)
def _catastro_atom_tabla(prov: str) -> list[dict]:
    """Tabla [{dgc, nombre, url_zip}] del feed ATOM provincial de parcelas INSPIRE.

    Un feed por provincia con TODOS sus municipios (código DGC + nombre + enlace
    directo al ZIP). Los fallos de red se propagan (no se cachean), igual que en
    _ovc_parcela."""
    url = f"{_CAT_INSPIRE_CP}/{prov}/ES.SDGC.CP.atom_{prov}.xml"
    with urllib.request.urlopen(url, timeout=10) as r:
        root = ET.fromstring(r.read())
    filas: list[dict] = []
    for link in root.iter("{http://www.w3.org/2005/Atom}link"):
        if link.get("rel") != "enclosure":
            continue
        href = link.get("href", "")
        # .../{prov}/{dgc5}-NOMBRE/A.ES.SDGC.CP.{dgc5}.zip
        m = re.search(r"/(\d{5})-([^/]+)/[^/]*\.CP\.\1\.zip$", href)
        if not m:
            continue
        dgc, nombre = m.group(1), m.group(2)
        # El nombre del municipio lleva espacios/acentos (p. ej. "FUENTES DE
        # EBRO", "ALCAÑIZ"); hay que percent-encodear la ruta o el navegador
        # no descarga el ZIP.
        sp = urllib.parse.urlsplit(href)
        url_zip = urllib.parse.urlunsplit(
            (sp.scheme, sp.netloc, urllib.parse.quote(sp.path), sp.query, sp.fragment)
        )
        filas.append({"dgc": dgc, "nombre": nombre.replace("%20", " ").strip(),
                      "url_zip": url_zip})
    return filas


def _catastro_cp_zip(dgc5: str) -> tuple[str, str] | None:
    """(nombre_municipio, url_zip) del ZIP INSPIRE de parcelas por código DGC."""
    for fila in _catastro_atom_tabla(dgc5[:2]):
        if fila["dgc"] == dgc5:
            return fila["nombre"], fila["url_zip"]
    return None


def _normalizar_nombre(s: str) -> str:
    """Normaliza un nombre de municipio para casarlo entre fuentes (IGN ↔ Catastro):
    sin acentos, mayúsculas, y guiones/apóstrofes/barras como espacio (el Catastro
    escribe "VILA REAL" donde el IGN dice "Vila-real")."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[-'’/·.,()]", " ", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def _catastro_atom_por_nombre(prov: str, nombre: str) -> dict | None:
    """Fila del feed ATOM cuyo municipio casa con <nombre> (del IGN).

    Necesario porque el código municipal del IGN es el INE y el del Catastro es
    el DGC, y NO coinciden (p. ej. Fuentes de Ebro: INE 50115, DGC 50116); el
    nombre es la clave común. Prueba igualdad exacta normalizada y después
    contención (nombres bilingües o con coletillas)."""
    tabla = _catastro_atom_tabla(prov)
    objetivo = _normalizar_nombre(nombre)
    if not objetivo:
        return None
    for fila in tabla:
        if _normalizar_nombre(fila["nombre"]) == objetivo:
            return fila
    for fila in tabla:
        fn = _normalizar_nombre(fila["nombre"])
        if fn and (objetivo in fn or fn in objetivo):
            return fila
    # Último nivel: por tokens — casa "VILAFRANCA DEL CID" con la entrada doble
    # "VILAFRANCA VILLAFRANCA DEL CID" (feed con el nombre en ambos idiomas).
    tok_obj = set(objetivo.split())
    for fila in tabla:
        tok_fila = set(_normalizar_nombre(fila["nombre"]).split())
        if tok_obj and (tok_obj <= tok_fila or tok_fila <= tok_obj):
            return fila
    return None


# ── Subida de ZIP catastrales por municipio (paso manual con cl@ve) ────────────
# El usuario descarga en la Sede Electronica (cl@ve) la cartografia urbana y
# rustica de cada municipio y la sube aqui. Cada municipio tiene su carpeta
# data/raw/Catastro/<dgc>/; se considera "listo" (tick) cuando hay un PARCELA.shp
# legible por el pipeline (subido directamente o convertido desde GML INSPIRE).

def _cat_upload_dir(dgc: str) -> Path:
    """Carpeta destino de los ZIP subidos para el municipio <dgc>."""
    return _CAT_RAW_DIR / dgc


def _cat_es_legible(dgc: str) -> bool:
    """True si el municipio <dgc> tiene un PARCELA.shp que el pipeline puede leer.

    Es el tick "de verdad": un ZIP subido solo cuenta cuando existe (o se ha
    convertido a) PARCELA.shp, el formato que consume alinear_capas.py.
    """
    d = _cat_upload_dir(dgc)
    if not d.exists():
        return False
    return any(p.stem.lower() == "parcela" for p in d.rglob("*.shp"))


def _cat_normalizar(dgc: str, zip_path: Path) -> dict:
    """Convierte el ZIP subido al formato del pipeline (PARCELA.shp)."""
    from ingesta.convertir_catastro import normalizar_zip_catastro
    return normalizar_zip_catastro(zip_path, _cat_upload_dir(dgc))


def _cat_guardar_subida(dgc: str, uploaded) -> Path:
    """Guarda un fichero subido (UploadedFile) en data/raw/Catastro/<dgc>/.

    Conserva el nombre original (p. ej. 50074_URBANA.zip); si ya existe uno con
    ese nombre lo sobrescribe. Devuelve la ruta escrita.
    """
    d = _cat_upload_dir(dgc)
    d.mkdir(parents=True, exist_ok=True)
    # Sanea el nombre para evitar rutas raras; conserva extension.
    nombre = Path(uploaded.name).name or f"{dgc}.zip"
    dest = d / nombre
    dest.write_bytes(uploaded.getbuffer())
    return dest


# Centinela para distinguir "fallo de red" de "sin parcela" en el muestreo paralelo.
_OVC_NET_ERROR = object()


def _puntos_ovc_aoi(coords_esc: dict) -> tuple[list[tuple[int, int]], LineString]:
    """Puntos de muestreo (rejilla de 500 m) que cubren el AOI COMPLETO del
    corredor: la línea origen-destino con buffer de 1 km a cada lado — el mismo
    corredor que usa la ingesta (_AOI_BUFFER_M). Antes solo se muestreaba el eje,
    con lo que un municipio que entrara en el AOI solo por los flancos no salía.

    Los puntos van snapeados a la rejilla (reaprovechan la caché OVC) y ordenados
    por avance a lo largo del eje, para listar los municipios origen → destino.
    """
    line = LineString([
        (coords_esc["origen"]["x"], coords_esc["origen"]["y"]),
        (coords_esc["destino"]["x"], coords_esc["destino"]["y"]),
    ])
    aoi = line.buffer(_AOI_BUFFER_M, cap_style=2)
    paso = 500
    xmin, ymin, xmax, ymax = aoi.bounds
    pts: list[tuple[int, int]] = []
    for gx in range(int(xmin // paso) * paso, (int(xmax // paso) + 1) * paso + 1, paso):
        for gy in range(int(ymin // paso) * paso, (int(ymax // paso) + 1) * paso + 1, paso):
            if aoi.intersects(Point(gx, gy)):
                pts.append((gx, gy))
    # Origen y destino siempre incluidos aunque su nodo de rejilla caiga fuera.
    for rol in ("origen", "destino"):
        p = (round(coords_esc[rol]["x"] / paso) * paso,
             round(coords_esc[rol]["y"] / paso) * paso)
        if p not in pts:
            pts.append(p)
    pts.sort(key=lambda p: line.project(Point(p)))
    return pts, line


# OGC API Features del IGN — límites municipales oficiales (INSPIRE AU).
_URL_IGN_AU = "https://api-features.ign.es/collections/administrativeunit/items"


@st.cache_data(show_spinner=False, ttl=86400)
def _ign_municipios_bbox(xmin: float, ymin: float, xmax: float, ymax: float) -> list[dict]:
    """Municipios (IGN) cuyo término toca el bbox (EPSG:25830), CON su geometría.

    Devuelve [{ine, nombre, geom_wkt}] con la geometría ya en 25830 para poder
    intersectarla con el corredor exacto. Los fallos de red se propagan (no se
    cachean)."""
    lon1, lat1 = _to_wgs84.transform(xmin, ymin)
    lon2, lat2 = _to_wgs84.transform(xmax, ymax)
    q = urllib.parse.urlencode({
        "f": "json", "limit": "100",
        "bbox": f"{lon1:.6f},{lat1:.6f},{lon2:.6f},{lat2:.6f}",
        "nationallevelname": "Municipio",
        "crs": "http://www.opengis.net/def/crs/EPSG/0/25830",
    })
    req = urllib.request.Request(f"{_URL_IGN_AU}?{q}",
                                 headers={"Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        fc = json.load(r)
    out = []
    for f in fc.get("features", []):
        props = f.get("properties", {})
        geom = f.get("geometry")
        if not geom:
            continue
        out.append({
            "ine": str(props.get("nationalcode", ""))[-5:],
            "nombre": props.get("nameunit", "") or "",
            "geom_wkt": _shp_shape(geom).wkt,
        })
    return out


def _catastro_municipios_aoi(coords_esc: dict) -> list[dict]:
    """Municipios cuyo término toca el AOI del corredor (línea origen-destino
    + buffer de 1 km por lado), con enlace directo a su ZIP INSPIRE.

    Fuente primaria: límites municipales oficiales del IGN (OGC API Features) —
    intersección EXACTA término ↔ corredor, no muestreo por puntos, así no se
    escapa ningún municipio por estrecho que sea su término. El código DGC y el
    ZIP salen del feed ATOM del Catastro casando el nombre (el código INE del
    IGN no es el DGC). Si el servicio del IGN falla, se cae al muestreo OVC.
    Devuelve [{dgc, nombre, url_zip}] en orden origen → destino.
    """
    line = LineString([
        (coords_esc["origen"]["x"], coords_esc["origen"]["y"]),
        (coords_esc["destino"]["x"], coords_esc["destino"]["y"]),
    ])
    corredor = line.buffer(_AOI_BUFFER_M, cap_style=2)
    try:
        candidatos = _ign_municipios_bbox(*corredor.bounds)
    except Exception:
        return _catastro_municipios_ovc(coords_esc)

    dentro: list[tuple[float, dict]] = []
    for c in candidatos:
        try:
            geom = _shp_wkt.loads(c["geom_wkt"])
        except Exception:
            continue
        if not geom.intersects(corredor):
            continue  # tocaba el bbox pero no el corredor real de 1 km
        avance = line.project(geom.intersection(corredor).centroid)
        dentro.append((avance, c))
    dentro.sort(key=lambda t: t[0])

    municipios: list[dict] = []
    for _, c in dentro:
        fila = None
        try:
            fila = _catastro_atom_por_nombre(c["ine"][:2], c["nombre"])
        except Exception:
            fila = None  # sin feed ATOM: se cae al portal general
        municipios.append({
            "dgc": fila["dgc"] if fila else f"INE-{c['ine']}",
            "nombre": (fila["nombre"] if fila else c["nombre"]) or "",
            "url_zip": fila["url_zip"] if fila else _URL_CATASTRO_PORTAL,
        })
    return municipios


def _catastro_municipios_ovc(coords_esc: dict) -> list[dict]:
    """Fallback por muestreo OVC (rejilla de 500 m sobre el corredor) cuando el
    servicio de límites municipales del IGN no responde. Menos exhaustivo: un
    término que no caiga en ningún nodo de la rejilla no se detecta."""
    pts, _ = _puntos_ovc_aoi(coords_esc)

    def _consulta(p: tuple[int, int]):
        try:
            return _ovc_parcela(*p)
        except Exception:
            # Fallo de red en este punto: lo marcamos pero seguimos; basta con
            # que responda algún punto para localizar municipios.
            return _OVC_NET_ERROR

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(_consulta, pts))

    errores_red = sum(1 for r in resultados if r is _OVC_NET_ERROR)
    municipios: dict[str, dict] = {}
    for parc in resultados:  # ya en orden origen → destino
        if parc is _OVC_NET_ERROR or not parc or parc[0] in municipios:
            continue
        dgc, _refcat = parc
        try:
            info = _catastro_cp_zip(dgc)
        except Exception:
            info = None  # sin enlace directo al ZIP; se cae al portal general
        municipios[dgc] = {
            "dgc": dgc,
            "nombre": info[0] if info else "",
            "url_zip": info[1] if info else _URL_CATASTRO_PORTAL,
        }
    # Sin ningún municipio Y todas las consultas fallaron por red → es un problema
    # de conexión, no de cobertura. Lo señalamos para que el caller no memorice una
    # lista vacía y permita reintentar (en vez de quedar pegado en "sin conexión").
    if not municipios and errores_red and errores_red == len(pts):
        raise ConnectionError("Servicio OVC del Catastro no accesible")
    return list(municipios.values())


def _render_municipios_catastro(municipios: list[dict]) -> None:
    """Lista interactiva de municipios del corredor (paso 4 + 5).

    Por cada municipio: enlace a la Sede Electronica (cl@ve) para descargar la
    cartografia urbana y rustica, y un subidor de ZIP. Con ≥1 fichero subido el
    municipio queda marcado con un tick. El estado se persiste en disco
    (data/raw/Catastro/<dgc>/), asi que sobrevive a los reruns de Streamlit.
    """
    listos = sum(1 for m in municipios if _cat_es_legible(m["dgc"]))
    total = len(municipios)
    completo = listos == total
    st.markdown(
        f'<div class="cat-count" style="color:{"var(--secondary)" if completo else "#b26a00"};">'
        f'<span class="material-symbols-outlined" style="font-size:19px;">expand_more</span>'
        f'{listos}/{total} municipios con catastro listo (shapefile de parcelas)</div>',
        unsafe_allow_html=True,
    )
    for m in municipios:
        dgc = m["dgc"]
        nombre = (m["nombre"] or "Municipio").title()
        subido = _cat_es_legible(dgc)
        tick = "✅" if subido else "⚪"
        # Expander por municipio: chevron + estado en la cabecera; el cuerpo
        # (enlaces cl@ve + subidor) queda desplegado mientras falte el catastro.
        with st.expander(f"{tick} **{nombre}** ({dgc})", expanded=not subido):
            c_urb, c_rus = st.columns(2)
            with c_urb:
                st.link_button("Urbana · Sede (cl@ve)", _CAT_SEDE_DESCARGA,
                               use_container_width=True,
                               help="Abre la Sede Electronica. Identificate con cl@ve y "
                                    f"descarga la cartografia URBANA del municipio {dgc}.")
            with c_rus:
                st.link_button("Rústica · Sede (cl@ve)", _CAT_SEDE_DESCARGA,
                               use_container_width=True,
                               help="Abre la Sede Electronica. Identificate con cl@ve y "
                                    f"descarga la cartografia RÚSTICA del municipio {dgc}.")
            ups = st.file_uploader(
                f"Subir ZIP(s) de {nombre}", type=["zip"],
                accept_multiple_files=True, key=f"cat_up_{dgc}",
                label_visibility="collapsed",
            )
            # Guarda y NORMALIZA solo ficheros nuevos (evita re-procesar y bucles
            # de rerun). Normalizar = dejar un PARCELA.shp legible por el pipeline:
            # si el ZIP es shapefile Catastro se extrae; si es GML INSPIRE se convierte.
            proc_key = f"_cat_proc_{dgc}"
            res_key = f"_cat_res_{dgc}"
            procesados = st.session_state.setdefault(proc_key, set())
            hubo_nuevo = False
            for up in ups or []:
                sig = (up.name, up.size)
                if sig in procesados:
                    continue
                dest = _cat_guardar_subida(dgc, up)
                with st.spinner(f"Procesando catastro de {nombre}…"):
                    try:
                        st.session_state[res_key] = _cat_normalizar(dgc, dest)
                    except Exception as exc:
                        st.session_state[res_key] = {
                            "estado": "error", "mensaje": str(exc)}
                procesados.add(sig)
                hubo_nuevo = True
            # Feedback del último procesado.
            res = st.session_state.get(res_key)
            if _cat_es_legible(dgc):
                extra = ""
                if res and res.get("estado") == "convertido":
                    extra = f" · {res.get('mensaje', '')}"
                # Mostramos "shapefile de parcelas" (no el nombre técnico PARCELA.shp)
                st.caption(f"✓ Listo para el pipeline: shapefile de parcelas{extra}")
            elif res and res.get("estado") in ("no_geom", "error"):
                st.error(res.get("mensaje", "No se pudo preparar el catastro."))
            if hubo_nuevo:
                st.rerun()


def _estado_datos_aoi(coords_esc: dict, esc: str) -> list[dict]:
    """Estado por capa para el corredor actual — comprobado contra disco.

    Cada item: {nombre, estado ∈ {ok, warn, rec, pend}, detalle}. 'ok' verde
    (los datos de esta zona YA están en disco), 'pend' gris (aún no descargado;
    la ingesta lo bajará sola), 'warn' ambar (verificar / aportar a mano),
    'rec' azul (recomendado incluir).
    """
    from shapely import wkt as _wkt

    xmin, ymin, xmax, ymax = _aoi_bounds(coords_esc)
    aoi = _shp_box(xmin, ymin, xmax, ymax)
    recorte_dir = _ROOT / "data" / "processed" / "Recorte_AOI"

    def _capa_lista(stem: str, ext: str = ".gpkg") -> bool:
        """True si el recorte <stem>_aoi_<esc> existe y sus datos tocan el AOI
        actual. Un vector vacío también cuenta (ausencia confirmada de la capa
        en la zona, contrato de la ingesta); si los datos no tocan el AOI es un
        recorte de otras coordenadas (obsoleto) y la capa queda pendiente."""
        p = recorte_dir / f"{stem}_aoi_{esc}{ext}"
        if not p.exists():
            return False
        bbox_wkt = _recorte_bbox_wkt(str(p), p.stat().st_mtime)
        if bbox_wkt is None:
            return ext == ".gpkg"  # vector vacío legítimo; un .tif ilegible no vale
        try:
            return _wkt.loads(bbox_wkt).intersects(aoi)
        except Exception:
            return False

    def _capa_auto(nombre: str, stems: list[tuple[str, str]], fuente: str,
                   enlaces: list[dict]) -> dict:
        """Tarjeta de capa automática con tick real: verde si TODOS sus recortes
        están en disco para esta zona; gris (pendiente de descarga) si falta alguno."""
        if all(_capa_lista(s, ext) for s, ext in stems):
            return {"nombre": nombre, "estado": "ok",
                    "detalle": f"Ya descargado para esta zona ({fuente})",
                    "enlaces": enlaces}
        return {"nombre": nombre, "estado": "pend",
                "detalle": f"Aún no descargado — se descargará automáticamente ({fuente})",
                "enlaces": enlaces}

    # Catastro — comprobacion real de cobertura contra lo ya descargado/preparado
    cob_wkt = _catastro_cobertura_wkt(str(recorte_dir))
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

    # Catastro es la única capa manual: sus municipios se resuelven bajo demanda
    # (botón en la tarjeta), no aquí, porque son consultas OVC lentas por punto.
    return [
        {"nombre": "Catastro (expropiación)", "estado": cat[0], "detalle": cat[1],
         "manual": True, "enlaces": []},
        # Ticks reales (nuestra rama) + fuente RN2000 actualizada a MITECO (main)
        _capa_auto("Red Natura 2000", [("natura2000", ".gpkg")],
                   "OGC API Features, MITECO",
                   [{"label": "Fuente oficial (OGC API MITECO)", "url": _URL_RN2000,
                     "icono": "open_in_new", "nivel": 0}]),
        _capa_auto("Zonas inundables (SNCZI)", [("inundable", ".gpkg")],
                   "OGC API Features, MITECO",
                   [{"label": "Fuente oficial (OGC API MITECO)", "url": _URL_SNCZI,
                     "icono": "open_in_new", "nivel": 0}]),
        _capa_auto("DEM · Hidrografía · Geología · Viario (OSM)",
                   [("dem", ".tif"), ("hidrografia", ".gpkg"),
                    ("igme", ".gpkg"), ("osm", ".gpkg")],
                   "por zona, bbox", []),
    ]


def _render_estado_datos(coords_esc: dict, esc: str) -> None:
    """Tarjeta de disponibilidad de capas para el corredor origen-destino actual."""
    try:
        items = _estado_datos_aoi(coords_esc, esc)
    except Exception:
        return  # ante cualquier fallo (ficheros/shapely) no romper el Paso 1

    _ICONO = {
        "ok":   ("check_circle",   "var(--secondary)"),
        "pend": ("cloud_download", "var(--on-surface-variant)"),
        "warn": ("warning",        "#b26a00"),
        "rec":  ("lightbulb",      "var(--primary)"),
    }

    def _celda(it: dict, grow: bool = False) -> str:
        icono, icolor = _ICONO[it["estado"]]
        enlaces = ""
        for en in it.get("enlaces", []):
            sec = en.get("nivel", 0) == 1
            margin = "margin-left:19px;" if sec else ""
            peso = "500" if sec else "600"
            tamano = "0.64rem" if sec else "0.68rem"
            lcolor = "var(--on-surface-variant)" if sec else "var(--primary)"
            enlaces += (
                f'<a href="{en["url"]}" target="_blank" rel="noopener" '
                f'style="font-family:var(--font-body);font-size:{tamano};font-weight:{peso};'
                f'color:{lcolor};text-decoration:none;display:inline-flex;'
                f'align-items:center;gap:4px;{margin}">'
                f'<span class="material-symbols-outlined" style="font-size:15px;">'
                f'{en["icono"]}</span>{en["label"]}</a>'
            )
        enlaces_html = (
            f'<div style="margin-top:6px;display:flex;flex-direction:column;gap:3px;">'
            f'{enlaces}</div>' if enlaces else ""
        )
        return (
            f'<div style="border:1px solid var(--outline-variant);'
            f'border-radius:var(--radius-xl);padding:12px 14px;'
            f'background:var(--surface-lowest);box-shadow:var(--shadow-card);'
            f'display:flex;flex-direction:column;{"flex:1 1 0;" if grow else ""}">'
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<span class="material-symbols-outlined" style="font-size:19px;color:{icolor};'
            f'flex:none;">{icono}</span>'
            f'<span style="font-family:var(--font-body);font-weight:700;font-size:0.78rem;'
            f'color:var(--on-surface);line-height:1.2;">{it["nombre"]}</span></div>'
            f'<div style="font-family:var(--font-body);font-size:0.68rem;'
            f'color:var(--on-surface-variant);margin-top:4px;line-height:1.3;">'
            f'{it["detalle"]}</div>{enlaces_html}</div>'
        )

    def _lista_municipios_html(municipios: list[dict], offline: bool = False) -> str:
        """Enlaces al ZIP de parcelas (Catastro INSPIRE) de cada municipio que
        cruza el corredor. Apunta al fichero oficial (catastro.hacienda.gob.es);
        un clic lleva a la descarga del ZIP de ese municipio."""
        if not municipios:
            msg = ("No se han podido localizar los municipios (sin conexión con el "
                   "Catastro). Comprueba tu red y pulsa «Reintentar». "
                   if offline else
                   "No se han encontrado municipios en este corredor. ")
            return (
                f'<div style="font-family:var(--font-body);font-size:0.66rem;'
                f'color:var(--on-surface-variant);margin-top:2px;">'
                f'{msg}'
                f'<a href="{_URL_CATASTRO_PORTAL}" target="_blank" rel="noopener" '
                f'style="color:var(--primary);font-weight:600;text-decoration:none;">'
                f'Abrir portal INSPIRE del Catastro</a></div>'
            )
        filas = ""
        for m in municipios:
            nombre = f"{(m['nombre'] or 'Municipio').title()} ({m['dgc']})"
            tiene_zip = str(m.get("url_zip", "")).lower().endswith(".zip")
            icono, texto = (("download", "descargar ZIP de parcelas") if tiene_zip
                            else ("open_in_new", "abrir portal de descarga INSPIRE"))
            filas += (
                f'<a href="{m["url_zip"]}" target="_blank" rel="noopener" '
                f'style="font-family:var(--font-body);font-size:0.68rem;font-weight:600;'
                f'color:var(--primary);text-decoration:none;display:inline-flex;'
                f'align-items:center;gap:5px;padding:2px 0;">'
                f'<span class="material-symbols-outlined" style="font-size:15px;">'
                f'{icono}</span>{nombre} · {texto}</a>'
            )
        return (
            f'<div style="margin-top:6px;display:flex;flex-direction:column;gap:1px;">'
            f'{filas}</div>'
        )

    # Catastro (capa manual) ocupa media tarjeta; las demás capas, la otra mitad.
    catastro = next((it for it in items if it.get("manual")), None)
    resto = [it for it in items if it is not catastro]

    with st.container(border=False):
        st.markdown(
            '<div style="display:flex;align-items:center;gap:6px;color:var(--primary);'
            'font-weight:700;margin:10px 0 6px 0;">'
            '<span class="material-symbols-outlined" style="font-size:18px;">dataset</span>'
            '<span style="font-size:0.68rem;letter-spacing:0.05em;text-transform:uppercase;">'
            'Datos para esta zona</span></div>',
            unsafe_allow_html=True,
        )
        col_izq, col_der = st.columns(2, gap="small")

        with col_izq:
            if catastro:
                cat_ico, cat_col = _ICONO[catastro["estado"]]
                with st.container(border=False, key="cat_card"):
                    st.markdown(
                        f'<div class="cat-title">'
                        f'<span class="material-symbols-outlined" style="color:{cat_col};">'
                        f'{cat_ico}</span>'
                        f'<span class="txt">{catastro["nombre"]}</span></div>'
                        f'<div class="cat-sub">{catastro["detalle"]}</div>'
                        f'<hr class="cat-div">',
                        unsafe_allow_html=True,
                    )
                    key_exp = "_cat_municipios_abierto"
                    # Firma del corredor actual. La versión ("v2-ign") invalida
                    # listas memorizadas por el algoritmo anterior (muestreo por eje).
                    firma = (
                        coords_esc["origen"]["x"], coords_esc["origen"]["y"],
                        coords_esc["destino"]["x"], coords_esc["destino"]["y"],
                        "v2-ign",
                    )
                    # Si cambian origen/destino (a mano, por clic en el mapa o al
                    # cambiar de escenario), la lista de municipios deja de valer:
                    # se borra, se cierra el desplegable y hay que volver a pulsar
                    # "Ver municipios" para recalcular sobre el nuevo AOI.
                    if st.session_state.get("_cat_municipios_firma") not in (None, firma):
                        st.session_state.pop("_cat_municipios_firma", None)
                        st.session_state.pop("_cat_municipios_lista", None)
                        st.session_state.pop("_cat_municipios_offline", None)
                        st.session_state[key_exp] = False
                    _, c_btn, _ = st.columns([1, 2, 1])
                    with c_btn:
                        if st.button(
                            "Ver municipios",
                            key="btn_cat_municipios",
                            use_container_width=True,
                            icon=":material/travel_explore:",
                            help="Localiza los municipios que cruza el corredor y abre su "
                                 "cartografía en la Sede Electrónica del Catastro.",
                        ):
                            st.session_state[key_exp] = not st.session_state.get(key_exp, False)
                    if st.session_state.get(key_exp):
                        if st.session_state.get("_cat_municipios_firma") != firma:
                            with st.container(key="cat_muni_spinner"), \
                                    st.spinner("Localizando municipios del corredor…"):
                                try:
                                    municipios = _catastro_municipios_aoi(coords_esc)
                                    offline = False
                                except ConnectionError:
                                    municipios = []
                                    offline = True
                                except Exception:
                                    municipios = []
                                    offline = False
                            st.session_state["_cat_municipios_offline"] = offline
                            # Solo memorizamos la firma si el resultado es fiable (éxito,
                            # aunque sea lista vacía legítima). Si fue un corte de red NO
                            # la fijamos: así el próximo intento reintenta en vez de quedar
                            # pegado a una lista vacía por coordenadas.
                            if not offline:
                                st.session_state["_cat_municipios_firma"] = firma
                                # Cacheamos la lista para que la puerta de paso (Paso 1 →
                                # Paso 2) sepa qué municipios exigir subidos antes de seguir.
                                st.session_state["_cat_municipios_lista"] = municipios
                        else:
                            municipios = st.session_state.get("_cat_municipios_lista") or []
                            st.session_state["_cat_municipios_offline"] = False
                        if municipios:
                            with st.container(border=False, key="cat_muni_box"):
                                _render_municipios_catastro(municipios)
                        else:
                            offline = st.session_state.get("_cat_municipios_offline", False)
                            st.markdown(
                                _lista_municipios_html(municipios, offline=offline),
                                unsafe_allow_html=True,
                            )
                            if offline and st.button(
                                "Reintentar",
                                key="btn_cat_reintentar",
                                icon=":material/refresh:",
                            ):
                                # Fuerza recomputar en el rerun: borra la firma y limpia
                                # la caché de datos por si algún None transitorio quedó.
                                st.session_state.pop("_cat_municipios_firma", None)
                                _ovc_parcela.cache_clear()
                                _ign_municipios_bbox.clear()
                                _catastro_atom_tabla.clear()
                                st.rerun()

        with col_der:
            st.markdown(
                f'<div style="display:flex;flex-direction:column;gap:14px;">'
                f'{"".join(_celda(it, grow=True) for it in resto)}</div>',
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

    col_panel, col_map = st.columns([1.15, 2], gap="small")

    with col_panel:
        with st.container(border=True):
            st.markdown(
                '<div class="constraints-box">'
                '<div style="display:flex;align-items:center;gap:6px;color:var(--primary);'
                'font-weight:700;margin-bottom:5px;">'
                '<span class="material-symbols-outlined" style="font-size:18px;">info</span>'
                '<span style="font-size:0.68rem;letter-spacing:0.05em;text-transform:uppercase;">'
                'Restricciones del modelo</span></div>'
                'Corredor de referencia: <b>2 km de ancho</b> (&plusmn;1 km a cada lado).'
                '</div>',
                unsafe_allow_html=True,
            )

            # Desplegable de escenario: el disparador muestra el escenario activo;
            # al abrirlo, cada escenario es una fila con su nombre (selección), un
            # lápiz para renombrarlo y una papelera para borrarlo, más una opción
            # "＋ Nuevo escenario" al final. El popover permanece abierto entre
            # interacciones internas, así que el renombrado se hace en línea.
            with st.container(key="esc_dropdown"):
                with st.popover(f"Escenario {esc_activo}", use_container_width=True):
                    editando = st.session_state.get("_editando_esc")
                    for s in escenarios:
                        if editando == s:
                            # Fila en modo edición: campo de texto + confirmar / cancelar.
                            c_in, c_ok, c_no = st.columns(
                                [4, 1, 1], vertical_alignment="center"
                            )
                            with c_in:
                                nuevo_nombre = st.text_input(
                                    "Nuevo nombre",
                                    value=s,
                                    label_visibility="collapsed",
                                    key=f"rename_input_{s}",
                                )
                            with c_ok:
                                if st.button(
                                    ":material/check:", use_container_width=True,
                                    key=f"rename_ok_{s}", help="Guardar nombre",
                                ):
                                    try:
                                        nuevo = _renombrar_escenario(
                                            cfg, coords, s, nuevo_nombre
                                        )
                                        if st.session_state.escenario_activo == s:
                                            st.session_state.escenario_activo = nuevo
                                        st.session_state._editando_esc = None
                                        st.rerun()
                                    except ValueError as exc:
                                        st.error(str(exc))
                            with c_no:
                                if st.button(
                                    ":material/close:", use_container_width=True,
                                    key=f"rename_no_{s}", help="Cancelar",
                                ):
                                    st.session_state._editando_esc = None
                                    st.rerun()
                            continue

                        c_sel, c_edit, c_del = st.columns(
                            [4, 1, 1], vertical_alignment="center"
                        )
                        with c_sel:
                            activo = s == esc_activo
                            marca = "●" if activo else "○"
                            etiqueta = (
                                f"{marca}  **Escenario {s}**" if activo
                                else f"{marca}  Escenario {s}"
                            )
                            if st.button(
                                etiqueta,
                                use_container_width=True,
                                key=f"sel_esc_{s}",
                            ):
                                st.session_state.escenario_activo = s
                                st.rerun()
                        with c_edit:
                            if st.button(
                                ":material/edit:",
                                use_container_width=True,
                                key=f"edit_esc_{s}",
                                help="Editar nombre",
                            ):
                                st.session_state._editando_esc = s
                                st.rerun()
                        with c_del:
                            puede_borrar = len(escenarios) > 1
                            if st.button(
                                ":material/delete:",
                                use_container_width=True,
                                key=f"del_esc_{s}",
                                disabled=not puede_borrar,
                                help="Borrar este escenario" if puede_borrar
                                else "Debe quedar al menos un escenario",
                            ):
                                try:
                                    era_activo = s == st.session_state.escenario_activo
                                    _borrar_escenario(cfg, coords, s)
                                    if era_activo:
                                        restantes = sorted(
                                            coords.keys(), key=lambda x: (len(x), x)
                                        )
                                        st.session_state.escenario_activo = restantes[0]
                                    st.rerun()
                                except ValueError as exc:
                                    st.error(str(exc))
                    st.divider()
                    if st.button(
                        "＋ Nuevo escenario",
                        use_container_width=True,
                        key="btn_nuevo_esc",
                    ):
                        nuevo = _crear_escenario(
                            cfg, coords, _siguiente_id_escenario(escenarios), esc_activo
                        )
                        st.session_state.escenario_activo = nuevo
                        st.session_state.punto_activo_rol = "origen"
                        st.session_state._editando_esc = None
                        st.rerun()

            esc_activo = st.session_state.escenario_activo

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
                f'padding:15px 20px;margin:6px 0 10px;">'
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
                    # Si no hay punto activo (segmentos deseleccionados), el clic
                    # no fija nada: las coordenadas se editan a mano.
                    if rol in ("origen", "destino"):
                        x_utm, y_utm = _latlon_to_utm(click["lat"], click["lng"])
                        # Guardar el clic como pendiente: se aplica al estado de los
                        # widgets al inicio del proximo run, antes de instanciarlos.
                        st.session_state._pending_click = {
                            "esc": esc_activo, "rol": rol,
                            "x": round(x_utm), "y": round(y_utm),
                        }
                        st.rerun()

            # Debajo del mapa, centrado: la etiqueta "El próximo clic fija:" es la
            # PROPIA etiqueta del control segmentado (no un markdown aparte). Así el
            # CSS coloca etiqueta y botones en una fila flex y quedan alineados
            # verticalmente sin depender de columnas de Streamlit (que colapsan).
            # El modo "single" permite deseleccionar ambos (devuelve None): entonces
            # el clic en el mapa no fija nada y todo se mete por coordenadas.
            with st.container(key="p1_map_selector"):
                # Sembrar la clave del widget una sola vez (no usar `default=` junto
                # a `key=`: eso impide deseleccionar). Con "single" se puede volver a
                # pulsar el segmento activo para dejar ninguno seleccionado.
                if "seg_punto_rol" not in st.session_state:
                    st.session_state.seg_punto_rol = (
                        st.session_state.punto_activo_rol or "origen"
                    )
                st.session_state.punto_activo_rol = st.segmented_control(
                    "El próximo clic fija:",
                    options=["origen", "destino"],
                    format_func=lambda r: (
                        ":material/location_on: Origen" if r == "origen"
                        else ":material/flag: Destino"
                    ),
                    selection_mode="single",
                    key="seg_punto_rol",
                )
        else:
            from streamlit.components.v1 import html as _html
            _html(m._repr_html_(), height=560)

    # Disponibilidad de capas para el corredor — a ancho completo, bajo el mapa.
    _render_estado_datos(coords[esc_activo], esc_activo)

    # ── Navegación ────────────────────────────────────────────────────────────
    distancias = {
        s: _dist_m(
            coords[s]["origen"]["x"], coords[s]["origen"]["y"],
            coords[s]["destino"]["x"], coords[s]["destino"]["y"],
        )
        for s in escenarios
    }
    can_next_dist = all(d <= MAX_DIST_M for d in distancias.values())

    # Puerta de catastro: si se localizaron los municipios del corredor y falta
    # subir el ZIP de alguno, avisamos — pero SOLO al pulsar "Pesos y Perfiles →"
    # (no de forma preventiva). El primer clic con catastros pendientes muestra
    # el aviso y pide confirmación explícita (checkbox) en vez de navegar.
    municipios_cat = st.session_state.get("_cat_municipios_lista") or []
    faltan_cat = [m for m in municipios_cat if not _cat_es_legible(m["dgc"])]
    if not faltan_cat:
        # Ya está todo subido (o no hay lista): retiramos el aviso si estaba.
        st.session_state.pop("_cat_aviso_pendiente", None)

    st.markdown("---")

    confirmar_cat = False
    if faltan_cat and st.session_state.get("_cat_aviso_pendiente"):
        nombres = ", ".join((m["nombre"] or m["dgc"]).title() for m in faltan_cat)
        st.warning(
            f"Faltan catastros por subir en {len(faltan_cat)} de "
            f"{len(municipios_cat)} municipios: {nombres}. Súbelos arriba en "
            "«Ver municipios del corredor» o continúa sin ellos."
        )
        confirmar_cat = st.checkbox(
            "Continuar sin todos los catastros subidos",
            key="cat_confirmar_incompleto",
        )

    can_next = can_next_dist

    c_back, _, c_next = st.columns([1.4, 2, 1.4])
    with c_back:
        if st.button("← Inicio", use_container_width=True, key="btn_p1_inicio"):
            st.session_state.pantalla = "bienvenida"
            st.rerun()
    with c_next:
        if st.button("Pesos y Perfiles  →", type="primary",
                     disabled=not can_next, use_container_width=True, key="btn_p1_next"):
            if faltan_cat and not confirmar_cat:
                # Primer intento con catastros pendientes: enseñar el aviso y
                # esperar confirmación en vez de pasar de pantalla.
                st.session_state["_cat_aviso_pendiente"] = True
                st.rerun()
            else:
                cfg = _aplicar_coords_a_cfg(cfg, coords)
                _guardar_cfg(cfg)
                st.session_state.pantalla = "paso2"
                st.rerun()

    if not can_next_dist:
        invalidos = [s for s, d in distancias.items() if d > MAX_DIST_M]
        st.warning(
            "Corrige las distancias antes de continuar. "
            f"Escenarios fuera de limite: {', '.join(invalidos)}"
        )


# ── Paso 2: Pesos y Perfiles ───────────────────────────────────────────────────

def _render_paso2():
    coords = st.session_state.get("coords") or _coords_desde_cfg(_leer_cfg())
    escenarios = sorted(coords.keys(), key=lambda x: (len(x), x))

    st.markdown(
        '<div class="section-h1">Paso 2: Pesos y Perfiles</div>',
        unsafe_allow_html=True,
    )

    # Editor de pesos a todo el ancho (sin tabla comparativa a la derecha).
    perfiles_cfg = _render_editor_pesos()

    # ── Caja: barrera dura de pendiente ───────────────────────────────────────
    barrera_defecto = _barrera_pendiente_actual()
    with st.container(border=True):
        st.markdown(
            '<div class="scenario-title">Barrera dura de pendiente</div>'
            '<p style="color:var(--on-surface-variant);font-size:0.85rem;margin:0 0 8px;">'
            'Pendiente máxima transitable: las celdas cuyo terreno supere este valor se '
            'marcan como <b>intransitables</b> y las rutas las esquivan. '
            '(70&nbsp;% ≈ 35°).</p>',
            unsafe_allow_html=True,
        )
        c_in, _sp = st.columns([1, 2])
        with c_in:
            barrera_pct = st.number_input(
                "Barrera de pendiente (%)",
                min_value=5, max_value=100,
                value=int(barrera_defecto), step=5,
                format="%d",
                key="barrera_pendiente_pct",
            )

    # ── Navegación inferior (como en el Paso 1) ───────────────────────────────
    st.markdown("---")
    c_back, _, c_next = st.columns([1.4, 2, 1.4])
    with c_back:
        if st.button("← Origen y Destino", use_container_width=True, key="btn_p2_back"):
            st.session_state.pantalla = "paso1"
            st.rerun()
    with c_next:
        generar = st.button("Generar rutas", type="primary",
                            use_container_width=True, key="btn_generar_rutas")

    if generar:
        # Solo se pasa el umbral si cambió respecto al valor por defecto (evita
        # regenerar la capa TPI innecesariamente).
        umbral = float(barrera_pct) if int(barrera_pct) != int(barrera_defecto) else None
        bar = st.progress(0, text="Iniciando pipeline...")
        try:
            resultados = _ejecutar_pipeline(
                lambda pct, msg: bar.progress(pct, text=msg),
                escenarios=escenarios,
                perfiles=copy.deepcopy(perfiles_cfg),
                umbral_barrera_pct=umbral,
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

    def _validos(campo: str) -> list[float]:
        """Valores calculados del campo; excluye None (métrica fallida)."""
        return [r[campo] for r in rutas if r.get(campo) is not None]

    longs = _validos("longitud_km")
    costes = _validos("coste_relativo")
    pends = _validos("pendiente_max_pct")
    prots = _validos("km_protegida")

    # Los 4 KPI son la MEDIA de ese parámetro entre las rutas de los 4 perfiles
    # (no el máximo ni la suma), para que "resumen del escenario" signifique
    # siempre lo mismo: el promedio de las alternativas generadas.
    long_txt = f"{sum(longs) / len(longs):.2f} km".replace(".", ",") if longs else "s/d"
    coste_txt = f"{sum(costes) / len(costes):.3f}".replace(".", ",") if costes else "s/d"
    pend_txt = f"{sum(pends) / len(pends):.0f} %" if pends else "s/d"
    if prots:
        km_prot_medio = sum(prots) / len(prots)
        impacto = "Bajo" if km_prot_medio < 0.5 else ("Medio" if km_prot_medio < 2.0 else "Alto")
    else:
        impacto = "s/d"
    return [
        ("route", "Longitud media", long_txt),
        ("stacked_line_chart", "Coste relativo (índice)", coste_txt),
        ("trending_up", "Pendiente máx. media", pend_txt),
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
    st.caption(
        "Los 4 valores son la media entre las rutas de los cuatro perfiles de "
        "este escenario. Impacto ambiental, según la media de km en zona "
        "protegida (Red Natura 2000) por ruta: **Bajo** < 0,5 km · "
        "**Medio** 0,5-2 km · **Alto** > 2 km."
    )


_COL_RENAME_METRICAS = {
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


def _firma_pdf_informe(
    resultados: dict, escenarios: list[str], perfiles: list[dict] | None,
) -> tuple:
    """Firma de caché del informe PDF: además de escenarios/pesos (que ya
    cambian si se reprocesa con otro perfil), incluye el CONTENIDO de las
    métricas y la fecha de modificación de los ficheros de ráster/ruta que
    ilustran el informe. Sin esto, reprocesar el MISMO escenario con los
    mismos pesos (p. ej. tras arreglar una descarga que antes fallaba) no
    cambia la firma y el botón sigue sirviendo el PDF viejo."""
    pesos = tuple(
        (p.get("id"), tuple(sorted(p.get("pesos", {}).items())))
        for p in (perfiles or [])
    )
    metricas = tuple(
        (s, tuple(
            (r.perfil, tuple(sorted(r.to_dict().items(), key=lambda kv: kv[0])))
            for r in resultados.get(s, {}).get("rutas", [])
        ))
        for s in escenarios
    )

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return -1.0

    ficheros = tuple(
        (s, pid,
         _mtime(_TRAZADOS_DIR / f"superficie_{s}_{pid}.tif"),
         _mtime(_RUTAS_DIR / f"ruta_{s}_{pid}.gpkg"))
        for s in escenarios for pid in PERFILES
    )
    return (tuple(escenarios), pesos, metricas, ficheros)


def _boton_informe_pdf(resultados: dict, escenarios: list[str]) -> None:
    """Botón que genera y descarga el informe PDF completo de resultados.

    El PDF (matplotlib + reportlab) se construye una sola vez por combinación de
    escenarios/perfiles/métricas/ficheros y se cachea en sesión; los reruns
    (cambio de pestaña, etc.) reutilizan los bytes ya generados.
    """
    perfiles = st.session_state.get("perfiles_procesados")
    firma = _firma_pdf_informe(resultados, escenarios, perfiles)
    cache = st.session_state.get("_pdf_informe_cache")
    if not (cache and cache[0] == firma):
        try:
            from informe import construir_informe_pdf

            coords = _coords_desde_cfg(_leer_cfg())
            data = construir_informe_pdf(
                escenarios=escenarios,
                resultados=resultados,
                perfiles=perfiles,
                coords=coords,
                rutas_dir=_RUTAS_DIR,
                trazados_dir=_TRAZADOS_DIR,
                perfiles_orden=PERFILES,
                colores=_COLORES,
                nombre_perfil=_NOMBRE_PERFIL,
                capas_peso=_CAPAS_PESO,
                col_rename=_COL_RENAME_METRICAS,
                logo_path=_ICON_PATH,
            )
        except Exception as exc:  # noqa: BLE001
            st.button("Generar informe PDF", disabled=True,
                      use_container_width=True, icon=":material/download:",
                      help=f"No se pudo generar el informe: {exc}")
            return
        cache = (firma, data)
        st.session_state["_pdf_informe_cache"] = cache

    st.download_button(
        "Generar informe PDF",
        data=cache[1],
        file_name="informe_trazados_alternativos.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
        icon=":material/download:",
        key="dl_informe_pdf",
    )


def _boton_descargar_rutas_zip(escenarios: list[str]) -> None:
    """Botón que empaqueta las rutas .gpkg generadas en un ZIP descargable.

    Estructura del archivo «Trazados de ramales.zip»: una carpeta por escenario
    (`Escenario {s}/`) y dentro los .gpkg de las rutas generadas de ese
    escenario (un fichero por perfil) junto a su .qml de estilo QGIS, cuando
    existe. El ZIP se construye una sola vez por combinación de rutas y se
    cachea en sesión; los reruns reutilizan los bytes.
    """
    import io
    import zipfile

    rutas = [
        (s, perfil, _RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg")
        for s in escenarios
        for perfil in PERFILES
        if (_RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg").exists()
    ]
    if not rutas:
        st.button(
            "Descargar rutas (.gpkg)", disabled=True, type="primary",
            use_container_width=True, icon=":material/folder_zip:",
            help="No hay rutas generadas para descargar.",
            key="dl_rutas_zip_disabled",
        )
        return

    firma = tuple((s, perfil) for s, perfil, _ in rutas)
    cache = st.session_state.get("_zip_rutas_cache")
    if not (cache and cache[0] == firma):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for s, _perfil, path in rutas:
                zf.write(path, f"Escenario {s}/{path.name}")
                qml = path.with_suffix(".qml")   # estilo QGIS de la ruta
                if qml.exists():
                    zf.write(qml, f"Escenario {s}/{qml.name}")
        cache = (firma, buf.getvalue())
        st.session_state["_zip_rutas_cache"] = cache

    st.download_button(
        "Descargar rutas (.gpkg)",
        data=cache[1],
        file_name="Trazados de ramales.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
        icon=":material/folder_zip:",
        key="dl_rutas_zip",
    )


def _render_results():
    resultados = st.session_state.get("resultados", {})
    escenarios = st.session_state.get(
        "escenarios_procesados", sorted(resultados.keys(), key=lambda x: (len(x), x))
    )

    head_l, head_r = st.columns([3.2, 1], vertical_alignment="center")
    with head_l:
        st.markdown(
            '<div class="results-title">Comparativa de Trazados</div>'
            '<p class="results-sub">Visualización métrica de indicadores de rendimiento de los '
            'trazados alternativos. Proyecto CI2 Lab 2026.</p>',
            unsafe_allow_html=True,
        )
    with head_r:
        with st.container(key="btn_pdf_informe"):
            _boton_informe_pdf(resultados, escenarios)
        with st.container(key="btn_dl_rutas"):
            _boton_descargar_rutas_zip(escenarios)

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
    col_rename = _COL_RENAME_METRICAS
    # Formato por columna: máximo 3 decimales; los recuentos de cruces, enteros.
    fmt_metricas = {
        "km":          "{:.2f}",
        "Coste rel.":  "{:.3f}",
        "Pend.max %":  "{:.1f}",
        "Pend.med %":  "{:.2f}",
        "km prot.":    "{:.3f}",
        "km inund.":   "{:.3f}",
        "km urbano":   "{:.3f}",
        "Rios":        "{:.0f}",
        "Carreteras":  "{:.0f}",
        "FFCC":        "{:.0f}",
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

            # Cada columna numérica se formatea a texto (máx. 3 decimales) y se
            # usa st.dataframe: la tabla sigue siendo ajustable (redimensionar,
            # ordenar, fijar, ocultar…), pero al ser columnas de texto ya NO
            # aparece la opción "Format" del menú de columna (que solo existe
            # para columnas numéricas).
            df_txt = df_show.copy()
            for etiqueta, spec in fmt_metricas.items():
                if etiqueta in df_txt.columns:
                    df_txt[etiqueta] = df_txt[etiqueta].map(
                        lambda v, _sp=spec: "—" if pd.isna(v) else _sp.format(v)
                    )
            st.dataframe(df_txt, use_container_width=True, hide_index=True)

            # Métricas que fallaron al calcularse aparecen como «—» en la
            # tabla; aquí se indica brevemente el motivo, sin interrumpir
            # la lectura con un aviso destacado.
            motivos_s = list(dict.fromkeys(
                v for r in rutas for v in r.errores.values()
            ))
            if motivos_s:
                st.caption("«—» sin dato — " + " · ".join(motivos_s))

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

    # ── Navegación inferior (como en el resto de ventanas) ────────────────────
    st.markdown("---")
    c_back, _, _ = st.columns([1.4, 2, 1.4])
    with c_back:
        if st.button("← Volver a configuración", use_container_width=True,
                     key="btn_back_results"):
            st.session_state.pantalla = "paso2"
            st.rerun()


# ── Stepper de progreso ───────────────────────────────────────────────────────

def _stepper(paso: int) -> None:
    """Barra de pasos (1: Origen y Destino · 2: Pesos y Perfiles · 3: Resultados).

    Anima el avance (relleno del conector + pulso del paso nuevo + rebote del que
    se completa) SOLO cuando se avanza de paso, no en cada rerun de la misma
    pantalla: se compara con el paso pintado la última vez (``_stepper_prev``).
    """
    nombres = ["Origen y Destino", "Pesos y Perfiles", "Resultados"]
    kicker = {"done": "Completado", "active": "Paso actual", "pending": "Siguiente"}
    prev = st.session_state.get("_stepper_prev", paso)
    avanza = paso > prev  # solo animamos hacia delante

    partes = ['<div class="enagas-stepper">']
    for i, nombre in enumerate(nombres, start=1):
        estado = "done" if i < paso else ("active" if i == paso else "pending")
        clases = ["step", estado]
        if avanza and prev <= i < paso:            # pasos recién completados
            clases.append("just-done")
        if avanza and estado == "active":          # paso recién activado
            clases.append("just-active")
        partes.append(
            f'<div class="{" ".join(clases)}">'
            f'<div class="step-num">{i}</div>'
            f'<div class="step-txt">'
            f'<span class="step-kicker">{kicker[estado]}</span>'
            f'<span class="step-name">{nombre}</span>'
            f'</div></div>'
        )
        if i < len(nombres):
            conn = ["step-conn"]
            if paso > i:
                conn.append("done")
            if avanza and prev <= i < paso:        # conector que acaba de rellenarse
                conn.append("just-done")
            partes.append(
                f'<div class="{" ".join(conn)}"><div class="step-conn-fill"></div></div>'
            )
    partes.append("</div>")
    # Envuelto en un contenedor con clave: el sticky se aplica al contenedor
    # (hermano del resto de la página), no al markdown, para que tenga recorrido.
    with st.container(key="stepper_wrap"):
        st.markdown("".join(partes), unsafe_allow_html=True)
    st.session_state["_stepper_prev"] = paso


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
                f'<div style="height:100%;min-height:480px;border-radius:var(--radius-xl);'
                f'background-image:url(\'data:image/{mime};base64,{b64}\');'
                f'background-size:cover;background-position:center;'
                f'border:1px solid var(--outline-variant);"></div>'
            )
    # Sin imagen: panel degradado con motivo de red de conducciones
    return (
        '<div style="height:100%;min-height:480px;border-radius:var(--radius-xl);'
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


def _docs_buttons() -> None:
    """Dos botones que abren, en una pestaña nueva, el diagrama de flujo y el
    informe de arquitectura (HTML de docs/entregable/)."""
    import base64
    from streamlit.components.v1 import html as _html

    docs_dir = _ROOT.parent / "docs" / "entregable"
    botones = [
        ("Ver diagrama de flujo", "Diagrama_Flujo_Pipeline.html"),
        ("Ver informe de arquitectura", "Informe_Arquitectura_App.html"),
    ]
    items = []
    for i, (label, fname) in enumerate(botones):
        ruta = docs_dir / fname
        if ruta.exists():
            b64 = base64.b64encode(ruta.read_bytes()).decode()
            items.append((f"doc{i}", label, b64))

    if not items:
        st.toast("Documentos no encontrados.")
        return

    botones_html = "".join(
        f'<button class="docbtn" onclick="openDoc(\'{key}\')">'
        f'<span>{label}</span><span>&#128196;</span></button>'
        for key, label, _ in items
    )
    data_scripts = "".join(
        f'<script type="text/plain" id="{key}">{b64}</script>'
        for key, _, b64 in items
    )
    snippet = f"""
    <style>
      body {{ margin:0; }}
      .docwrap {{ display:flex; flex-direction:column; gap:10px; }}
      .docbtn {{
        display:flex; align-items:center; justify-content:center; gap:8px;
        width:100%; padding:10px 16px; cursor:pointer;
        font-family:'Inter','Segoe UI',Arial,sans-serif; font-weight:600; font-size:0.9rem;
        color:#004e7e; background:#ffffff; border:1px solid #004e7e; border-radius:4px;
        transition:background .15s;
      }}
      .docbtn:hover {{ background:#ebeef0; }}
    </style>
    <div class="docwrap">{botones_html}</div>
    {data_scripts}
    <script>
      function openDoc(id) {{
        var b64 = document.getElementById(id).textContent;
        var bin = atob(b64);
        var arr = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        var blob = new Blob([arr], {{type: 'text/html'}});
        window.open(URL.createObjectURL(blob), '_blank');
      }}
    </script>
    """
    _html(snippet, height=len(items) * 54 + 12)


def _render_bienvenida() -> None:
    col_left, col_right = st.columns([1.15, 1], gap="large")
    with col_left:
        st.markdown(
            '<div style="font-family:var(--font-body);font-weight:700;font-size:0.72rem;'
            'letter-spacing:0.08em;text-transform:uppercase;color:var(--secondary);'
            'margin-bottom:6px;">Infrastructure Routing Tool</div>'
            '<div style="font-family:var(--font-head);font-size:2.3rem;font-weight:800;'
            'color:var(--primary);line-height:1.1;letter-spacing:-0.02em;margin-bottom:14px;">'
            'Generador<br>de Trazados</div>'
            '<p class="welcome-sub" style="text-align:justify;">Herramienta avanzada '
            'para la optimización y diseño de trazados de infraestructuras lineales. Utilice algoritmos '
            'de última generación para calcular las rutas más eficientes basadas en criterios '
            'geográficos, ambientales y de coste.</p>',
            unsafe_allow_html=True,
        )
        st.write("")
        cc1, cc2 = st.columns(2, gap="medium")
        with cc1:
            with st.container(border=True, key="wcard_sim"):
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
            with st.container(border=True, key="wcard_docs"):
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
                _docs_buttons()
    with col_right:
        with st.container(key="hero_col"):
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
    st.components.v1.html(_SLIDER_FILL_JS, height=0)

    with st.container(key="topnav"):
        st.markdown(f'<div class="topnav-left">{_logo_tag}</div>', unsafe_allow_html=True)

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
