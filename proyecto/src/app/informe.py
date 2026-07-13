"""Generación del informe PDF de resultados (Reto 6, Enagás / CI2 Lab 2026).

"Informe de trazados alternativos": explica brevemente cómo se combinan las
capas de coste (con los pesos de cada perfil) en un único ráster de coste
global y cómo el motor LCP traza la ruta sobre ese ráster; después desglosa
el resultado en una sección por escenario, cada una con la imagen del ráster
de coste + ruta (rotada a horizontal) de cada perfil de prioridad y la tabla
de métricas de esas rutas en ese escenario.

Las dependencias pesadas (matplotlib, reportlab, rasterio) se importan aquí
y no en el arranque de la app; este módulo se carga de forma perezosa desde
streamlit_app.
"""

from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

# Backend sin pantalla — imprescindible dentro de Streamlit/servidor.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.transforms import Affine2D  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
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


def _primera_frase(texto: str) -> str:
    """Extrae la primera frase de un texto más largo.

    Se usa para resumir en una línea la ``descripcion`` de un perfil (definida en
    perfiles.yaml) dentro del informe. Corta en el primer punto seguido de espacio
    y garantiza que la frase termine en punto.

    Args:
        texto: Texto de partida (puede ir vacío).

    Returns:
        str: La primera frase con punto final, o cadena vacía si ``texto`` es vacío.
    """
    if not texto:
        return ""
    # Corta en el primer ". " (punto seguido): el resto se descarta.
    primera = texto.strip().split(". ")[0].strip()
    # Reañade el punto final salvo que ya termine en punto o puntos suspensivos.
    if primera and not primera.endswith((".", "…")):
        primera += "."
    return primera


def _fmt_valor(etiqueta: str, valor) -> str:
    """Formatea un valor de métrica para mostrarlo en una tabla del PDF.

    El número de decimales depende de la columna (ver ``_DECIMALES``): las columnas
    no listadas (recuentos de cruces y demás) se muestran como enteros si el valor
    es entero, y con 3 decimales en caso contrario. Los valores ausentes se
    representan con un guión largo.

    Args:
        etiqueta: Etiqueta ya renombrada de la columna (clave de ``_DECIMALES``).
        valor: Valor a formatear; puede ser ``None`` o no numérico.

    Returns:
        str: Representación textual del valor lista para la tabla.
    """
    if valor is None:
        return "—"
    try:
        num = float(valor)
    except (TypeError, ValueError):
        # Valor no numérico: se muestra tal cual.
        return str(valor)
    dec = _DECIMALES.get(etiqueta)
    if dec is None:
        # Recuentos y demás enteros: sin decimales si el valor es entero.
        if num == int(num):
            return str(int(num))
        return f"{num:.3f}"
    return f"{num:.{dec}f}"


def _marcar_origen_destino(ax, origen: dict | None, destino: dict | None, transform=None) -> list:
    """Dibuja los marcadores de origen y destino sobre unos ejes de matplotlib.

    Pinta el origen como un círculo verde y el destino como un cuadrado rojo. El
    argumento ``transform`` se pasa cuando la figura está rotada (ver
    ``_figura_raster_ruta``) para que los marcadores queden en el mismo sistema de
    coordenadas que el ráster y la ruta.

    Args:
        ax: Ejes de matplotlib sobre los que dibujar.
        origen: Dict con claves ``x``/``y`` del origen, o ``None``.
        destino: Dict con claves ``x``/``y`` del destino, o ``None``.
        transform: Transformación de coordenadas (rotación) a aplicar; ``None`` si
            los ejes no están rotados.

    Returns:
        list: Handles de leyenda (Origen/Destino) para que el llamante decida cómo
        combinarlos con el resto de su leyenda (una figura solo puede tener una).
    """
    # Solo se propaga transform a scatter si se ha pasado (ejes rotados).
    kwargs = {"transform": transform} if transform is not None else {}
    handles = []
    if origen:
        ax.scatter([origen["x"]], [origen["y"]], s=75, marker="o",
                   facecolor="#2e7d32", edgecolor="white", linewidth=1.3,
                   zorder=6, **kwargs)
        handles.append(Line2D([0], [0], marker="o", color="none",
                               markerfacecolor="#2e7d32", markeredgecolor="white",
                               markersize=8, label="Origen"))
    if destino:
        ax.scatter([destino["x"]], [destino["y"]], s=75, marker="s",
                   facecolor="#c62828", edgecolor="white", linewidth=1.3,
                   zorder=6, **kwargs)
        handles.append(Line2D([0], [0], marker="s", color="none",
                               markerfacecolor="#c62828", markeredgecolor="white",
                               markersize=8, label="Destino"))
    return handles


