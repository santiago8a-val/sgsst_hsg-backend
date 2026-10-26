from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from pydantic import BaseModel
from app.db import db_cursor
from app.auth import token_requerido, requiere_permiso, requiere_rol_admin, es_admin_general, sede_del_usuario_actual
from app.utils.archivos import guardar_archivo, FORMATOS_EXTENSIONES
from app.services.plan_anual_service import calcular_cumplimiento_sede_mes, calcular_cumplimiento_todas_las_sedes
from app.services.email_services import enviar_correo_rechazo
from app.services.reporte_plan_anual_pdf_service import generar_reporte_plan_anual_pdf
from fastapi.responses import FileResponse, StreamingResponse
from datetime import datetime as dt
from datetime import datetime as dt_mod
from typing import List
import os
import io


router = APIRouter(prefix="/api/plan-anual", tags=["plan_anual"])
ANIO_MINIMO = 2026


class ProgramaCreate(BaseModel):
    nombre_programa: str


class SubprogramaCreate(BaseModel):
    id_programa: int
    nombre_subprograma: Optional[str] = None


class ActividadCreate(BaseModel):
    id_subprograma: int
    descripcion_actividad: str
    responsable_sugerido: Optional[str] = None
    formato_evidencia: str = "PDF"
    meses: List[int]


class ActividadUpdate(BaseModel):
    descripcion_actividad: Optional[str] = None
    responsable_sugerido: Optional[str] = None
    formato_evidencia: Optional[str] = None
    meses: Optional[List[int]] = None
    activo: Optional[bool] = None

@router.get("/programas")
def listar_programas(usuario_actual: dict = Depends(token_requerido)):
    with db_cursor() as cur:
        cur.execute("SELECT id_programa, nombre_programa FROM plan_programas ORDER BY nombre_programa")
        return cur.fetchall()


@router.post("/programas", status_code=201)
def crear_programa(data: ProgramaCreate, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor(commit=True) as cur:
        cur.execute("INSERT INTO plan_programas (nombre_programa) VALUES (%s)", (data.nombre_programa.strip(),))
        return {"id_programa": cur.lastrowid, "mensaje": "Programa creado"}


#cambios editar/eliminar programa
@router.put("/programas/{id_programa}")
def editar_programa(id_programa: int, data: ProgramaCreate, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT id_programa FROM plan_programas WHERE id_programa = %s", (id_programa,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Programa no encontrado")

    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE plan_programas SET nombre_programa=%s WHERE id_programa=%s",
            (data.nombre_programa.strip(), id_programa),
        )
    return {"mensaje": "Programa actualizado"}


@router.delete("/programas/{id_programa}")
def eliminar_programa(id_programa: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT id_programa FROM plan_programas WHERE id_programa = %s", (id_programa,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Programa no encontrado")

        cur.execute("SELECT COUNT(*) AS total FROM plan_subprogramas WHERE id_programa = %s", (id_programa,))
        subprogramas_en_uso = cur.fetchone()["total"]

    if subprogramas_en_uso > 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar: {subprogramas_en_uso} subprograma(s) pertenecen a este programa."
        )

    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM plan_programas WHERE id_programa = %s", (id_programa,))

    return {"mensaje": "Programa eliminado"}
#final de cambios editar/eliminar programa

@router.get("/subprogramas")
def listar_subprogramas(id_programa: Optional[int] = None, usuario_actual: dict = Depends(token_requerido)):
    with db_cursor() as cur:
        if id_programa:
            cur.execute(
                "SELECT id_subprograma, nombre_subprograma, id_programa FROM plan_subprogramas WHERE id_programa=%s ORDER BY nombre_subprograma",
                (id_programa,),
            )
        else:
            cur.execute(
                """SELECT ps.id_subprograma, ps.nombre_subprograma, ps.id_programa, pp.nombre_programa
                   FROM plan_subprogramas ps JOIN plan_programas pp ON ps.id_programa = pp.id_programa
                   ORDER BY pp.nombre_programa, ps.nombre_subprograma"""
            )
        return cur.fetchall()


@router.post("/subprogramas", status_code=201)
def crear_subprograma(data: SubprogramaCreate, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO plan_subprogramas (id_programa, nombre_subprograma) VALUES (%s, %s)",
            (data.id_programa, (data.nombre_subprograma or "").strip() or None),
        )
        return {"id_subprograma": cur.lastrowid, "mensaje": "Subprograma creado"}
