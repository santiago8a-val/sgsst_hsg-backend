import os
import io
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from app.db import db_cursor
from app.auth import token_requerido, requiere_permiso, es_admin_general, sede_del_usuario_actual
from app.utils.archivos import guardar_archivo, EXTENSIONES_IMAGENES
from app.utils.auditoria import registrar_auditoria

router = APIRouter(prefix="/api/evidencias", tags=["evidencias"])


def _sede_del_registro(id_registro):
    with db_cursor() as cur:
        cur.execute("SELECT id_sede FROM registros_cumplimiento WHERE id_registro = %s", (id_registro,))
        fila = cur.fetchone()
    return fila["id_sede"] if fila else None


@router.post("/{id_registro}", status_code=201)
def subir_evidencia(id_registro: int, archivo: UploadFile = File(...),
                     usuario_actual: dict = Depends(requiere_permiso("crear"))):
    """Sube una evidencia adicional (aparte de la principal) a un registro ya existente."""
    id_sede_registro = _sede_del_registro(id_registro)
    if id_sede_registro is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if not es_admin_general(usuario_actual) and id_sede_registro != sede_del_usuario_actual(usuario_actual):
        raise HTTPException(status_code=403, detail="No tiene acceso a registros de otra sede")

    try:
        datos = guardar_archivo(archivo, EXTENSIONES_IMAGENES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO evidencias
               (id_registro, nombre_archivo, nombre_original, ruta_archivo,
                tipo_archivo, tamano_bytes, subido_por, contenido_archivo)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (id_registro, datos["nombre_archivo"], datos["nombre_original"],
             datos["ruta_archivo"], datos["tipo_archivo"], datos["tamano_bytes"],
             usuario_actual["id_usuario"], datos["contenido_bytes"]),
        )
        id_evidencia = cur.lastrowid

    registrar_auditoria("evidencias", id_evidencia, "CREAR", usuario_actual["id_usuario"],
                         nuevos={"archivo": datos["nombre_original"]})
    return {"mensaje": "Evidencia subida", "id_evidencia": id_evidencia}


@router.put("/{id_evidencia}")
def editar_evidencia(id_evidencia: int, archivo: UploadFile = File(...),
                      usuario_actual: dict = Depends(requiere_permiso("editar"))):
    """
    Reemplaza el archivo de una evidencia existente, conservando su mismo
    id_evidencia (actualiza la fila con UPDATE, no borra y crea una nueva).
    """
    with db_cursor() as cur:
        cur.execute(
            """SELECT e.*, r.id_sede FROM evidencias e
               JOIN registros_cumplimiento r ON e.id_registro = r.id_registro
               WHERE e.id_evidencia = %s""",
            (id_evidencia,),
        )
        ev = cur.fetchone()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    if not es_admin_general(usuario_actual) and ev["id_sede"] != sede_del_usuario_actual(usuario_actual):
        raise HTTPException(status_code=403, detail="No tiene permiso para editar evidencias de otra sede")

    try:
        datos_nuevos = guardar_archivo(archivo, EXTENSIONES_IMAGENES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE evidencias SET
                 nombre_archivo=%s, nombre_original=%s, ruta_archivo=%s,
                 tipo_archivo=%s, tamano_bytes=%s, subido_por=%s,
                 contenido_archivo=%s, fecha_subida=NOW()
               WHERE id_evidencia=%s""",
            (datos_nuevos["nombre_archivo"], datos_nuevos["nombre_original"],
             datos_nuevos["ruta_archivo"], datos_nuevos["tipo_archivo"],
             datos_nuevos["tamano_bytes"], usuario_actual["id_usuario"],
             datos_nuevos["contenido_bytes"], id_evidencia),
        )

    try:
        os.remove(ev["ruta_archivo"])
    except OSError:
        pass

    registrar_auditoria("evidencias", id_evidencia, "EDITAR", usuario_actual["id_usuario"],
                         anteriores={"archivo": ev["nombre_original"]},
                         nuevos={"archivo": datos_nuevos["nombre_original"]})
    return {"mensaje": "Evidencia actualizada"}


@router.get("/descargar/{id_evidencia}")
def descargar_evidencia(id_evidencia: int, usuario_actual: dict = Depends(token_requerido)):
    """
    Extrae el archivo directamente desde la base de datos. El administrador general
    puede descargar evidencias de cualquier sede; los demás roles, solo las de su
    propia sede.
    """
    with db_cursor() as cur:
        cur.execute(
            """SELECT e.*, r.id_sede FROM evidencias e
               JOIN registros_cumplimiento r ON e.id_registro = r.id_registro
               WHERE e.id_evidencia = %s""",
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


@router.delete("/{id_evidencia}")
def eliminar_evidencia(id_evidencia: int, usuario_actual: dict = Depends(requiere_permiso("eliminar"))):
    with db_cursor() as cur:
        cur.execute(
            """SELECT e.*, r.id_sede FROM evidencias e
               JOIN registros_cumplimiento r ON e.id_registro = r.id_registro
               WHERE e.id_evidencia = %s""",
            (id_evidencia,),
        )
        ev = cur.fetchone()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    if not es_admin_general(usuario_actual) and ev["id_sede"] != sede_del_usuario_actual(usuario_actual):
        raise HTTPException(status_code=403, detail="No tiene permiso para eliminar evidencias de otra sede")

    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM evidencias WHERE id_evidencia = %s", (id_evidencia,))
    try:
        os.remove(ev["ruta_archivo"])
    except OSError:
        pass

    registrar_auditoria("evidencias", id_evidencia, "ELIMINAR", usuario_actual["id_usuario"], ev)
    return {"mensaje": "Evidencia eliminada"}
