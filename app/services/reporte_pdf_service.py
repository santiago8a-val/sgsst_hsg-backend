import os

from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.textlabels import Label
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)

from app.config import Config

# =========================================================
# PALETA VISUAL DEL INFORME
# =========================================================

AZUL_NOCHE = colors.HexColor("#102A43")
AZUL_PRINCIPAL = colors.HexColor("#1F4E78")
AZUL_MEDIO = colors.HexColor("#3E7CB1")
AZUL_CLARO = colors.HexColor("#EAF2F8")

GRIS_FONDO = colors.HexColor("#F7F9FC")
GRIS_BORDE = colors.HexColor("#D5DEE8")
GRIS_TEXTO = colors.HexColor("#52606D")

VERDE = colors.HexColor("#2EAD67")
NARANJA = colors.HexColor("#F59E42")
ROJO = colors.HexColor("#D9534F")


def _texto(valor):
    """Convierte valores vacíos en texto legible."""
    if valor is None or str(valor).strip() == "":
        return "Sin observación"
    return str(valor)


def _fecha_legible(fecha):
    """Convierte la fecha de BD a DD/MM/AAAA."""
    if not fecha:
        return "Sin fecha"

    try:
        return fecha.strftime("%d/%m/%Y")
    except AttributeError:
        return str(fecha)


def _estado_legible(estado):
    estados = {
        "CUMPLE": "Cumple",
        "PARCIAL": "Cumplimiento parcial",
        "NO_CUMPLE": "No cumple",
    }

    return estados.get(estado, estado)

def _color_estado(estado):
    """
    Devuelve el color correspondiente al estado de cumplimiento.
    """

    if estado == "CUMPLE":
        return VERDE

    if estado == "PARCIAL":
        return NARANJA

    if estado == "NO_CUMPLE":
        return ROJO

    return AZUL_PRINCIPAL


def _generar_conclusiones(consolidado):
    """Genera conclusiones exclusivamente a partir de los datos del reporte."""

    t = consolidado["totales"]
    conclusiones = []

    total = t["total_registros"]

    if total == 0:
        return [
            "No se registraron actividades SG-SST durante el periodo seleccionado."
        ]

    conclusiones.append(
        f"Durante el periodo se evaluaron {total} actividades SG-SST. "
        f"El cumplimiento general alcanzado fue del "
        f"{t['porcentaje_avance']}%."
    )

    conclusiones.append(
        f"De las {total} actividades evaluadas, "
        f"{t['cumplidos']} alcanzaron cumplimiento total, "
        f"{t['parciales']} presentaron cumplimiento parcial y "
        f"{t['no_cumplidos']} fueron clasificadas como no cumplidas."
    )

    if t["parciales"] > 0:
        conclusiones.append(
            f"Se identificaron {t['parciales']} actividades con "
            f"cumplimiento parcial. Estas actividades requieren seguimiento "
            f"para verificar su cierre y cumplimiento completo."
        )

    if t["no_cumplidos"] > 0:
        conclusiones.append(
            f"Se identificaron {t['no_cumplidos']} actividades en estado "
            f"No Cumple, las cuales requieren atención y seguimiento."
        )

    fases = consolidado.get("por_fase", [])

    if fases:
        fase_menor = min(
            fases,
            key=lambda x: x["porcentaje_avance"]
        )

        conclusiones.append(
            f"La fase PHVA con menor nivel de cumplimiento fue "
            f"{fase_menor['nombre_fase']}, con un avance del "
            f"{fase_menor['porcentaje_avance']}%."
        )

    sedes = consolidado.get("por_sede", [])

    if len(sedes) > 1:
        mejor_sede = max(
            sedes,
            key=lambda x: x["porcentaje_avance"]
        )

        menor_sede = min(
            sedes,
            key=lambda x: x["porcentaje_avance"]
        )

        conclusiones.append(
            f"La sede con mayor cumplimiento durante el periodo fue "
            f"{mejor_sede['nombre_sede']}, con "
            f"{mejor_sede['porcentaje_avance']}%."
        )

        conclusiones.append(
            f"La sede con menor cumplimiento fue "
            f"{menor_sede['nombre_sede']}, con "
            f"{menor_sede['porcentaje_avance']}%, por lo que representa "
            f"un punto prioritario de seguimiento."
        )

    return conclusiones