#cambios beta
@router.put("/subprogramas/{id_subprograma}")
def editar_subprograma(id_subprograma: int, data: SubprogramaCreate, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT id_subprograma FROM plan_subprogramas WHERE id_subprograma = %s", (id_subprograma,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subprograma no encontrado")

    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE plan_subprogramas SET id_programa=%s, nombre_subprograma=%s WHERE id_subprograma=%s",
            (data.id_programa, (data.nombre_subprograma or "").strip() or None, id_subprograma),
        )
    return {"mensaje": "Subprograma actualizado"}


@router.delete("/subprogramas/{id_subprograma}")
def eliminar_subprograma(id_subprograma: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT id_subprograma FROM plan_subprogramas WHERE id_subprograma = %s", (id_subprograma,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Subprograma no encontrado")

        cur.execute("SELECT COUNT(*) AS total FROM plan_actividades WHERE id_subprograma = %s", (id_subprograma,))
        actividades_en_uso = cur.fetchone()["total"]

    if actividades_en_uso > 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar: {actividades_en_uso} actividad(es) pertenecen a este subprograma."
        )

    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM plan_subprogramas WHERE id_subprograma = %s", (id_subprograma,))

    return {"mensaje": "Subprograma eliminado"}
#final de cambios beta

@router.post("/actividades", status_code=201)
def crear_actividad(data: ActividadCreate, usuario_actual: dict = Depends(requiere_rol_admin)):
    if data.formato_evidencia not in ("PDF", "WORD", "EXCEL", "IMAGEN"):
        raise HTTPException(status_code=400, detail="formato_evidencia inválido")
    if not data.meses or any(m < 1 or m > 12 for m in data.meses):
        raise HTTPException(status_code=400, detail="meses debe ser una lista de números entre 1 y 12")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO plan_actividades (id_subprograma, descripcion_actividad, responsable_sugerido, formato_evidencia)
               VALUES (%s, %s, %s, %s)""",
            (data.id_subprograma, data.descripcion_actividad.strip(), data.responsable_sugerido, data.formato_evidencia),
        )
        id_actividad = cur.lastrowid
        for m in set(data.meses):
            cur.execute("INSERT INTO plan_actividad_meses (id_actividad, mes) VALUES (%s, %s)", (id_actividad, m))

    return {"id_actividad": id_actividad, "mensaje": "Actividad creada"}


@router.put("/actividades/{id_actividad}")
def editar_actividad(id_actividad: int, data: ActividadUpdate, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM plan_actividades WHERE id_actividad = %s", (id_actividad,))
        anterior = cur.fetchone()
    if not anterior:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    formato = data.formato_evidencia if data.formato_evidencia is not None else anterior["formato_evidencia"]
    if formato not in ("PDF", "WORD", "EXCEL", "IMAGEN"):
        raise HTTPException(status_code=400, detail="formato_evidencia inválido")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE plan_actividades SET descripcion_actividad=%s, responsable_sugerido=%s,
                                            formato_evidencia=%s, activo=%s WHERE id_actividad=%s""",
            (
                data.descripcion_actividad if data.descripcion_actividad is not None else anterior["descripcion_actividad"],
                data.responsable_sugerido if data.responsable_sugerido is not None else anterior["responsable_sugerido"],
                formato,
                data.activo if data.activo is not None else anterior["activo"],
                id_actividad,
            ),
        )
        if data.meses is not None:
            if any(m < 1 or m > 12 for m in data.meses):
                raise HTTPException(status_code=400, detail="meses debe contener valores entre 1 y 12")
            cur.execute("DELETE FROM plan_actividad_meses WHERE id_actividad = %s", (id_actividad,))
            for m in set(data.meses):
                cur.execute("INSERT INTO plan_actividad_meses (id_actividad, mes) VALUES (%s, %s)", (id_actividad, m))

    return {"mensaje": "Actividad actualizada"}


