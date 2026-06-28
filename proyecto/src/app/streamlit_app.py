"""Interfaz web — Generador de trazados de ramales de H2 (Enagás / CI2 Lab 2026).

Ejecutar desde proyecto/:
    streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import math
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

try:
    from streamlit_folium import st_folium as _st_folium
    _HAS_ST_FOLIUM = True
except ImportError:
    _HAS_ST_FOLIUM = False

# ── CSS estilo Enagás ─────────────────────────────────────────────────────────
_CSS = """
<style>
  .stApp { background-color: #f4f6f9; }

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

  div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #002B5C 0%, #005BAA 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    letter-spacing: 0.3px !important;
    padding: 12px 28px !important;
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


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _ejecutar_pipeline(progress_cb) -> dict:
    import logging as _logging
    _logging.basicConfig(level=_logging.WARNING)

    from trazados.ruta_pendiente import run_perfiles
    from metricas.calculo import calcular_todas

    progress_cb(0.05, "Calculando rutas — Escenario A...")
    run_perfiles("A", lam=4.0)

    progress_cb(0.50, "Calculando rutas — Escenario B...")
    run_perfiles("B", lam=4.0)

    progress_cb(0.85, "Calculando metricas...")
    resultados = calcular_todas()

    progress_cb(1.0, "Listo")
    return resultados


# ── Mapas Folium ──────────────────────────────────────────────────────────────

def _mapa_entrada(coords: dict) -> folium.Map:
    lats, lons = [], []
    for s in ("A", "B"):
        for rol in ("origen", "destino"):
            lat, lon = _utm_to_latlon(coords[s][rol]["x"], coords[s][rol]["y"])
            lats.append(lat)
            lons.append(lon)

    m = folium.Map(
        location=[sum(lats) / len(lats), sum(lons) / len(lons)],
        zoom_start=11,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri WorldImagery",
    )

    cfg_markers = {
        "A_origen":  ("green",   "play",    "Escenario A — Origen"),
        "A_destino": ("red",     "stop",    "Escenario A — Destino"),
        "B_origen":  ("blue",    "play",    "Escenario B — Origen"),
        "B_destino": ("darkred", "stop",    "Escenario B — Destino"),
    }
    for s in ("A", "B"):
        for rol in ("origen", "destino"):
            lat, lon = _utm_to_latlon(coords[s][rol]["x"], coords[s][rol]["y"])
            key = f"{s}_{rol}"
            color, icon, tooltip = cfg_markers[key]
            popup_html = (
                f"<b style='color:#002B5C'>{tooltip}</b><br>"
                f"X: {coords[s][rol]['x']:.0f} m<br>"
                f"Y: {coords[s][rol]['y']:.0f} m<br>"
                f"<small>({lat:.5f}, {lon:.5f})</small>"
            )
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=220),
                tooltip=tooltip,
                icon=folium.Icon(color=color, icon=icon, prefix="fa"),
            ).add_to(m)

        # Línea origen–destino (a modo indicativo)
        lat_o, lon_o = _utm_to_latlon(coords[s]["origen"]["x"],  coords[s]["origen"]["y"])
        lat_d, lon_d = _utm_to_latlon(coords[s]["destino"]["x"], coords[s]["destino"]["y"])
        folium.PolyLine(
            locations=[[lat_o, lon_o], [lat_d, lon_d]],
            color="#888888",
            weight=1.5,
            dash_array="6 4",
            opacity=0.6,
            tooltip=f"Esc. {s} — línea directa",
        ).add_to(m)

    return m