def _crear_grafica_sedes(sedes):
    """
    Genera una gráfica de barras usando EXCLUSIVAMENTE
    las sedes y porcentajes obtenidos de la base de datos.
    """

    if not sedes:
        return None

    # Tamaño de la gráfica
    ancho = 720
    alto = 280

    dibujo = Drawing(ancho, alto)

    grafica = VerticalBarChart()

    grafica.x = 65
    grafica.y = 65
    grafica.height = 165
    grafica.width = 610

    # =====================================================
    # DATOS REALES DE LA BASE DE DATOS
    # =====================================================

    valores = [
        float(sede["porcentaje_avance"] or 0)
        for sede in sedes
    ]

    nombres_sedes = [
        str(sede["nombre_sede"])
        for sede in sedes
    ]

    grafica.data = [valores]

    grafica.categoryAxis.categoryNames = nombres_sedes

    # =====================================================
    # EJE Y - PORCENTAJE
    # =====================================================

    grafica.valueAxis.valueMin = 0
    grafica.valueAxis.valueMax = 100
    grafica.valueAxis.valueStep = 20

    grafica.valueAxis.labels.fontSize = 8

    # Líneas horizontales suaves
    grafica.valueAxis.visibleGrid = True
    grafica.valueAxis.gridStrokeColor = colors.HexColor("#D9E2EC")
    grafica.valueAxis.gridStrokeWidth = 0.5

    # =====================================================
    # NOMBRES DE LAS SEDES
    # =====================================================

    grafica.categoryAxis.labels.fontSize = 8

    # Dejamos los nombres horizontales para facilitar lectura
    grafica.categoryAxis.labels.angle = 0

    grafica.categoryAxis.labels.dy = -12

    # =====================================================
    # BARRAS
    # =====================================================

    # Barras más delgadas
    grafica.barWidth = 20

    # Mayor espacio entre barras
    grafica.groupSpacing = 25

    # =====================================================
    # PORCENTAJE ENCIMA DE CADA BARRA
    # =====================================================

    grafica.barLabelFormat = "%.1f%%"
    grafica.barLabels.nudge = 8
    grafica.barLabels.fontSize = 8
    grafica.barLabels.fontName = "Helvetica-Bold"

    # =====================================================
    # COLORES
    # =====================================================

    colores_sedes = [
        colors.HexColor("#2EAD67"),  # verde
        colors.HexColor("#3B82F6"),  # azul
        colors.HexColor("#F59E42"),  # naranja
        colors.HexColor("#7C4DCC"),  # morado
        colors.HexColor("#EAB308"),  # amarillo
        colors.HexColor("#EF5B5B"),  # rojo suave
        colors.HexColor("#06B6D4"),  # turquesa
        colors.HexColor("#8B5CF6"),  # violeta
    ]

    # ReportLab representa todas las barras como una serie.
    # Intentamos asignar un color individual a cada barra.
    for indice, sede in enumerate(sedes):
        color = colores_sedes[indice % len(colores_sedes)]

        try:
            grafica.bars[(0, indice)].fillColor = color
            grafica.bars[(0, indice)].strokeColor = color
        except Exception:
            pass

    # Color predeterminado por si la versión de ReportLab
    # no admite configuración individual.
    grafica.bars[0].fillColor = colors.HexColor("#3B82F6")
    grafica.bars[0].strokeColor = colors.HexColor("#3B82F6")

    dibujo.add(grafica)

    # =====================================================
    # ETIQUETA EJE Y
    # =====================================================

    etiqueta_y = Label()
    etiqueta_y.setOrigin(18, 145)
    etiqueta_y.angle = 90
    etiqueta_y.setText("Cumplimiento (%)")
    etiqueta_y.fontSize = 8
    etiqueta_y.fillColor = colors.HexColor("#334155")

    dibujo.add(etiqueta_y)

    # =====================================================
    # TÍTULO
    # =====================================================

    titulo = Label()
    titulo.setOrigin(ancho / 2, 258)
    titulo.setText("Cumplimiento por sede")
    titulo.fontSize = 13
    titulo.fontName = "Helvetica-Bold"
    titulo.textAnchor = "middle"
    titulo.fillColor = AZUL_PRINCIPAL

    dibujo.add(titulo)

    return dibujo