@router.delete("/actividades/{id_actividad}")
def eliminar_actividad(id_actividad: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM plan_ejecuciones WHERE id_actividad = %s", (id_actividad,))
        en_uso = cur.fetchone()["total"]

    if en_uso > 0:
        raise HTTPException(status_code=409, detail=f"No se puede eliminar: hay {en_uso} ejecución(es) registradas para esta actividad")

    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM plan_actividades WHERE id_actividad = %s", (id_actividad,))  # cascada borra sus meses

    return {"mensaje": "Actividad eliminada permanentemente"}

# ---------- Catálogo (solo lectura por ahora) ----------
#cambios 2 beta
@router.get("/actividades")
def listar_actividades(incluir_inactivas: bool = False, usuario_actual: dict = Depends(token_requerido)):
    filtro_activo = "" if incluir_inactivas else "WHERE pa.activo = TRUE"
    with db_cursor() as cur:
        cur.execute(
            f"""SELECT pa.id_actividad, pa.descripcion_actividad, pa.responsable_sugerido,
                      pa.formato_evidencia, pa.activo, pp.nombre_programa, ps.nombre_subprograma
               FROM plan_actividades pa
               JOIN plan_subprogramas ps ON pa.id_subprograma = ps.id_subprograma
               JOIN plan_programas pp ON ps.id_programa = pp.id_programa
               {filtro_activo}
               ORDER BY pp.nombre_programa, ps.nombre_subprograma, pa.id_actividad"""
        )
#final de cambios 2 beta
        actividades = cur.fetchall()
        for a in actividades:
            cur.execute("SELECT mes FROM plan_actividad_meses WHERE id_actividad = %s ORDER BY mes",
                        (a["id_actividad"],))
            a["meses_programados"] = [f["mes"] for f in cur.fetchall()]
    return actividades


@router.get("/actividades/mes/{anio}/{mes}")
def listar_actividades_del_mes(
    anio: int, mes: int, sede: Optional[int] = None,
    usuario_actual: dict = Depends(token_requerido)
):
    """Actividades programadas para un mes específico, con su estado de ejecución de la sede del usuario."""
    id_sede = sede_del_usuario_actual(usuario_actual) if not es_admin_general(usuario_actual) else sede

    with db_cursor() as cur:
        cur.execute(
            """SELECT pa.id_actividad, pa.descripcion_actividad, pa.responsable_sugerido,
                      pa.formato_evidencia, pp.nombre_programa, ps.nombre_subprograma
               FROM plan_actividad_meses pam
               JOIN plan_actividades pa ON pam.id_actividad = pa.id_actividad
               JOIN plan_subprogramas ps ON pa.id_subprograma = ps.id_subprograma
               JOIN plan_programas pp ON ps.id_programa = pp.id_programa
               WHERE pam.mes = %s AND pa.activo = TRUE
               ORDER BY pp.nombre_programa, pa.id_actividad""",
            (mes,),
        )
        actividades = cur.fetchall()

        if id_sede:
            for a in actividades:
                cur.execute(
                    """SELECT id_ejecucion, estado_revision, aprobado, rechazado FROM plan_ejecuciones
                       WHERE id_actividad = %s AND id_sede = %s AND anio = %s AND mes = %s""",
                    (a["id_actividad"], id_sede, anio, mes),
                )
                a["ejecucion"] = cur.fetchone()

    return actividades


# ---------- Ejecuciones ----------
@router.get("/ejecuciones")
def listar_ejecuciones(
    anio: Optional[int] = None, mes: Optional[int] = None, sede: Optional[int] = None,
    estado_aprobacion: Optional[str] = None,
    usuario_actual: dict = Depends(token_requerido),
    ):

    condiciones, params = ["1=1"], []
    if not es_admin_general(usuario_actual):
        condiciones.append("e.id_sede = %s"); params.append(sede_del_usuario_actual(usuario_actual))
    elif sede:
        condiciones.append("e.id_sede = %s"); params.append(sede)

    if anio: condiciones.append("e.anio = %s"); params.append(anio)
    if mes: condiciones.append("e.mes = %s"); params.append(mes)
    if estado_aprobacion == "PENDIENTE":
        condiciones.append("e.aprobado = FALSE AND e.rechazado = FALSE")
    elif estado_aprobacion == "APROBADO":
        condiciones.append("e.aprobado = TRUE")
    elif estado_aprobacion == "RECHAZADO":
        condiciones.append("e.rechazado = TRUE")

    query = f"""
        SELECT e.id_ejecucion, e.anio, e.mes, e.fecha_ejecucion, e.observacion,
               e.estado_revision, e.aprobado, e.rechazado, e.fecha_creacion, e.id_sede, s.nombre_sede,
               pa.descripcion_actividad, pp.nombre_programa, ps.nombre_subprograma,
               u.nombre_completo AS responsable
        FROM plan_ejecuciones e
        JOIN plan_actividades pa ON e.id_actividad = pa.id_actividad
        JOIN plan_subprogramas ps ON pa.id_subprograma = ps.id_subprograma
        JOIN plan_programas pp ON ps.id_programa = pp.id_programa
        JOIN sedes s ON e.id_sede = s.id_sede
        JOIN usuarios u ON e.id_responsable = u.id_usuario
        WHERE {' AND '.join(condiciones)}
        ORDER BY e.fecha_creacion DESC
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


@router.get("/ejecuciones/pendientes")
def listar_ejecuciones_pendientes(usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute(
            """SELECT e.id_ejecucion, e.anio, e.mes, e.fecha_ejecucion,
                      s.nombre_sede, pa.descripcion_actividad, u.nombre_completo AS responsable,
                      pe.id_evidencia, pe.nombre_original
               FROM plan_ejecuciones e
               JOIN plan_actividades pa ON e.id_actividad = pa.id_actividad
               JOIN sedes s ON e.id_sede = s.id_sede
               JOIN usuarios u ON e.id_responsable = u.id_usuario
               LEFT JOIN plan_evidencias pe ON pe.id_ejecucion = e.id_ejecucion
               WHERE e.aprobado = FALSE AND e.rechazado = FALSE
               ORDER BY e.fecha_creacion DESC"""
        )
        return cur.fetchall()

@router.post("", status_code=201)
def crear_ejecucion(
    id_actividad: int = Form(...), anio: int = Form(...), mes: int = Form(...),
    fecha_ejecucion: str = Form(...), observacion: Optional[str] = Form(None),
    id_sede: Optional[int] = Form(None), archivo_evidencia: UploadFile = File(...),
    usuario_actual: dict = Depends(requiere_permiso("crear")),
    ):
    anio_maximo = dt_mod.now().year + 1
    if not (ANIO_MINIMO <= anio <= anio_maximo):
        raise HTTPException(status_code=400, detail=f"El año debe estar entre {ANIO_MINIMO} y {anio_maximo}")
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12")
    with db_cursor() as cur:
        cur.execute("SELECT formato_evidencia FROM plan_actividades WHERE id_actividad = %s AND activo = TRUE",
                    (id_actividad,))
        actividad = cur.fetchone()
        if not actividad:
            raise HTTPException(status_code=400, detail="La actividad no existe")

        cur.execute("SELECT 1 FROM plan_actividad_meses WHERE id_actividad = %s AND mes = %s",
                    (id_actividad, mes))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Esta actividad no está programada para ese mes")

    sede_final = sede_del_usuario_actual(usuario_actual)
    if not sede_final:
        if not id_sede:
            raise HTTPException(status_code=400, detail="id_sede es obligatorio")
        sede_final = id_sede

    with db_cursor() as cur:
        cur.execute(
            "SELECT id_ejecucion FROM plan_ejecuciones WHERE id_actividad=%s AND id_sede=%s AND anio=%s AND mes=%s",
            (id_actividad, sede_final, anio, mes),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Ya existe un registro de esta actividad para este mes en esta sede")

    formato_esperado = actividad["formato_evidencia"]
    try:
        datos_archivo = guardar_archivo(archivo_evidencia, FORMATOS_EXTENSIONES[formato_esperado])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"El archivo no es válido (se espera {formato_esperado}): {e}")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO plan_ejecuciones
               (id_actividad, id_sede, id_responsable, anio, mes, fecha_ejecucion, observacion)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (id_actividad, sede_final, usuario_actual["id_usuario"], anio, mes, fecha_ejecucion, observacion),
        )
        nuevo_id = cur.lastrowid

        cur.execute(
            """INSERT INTO plan_evidencias
               (id_ejecucion, nombre_archivo, nombre_original, ruta_archivo,
                tipo_archivo, tamano_bytes, subido_por, contenido_archivo)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (nuevo_id, datos_archivo["nombre_archivo"], datos_archivo["nombre_original"],
             datos_archivo["ruta_archivo"], datos_archivo["tipo_archivo"],
             datos_archivo["tamano_bytes"], usuario_actual["id_usuario"], datos_archivo["contenido_bytes"]),
        )

    return {"mensaje": "Ejecución registrada, pendiente de aprobación", "id_ejecucion": nuevo_id}


