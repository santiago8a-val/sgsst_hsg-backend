import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from app.db import db_cursor
from app.auth import token_requerido, requiere_permiso, requiere_rol_admin, es_admin_general, sede_del_usuario_actual
from app.schemas import RechazarRegistroRequest
from app.services.email_services import enviar_correo_rechazo
from app.utils.archivos import guardar_archivo, FORMATOS_EXTENSIONES
from app.utils.auditoria import registrar_auditoria

router = APIRouter(prefix="/api/registros", tags=["registros"])


def calcular_periodos(fecha_str: str):
    fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
    mes = fecha.month
    trimestre = (mes - 1) // 3 + 1
    semestre = 1 if mes <= 6 else 2
    return mes, trimestre, semestre, fecha.year


def _reemplazar_evidencia_registro(id_registro, archivo: UploadFile, formato_esperado, id_usuario):
    """Reemplaza (UPDATE) el archivo de evidencia de un registro existente, o lo crea si no había."""
    datos_nuevos = guardar_archivo(archivo, FORMATOS_EXTENSIONES[formato_esperado])

    with db_cursor() as cur:
        cur.execute(
            "SELECT id_evidencia, ruta_archivo FROM evidencias WHERE id_registro=%s LIMIT 1",
            (id_registro,),
        )
        anterior = cur.fetchone()

    with db_cursor(commit=True) as cur:
        if anterior:
            cur.execute(
                """UPDATE evidencias SET
                     nombre_archivo=%s, nombre_original=%s, ruta_archivo=%s,
                     tipo_archivo=%s, tamano_bytes=%s, subido_por=%s,
                     contenido_archivo=%s, fecha_subida=NOW()
                   WHERE id_evidencia=%s""",
                (datos_nuevos["nombre_archivo"], datos_nuevos["nombre_original"],
                 datos_nuevos["ruta_archivo"], datos_nuevos["tipo_archivo"],
                 datos_nuevos["tamano_bytes"], id_usuario,
                 datos_nuevos["contenido_bytes"], anterior["id_evidencia"]),
            )
        else:
            cur.execute(
                """INSERT INTO evidencias
                   (id_registro, nombre_archivo, nombre_original, ruta_archivo,
                    tipo_archivo, tamano_bytes, subido_por, contenido_archivo)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (id_registro, datos_nuevos["nombre_archivo"], datos_nuevos["nombre_original"],
                 datos_nuevos["ruta_archivo"], datos_nuevos["tipo_archivo"],
                 datos_nuevos["tamano_bytes"], id_usuario, datos_nuevos["contenido_bytes"]),
            )

    if anterior:
        try:
            os.remove(anterior["ruta_archivo"])
        except OSError:
            pass


@router.get("")
def listar_registros(
    fase: Optional[str] = None, codigo_item: Optional[str] = None, estado: Optional[str] = None,
    responsable: Optional[int] = None, fecha_desde: Optional[str] = None, fecha_hasta: Optional[str] = None,
    anio: Optional[int] = None, mes: Optional[int] = None, trimestre: Optional[int] = None,
    semestre: Optional[int] = None, sede: Optional[int] = None,
    estado_aprobacion: Optional[str] = None,  # "PENDIENTE" | "APROBADO" | "RECHAZADO" | None = todos
    usuario_actual: dict = Depends(token_requerido),
):
    condiciones, params = ["1=1"], []
    if not es_admin_general(usuario_actual):
        condiciones.append("r.id_sede = %s"); params.append(sede_del_usuario_actual(usuario_actual))
    elif sede:
        condiciones.append("r.id_sede = %s"); params.append(sede)

    if fase: condiciones.append("fp.codigo_fase = %s"); params.append(fase)
    if codigo_item: condiciones.append("i.codigo_item = %s"); params.append(codigo_item)
    if estado: condiciones.append("r.estado_cumplimiento = %s"); params.append(estado)
    if responsable: condiciones.append("r.id_responsable = %s"); params.append(responsable)
    if fecha_desde: condiciones.append("r.fecha_registro >= %s"); params.append(fecha_desde)
    if fecha_hasta: condiciones.append("r.fecha_registro <= %s"); params.append(fecha_hasta)
    if anio: condiciones.append("r.periodo_anio = %s"); params.append(anio)
    if mes: condiciones.append("r.periodo_mes = %s"); params.append(mes)
    if trimestre: condiciones.append("r.periodo_trimestre = %s"); params.append(trimestre)
    if semestre: condiciones.append("r.periodo_semestre = %s"); params.append(semestre)

    if estado_aprobacion == "PENDIENTE":
        condiciones.append("r.aprobado = FALSE AND r.rechazado = FALSE")
    elif estado_aprobacion == "APROBADO":
        condiciones.append("r.aprobado = TRUE")
    elif estado_aprobacion == "RECHAZADO":
        condiciones.append("r.rechazado = TRUE")

    query = f"""
        SELECT r.id_registro, i.codigo_item, fp.nombre_fase, i.descripcion_item,
               r.estado_cumplimiento, r.puntaje_item, r.porcentaje_item, r.fecha_registro,
               r.periodo_mes, r.periodo_trimestre, r.periodo_semestre, r.periodo_anio,
               r.observacion, r.aprobado, r.rechazado, r.id_sede, s.nombre_sede,
               u.nombre_completo AS responsable
        FROM registros_cumplimiento r
        JOIN items_sgsst i ON r.id_item = i.id_item
        JOIN fases_phva fp ON i.id_fase = fp.id_fase
        JOIN usuarios u ON r.id_responsable = u.id_usuario
        JOIN sedes s ON r.id_sede = s.id_sede
        WHERE {' AND '.join(condiciones)}
        ORDER BY r.fecha_registro DESC
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()

@router.get("/pendientes")
def listar_pendientes(usuario_actual: dict = Depends(requiere_rol_admin)):
    """Solo el administrador general puede ver los registros en espera de autenticación."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT r.id_registro, i.codigo_item, fp.nombre_fase, i.descripcion_item,
                      r.estado_cumplimiento, r.porcentaje_item, r.fecha_registro,
                      u.nombre_completo AS responsable
               FROM registros_cumplimiento r
               JOIN items_sgsst i ON r.id_item = i.id_item
               JOIN fases_phva fp ON i.id_fase = fp.id_fase
               JOIN usuarios u ON r.id_responsable = u.id_usuario
               WHERE r.aprobado = FALSE AND r.rechazado = FALSE
               ORDER BY r.fecha_creacion DESC"""
        )
        pendientes = cur.fetchall()
        for registro in pendientes:
            cur.execute(
                "SELECT id_evidencia, nombre_original, tipo_archivo FROM evidencias WHERE id_registro = %s",
                (registro["id_registro"],),
            )
            registro["evidencia"] = cur.fetchone()
    return pendientes