def _mapa_resultados() -> folium.Map | None:
    rutas = [
        (s, perfil, _RUTAS_DIR / f"ruta_{s}_{perfil}.gpkg")
        for s in ("A", "B")
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

    grupos = {s: folium.FeatureGroup(name=f"Escenario {s}", show=True) for s in ("A", "B")}

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
    <div style="position:fixed;bottom:28px;left:28px;z-index:1000;background:white;
                padding:12px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.18);font-family:'Segoe UI',sans-serif;
                font-size:13px;border-top:3px solid #002B5C;">
      <b style="color:#002B5C;">Perfiles</b><br>
      <span style="color:#1f78b4;font-size:1.3em;">&#9644;</span> Ruta Corta<br>
      <span style="color:#ff7f00;font-size:1.3em;">&#9644;</span> Equilibrio<br>
      <span style="color:#33a02c;font-size:1.3em;">&#9644;</span> Ambiental<br>
      <span style="color:#e31a1c;font-size:1.3em;">&#9644;</span> Min. Pendiente
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

    if "coords" not in st.session_state:
        st.session_state.coords = {
            s: {
                rol: {
                    "x": float(cfg[f"escenario_{s}"][rol]["x"]),
                    "y": float(cfg[f"escenario_{s}"][rol]["y"]),
                }
                for rol in ("origen", "destino")
            }
            for s in ("A", "B")
        }
    if "punto_activo" not in st.session_state:
        st.session_state.punto_activo = "A_origen"
    if "_last_click" not in st.session_state:
        st.session_state._last_click = None

    coords = st.session_state.coords

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
        for s in ("A", "B"):
            st.markdown(
                f'<div class="scenario-card"><h3>Escenario {s}</h3>',
                unsafe_allow_html=True,
            )
            for rol in ("origen", "destino"):
                st.markdown(
                    f'<p class="section-label">{rol.capitalize()}</p>',
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2)
                with c1:
                    coords[s][rol]["x"] = st.number_input(
                        "X (m)", value=coords[s][rol]["x"],
                        step=1.0, format="%.0f", key=f"{s}_{rol}_x",
                    )
                with c2:
                    coords[s][rol]["y"] = st.number_input(
                        "Y (m)", value=coords[s][rol]["y"],
                        step=1.0, format="%.0f", key=f"{s}_{rol}_y",
                    )

            dist = _dist_m(
                coords[s]["origen"]["x"], coords[s]["origen"]["y"],
                coords[s]["destino"]["x"], coords[s]["destino"]["y"],
            )
            if dist > MAX_DIST_M:
                st.error(f"Distancia: {dist / 1000:.1f} km — supera los {MAX_DIST_M / 1000:.0f} km")
            else:
                st.success(f"Distancia: {dist / 1000:.1f} km")

            st.markdown("</div>", unsafe_allow_html=True)

        if _HAS_ST_FOLIUM:
            st.markdown("---")
            st.markdown("**Siguiente clic en el mapa establece:**")
            opciones = {
                "A_origen":  "Escenario A — Origen",
                "A_destino": "Escenario A — Destino",
                "B_origen":  "Escenario B — Origen",
                "B_destino": "Escenario B — Destino",
            }
            st.session_state.punto_activo = st.radio(
                "Punto activo",
                options=list(opciones.keys()),
                format_func=lambda k: opciones[k],
                index=list(opciones.keys()).index(st.session_state.punto_activo),
                label_visibility="collapsed",
                key="radio_punto",
            )
        else:
            st.info("Instala `streamlit-folium` para activar el clic en mapa.")

    with col_map:
        m = _mapa_entrada(coords)
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
                    esc, rol = st.session_state.punto_activo.split("_", 1)
                    x_utm, y_utm = _latlon_to_utm(click["lat"], click["lng"])
                    coords[esc][rol]["x"] = round(x_utm)
                    coords[esc][rol]["y"] = round(y_utm)
                    st.rerun()
        else:
            from streamlit.components.v1 import html as _html
            _html(m._repr_html_(), height=560)

    # ── Botón ─────────────────────────────────────────────────────────────────
    st.markdown("---")
    dist_A = _dist_m(
        coords["A"]["origen"]["x"], coords["A"]["origen"]["y"],
        coords["A"]["destino"]["x"], coords["A"]["destino"]["y"],
    )
    dist_B = _dist_m(
        coords["B"]["origen"]["x"], coords["B"]["origen"]["y"],
        coords["B"]["destino"]["x"], coords["B"]["destino"]["y"],
    )
    can_run = dist_A <= MAX_DIST_M and dist_B <= MAX_DIST_M

    btn_col, _ = st.columns([1, 3])
    with btn_col:
        if st.button("Procesamiento", type="primary", disabled=not can_run,
                     use_container_width=True):
            cfg["escenario_A"]["origen"]["x"]  = int(round(coords["A"]["origen"]["x"]))
            cfg["escenario_A"]["origen"]["y"]  = int(round(coords["A"]["origen"]["y"]))
            cfg["escenario_A"]["destino"]["x"] = int(round(coords["A"]["destino"]["x"]))
            cfg["escenario_A"]["destino"]["y"] = int(round(coords["A"]["destino"]["y"]))
            cfg["escenario_B"]["origen"]["x"]  = int(round(coords["B"]["origen"]["x"]))
            cfg["escenario_B"]["origen"]["y"]  = int(round(coords["B"]["origen"]["y"]))
            cfg["escenario_B"]["destino"]["x"] = int(round(coords["B"]["destino"]["x"]))
            cfg["escenario_B"]["destino"]["y"] = int(round(coords["B"]["destino"]["y"]))
            _guardar_cfg(cfg)

            bar = st.progress(0, text="Iniciando pipeline...")

            try:
                resultados = _ejecutar_pipeline(
                    lambda pct, msg: bar.progress(pct, text=msg)
                )
                st.session_state.resultados = resultados
                st.session_state.pantalla = "resultados"
                st.rerun()
            except Exception as exc:
                st.error(f"Error durante el procesamiento: {exc}")

    if not can_run:
        st.warning("Corrige las distancias antes de lanzar el procesamiento.")