@router.post("/{id_ejecucion}/aprobar")
def aprobar_ejecucion(id_ejecucion: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE plan_ejecuciones
               SET estado_revision = 'APROBADA', aprobado = TRUE, rechazado = FALSE,
                   motivo_rechazo = NULL, id_aprobador = %s, fecha_aprobacion = NOW()
               WHERE id_ejecucion = %s""",
            (usuario_actual["id_usuario"], id_ejecucion),
        )
    return {"mensaje": "Ejecución aprobada"}


class RechazarEjecucionRequest(BaseModel):
    motivo: str


@router.post("/{id_ejecucion}/rechazar")
def rechazar_ejecucion(id_ejecucion: int, data: RechazarEjecucionRequest,
                        usuario_actual: dict = Depends(requiere_rol_admin)):
    motivo = data.motivo.strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Debe indicar el motivo del rechazo")

    with db_cursor() as cur:
        cur.execute(
            """SELECT e.id_sede, pa.descripcion_actividad
               FROM plan_ejecuciones e JOIN plan_actividades pa ON e.id_actividad = pa.id_actividad
               WHERE e.id_ejecucion = %s""",
            (id_ejecucion,),
        )
        ejecucion = cur.fetchone()
    if not ejecucion:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE plan_ejecuciones SET estado_revision = 'RECHAZADA', rechazado = TRUE,
               motivo_rechazo = %s, aprobado = FALSE, id_aprobador = %s, fecha_aprobacion = NOW()
               WHERE id_ejecucion = %s""",
            (motivo, usuario_actual["id_usuario"], id_ejecucion),
        )
        cur.execute(
            """SELECT u.correo, u.nombre_completo FROM usuarios u
               JOIN roles r ON u.id_rol = r.id_rol
               WHERE r.nombre_rol = 'ADMIN_SEDE' AND u.id_sede = %s AND u.activo = TRUE""",
            (ejecucion["id_sede"],),
        )
        admins_sede = cur.fetchall()

    for admin in admins_sede:
        try:
            enviar_correo_rechazo(admin["correo"], admin["nombre_completo"],
                                   "PLAN-ANUAL", ejecucion["descripcion_actividad"], motivo)
        except Exception:
            pass

    return {"mensaje": "Ejecución rechazada, se notificó al administrador de la sede"}