@router.get("/{id_registro}")
def obtener_registro(id_registro: int, usuario_actual: dict = Depends(token_requerido)):
    with db_cursor() as cur:
        cur.execute(
            """SELECT r.*, i.codigo_item, i.descripcion_item, u.nombre_completo AS responsable
               FROM registros_cumplimiento r
               JOIN items_sgsst i ON r.id_item = i.id_item
               JOIN usuarios u ON r.id_responsable = u.id_usuario
               WHERE r.id_registro = %s""",
            (id_registro,),
        )
        registro = cur.fetchone()
        if not registro:
            raise HTTPException(status_code=404, detail="Registro no encontrado")
        if not es_admin_general(usuario_actual) and registro["id_sede"] != sede_del_usuario_actual(usuario_actual):
            raise HTTPException(status_code=403, detail="No tiene acceso a registros de otra sede")

        # Se excluye contenido_archivo (LONGBLOB) del listado: son bytes crudos y
        # no se pueden convertir a JSON; solo se usan en el endpoint de descarga.
        cur.execute(
            """SELECT id_evidencia, id_registro, nombre_archivo, nombre_original,
                      tipo_archivo, tamano_bytes, subido_por, fecha_subida
               FROM evidencias WHERE id_registro = %s""",
            (id_registro,),
        )
        registro["evidencias"] = cur.fetchall()

        cur.execute(
            """SELECT o.*, u.nombre_completo FROM observaciones o
               JOIN usuarios u ON o.id_usuario = u.id_usuario
               WHERE id_registro = %s ORDER BY fecha_observacion DESC""",
            (id_registro,),
        )
        registro["historial_observaciones"] = cur.fetchall()

    return registro


