from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.db import db_cursor
from app.auth import token_requerido, requiere_permiso
from app.schemas import GenerarReporteRequest
from app.services.consolidado_service import obtener_consolidado
from app.services.reporte_word_service import generar_reporte_word
from app.services.reporte_pdf_service import generar_reporte_pdf
from app.config import Config
import os

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


@router.post("/generar", status_code=201)
def generar_reporte(data: GenerarReporteRequest, usuario_actual: dict = Depends(requiere_permiso("exportar"))):
    tipo_corte = data.tipo_corte.upper()
    formato = data.formato.upper()

    consolidado = obtener_consolidado(tipo_corte, data.periodo)
    generado_por = usuario_actual["usuario"]
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    base_nombre = f"reporte_sgsst_{tipo_corte}_{data.periodo}_{timestamp}"

    if formato == "WORD":
        nombre_archivo = f"{base_nombre}.docx"
        ruta = generar_reporte_word(consolidado, generado_por, nombre_archivo)
    elif formato == "PDF":
        nombre_archivo = f"{base_nombre}.pdf"
        ruta = generar_reporte_pdf(consolidado, generado_por, nombre_archivo)
    else:
        raise HTTPException(status_code=400, detail="formato debe ser 'WORD' o 'PDF'")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO reportes (tipo_corte, periodo_valor, formato, ruta_archivo, generado_por)
               VALUES (%s,%s,%s,%s,%s)""",
            (tipo_corte, data.periodo, formato, ruta, usuario_actual["id_usuario"]),
        )
        id_reporte = cur.lastrowid

    return {
        "mensaje": "Reporte generado",
        "id_reporte": id_reporte,
        "archivo": nombre_archivo,
        "url_descarga": f"/api/reportes/descargar/{nombre_archivo}",
    }


@router.get("/descargar/{nombre_archivo:path}")
def descargar_reporte(nombre_archivo: str, usuario_actual: dict = Depends(token_requerido)):
    ruta = os.path.join(Config.REPORTS_FOLDER, nombre_archivo)
    if not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return FileResponse(ruta, filename=nombre_archivo)


@router.get("/historial")
def historial_reportes(usuario_actual: dict = Depends(token_requerido)):
    with db_cursor() as cur:
        cur.execute(
            """SELECT r.id_reporte, r.tipo_corte, r.periodo_valor, r.formato,
                      r.fecha_generacion, u.nombre_completo AS generado_por
               FROM reportes r JOIN usuarios u ON r.generado_por = u.id_usuario
               ORDER BY r.fecha_generacion DESC LIMIT 100"""
        )
        return cur.fetchall()