class RegularEjecucionRequest(BaseModel):
    observacion: Optional[str] = None


@router.post("/{id_ejecucion}/regular")
def marcar_ejecucion_regular(
    id_ejecucion: int,
    data: RegularEjecucionRequest,
    usuario_actual: dict = Depends(requiere_rol_admin),
):
    with db_cursor() as cur:
        cur.execute("SELECT id_ejecucion FROM plan_ejecuciones WHERE id_ejecucion = %s", (id_ejecucion,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Ejecución no encontrada")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE plan_ejecuciones
               SET estado_revision = 'REGULAR', aprobado = FALSE, rechazado = FALSE,
                   motivo_rechazo = %s, id_aprobador = %s, fecha_aprobacion = NOW()
               WHERE id_ejecucion = %s""",
            ((data.observacion or "").strip() or None, usuario_actual["id_usuario"], id_ejecucion),
        )
    return {"mensaje": "Ejecución marcada como regular (50 %)"}


@router.get("/cumplimiento/detalle")
def detalle_cumplimiento(
    anio: int,
    mes: Optional[int] = None,
    sede: Optional[int] = None,
    usuario_actual: dict = Depends(token_requerido),
):
    """Detalle jerárquico. Si mes no se envía, muestra por defecto todo el año."""
    if mes is not None and not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12")

    if es_admin_general(usuario_actual):
        if not sede:
            raise HTTPException(status_code=400, detail="Debe seleccionar una sede")
        id_sede = sede
    else:
        id_sede = sede_del_usuario_actual(usuario_actual)
        if not id_sede:
            raise HTTPException(status_code=403, detail="El usuario no tiene una sede asignada")

    with db_cursor() as cur:
        cur.execute(
            "SELECT id_sede, nombre_sede FROM sedes WHERE id_sede = %s AND activa = TRUE",
            (id_sede,),
        )
        sede_info = cur.fetchone()
        if not sede_info:
            raise HTTPException(status_code=404, detail="Sede no encontrada")

        filtro_mes = "AND pam.mes = %s" if mes is not None else ""
        params = [id_sede, anio]
        if mes is not None:
            params.append(mes)

        cur.execute(
            f"""
            SELECT pa.id_actividad, pa.descripcion_actividad, pa.formato_evidencia,
                   pam.mes AS mes_programado,
                   pp.id_programa, pp.nombre_programa,
                   ps.id_subprograma, ps.nombre_subprograma,
                   e.id_ejecucion, e.fecha_ejecucion, e.observacion,
                   e.estado_revision, e.aprobado, e.rechazado, e.motivo_rechazo,
                   e.fecha_creacion, e.fecha_aprobacion,
                   u.nombre_completo AS responsable,
                   pe.id_evidencia, pe.nombre_original
            FROM plan_actividad_meses pam
            JOIN plan_actividades pa ON pam.id_actividad = pa.id_actividad
            JOIN plan_subprogramas ps ON pa.id_subprograma = ps.id_subprograma
            JOIN plan_programas pp ON ps.id_programa = pp.id_programa
            LEFT JOIN plan_ejecuciones e
              ON e.id_actividad = pa.id_actividad
             AND e.id_sede = %s AND e.anio = %s AND e.mes = pam.mes
            LEFT JOIN usuarios u ON e.id_responsable = u.id_usuario
            LEFT JOIN plan_evidencias pe ON pe.id_evidencia = (
                SELECT pe2.id_evidencia FROM plan_evidencias pe2
                WHERE pe2.id_ejecucion = e.id_ejecucion
                ORDER BY pe2.id_evidencia DESC LIMIT 1
            )
            WHERE pa.activo = TRUE {filtro_mes}
            ORDER BY pp.nombre_programa, ps.nombre_subprograma, pam.mes, pa.id_actividad
            """,
            params,
        )
        filas = cur.fetchall()

    def estado_de(f):
        if not f.get("id_ejecucion"):
            return "NO_REALIZADA"
        if f.get("estado_revision"):
            return str(f["estado_revision"]).upper()
        if f.get("aprobado"):
            return "APROBADA"
        if f.get("rechazado"):
            return "RECHAZADA"
        return "PENDIENTE"

    valores = {
        "APROBADA": 100.0, "REGULAR": 50.0, "RECHAZADA": 0.0,
        "PENDIENTE": 0.0, "NO_REALIZADA": 0.0,
    }
    programas = {}
    for f in filas:
        estado = estado_de(f)
        actividad = {
            "id_actividad": f["id_actividad"],
            "descripcion_actividad": f["descripcion_actividad"],
            "formato_evidencia": f["formato_evidencia"],
            "mes": f["mes_programado"],
            "estado": estado,
            "porcentaje": valores.get(estado, 0.0),
            "id_ejecucion": f.get("id_ejecucion"),
            "fecha_ejecucion": f.get("fecha_ejecucion"),
            "fecha_envio": f.get("fecha_creacion"),
            "observacion": f.get("observacion"),
            "observacion_revision": f.get("motivo_rechazo"),
            "responsable": f.get("responsable"),
            "evidencia": ({"id_evidencia": f["id_evidencia"], "nombre_original": f["nombre_original"]}
                          if f.get("id_evidencia") else None),
        }
        prog = programas.setdefault(f["id_programa"], {
            "id_programa": f["id_programa"], "nombre_programa": f["nombre_programa"], "subprogramas": {}
        })
        sub = prog["subprogramas"].setdefault(f["id_subprograma"], {
            "id_subprograma": f["id_subprograma"], "nombre_subprograma": f["nombre_subprograma"], "actividades": []
        })
        sub["actividades"].append(actividad)

    salida_programas = []
    for prog in programas.values():
        subs, actividades_programa = [], []
        for sub in prog["subprogramas"].values():
            acts = sub["actividades"]
            sub["porcentaje"] = round(sum(a["porcentaje"] for a in acts) / len(acts), 2) if acts else 0
            subs.append(sub)
            actividades_programa.extend(acts)
        prog["subprogramas"] = subs
        prog["porcentaje"] = round(
            sum(a["porcentaje"] for a in actividades_programa) / len(actividades_programa), 2
        ) if actividades_programa else 0
        salida_programas.append(prog)

    total = len(filas)
    porcentaje_sede = round(sum(valores.get(estado_de(f), 0.0) for f in filas) / total, 2) if total else 0
    return {
        "sede": sede_info,
        "anio": anio,
        "mes": mes,
        "porcentaje_cumplimiento": porcentaje_sede,
        "programas": salida_programas,
        "puede_calificar": es_admin_general(usuario_actual),
    }


# ---------- Cumplimiento (calculado, no manual) ----------
@router.get("/cumplimiento")
def ver_cumplimiento(anio: int, mes: int, sede: Optional[int] = None,
                      usuario_actual: dict = Depends(token_requerido)):
    if es_admin_general(usuario_actual):
        if sede:
            return calcular_cumplimiento_sede_mes(sede, anio, mes)
        return calcular_cumplimiento_todas_las_sedes(anio, mes)

    id_sede = sede_del_usuario_actual(usuario_actual)
    return calcular_cumplimiento_sede_mes(id_sede, anio, mes)

@router.post("/reportes/generar", status_code=201)
def generar_reporte_plan_anual(anio: int, mes: int, sede: Optional[int] = None,
                                usuario_actual: dict = Depends(requiere_permiso("exportar"))):
    id_sede_final = sede
    if not es_admin_general(usuario_actual):
        id_sede_final = sede_del_usuario_actual(usuario_actual)

    condiciones, params = ["e.anio = %s", "e.mes = %s"], [anio, mes]
    if id_sede_final:
        condiciones.append("e.id_sede = %s"); params.append(id_sede_final)

    query = f"""
        SELECT e.aprobado, e.rechazado, s.nombre_sede, pp.nombre_programa,
               pa.descripcion_actividad, u.nombre_completo AS responsable
        FROM plan_ejecuciones e
        JOIN plan_actividades pa ON e.id_actividad = pa.id_actividad
        JOIN plan_subprogramas ps ON pa.id_subprograma = ps.id_subprograma
        JOIN plan_programas pp ON ps.id_programa = pp.id_programa
        JOIN sedes s ON e.id_sede = s.id_sede
        JOIN usuarios u ON e.id_responsable = u.id_usuario
        WHERE {' AND '.join(condiciones)}
        ORDER BY pp.nombre_programa
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        ejecuciones = cur.fetchall()

    timestamp = dt.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"reporte_plan_anual_{anio}_{mes:02d}_{timestamp}.pdf"
    generar_reporte_plan_anual_pdf(ejecuciones, anio, mes, nombre_archivo)

    return {"mensaje": "Reporte generado", "archivo": nombre_archivo,
            "url_descarga": f"/api/reportes/descargar/{nombre_archivo}"}
def _reemplazar_evidencia_ejecucion(id_ejecucion, archivo: UploadFile, formato_esperado, id_usuario):
    datos_nuevos = guardar_archivo(archivo, FORMATOS_EXTENSIONES[formato_esperado])

    with db_cursor() as cur:
        cur.execute("SELECT id_evidencia, ruta_archivo FROM plan_evidencias WHERE id_ejecucion=%s LIMIT 1", (id_ejecucion,))
        anterior = cur.fetchone()

    with db_cursor(commit=True) as cur:
        if anterior:
            cur.execute(
                """UPDATE plan_evidencias SET nombre_archivo=%s, nombre_original=%s, ruta_archivo=%s,
                     tipo_archivo=%s, tamano_bytes=%s, subido_por=%s, contenido_archivo=%s, fecha_subida=NOW()
                   WHERE id_evidencia=%s""",
                (datos_nuevos["nombre_archivo"], datos_nuevos["nombre_original"], datos_nuevos["ruta_archivo"],
                 datos_nuevos["tipo_archivo"], datos_nuevos["tamano_bytes"], id_usuario,
                 datos_nuevos["contenido_bytes"], anterior["id_evidencia"]),
            )
        else:
            cur.execute(
                """INSERT INTO plan_evidencias (id_ejecucion, nombre_archivo, nombre_original, ruta_archivo,
                     tipo_archivo, tamano_bytes, subido_por, contenido_archivo)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (id_ejecucion, datos_nuevos["nombre_archivo"], datos_nuevos["nombre_original"],
                 datos_nuevos["ruta_archivo"], datos_nuevos["tipo_archivo"], datos_nuevos["tamano_bytes"],
                 id_usuario, datos_nuevos["contenido_bytes"]),
            )

    if anterior:
        try:
            os.remove(anterior["ruta_archivo"])
        except OSError:
            pass

@router.put("/{id_ejecucion}")
def editar_ejecucion(
    id_ejecucion: int, fecha_ejecucion: Optional[str] = Form(None), observacion: Optional[str] = Form(None),
    archivo_evidencia: Optional[UploadFile] = File(None),
    usuario_actual: dict = Depends(requiere_permiso("editar")),
):
    with db_cursor() as cur:
        cur.execute(
            """SELECT e.*, pa.formato_evidencia FROM plan_ejecuciones e
               JOIN plan_actividades pa ON e.id_actividad = pa.id_actividad
               WHERE e.id_ejecucion = %s""",
            (id_ejecucion,),
        )
        anterior = cur.fetchone()
    if not anterior:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")

    if not es_admin_general(usuario_actual) and anterior["id_sede"] != sede_del_usuario_actual(usuario_actual):
        raise HTTPException(status_code=403, detail="No tiene permiso para editar ejecuciones de otra sede")

    if anterior["aprobado"]:
        raise HTTPException(status_code=409, detail="No se puede editar una ejecución ya aprobada")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE plan_ejecuciones SET
                 fecha_ejecucion=%s, observacion=%s, estado_revision='PENDIENTE', aprobado=FALSE,
                 rechazado=FALSE, motivo_rechazo=NULL, id_aprobador=NULL, fecha_aprobacion=NULL
               WHERE id_ejecucion=%s""",
            (
                fecha_ejecucion if fecha_ejecucion is not None else str(anterior["fecha_ejecucion"]),
                observacion if observacion is not None else anterior["observacion"],
                id_ejecucion,
            ),
        )

    if archivo_evidencia is not None:
        try:
            _reemplazar_evidencia_ejecucion(id_ejecucion, archivo_evidencia, anterior["formato_evidencia"],
                                             usuario_actual["id_usuario"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"mensaje": "Ejecución actualizada, vuelve a quedar pendiente de aprobación"}

@router.delete("/{id_ejecucion}")
def eliminar_ejecucion(id_ejecucion: int, usuario_actual: dict = Depends(requiere_permiso("editar"))):
    with db_cursor() as cur:
        cur.execute("SELECT id_sede, aprobado FROM plan_ejecuciones WHERE id_ejecucion = %s", (id_ejecucion,))
        ejecucion = cur.fetchone()
    if not ejecucion:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")

    if not es_admin_general(usuario_actual):
        if ejecucion["id_sede"] != sede_del_usuario_actual(usuario_actual):
            raise HTTPException(status_code=403, detail="No tiene permiso para eliminar ejecuciones de otra sede")
        if ejecucion["aprobado"]:
            raise HTTPException(status_code=409, detail="No se puede eliminar una ejecución ya aprobada")

    with db_cursor() as cur:
        cur.execute("SELECT ruta_archivo FROM plan_evidencias WHERE id_ejecucion = %s", (id_ejecucion,))
        evidencias = cur.fetchall()

    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM plan_evidencias WHERE id_ejecucion = %s", (id_ejecucion,))
        cur.execute("DELETE FROM plan_ejecuciones WHERE id_ejecucion = %s", (id_ejecucion,))

    for ev in evidencias:
        try:
            os.remove(ev["ruta_archivo"])
        except OSError:
            pass

    return {"mensaje": "Ejecución eliminada"}

@router.get("/evidencias/descargar/{id_evidencia}")
def descargar_evidencia_plan_anual(id_evidencia: int, usuario_actual: dict = Depends(token_requerido)):
    with db_cursor() as cur:
        cur.execute(
            """SELECT pe.*, e.id_sede FROM plan_evidencias pe
               JOIN plan_ejecuciones e ON pe.id_ejecucion = e.id_ejecucion
               WHERE pe.id_evidencia = %s""",
            (id_evidencia,),
        )
        ev = cur.fetchone()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    if not es_admin_general(usuario_actual) and ev["id_sede"] != sede_del_usuario_actual(usuario_actual):
        raise HTTPException(status_code=403, detail="No tiene acceso a evidencias de otra sede")

    if ev["contenido_archivo"]:
        return StreamingResponse(
            io.BytesIO(ev["contenido_archivo"]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{ev["nombre_original"]}"'},
        )
    return FileResponse(ev["ruta_archivo"], filename=ev["nombre_original"])