@router.post("", status_code=201)
def crear_registro(
    id_item: int = Form(...), id_responsable: int = Form(...), estado_cumplimiento: str = Form(...),
    fecha_registro: str = Form(...), observacion: Optional[str] = Form(None),
    id_sede: Optional[int] = Form(None), archivo_evidencia: UploadFile = File(...),
    usuario_actual: dict = Depends(requiere_permiso("crear")),
):
    """
    Recibe multipart/form-data. El archivo de evidencia es OBLIGATORIO y su
    formato permitido (PDF, Word, Excel o Imagen) lo determina el ítem
    seleccionado (items_sgsst.formato_evidencia). Queda con aprobado=FALSE
    (pendiente de autenticación) hasta que el administrador general lo apruebe.
    """
    if estado_cumplimiento not in ("CUMPLE", "PARCIAL", "NO_CUMPLE"):
        raise HTTPException(status_code=400, detail="estado_cumplimiento inválido")

    sede_final = sede_del_usuario_actual(usuario_actual)
    if not sede_final:
        if not id_sede:
            raise HTTPException(status_code=400, detail="id_sede es obligatorio")
        sede_final = id_sede

    with db_cursor() as cur:
        cur.execute("SELECT formato_evidencia FROM items_sgsst WHERE id_item = %s", (id_item,))
        item = cur.fetchone()
    if not item:
        raise HTTPException(status_code=400, detail="El ítem seleccionado no existe")

    formato_esperado = item["formato_evidencia"]
    try:
        datos_archivo = guardar_archivo(archivo_evidencia, FORMATOS_EXTENSIONES[formato_esperado])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"El archivo no es válido (se espera {formato_esperado}): {e}")

    mes, trimestre, semestre, anio = calcular_periodos(fecha_registro)

    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO registros_cumplimiento
               (id_item, id_responsable, id_sede, estado_cumplimiento,
                fecha_registro, periodo_mes, periodo_trimestre, periodo_semestre,
                periodo_anio, observacion)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (id_item, id_responsable, sede_final, estado_cumplimiento, fecha_registro,
             mes, trimestre, semestre, anio, observacion),
        )
        nuevo_id = cur.lastrowid

        cur.execute(
            """INSERT INTO evidencias
               (id_registro, nombre_archivo, nombre_original, ruta_archivo,
                tipo_archivo, tamano_bytes, subido_por, contenido_archivo)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (nuevo_id, datos_archivo["nombre_archivo"], datos_archivo["nombre_original"],
             datos_archivo["ruta_archivo"], datos_archivo["tipo_archivo"],
             datos_archivo["tamano_bytes"], usuario_actual["id_usuario"], datos_archivo["contenido_bytes"]),
        )

    registrar_auditoria("registros_cumplimiento", nuevo_id, "CREAR", usuario_actual["id_usuario"],
                         nuevos={"estado_cumplimiento": estado_cumplimiento, "formato": formato_esperado})
    return {"mensaje": "Registro creado, pendiente de autenticación", "id_registro": nuevo_id}


@router.put("/{id_registro}")
def editar_registro(id_registro: int, id_item: Optional[int] = Form(None),
                     estado_cumplimiento: Optional[str] = Form(None),
                     fecha_registro: Optional[str] = Form(None), observacion: Optional[str] = Form(None),
                     archivo_evidencia: Optional[UploadFile] = File(None),
                     usuario_actual: dict = Depends(requiere_permiso("editar"))):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM registros_cumplimiento WHERE id_registro = %s", (id_registro,))
        anterior = cur.fetchone()
    if not anterior:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    # El chequeo de sede va ANTES de escribir nada
    if not es_admin_general(usuario_actual) and anterior["id_sede"] != sede_del_usuario_actual(usuario_actual):
        raise HTTPException(status_code=403, detail="No tiene permiso para modificar registros de otra sede")

    fecha_final = fecha_registro or str(anterior["fecha_registro"])
    mes, trimestre, semestre, anio = calcular_periodos(fecha_final)
    estado_final = estado_cumplimiento or anterior["estado_cumplimiento"]
    if estado_final not in ("CUMPLE", "PARCIAL", "NO_CUMPLE"):
        raise HTTPException(status_code=400, detail="estado_cumplimiento inválido")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE registros_cumplimiento SET
                 estado_cumplimiento=%s, fecha_registro=%s,
                 periodo_mes=%s, periodo_trimestre=%s, periodo_semestre=%s, periodo_anio=%s,
                 observacion=%s
               WHERE id_registro=%s""",
            (estado_final, fecha_final, mes, trimestre, semestre, anio,
             observacion if observacion is not None else anterior["observacion"], id_registro),
        )

    if archivo_evidencia is not None:
        with db_cursor() as cur:
            cur.execute("SELECT formato_evidencia FROM items_sgsst WHERE id_item = %s",
                        (id_item if id_item is not None else anterior["id_item"],))
            item = cur.fetchone()
        try:
            _reemplazar_evidencia_registro(id_registro, archivo_evidencia, item["formato_evidencia"],
                                            usuario_actual["id_usuario"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    registrar_auditoria("registros_cumplimiento", id_registro, "EDITAR", usuario_actual["id_usuario"], anterior)
    return {"mensaje": "Registro actualizado"}


@router.delete("/{id_registro}")
def eliminar_registro(id_registro: int, usuario_actual: dict = Depends(requiere_permiso("eliminar"))):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM registros_cumplimiento WHERE id_registro = %s", (id_registro,))
        anterior = cur.fetchone()
    if not anterior:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    # El chequeo de sede va ANTES de borrar
    if not es_admin_general(usuario_actual) and anterior["id_sede"] != sede_del_usuario_actual(usuario_actual):
        raise HTTPException(status_code=403, detail="No tiene permiso para modificar registros de otra sede")

    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM registros_cumplimiento WHERE id_registro = %s", (id_registro,))

    registrar_auditoria("registros_cumplimiento", id_registro, "ELIMINAR", usuario_actual["id_usuario"], anterior)
    return {"mensaje": "Registro eliminado"}


@router.post("/{id_registro}/aprobar")
def aprobar_registro(id_registro: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE registros_cumplimiento
               SET aprobado = TRUE, rechazado = FALSE, id_aprobador = %s, fecha_aprobacion = NOW()
               WHERE id_registro = %s""",
            (usuario_actual["id_usuario"], id_registro),
        )
    registrar_auditoria("registros_cumplimiento", id_registro, "APROBAR", usuario_actual["id_usuario"])
    return {"mensaje": "Registro aprobado"}


@router.post("/{id_registro}/rechazar")
def rechazar_registro(id_registro: int, data: RechazarRegistroRequest,
                       usuario_actual: dict = Depends(requiere_rol_admin)):
    motivo = data.motivo.strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Debe indicar el motivo del rechazo")

    with db_cursor() as cur:
        cur.execute(
            """SELECT r.id_sede, i.codigo_item, i.descripcion_item
               FROM registros_cumplimiento r
               JOIN items_sgsst i ON r.id_item = i.id_item
               WHERE r.id_registro = %s""",
            (id_registro,),
        )
        registro = cur.fetchone()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE registros_cumplimiento
               SET rechazado = TRUE, motivo_rechazo = %s, aprobado = FALSE
               WHERE id_registro = %s""",
            (motivo, id_registro),
        )
        cur.execute(
            """SELECT u.correo, u.nombre_completo FROM usuarios u
               JOIN roles r ON u.id_rol = r.id_rol
               WHERE r.nombre_rol = 'ADMIN_SEDE' AND u.id_sede = %s AND u.activo = TRUE""",
            (registro["id_sede"],),
        )
        admins_sede = cur.fetchall()

    for admin in admins_sede:
        try:
            enviar_correo_rechazo(admin["correo"], admin["nombre_completo"],
                                   registro["codigo_item"], registro["descripcion_item"], motivo)
        except Exception:
            pass

    registrar_auditoria("registros_cumplimiento", id_registro, "EDITAR", usuario_actual["id_usuario"],
                         nuevos={"rechazado": True, "motivo": motivo})
    return {"mensaje": "Registro rechazado, se notificó al administrador de la sede"}
