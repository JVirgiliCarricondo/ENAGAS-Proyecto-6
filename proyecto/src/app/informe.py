"""Generación del informe PDF de resultados (Reto 6, Enagás / CI2 Lab 2026).

Construye un informe en PDF con: escenarios seleccionados (origen/destino),
perfiles de prioridad usados (pesos por capa), y por cada escenario una imagen
de los trazados generados junto con su tabla de métricas multicriterio.

Las dependencias pesadas (matplotlib, reportlab) se importan aquí y no en el
arranque de la app; este módulo se carga de forma perezosa desde streamlit_app.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import geopandas as gpd

# Backend sin pantalla — imprescindible dentro de Streamlit/servidor.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_PRIMARY = colors.HexColor("#004e7e")
_PRIMARY_LIGHT = colors.HexColor("#e6eef4")
_GREY = colors.HexColor("#5b6670")

# Nº de decimales por columna (etiqueta ya renombrada). Las columnas no listadas
# (recuentos de cruces) se muestran como enteros. Máximo 3 decimales.
_DECIMALES = {
    "km": 2,
    "Coste rel.": 3,
    "Pend.max %": 1,
    "Pend.med %": 2,
    "km prot.": 3,
    "km inund.": 3,
    "km urbano": 3,
}


def _fmt_valor(etiqueta: str, valor) -> str:
    """Formatea un valor de métrica con como mucho 3 decimales."""
    if valor is None:
        return "—"
    try:
        num = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    dec = _DECIMALES.get(etiqueta)
    if dec is None:
        # Recuentos y demás enteros.
        if num == int(num):
            return str(int(num))
        return f"{num:.3f}"
    return f"{num:.{dec}f}"


def _figura_rutas(
    sid: str,
    rutas_dir: Path,
    perfiles_orden: list[str],
    colores: dict[str, str],
    nombre_perfil: dict[str, str],
) -> bytes | None:
    """Imagen PNG (bytes) con los trazados del escenario coloreados por perfil."""
    paths = [
        (p, rutas_dir / f"ruta_{sid}_{p}.gpkg")
        for p in perfiles_orden
    ]
    paths = [(p, pt) for p, pt in paths if pt.exists()]
    if not paths:
        return None

    fig, ax = plt.subplots(figsize=(6.6, 4.4), dpi=150)
    handles = []
    for perfil, pt in paths:
        try:
            gdf = gpd.read_file(pt)
        except Exception:
            continue
        color = colores.get(perfil, "#004e7e")
        gdf.plot(ax=ax, color=color, linewidth=2.2, alpha=0.9)
        handles.append(
            Line2D([0], [0], color=color, lw=2.6,
                   label=nombre_perfil.get(perfil, perfil))
        )

    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.margins(0.06)
    if handles:
        ax.legend(handles=handles, loc="best", fontsize=8, frameon=True,
                  framealpha=0.9, edgecolor="#c9d2da")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _tabla(datos: list[list[str]], anchos: list[float] | None = None) -> Table:
    """Tabla con cabecera corporativa (fila 0) y filas alternas."""
    t = Table(datos, colWidths=anchos, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), _PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7dee5")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, _PRIMARY),
    ]
    for i in range(1, len(datos)):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), _PRIMARY_LIGHT))
    t.setStyle(TableStyle(estilo))
    return t


def construir_informe_pdf(
    *,
    escenarios: list[str],
    resultados: dict,
    perfiles: list[dict] | None,
    coords: dict,
    rutas_dir: Path,
    perfiles_orden: list[str],
    colores: dict[str, str],
    nombre_perfil: dict[str, str],
    capas_peso: list[tuple[str, str]],
    col_rename: dict[str, str],
    logo_path: Path | None = None,
) -> bytes:
    """Genera el informe PDF completo y devuelve sus bytes.

    Incluye: portada, escenarios seleccionados (origen/destino), perfiles de
    prioridad usados (pesos por capa) y, por escenario, imagen de trazados +
    tabla de métricas (máx. 3 decimales).
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Informe de Trazados de Ramales de H2",
        author="CI2 Lab 2026 — Grupo 6 (Reto 6, Enagás)",
    )

    ss = getSampleStyleSheet()
    h_title = ParagraphStyle(
        "h_title", parent=ss["Title"], fontName="Helvetica-Bold",
        fontSize=20, textColor=_PRIMARY, spaceAfter=2,
    )
    h_sub = ParagraphStyle(
        "h_sub", parent=ss["Normal"], fontSize=9.5, textColor=_GREY, spaceAfter=2,
    )
    h_sec = ParagraphStyle(
        "h_sec", parent=ss["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, textColor=_PRIMARY, spaceBefore=14, spaceAfter=6,
    )
    h_esc = ParagraphStyle(
        "h_esc", parent=ss["Heading2"], fontName="Helvetica-Bold",
        fontSize=12.5, textColor=colors.white, spaceBefore=2, spaceAfter=2,
        leftIndent=6,
    )
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5, textColor=colors.HexColor("#22272b"))

    story: list = []

    # ── Cabecera / portada ────────────────────────────────────────────────────
    if logo_path is not None and Path(logo_path).exists():
        try:
            story.append(RLImage(str(logo_path), width=34 * mm, height=34 * mm,
                                  kind="proportional"))
            story.append(Spacer(1, 4))
        except Exception:
            pass
    story.append(Paragraph("Informe de Trazados de Ramales de H₂", h_title))
    story.append(Paragraph(
        "Comparativa multicriterio de trazados alternativos · "
        "Reto 6 (Enagás) — CI2 Lab 2026, Grupo 6", h_sub))
    story.append(Paragraph(
        "Generado el " + datetime.now().strftime("%d/%m/%Y %H:%M"), h_sub))
    story.append(Spacer(1, 4))

    # ── Escenarios seleccionados ──────────────────────────────────────────────
    story.append(Paragraph("Escenarios seleccionados", h_sec))
    datos_esc = [["Escenario", "Origen (X, Y) · EPSG:25830", "Destino (X, Y) · EPSG:25830"]]
    for s in escenarios:
        pts = coords.get(s, {})
        o = pts.get("origen", {})
        d = pts.get("destino", {})
        o_txt = (f"{o['x']:,.0f}, {o['y']:,.0f}".replace(",", " ")
                 if o else "—")
        d_txt = (f"{d['x']:,.0f}, {d['y']:,.0f}".replace(",", " ")
                 if d else "—")
        datos_esc.append([f"Escenario {s}", o_txt, d_txt])
    story.append(_tabla(datos_esc, anchos=[28 * mm, 66 * mm, 66 * mm]))

    # ── Perfiles de prioridad usados ──────────────────────────────────────────
    if perfiles:
        story.append(Paragraph("Perfiles de prioridad usados (pesos por capa)", h_sec))
        cabecera = ["Perfil"] + [et.split(" (")[0] for _, et in capas_peso]
        datos_perf = [cabecera]
        for p in perfiles:
            fila = [nombre_perfil.get(p.get("id"), p.get("id", "—"))]
            for clave, _et in capas_peso:
                v = p.get("pesos", {}).get(clave, 0.0)
                fila.append(f"{round(float(v) * 100)}%")
            datos_perf.append(fila)
        n_cols = len(cabecera)
        ancho_total = 170 * mm
        anchos = [34 * mm] + [(ancho_total - 34 * mm) / (n_cols - 1)] * (n_cols - 1)
        story.append(_tabla(datos_perf, anchos=anchos))

    # ── Por escenario: imagen de trazados + métricas ──────────────────────────
    for s in escenarios:
        res = resultados.get(s, {})
        rutas = res.get("rutas", [])

        banda = _tabla([[Paragraph(f"Escenario {s}", h_esc)]], anchos=[170 * mm])
        banda.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _PRIMARY),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(Spacer(1, 6))
        story.append(banda)
        story.append(Spacer(1, 8))

        img = _figura_rutas(s, rutas_dir, perfiles_orden, colores, nombre_perfil)
        if img is not None:
            story.append(RLImage(io.BytesIO(img), width=150 * mm, height=100 * mm,
                                 kind="proportional"))
            story.append(Spacer(1, 8))
        else:
            story.append(Paragraph("Sin trazados disponibles para este escenario.", body))

        if not rutas:
            story.append(Paragraph("Sin métricas calculadas para este escenario.", body))
            continue

        filas = [r.to_dict() for r in rutas]
        cols = [c for c in col_rename if any(c in f for f in filas)]
        cabecera = [col_rename[c] for c in cols]
        datos_met = [cabecera]
        for f in filas:
            fila = []
            for c in cols:
                et = col_rename[c]
                val = f.get(c)
                if c == "perfil":
                    fila.append(nombre_perfil.get(val, val))
                else:
                    fila.append(_fmt_valor(et, val))
            datos_met.append(fila)
        story.append(_tabla(datos_met))

    doc.build(story)
    return buf.getvalue()