def _decorar_pagina(canvas, doc):
    """
    Agrega identidad visual a todas las páginas del informe.
    """

    canvas.saveState()

    ancho, alto = landscape(letter)

    # Línea superior
    canvas.setFillColor(AZUL_NOCHE)
    canvas.rect(
        0,
        alto - 13,
        ancho,
        13,
        fill=1,
        stroke=0
    )

    # Borde izquierdo
    canvas.setFillColor(AZUL_PRINCIPAL)
    canvas.rect(
        0,
        0,
        7,
        alto,
        fill=1,
        stroke=0
    )

    # Borde inferior
    canvas.setFillColor(AZUL_NOCHE)
    canvas.rect(
        0,
        0,
        ancho,
        8,
        fill=1,
        stroke=0
    )

    # Pie de página
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GRIS_TEXTO)

    canvas.drawString(
        1.4 * cm,
        0.45 * cm,
        "Informe de Gestión SG-SST"
    )

    canvas.drawRightString(
        ancho - 1.4 * cm,
        0.45 * cm,
        f"Página {doc.page}"
    )

    canvas.restoreState()

def generar_reporte_pdf(
    consolidado: dict,
    generado_por: str,
    nombre_archivo: str
) -> str:

    os.makedirs(
        Config.REPORTS_FOLDER,
        exist_ok=True
    )

    ruta = os.path.join(
        Config.REPORTS_FOLDER,
        nombre_archivo
    )

    # Usamos página horizontal porque ahora tenemos
    # información mucho más completa.
    doc = SimpleDocTemplate(
        ruta,
        pagesize=landscape(letter),
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    estilos = getSampleStyleSheet()

    titulo = ParagraphStyle(
        "TituloReporte",
        parent=estilos["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        spaceAfter=7,
        textColor=AZUL_NOCHE,
    )

    subtitulo = ParagraphStyle(
        "SubtituloReporte",
        parent=estilos["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        leading=13,
        textColor=GRIS_TEXTO,
        spaceAfter=4,
    )

    seccion = ParagraphStyle(
        "Seccion",
        parent=estilos["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        spaceBefore=14,
        spaceAfter=9,
        textColor=AZUL_PRINCIPAL,
    )

    texto_normal = ParagraphStyle(
        "TextoNormal",
        parent=estilos["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#243B53"),
        spaceAfter=5,
    )

    texto_pequeno = ParagraphStyle(
        "TextoPequeno",
        parent=estilos["Normal"],
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#334E68"),
    )

    elementos = []

    # =========================================================
    # ENCABEZADO
    # =========================================================

    elementos.append(
        Paragraph(
            "INFORME DE GESTIÓN SG-SST",
            titulo
        )
    )

    elementos.append(
        Paragraph(
            "Sistema de Gestión de Seguridad y Salud en el Trabajo",
            subtitulo
        )
    )

    elementos.append(Spacer(1, 12))

    datos_encabezado = [
        [
            Paragraph(
                f"<b>Tipo de corte</b><br/>{consolidado['tipo_corte']}",
                texto_normal
            ),
            Paragraph(
                f"<b>Periodo evaluado</b><br/>{consolidado['periodo']}",
                texto_normal
            ),
            Paragraph(
                f"<b>Generado por</b><br/>{generado_por}",
                texto_normal
            ),
        ]
    ]

    tabla_encabezado = Table(
        datos_encabezado,
        colWidths=[8 * cm, 8 * cm, 8 * cm]
    )

    tabla_encabezado.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                AZUL_CLARO
            ),
            (
                "BOX",
                (0, 0),
                (-1, -1),
                0.5,
                colors.HexColor("#CBD5E1")
            ),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )

    elementos.append(tabla_encabezado)
    elementos.append(Spacer(1, 16))

    # =========================================================
    # 1. RESUMEN EJECUTIVO
    # =========================================================

    elementos.append(
        Paragraph(
            "1. RESUMEN EJECUTIVO",
            seccion
        )
    )

    t = consolidado["totales"]

    elementos.append(
        Paragraph(
            f"Durante el periodo <b>{consolidado['periodo']}</b> "
            f"se evaluaron <b>{t['total_registros']} actividades</b> "
            f"del Sistema de Gestión de Seguridad y Salud en el Trabajo. "
            f"De estas, <b>{t['cumplidos']}</b> alcanzaron cumplimiento "
            f"total, <b>{t['parciales']}</b> presentaron cumplimiento "
            f"parcial y <b>{t['no_cumplidos']}</b> fueron clasificadas "
            f"como no cumplidas. El nivel general de cumplimiento del "
            f"periodo fue del <b>{t['porcentaje_avance']}%</b>.",
            texto_normal
        )
    )

    elementos.append(Spacer(1, 8))

    indicadores = [
        [
            "ACTIVIDADES\nEVALUADAS",
            "CUMPLIDAS",
            "PARCIALES",
            "NO CUMPLIDAS",
            "CUMPLIMIENTO\nGENERAL",
        ],
        [
            str(t["total_registros"]),
            str(t["cumplidos"]),
            str(t["parciales"]),
            str(t["no_cumplidos"]),
            f"{t['porcentaje_avance']}%",
        ],
    ]

    tabla_indicadores = Table(
        indicadores,
        colWidths=[
            4.8 * cm,
            4.8 * cm,
            4.8 * cm,
            4.8 * cm,
            4.8 * cm,
        ]
    )

    tabla_indicadores.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                AZUL_PRINCIPAL
            ),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("FONTSIZE", (0, 1), (-1, 1), 15),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.HexColor("#CBD5E1")
            ),
        ])
    )

    elementos.append(tabla_indicadores)
    elementos.append(Spacer(1, 14))

    # =========================================================
    # 2. DESEMPEÑO POR SEDE
    # =========================================================

    elementos.append(
        Paragraph(
            "2. DESEMPEÑO POR SEDE",
            seccion
        )
    )

    sedes = consolidado.get("por_sede", [])

    if sedes:
        datos_sedes = [[
            "Sede",
            "Evaluadas",
            "Cumple",
            "Parcial",
            "No cumple",
            "% Cumplimiento",
        ]]

        for sede in sedes:
            datos_sedes.append([
                sede["nombre_sede"],
                sede["total"],
                sede["cumplidos"],
                sede["parciales"],
                sede["no_cumplidos"],
                f"{sede['porcentaje_avance']}%",
            ])

        tabla_sedes = Table(
            datos_sedes,
            colWidths=[
                7 * cm,
                3 * cm,
                3 * cm,
                3 * cm,
                3 * cm,
                4 * cm,
            ],
            repeatRows=1
        )

        tabla_sedes.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    AZUL_PRINCIPAL
                ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.HexColor("#CBD5E1")
                ),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )

        elementos.append(tabla_sedes)
                # Gráfica comparativa de cumplimiento por sede
        grafica_sedes = _crear_grafica_sedes(sedes)

        if grafica_sedes:
            elementos.append(Spacer(1, 14))

            elementos.append(
                Paragraph(
                    "Comparación visual del cumplimiento por sede",
                    estilos["Heading3"]
                )
            )

            elementos.append(Spacer(1, 6))
            elementos.append(grafica_sedes)

        if len(sedes) > 1:
            mejor = max(
                sedes,
                key=lambda x: x["porcentaje_avance"]
            )

            menor = min(
                sedes,
                key=lambda x: x["porcentaje_avance"]
            )

            elementos.append(Spacer(1, 8))

            elementos.append(
                Paragraph(
                    f"<b>Lectura del resultado:</b> "
                    f"{mejor['nombre_sede']} presentó el mayor nivel "
                    f"de cumplimiento ({mejor['porcentaje_avance']}%). "
                    f"{menor['nombre_sede']} registró el menor resultado "
                    f"del periodo ({menor['porcentaje_avance']}%).",
                    texto_normal
                )
            )

    else:
        elementos.append(
            Paragraph(
                "No existen registros por sede para el periodo seleccionado.",
                texto_normal
            )
        )

    elementos.append(Spacer(1, 12))

    # =========================================================
    # 3. ANÁLISIS POR FASE PHVA
    # =========================================================

    elementos.append(
        Paragraph(
            "3. ANÁLISIS POR FASE PHVA",
            seccion
        )
    )

    datos_fase = [[
        "Fase",
        "Actividades",
        "Cumple",
        "Parcial",
        "No cumple",
        "% Avance",
    ]]

    for fase in consolidado["por_fase"]:
        datos_fase.append([
            fase["nombre_fase"],
            fase["total"],
            fase["cumplidos"],
            fase["parciales"],
            fase["no_cumplidos"],
            f"{fase['porcentaje_avance']}%",
        ])

    tabla_fase = Table(
        datos_fase,
        colWidths=[
            6 * cm,
            3.5 * cm,
            3.5 * cm,
            3.5 * cm,
            3.5 * cm,
            4 * cm,
        ],
        repeatRows=1
    )

    tabla_fase.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                AZUL_PRINCIPAL
            ),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.HexColor("#CBD5E1")
            ),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )

    elementos.append(tabla_fase)

    # Texto explicativo de cada fase
    elementos.append(Spacer(1, 8))

    for fase in consolidado["por_fase"]:
        elementos.append(
            Paragraph(
                f"<b>{fase['nombre_fase']}:</b> "
                f"se evaluaron {fase['total']} actividades. "
                f"{fase['cumplidos']} cumplieron completamente, "
                f"{fase['parciales']} presentaron cumplimiento parcial "
                f"y {fase['no_cumplidos']} no cumplieron. "
                f"El avance de la fase fue del "
                f"<b>{fase['porcentaje_avance']}%</b>.",
                texto_normal
            )
        )

    elementos.append(PageBreak())

    # =========================================================
    # 4. DETALLE DE ACTIVIDADES
    # =========================================================

    elementos.append(
        Paragraph(
            "4. ACTIVIDADES REALIZADAS DURANTE EL PERIODO",
            seccion
        )
    )

    elementos.append(
        Paragraph(
            "A continuación se presentan las actividades registradas, "
            "indicando la sede donde fueron realizadas, su responsable, "
            "fecha y resultado de cumplimiento.",
            texto_normal
        )
    )

    elementos.append(Spacer(1, 6))

    for item in consolidado["detalle"]:

        porcentaje = item["porcentaje_item"]

        # Color según el estado de cumplimiento
        color_resultado = _color_estado(
            item["estado_cumplimiento"]
        )

        contenido_actividad = [
            [
                Paragraph(
                    f"<b>Actividad {item['codigo_item']}</b>",
                    texto_normal
                ),
                Paragraph(
                    f"<b>{_texto(item['descripcion_item'])}</b>",
                    texto_normal
                ),
            ],
            [
                Paragraph("<b>Fase PHVA</b>", texto_pequeno),
                Paragraph(
                    _texto(item["nombre_fase"]),
                    texto_pequeno
                ),
            ],
            [
                Paragraph("<b>Sede</b>", texto_pequeno),
                Paragraph(
                    _texto(item["nombre_sede"]),
                    texto_pequeno
                ),
            ],
            [
                Paragraph("<b>Responsable</b>", texto_pequeno),
                Paragraph(
                    _texto(item["responsable"]),
                    texto_pequeno
                ),
            ],
            [
                Paragraph("<b>Fecha</b>", texto_pequeno),
                Paragraph(
                    _fecha_legible(item["fecha_registro"]),
                    texto_pequeno
                ),
            ],
            [
                Paragraph("<b>Resultado</b>", texto_pequeno),
                Paragraph(
                    f"<b>{_estado_legible(item['estado_cumplimiento'])} "
                    f"— {porcentaje}%</b>",
                    texto_pequeno
                ),
            ],
            [
                Paragraph("<b>Evidencia requerida</b>", texto_pequeno),
                Paragraph(
                    _texto(item["evidencia_requerida"]),
                    texto_pequeno
                ),
            ],
            [
                Paragraph("<b>Observación</b>", texto_pequeno),
                Paragraph(
                    _texto(item["observacion"]),
                    texto_pequeno
                ),
            ],
        ]

        tabla_actividad = Table(
            contenido_actividad,
            colWidths=[
                5 * cm,
                19 * cm,
            ]
        )

        tabla_actividad.setStyle(
            TableStyle([
                # Encabezado de la actividad
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#E8EEF7")
                ),

                # Columna izquierda
                (
                    "BACKGROUND",
                    (0, 1),
                    (0, -1),
                    colors.HexColor("#F8FAFC")
                ),

                # Bordes
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#CBD5E1")
                ),

                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),

                # =================================================
                # COLOR DEL RESULTADO
                # =================================================

                # Fondo verde, naranja o rojo
                (
                    "BACKGROUND",
                    (1, 5),
                    (1, 5),
                    color_resultado
                ),

                # Texto blanco
                (
                    "TEXTCOLOR",
                    (1, 5),
                    (1, 5),
                    colors.white
                ),

                # Texto en negrita
                (
                    "FONTNAME",
                    (1, 5),
                    (1, 5),
                    "Helvetica-Bold"
                ),

                # Centrado vertical
                (
                    "VALIGN",
                    (1, 5),
                    (1, 5),
                    "MIDDLE"
                ),
            ])
        )

        elementos.append(
            KeepTogether([
                tabla_actividad,
                Spacer(1, 10)
            ])
        )

        # =========================================================
    # 5. ACTIVIDADES QUE REQUIEREN SEGUIMIENTO
    # =========================================================

    elementos.append(PageBreak())

    elementos.append(
        Paragraph(
            "5. ACTIVIDADES QUE REQUIEREN SEGUIMIENTO",
            seccion
        )
    )

    pendientes = [
        item
        for item in consolidado["detalle"]
        if item["estado_cumplimiento"] in (
            "PARCIAL",
            "NO_CUMPLE"
        )
    ]

    if pendientes:

        datos_pendientes = [
            [
                "Actividad",
                "Sede",
                "Responsable",
                "Estado",
                "Fecha",
                "Observación",
            ]
        ]

        for item in pendientes:

            datos_pendientes.append(
                [
                    Paragraph(
                        f"{item['codigo_item']} - "
                        f"{_texto(item['descripcion_item'])}",
                        texto_pequeno,
                    ),
                    Paragraph(
                        _texto(item["nombre_sede"]),
                        texto_pequeno,
                    ),
                    Paragraph(
                        _texto(item["responsable"]),
                        texto_pequeno,
                    ),
                    Paragraph(
                        f"<b>{_estado_legible(item['estado_cumplimiento'])}</b>",
                        texto_pequeno,
                    ),
                    _fecha_legible(
                        item["fecha_registro"]
                    ),
                    Paragraph(
                        _texto(item["observacion"]),
                        texto_pequeno,
                    ),
                ]
            )

        tabla_pendientes = Table(
            datos_pendientes,
            colWidths=[
                7 * cm,
                4 * cm,
                4 * cm,
                3.5 * cm,
                3 * cm,
                6 * cm,
            ],
            repeatRows=1,
        )

        # Estilo general
        estilos_pendientes = [
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                AZUL_PRINCIPAL,
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.HexColor("#CBD5E1"),
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                7.5,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
        ]

        # =====================================================
        # COLORES DE ESTADO POR CADA FILA
        # =====================================================

        for numero_fila, item in enumerate(
            pendientes,
            start=1
        ):

            color_estado = _color_estado(
                item["estado_cumplimiento"]
            )

            estilos_pendientes.extend([
                (
                    "BACKGROUND",
                    (3, numero_fila),
                    (3, numero_fila),
                    color_estado
                ),
                (
                    "TEXTCOLOR",
                    (3, numero_fila),
                    (3, numero_fila),
                    colors.white
                ),
                (
                    "FONTNAME",
                    (3, numero_fila),
                    (3, numero_fila),
                    "Helvetica-Bold"
                ),
                (
                    "ALIGN",
                    (3, numero_fila),
                    (3, numero_fila),
                    "CENTER"
                ),
                (
                    "VALIGN",
                    (3, numero_fila),
                    (3, numero_fila),
                    "MIDDLE"
                ),
            ])

        tabla_pendientes.setStyle(
            TableStyle(
                estilos_pendientes
            )
        )

        elementos.append(
            tabla_pendientes
        )

    else:

        elementos.append(
            Paragraph(
                "Durante el periodo no se registraron actividades "
                "con cumplimiento parcial o estado No Cumple.",
                texto_normal
            )
        )

    elementos.append(
        Spacer(
            1,
            18
        )
    )

    # =========================================================
    # 6. CONCLUSIONES
    # =========================================================

    elementos.append(
        Paragraph(
           "6. CONCLUSIONES DEL PERIODO",
            seccion
        )
    )

    conclusiones = _generar_conclusiones(
        consolidado
    )

    for numero, conclusion in enumerate(
        conclusiones,
        start=1
    ):
        elementos.append(
            Paragraph(
                f"<b>{numero}.</b> {conclusion}",
                texto_normal
            )
        )

    # =========================================================
    # FIRMA
    # =========================================================

    elementos.append(Spacer(1, 28))

    elementos.append(
        Paragraph(
            "____________________________________________",
            texto_normal
        )
    )

    elementos.append(
        Paragraph(
            f"<b>Generado por:</b> {generado_por}",
            texto_normal
        )
    )

    elementos.append(
        Paragraph(
            "Responsable del Sistema de Gestión de Seguridad "
            "y Salud en el Trabajo",
            texto_normal
        )
    )

    doc.build(
        elementos,
        onFirstPage=_decorar_pagina,
        onLaterPages=_decorar_pagina
    )

    return ruta