def _figura_raster_ruta(
    sid: str,
    perfil: str,
    trazados_dir: Path,
    rutas_dir: Path,
    color: str,
    origen: dict | None,
    destino: dict | None,
) -> bytes | None:
    """Genera la imagen ráster de coste + ruta de un perfil, rotada a horizontal.

    Produce un PNG (en bytes) con el ráster de coste del perfil (verde = paso
    barato, rojo = paso caro) y la ruta del LCP encima. La figura se rota para que
    el corredor origen→destino quede siempre en horizontal, lo que evita huecos en
    blanco cuando el trazado es predominantemente norte-sur.

    Args:
        sid: Id del escenario.
        perfil: Id del perfil de prioridad.
        trazados_dir: Directorio con las superficies de coste (``superficie_*.tif``).
        rutas_dir: Directorio con las rutas LCP (``ruta_*.gpkg``).
        color: Color de la línea de la ruta.
        origen: Dict con ``x``/``y`` del origen, o ``None``.
        destino: Dict con ``x``/``y`` del destino, o ``None``.

    Returns:
        bytes | None: PNG codificado, o ``None`` si no existe el ráster del perfil.
    """
    raster_path = trazados_dir / f"superficie_{sid}_{perfil}.tif"
    if not raster_path.exists():
        return None

    # Lee la banda 1 del ráster (enmascarada) junto con sus bounds y transform.
    with rasterio.open(raster_path) as src:
        arr = src.read(1, masked=True)
        b = src.bounds
        transform = src.transform

    # Ángulo de rotación: el que pone la línea origen→destino en horizontal.
    # Se niega el ángulo porque el eje Y de la imagen crece hacia abajo.
    angle_deg = 0.0
    if origen and destino:
        dx = destino["x"] - origen["x"]
        dy = destino["y"] - origen["y"]
        if dx or dy:
            angle_deg = -math.degrees(math.atan2(dy, dx))

    # Centro del ráster: pivote de la rotación.
    cx, cy = (b.left + b.right) / 2, (b.bottom + b.top) / 2

    # El coste combinado NO está acotado a [0,1] (incluye BASE_LONG · peso
    # longitud, ver combinar.py); se normaliza al rango real de la celda para
    # que la rampa verde→rojo distinga barato/caro dentro de este perfil.
    valid_arr = arr.compressed() if np.ma.is_masked(arr) else arr[np.isfinite(arr)]
    vmin, vmax = (float(valid_arr.min()), float(valid_arr.max())) if valid_arr.size else (0.0, 1.0)
    if vmin == vmax:
        vmax = vmin + 1.0

    # El AOI es un rectángulo orientado a lo largo de la línea origen→destino,
    # recortado dentro de un ráster de almacenamiento con orientación norte
    # (bounds axis-aligned): los datos válidos ya forman una banda diagonal
    # dentro de ese cuadro, con nan en las esquinas. Encuadrar por los bounds
    # (el cuadro completo) deja huecos enormes al rotar; hay que encuadrar por
    # la extensión real de los píxeles con dato, ya rotados.
    theta = math.radians(angle_deg)
    rmat = np.array([[math.cos(theta), -math.sin(theta)],
                      [math.sin(theta), math.cos(theta)]])
    valid_mask = ~np.ma.getmaskarray(arr) if np.ma.is_masked(arr) else np.isfinite(arr)
    rows, cols = np.nonzero(valid_mask)
    if rows.size:
        xs = transform.a * (cols + 0.5) + transform.b * (rows + 0.5) + transform.c
        ys = transform.d * (cols + 0.5) + transform.e * (rows + 0.5) + transform.f
        pts = np.column_stack([xs, ys]) - [cx, cy]
        rotated = pts @ rmat.T + [cx, cy]
        xmin, ymin = rotated.min(axis=0)
        xmax, ymax = rotated.max(axis=0)
    else:
        xmin, xmax, ymin, ymax = b.left, b.right, b.bottom, b.top
    padx, pady = (xmax - xmin) * 0.02, (ymax - ymin) * 0.06
    xmin, xmax = xmin - padx, xmax + padx
    ymin, ymax = ymin - pady, ymax + pady

    # El lienzo se dimensiona con la MISMA proporción que los datos ya
    # rotados y los ejes ocupan el 100% de la figura: así no queda ningún
    # margen en blanco que recortar (evita el recorte "tight" poco fiable
    # cuando se combina con transformaciones de rotación de artistas).
    # Si algún límite de tamaño recorta el ancho, el ALTO se reajusta a la
    # misma proporción: si no, con aspect="equal" los datos no llenan el
    # lienzo y el PNG sale con bandas blancas arriba y abajo (espacios en
    # blanco en el informe).
    ratio = (xmax - xmin) / (ymax - ymin)
    fig_h = 5.2
    fig_w = max(3.5, min(fig_h * ratio, 15.0))
    fig_h = fig_w / ratio
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1])

    # Rampa verde→rojo invertida (verde barato, rojo caro); celdas sin dato
    # (nan/enmascaradas) en blanco para que no ensucien el fondo.
    cmap = plt.get_cmap("RdYlGn_r").copy()
    cmap.set_bad("white")
    # Transformación compuesta: rota los artistas alrededor del centro y luego los
    # sitúa en las coordenadas de datos de los ejes.
    rot = Affine2D().rotate_deg_around(cx, cy, angle_deg) + ax.transData

    # Pinta el ráster y le aplica la rotación (imshow no admite transform directo).
    im = ax.imshow(arr, extent=(b.left, b.right, b.bottom, b.top),
                    origin="upper", cmap=cmap, vmin=vmin, vmax=vmax)
    im.set_transform(rot)

    # Superpone la ruta con la misma rotación: primero un halo blanco grueso y
    # encima la línea del color del perfil, para que resalte sobre el ráster.
    ruta_path = rutas_dir / f"ruta_{sid}_{perfil}.gpkg"
    if ruta_path.exists():
        try:
            gdf = gpd.read_file(ruta_path)
            gdf.plot(ax=ax, color="white", linewidth=3.4, transform=rot, zorder=3)
            gdf.plot(ax=ax, color=color, linewidth=1.7, transform=rot, zorder=4)
        except Exception:
            # Ruta ilegible o corrupta: se omite la línea, no el ráster.
            pass

    # Marcadores origen/destino con la misma rotación + leyenda en la esquina.
    od_handles = _marcar_origen_destino(ax, origen, destino, transform=rot)
    if od_handles:
        ax.legend(handles=od_handles, loc="lower right", fontsize=7.5, frameon=True,
                  framealpha=0.9, edgecolor="#c9d2da", handletextpad=0.4)

    # Encuadre por la extensión real de los píxeles ya rotados (calculada arriba).
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.set_axis_off()

    # Vuelca la figura a PNG en memoria (no a disco) y libera la figura.
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _figura_todas_rutas(
    sid: str,
    rutas_dir: Path,
    perfiles_orden: list[str],
    colores: dict[str, str],
    nombre_perfil: dict[str, str],
    origen: dict | None = None,
    destino: dict | None = None,
) -> bytes | None:
    """Genera la imagen comparativa con todos los trazados de un escenario.

    Superpone los trazados de un escenario (uno por perfil, cada uno con su color)
    más los marcadores de origen y destino, con leyenda y sin ráster de fondo. Es
    la figura de la sección "Comparativa de perfiles superpuestos".

    Args:
        sid: Id del escenario.
        rutas_dir: Directorio con las rutas LCP (``ruta_*.gpkg``).
        perfiles_orden: Ids de perfil en el orden en que se dibujan.
        colores: Color por id de perfil.
        nombre_perfil: Nombre legible por id de perfil (para la leyenda).
        origen: Dict con ``x``/``y`` del origen, o ``None``.
        destino: Dict con ``x``/``y`` del destino, o ``None``.

    Returns:
        bytes | None: PNG codificado, o ``None`` si no hay ninguna ruta disponible.
    """
    # Empareja cada perfil con su fichero de ruta y descarta los que no existen.
    paths = [(p, rutas_dir / f"ruta_{sid}_{p}.gpkg") for p in perfiles_orden]
    paths = [(p, pt) for p, pt in paths if pt.exists()]
    if not paths:
        return None

    fig, ax = plt.subplots(figsize=(4.4, 4.4), dpi=150)
    handles = []
    # Dibuja cada ruta con su color y acumula un handle de leyenda por perfil.
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

    # Añade origen/destino a la leyenda (aquí los ejes no van rotados).
    handles += _marcar_origen_destino(ax, origen, destino)

    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.margins(0.08)
    if handles:
        # Leyenda FUERA del área de trazado (a la derecha): dentro tapaba
        # los propios trazados, sobre todo en corredores estrechos.
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1.0),
                  fontsize=8, frameon=True, framealpha=0.9,
                  edgecolor="#c9d2da", borderaxespad=0)

    # bbox_inches="tight" recorta el margen sobrante alrededor de los trazados
    # y de la leyenda externa antes de exportar el PNG en memoria.
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _tabla(datos: list[list[str]], anchos: list[float] | None = None) -> Table:
    """Construye una tabla reportlab con el estilo corporativo del informe.

    La fila 0 es la cabecera (fondo azul, texto blanco en negrita) y se repite en
    cada página (``repeatRows=1``); las filas de datos pares llevan fondo claro
    (efecto cebra) para facilitar la lectura.

    Args:
        datos: Filas de la tabla; la primera es la cabecera.
        anchos: Anchos de columna en puntos, o ``None`` para reparto automático.

    Returns:
        Table: Flowable de reportlab listo para añadir al ``story``.
    """
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
    # Efecto cebra: sombrea las filas de datos con índice par.
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
    trazados_dir: Path,
    perfiles_orden: list[str],
    colores: dict[str, str],
    nombre_perfil: dict[str, str],
    capas_peso: list[tuple[str, str]],
    col_rename: dict[str, str],
    logo_path: Path | None = None,
) -> bytes:
    """Genera el informe PDF completo y devuelve sus bytes.

    Compone el documento (mediante reportlab/platypus) acumulando "flowables" en
    una lista ``story`` que finalmente se maqueta en A4. El informe incluye, en
    orden: portada con logo, explicación breve de cómo se genera el ráster de
    coste global (capas de coste + pesos del perfil) y las rutas sobre él, la
    tabla de escenarios seleccionados (origen/destino), la tabla de pesos por
    perfil de prioridad, la comparativa de perfiles superpuestos y, por cada
    escenario (en página nueva), la imagen del ráster de coste con la ruta encima
    (horizontal) de cada perfil y la tabla de métricas de esas rutas.

    Args:
        escenarios: Ids de los escenarios a incluir.
        resultados: Resultados por escenario; cada uno con la lista de ``rutas``
            (objetos con atributo ``perfil`` y método ``to_dict``).
        perfiles: Perfiles de prioridad (dicts con ``id``, ``pesos``,
            ``descripcion``), o ``None`` si no hay.
        coords: Coordenadas de origen/destino por escenario.
        rutas_dir: Directorio con las rutas LCP (``ruta_*.gpkg``).
        trazados_dir: Directorio con las superficies de coste (``superficie_*.tif``).
        perfiles_orden: Orden en que se muestran los perfiles.
        colores: Color por id de perfil.
        nombre_perfil: Nombre legible por id de perfil.
        capas_peso: Pares (clave, etiqueta) de las capas de coste, para la tabla
            de pesos.
        col_rename: Renombrado de columnas de métricas (clave interna → etiqueta).
        logo_path: Ruta al logo de portada, o ``None``.

    Returns:
        bytes: El PDF completo codificado.
    """
    # Documento base A4 con márgenes y metadatos (título/autor del PDF).
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Informe de trazados alternativos",
        author="CI2 Lab 2026 — Grupo 6 (Reto 6, Enagás)",
    )

    # Estilos de párrafo del informe (títulos, subtítulos, cabeceras de sección,
    # bandas de perfil, cuerpo de texto y cabeceras de tabla). Todos derivan de la
    # hoja de estilos por defecto y aplican la paleta corporativa.
    ss = getSampleStyleSheet()
    h_title = ParagraphStyle(
        "h_title", parent=ss["Title"], fontName="Helvetica-Bold",
        fontSize=19, textColor=_PRIMARY, spaceAfter=2, alignment=TA_LEFT,
    )
    h_sub = ParagraphStyle(
        "h_sub", parent=ss["Normal"], fontSize=9.5, textColor=_GREY, spaceAfter=2,
    )
    h_sec = ParagraphStyle(
        "h_sec", parent=ss["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, textColor=_PRIMARY, spaceBefore=14, spaceAfter=6,
    )
    h_perfil = ParagraphStyle(
        "h_perfil", parent=ss["Heading2"], fontName="Helvetica-Bold",
        fontSize=12.5, textColor=colors.white, spaceBefore=2, spaceAfter=2,
        leftIndent=6,
    )
    # Título de escenario: texto grande en azul corporativo con filete debajo,
    # SIN banda de fondo — para que no se confunda con las bandas de los
    # perfiles (que sí llevan color de fondo).
    h_escenario = ParagraphStyle(
        "h_escenario", parent=ss["Heading1"], fontName="Helvetica-Bold",
        fontSize=17, textColor=_PRIMARY, spaceBefore=0, spaceAfter=3,
    )
    h_esc = ParagraphStyle(
        "h_esc", parent=ss["Heading3"], fontName="Helvetica-Bold",
        fontSize=10, textColor=_PRIMARY, spaceBefore=8, spaceAfter=4,
    )
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5,
                           textColor=colors.HexColor("#22272b"), leading=13.5,
                           alignment=TA_JUSTIFY)
    desc_perfil_style = ParagraphStyle(
        "desc_perfil", parent=body, fontName="Helvetica-Oblique",
        textColor=_GREY, spaceBefore=6, spaceAfter=2,
    )
    th_style = ParagraphStyle(
        "th", fontName="Helvetica-Bold", fontSize=7.3, leading=8.6,
        textColor=colors.white, alignment=TA_CENTER,
    )

    # story: secuencia de flowables (párrafos, tablas, imágenes, saltos de página)
    # que reportlab maqueta en orden. Se va rellenando sección a sección.
    story: list = []

    # ── Cabecera / portada: logo pequeño arriba a la izquierda, título y
    # subtítulo a su derecha ────────────────────────────────────────────────
    logo_cell = ""
    if logo_path is not None and Path(logo_path).exists():
        try:
            logo_cell = RLImage(str(logo_path), width=20 * mm, height=20 * mm,
                                 kind="proportional")
        except Exception:
            logo_cell = ""
    info_cell = [
        Paragraph("Informe de trazados alternativos", h_title),
        Paragraph(
            "Comparativa multicriterio de trazados alternativos · "
            "Reto 6 (Enagás) — CI2 Lab 2026, Grupo 6", h_sub),
        Paragraph(
            "Generado el " + datetime.now().strftime("%d/%m/%Y %H:%M"), h_sub),
    ]
    cabecera_tbl = Table([[logo_cell, info_cell]], colWidths=[24 * mm, 146 * mm])
    cabecera_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(cabecera_tbl)
    story.append(Spacer(1, 10))

    # ── Metodología (primera parte) ───────────────────────────────────────────
    story.append(Paragraph("Cómo se generan los trazados", h_sec))
    story.append(Paragraph(
        "Cada condicionante del territorio (relieve, usos del suelo, zonas "
        "protegidas, zonas inundables, cruces con vías y ríos, geotecnia) se "
        "traduce en una <b>capa de coste</b> independiente: un valor entre 0 "
        "(paso barato) y 1 (paso caro) en cada celda del terreno. Estas capas "
        "se combinan celda a celda mediante una <b>suma ponderada</b>, usando "
        "los pesos que define cada <b>perfil de prioridad</b> (más corto, "
        "equilibrio, menor impacto ambiental, por relieve), en un único "
        "<b>ráster de coste global</b> para ese perfil.", body))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Sobre ese ráster, el motor de <b>camino de mínimo coste</b> "
        "(Dijkstra de 8 vecinos) calcula, celda a celda, el trayecto entre el "
        "origen y el destino que acumula el menor coste total. Como cada "
        "perfil pondera de forma distinta las mismas capas, cada uno da lugar "
        "a un ráster de coste — y por tanto a una ruta — diferenciados. Las "
        "páginas siguientes muestran, para cada escenario, ese ráster con la "
        "ruta resultante encima y sus métricas, para cada uno de los perfiles "
        "de prioridad.", body))

    # ── Escenarios seleccionados ──────────────────────────────────────────────
    story.append(Paragraph("Escenarios seleccionados", h_sec))
    datos_esc = [["Escenario", "Origen (X, Y) · EPSG:25830", "Destino (X, Y) · EPSG:25830"]]
    for s in escenarios:
        pts = coords.get(s, {})
        o = pts.get("origen", {})
        d = pts.get("destino", {})
        # Sin separador de miles dentro de cada cifra (735453 y no 735 453):
        # la coma que separaba X de Y se perdía al usar ',' como separador de
        # miles y luego sustituir TODAS las comas por espacios.
        o_txt = f"{o['x']:.0f}, {o['y']:.0f}" if o else "—"
        d_txt = f"{d['x']:.0f}, {d['y']:.0f}" if d else "—"
        datos_esc.append([f"Escenario {s}", o_txt, d_txt])
    story.append(_tabla(datos_esc, anchos=[28 * mm, 66 * mm, 66 * mm]))

    # ── Perfiles de prioridad usados ──────────────────────────────────────────
    if perfiles:
        story.append(Paragraph("Perfiles de prioridad usados (pesos por capa)", h_sec))
        # Cabecera como Paragraph (no texto plano): las etiquetas largas como
        # "Zonas protegidas" o "Zonas inundables" pasan a una segunda línea en
        # vez de desbordar sobre la columna vecina. "Expropiacion" se abrevia:
        # es una única palabra sin espacio donde partir, y al no caber en el
        # ancho de columna reportlab la corta en mitad de la palabra.
        _abrev_cabecera = {"Expropiacion": "Expropiac."}
        cabecera = [Paragraph("Perfil", th_style)] + [
            Paragraph(_abrev_cabecera.get(et.split(" (")[0], et.split(" (")[0]), th_style)
            for _, et in capas_peso
        ]
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

    # ── Comparativa: los 4 perfiles superpuestos, uno al lado del otro por
    # escenario ────────────────────────────────────────────────────────────
    imgs_cmp = [
        (s, _figura_todas_rutas(
            s, rutas_dir, perfiles_orden, colores, nombre_perfil,
            origen=coords.get(s, {}).get("origen"), destino=coords.get(s, {}).get("destino"),
        ))
        for s in escenarios
    ]
    if any(img is not None for _, img in imgs_cmp):
        ancho_celda = 170 * mm / len(imgs_cmp)
        # Tamaño moderado a propósito: esta comparativa va al pie de la
        # primera página, debajo de las tres tablas previas, así que solo
        # queda un margen de página acotado (no una página en blanco).
        ancho_img = min(ancho_celda - 6 * mm, 62 * mm)
        fila_cmp = []
        for s, img in imgs_cmp:
            celda = [Paragraph(f"Escenario {s}", h_esc)]
            if img is not None:
                celda.append(RLImage(io.BytesIO(img), width=ancho_img, height=ancho_img,
                                      kind="proportional"))
            else:
                celda.append(Paragraph("Sin rutas disponibles.", body))
            fila_cmp.append(celda)
        tabla_cmp = Table([fila_cmp], colWidths=[ancho_celda] * len(fila_cmp))
        tabla_cmp.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        story.append(KeepTogether([
            Paragraph("Comparativa de perfiles superpuestos", h_sec),
            tabla_cmp,
        ]))

    # ── Una sección por escenario: ráster+ruta (horizontal) de cada perfil +
    # métricas de sus rutas ───────────────────────────────────────────────────
    # Perfiles a incluir: los de perfiles_orden que además estén disponibles
    # (definidos en `perfiles`; si no hay `perfiles`, se asumen todos).
    ids_disponibles = [p.get("id") for p in perfiles] if perfiles else list(perfiles_orden)
    perfiles_a_incluir = [pid for pid in perfiles_orden if pid in ids_disponibles]

    # Columnas de métricas (todas las de col_rename salvo el propio "perfil").
    cols_metricas = [c for c in col_rename if c != "perfil"]
    desc_por_perfil = {
        p.get("id"): _primera_frase(p.get("descripcion", "")) for p in (perfiles or [])
    }
    comentario_metricas = (
        "La tabla siguiente recoge, para cada perfil de prioridad, la longitud "
        "y el coste relativo del trazado, sus pendientes máxima y media, el "
        "número de cruces con ríos, carreteras y ferrocarril, y los kilómetros "
        "del recorrido en zona protegida, inundable o urbana."
    )

    # Alto máximo de cada imagen de perfil. El contenido fluye de corrido: cada
    # bloque de perfil (banda + descripción + imagen) es una unidad KeepTogether
    # y reportlab mete en cada página tantas como quepan — sin saltos de página
    # forzados entre perfiles ni antes de la tabla, que dejaban medias caras y
    # páginas casi vacías. Solo cada ESCENARIO arranca en página nueva.
    alto_img_mm = 78

    for s in escenarios:
        pts = coords.get(s, {})
        origen_s, destino_s = pts.get("origen"), pts.get("destino")

        # Cada escenario arranca SIEMPRE en página nueva: en una misma cara
        # nunca se mezclan datos de escenarios distintos.
        story.append(PageBreak())
        story.append(Paragraph(f"Escenario {s}", h_escenario))
        story.append(HRFlowable(width="100%", thickness=1.1, color=_PRIMARY,
                                spaceBefore=0, spaceAfter=8))

        if not perfiles_a_incluir:
            story.append(Paragraph("Sin perfiles de prioridad configurados.", body))

        filas_perfil = []
        for pid in perfiles_a_incluir:
            banda_perfil = _tabla(
                [[Paragraph(nombre_perfil.get(pid, pid), h_perfil)]],
                anchos=[170 * mm])
            banda_perfil.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1),
                 colors.HexColor(colores.get(pid, "#004e7e"))),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ]))
            bloque: list = [banda_perfil]
            descripcion = desc_por_perfil.get(pid, "")
            if descripcion:
                bloque.append(Paragraph(descripcion, desc_perfil_style))

            img = _figura_raster_ruta(
                s, pid, trazados_dir, rutas_dir, colores.get(pid, "#004e7e"),
                origen_s, destino_s,
            )
            if img is not None:
                bloque.append(RLImage(io.BytesIO(img), width=165 * mm,
                                       height=alto_img_mm * mm, kind="proportional"))
            else:
                bloque.append(Paragraph(
                    "Sin ráster de coste / trazado disponible para este perfil.", body))
            bloque.append(Spacer(1, 8))
            # KeepTogether por perfil: si no cabe entero en lo que queda de
            # página, pasa completo a la siguiente (nunca se parte una banda
            # de su imagen).
            story.append(KeepTogether(bloque))

            # Localiza la ruta de este perfil en los resultados del escenario y
            # acumula sus métricas (aplanadas con to_dict) para la tabla final.
            ruta = next(
                (r for r in resultados.get(s, {}).get("rutas", []) if r.perfil == pid),
                None,
            )
            if ruta is not None:
                filas_perfil.append({"perfil": pid, **ruta.to_dict()})

        if filas_perfil:
            # Solo se muestran las columnas de métricas presentes en al menos una
            # fila: evita columnas totalmente vacías cuando una métrica no aplica.
            cols_usadas = [c for c in cols_metricas if any(c in f for f in filas_perfil)]
            # Cabecera (etiquetas renombradas) + una fila por perfil con sus
            # valores formateados.
            datos_met = [["Perfil"] + [col_rename[c] for c in cols_usadas]]
            for f in filas_perfil:
                nombre_fila = nombre_perfil.get(f["perfil"], f["perfil"])
                datos_met.append(
                    [nombre_fila] + [_fmt_valor(col_rename[c], f.get(c)) for c in cols_usadas]
                )
            # La tabla fluye tras el último perfil (sin página propia).
            story.append(KeepTogether([
                Paragraph(f"Comparativa de perfiles — Escenario {s}", h_sec),
                Paragraph(comentario_metricas, body),
                Spacer(1, 4),
                _tabla(datos_met),
            ]))
        else:
            story.append(Paragraph("Sin métricas calculadas para este escenario.", body))

    # Maqueta todos los flowables acumulados en el PDF y devuelve sus bytes.
    doc.build(story)
    return buf.getvalue()