# ── Página de resultados ──────────────────────────────────────────────────────

def _render_results():
    resultados = st.session_state.get("resultados", {})

    if st.button("← Volver a configuracion"):
        st.session_state.pantalla = "input"
        st.rerun()

    tab_mapa, tab_A, tab_B, tab_div = st.tabs([
        "Mapa de rutas",
        "Metricas — Escenario A",
        "Metricas — Escenario B",
        "Diversidad de corredores",
    ])

    # ── Tab mapa ──────────────────────────────────────────────────────────────
    with tab_mapa:
        m = _mapa_resultados()
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
        "km_suelo_urbano":       "km urbano",
        "n_cruces_rios":         "Rios",
        "n_cruces_carreteras":   "Carreteras",
        "n_cruces_ferrocarril":  "FFCC",
    }

    for s, tab in (("A", tab_A), ("B", tab_B)):
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
        for s in ("A", "B"):
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

    _LOGO_SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 185 80" width="120" height="52">'
        '<path d="M 25 19 A 30 30 0 0 1 55 19" fill="none" stroke="#76B82A"'
        ' stroke-width="5.5" stroke-linecap="round"/>'
        '<path d="M 55 19 A 30 30 0 1 1 25 19" fill="none" stroke="#0066B2"'
        ' stroke-width="5.5" stroke-linecap="round"/>'
        '<text x="82" y="53" font-family="Arial,Helvetica,sans-serif"'
        ' font-size="27" font-weight="bold" fill="#0066B2" letter-spacing="-0.5">enagas</text>'
        '</svg>'
    )

    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="enagas-page-header">'
        f'<div>{_LOGO_SVG}</div>'
        f'<div class="header-divider"></div>'
        f'<div>'
        f'<div class="header-title">Generador de Trazados de Ramales H₂</div>'
        f'<div class="header-subtitle">CI2 Lab 2026 &nbsp;&middot;&nbsp; Enágas</div>'
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
