from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import date
from app.auth import token_requerido, requiere_permiso, requiere_rol_admin, es_admin_general, sede_del_usuario_actual
from app.db import db_cursor
from app.auth import token_requerido, requiere_permiso, requiere_rol_admin
from app.schemas import ItemCreate, ItemUpdate
from app.utils.auditoria import registrar_auditoria
from app.services.consolidado_service import calcular_cumplimiento_items_todas_las_sedes
router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("")
def listar_items(fase: Optional[str] = None, activo: Optional[str] = None, busca: Optional[str] = None,
                  usuario_actual: dict = Depends(token_requerido)):
    condiciones, params = ["1=1"], []
    if fase:
        condiciones.append("f.codigo_fase = %s"); params.append(fase)
    if activo is not None:
        condiciones.append("i.activo = %s"); params.append(activo)
    if busca:
        condiciones.append("(i.codigo_item LIKE %s OR i.descripcion_item LIKE %s)")
        params.extend([f"%{busca}%", f"%{busca}%"])

    query = f"""
        SELECT i.id_item, i.codigo_item, f.codigo_fase, f.nombre_fase,
               i.descripcion_item, i.evidencia_requerida, i.recursos_necesarios,
               i.peso_porcentual, i.activo, i.formato_evidencia
        FROM items_sgsst i
        JOIN fases_phva f ON i.id_fase = f.id_fase
        WHERE {' AND '.join(condiciones)}
        ORDER BY f.orden, i.codigo_item
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()

@router.get("/cumplimiento-sedes")
def ver_cumplimiento_items_sedes(anio: int, mes: int, solo_incumplidas: bool = False,
                                  usuario_actual: dict = Depends(requiere_rol_admin)):
    return calcular_cumplimiento_items_todas_las_sedes(anio, mes, solo_incumplidas)
@router.get("/pendientes")
def listar_items_pendientes(
    anio: Optional[int] = None, mes: Optional[int] = None, sede: Optional[int] = None,
    usuario_actual: dict = Depends(token_requerido),
):
    """
    Ítems activos que NO cuentan como cumplidos este periodo, usando el MISMO
    criterio que el consolidado (calcular_cumplimiento_items_sede_mes):
    cumplido = existe un registro con aprobado=TRUE y estado_cumplimiento='CUMPLE'.
    Cualquier otro caso (sin registro, PARCIAL, NO_CUMPLE, pendiente de aprobar
    o rechazado) se considera pendiente. Si el ítem ya tiene un registro (aunque
    no cumpla el criterio), se devuelve su id para poder editarlo en vez de
    crear uno duplicado.
    """
    hoy = date.today()
    anio_final = anio or hoy.year
    mes_final = mes or hoy.month

    if es_admin_general(usuario_actual):
        if not sede:
            raise HTTPException(status_code=400, detail="Debe indicar la sede para consultar pendientes")
        sede_final = sede
    else:
        sede_final = sede_del_usuario_actual(usuario_actual)
        if not sede_final:
            raise HTTPException(status_code=400, detail="Su usuario no tiene una sede asignada")

    with db_cursor() as cur:
        cur.execute(
            """SELECT i.id_item, i.codigo_item, i.descripcion_item,
                      f.nombre_fase, f.codigo_fase, i.formato_evidencia,
                      r.id_registro AS id_registro_existente,
                      r.estado_cumplimiento AS estado_actual,
                      r.aprobado AS aprobado_actual,
                      r.rechazado AS rechazado_actual
               FROM items_sgsst i
               JOIN fases_phva f ON i.id_fase = f.id_fase
               LEFT JOIN (
                   SELECT rc1.*
                   FROM registros_cumplimiento rc1
                   JOIN (
                       SELECT id_item, MAX(id_registro) AS max_id
                       FROM registros_cumplimiento
                       WHERE id_sede = %s AND periodo_anio = %s AND periodo_mes = %s
                       GROUP BY id_item
                   ) ultimo ON ultimo.id_item = rc1.id_item AND ultimo.max_id = rc1.id_registro
               ) r ON r.id_item = i.id_item
               WHERE i.activo = TRUE
               AND i.id_item NOT IN (
                   SELECT id_item FROM registros_cumplimiento
                   WHERE id_sede = %s AND periodo_anio = %s AND periodo_mes = %s
                         AND aprobado = TRUE AND estado_cumplimiento = 'CUMPLE'
               )
               ORDER BY f.orden, i.codigo_item""",
            (sede_final, anio_final, mes_final, sede_final, anio_final, mes_final),
        )
        return cur.fetchall()
            
@router.get("/{id_item}")
def obtener_item(id_item: int, usuario_actual: dict = Depends(token_requerido)):
    with db_cursor() as cur:
        cur.execute(
            """SELECT i.*, f.codigo_fase, f.nombre_fase FROM items_sgsst i
               JOIN fases_phva f ON i.id_fase = f.id_fase WHERE i.id_item = %s""",
            (id_item,),
        )
        item = cur.fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    return item


@router.post("", status_code=201)
def crear_item(data: ItemCreate, usuario_actual: dict = Depends(requiere_permiso("crear"))):
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO items_sgsst
               (codigo_item, id_fase, descripcion_item, evidencia_requerida,
                recursos_necesarios, peso_porcentual)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (data.codigo_item, data.id_fase, data.descripcion_item, data.evidencia_requerida,
             data.recursos_necesarios, data.peso_porcentual),
        )
        nuevo_id = cur.lastrowid

    registrar_auditoria("items_sgsst", nuevo_id, "CREAR", usuario_actual["id_usuario"], nuevos=data.dict())
    return {"mensaje": "Item creado", "id_item": nuevo_id}



@router.put("/{id_item}")
def editar_item(id_item: int, data: ItemUpdate, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM items_sgsst WHERE id_item = %s", (id_item,))
        anterior = cur.fetchone()
    if not anterior:
        raise HTTPException(status_code=404, detail="Item no encontrado")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE items_sgsst SET
                 codigo_item = %s, id_fase = %s, descripcion_item = %s,
                 evidencia_requerida = %s, recursos_necesarios = %s,
                 peso_porcentual = %s, activo = %s
               WHERE id_item = %s""",
            (
                data.codigo_item if data.codigo_item is not None else anterior["codigo_item"],
                data.id_fase if data.id_fase is not None else anterior["id_fase"],
                data.descripcion_item if data.descripcion_item is not None else anterior["descripcion_item"],
                data.evidencia_requerida if data.evidencia_requerida is not None else anterior["evidencia_requerida"],
                data.recursos_necesarios if data.recursos_necesarios is not None else anterior["recursos_necesarios"],
                data.peso_porcentual if data.peso_porcentual is not None else anterior["peso_porcentual"],
                data.activo if data.activo is not None else anterior["activo"],
                id_item,
            ),
        )

    registrar_auditoria("items_sgsst", id_item, "EDITAR", usuario_actual["id_usuario"], anterior, data.dict())
    return {"mensaje": "Item actualizado"}


@router.delete("/{id_item}")
def eliminar_item(id_item: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM items_sgsst WHERE id_item = %s", (id_item,))
        anterior = cur.fetchone()
    if not anterior:
        raise HTTPException(status_code=404, detail="Item no encontrado")

    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS total FROM registros_cumplimiento WHERE id_item = %s",
            (id_item,),
        )
        en_uso = cur.fetchone()["total"]

    if en_uso > 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar: hay {en_uso} registro(s) de actividad que usan este ítem."
        )

    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM items_sgsst WHERE id_item = %s", (id_item,))

    registrar_auditoria("items_sgsst", id_item, "ELIMINAR", usuario_actual["id_usuario"], anterior)
    return {"mensaje": "Item eliminado permanentemente"}