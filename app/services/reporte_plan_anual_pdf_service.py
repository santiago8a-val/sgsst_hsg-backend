import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from app.config import Config


def generar_reporte_plan_anual_pdf(ejecuciones: list, anio: int, mes: int, nombre_archivo: str) -> str:
    """
    'ejecuciones' es la lista que retorna GET /api/plan-anual/ejecuciones, ya con
    nombre_sede, responsable, descripcion_actividad incluidos.
    """
    os.makedirs(Config.REPORTS_FOLDER, exist_ok=True)
    ruta = os.path.join(Config.REPORTS_FOLDER, nombre_archivo)

    doc = SimpleDocTemplate(ruta, pagesize=letter, topMargin=2 * cm, bottomMargin=2 * cm)
    estilos = getSampleStyleSheet()
    titulo_estilo = ParagraphStyle("TituloCentro", parent=estilos["Title"], alignment=1)
    elementos = []

    elementos.append(Paragraph("Informe Plan Anual SG-SST", titulo_estilo))
    elementos.append(Spacer(1, 12))
    elementos.append(Paragraph(f"<b>Periodo:</b> {mes:02d}/{anio}", estilos["Normal"]))
    elementos.append(Spacer(1, 18))

    datos = [["Programa", "Actividad", "Sede", "Responsable", "Estado"]]
    for e in ejecuciones:
        estado = "Aprobado" if e["aprobado"] else ("Rechazado" if e["rechazado"] else "Pendiente")
        datos.append([
            e["nombre_programa"], e["descripcion_actividad"][:60],
            e["nombre_sede"], e["responsable"], estado,
        ])

    tabla = Table(datos, hAlign="LEFT")
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(tabla)

    doc.build(elementos)
    return ruta