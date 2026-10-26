from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db import db_cursor
from app.auth import token_requerido, requiere_rol_admin, correo_existe
from app.schemas import SedeCreate, SedeUpdate
from app.services.email_services import enviar_correo_cuenta_reubicada

router = APIRouter(prefix="/api/sedes", tags=["sedes"])


@router.get("")
def listar_sedes(usuario_actual: dict = Depends(token_requerido)):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id_sede, nombre_sede, ciudad, direccion FROM sedes WHERE activa = TRUE ORDER BY nombre_sede"
        )
        return cur.fetchall()


@router.get("/publicas")
def listar_sedes_publicas():
    """Sin token: la usa el formulario de registro, antes de que exista sesión."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT id_sede, nombre_sede, ciudad FROM sedes WHERE activa = TRUE ORDER BY nombre_sede"
        )
        return cur.fetchall()


@router.post("", status_code=201)
def crear_sede(data: SedeCreate, usuario_actual: dict = Depends(requiere_rol_admin)):
    nombre_sede = data.nombre_sede.strip()
    if not nombre_sede:
        raise HTTPException(status_code=400, detail="El nombre de la sede es obligatorio")

    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO sedes (nombre_sede, ciudad, direccion, creada_por) VALUES (%s, %s, %s, %s)",
            (nombre_sede, (data.ciudad or "").strip(), (data.direccion or "").strip(),
             usuario_actual["id_usuario"]),
        )
        id_sede = cur.lastrowid

    return {"id_sede": id_sede, "mensaje": "Sede creada"}

@router.put("/{id_sede}")
def editar_sede(id_sede: int, data: SedeUpdate, usuario_actual: dict = Depends(requiere_rol_admin)):
    nombre_sede = data.nombre_sede.strip()
    if not nombre_sede:
        raise HTTPException(status_code=400, detail="El nombre de la sede es obligatorio")

    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE sedes SET nombre_sede = %s, ciudad = %s, direccion = %s WHERE id_sede = %s",
            (nombre_sede, (data.ciudad or "").strip(), (data.direccion or "").strip(), id_sede),
        )
    return {"mensaje": "Sede actualizada"}


@router.delete("/{id_sede}")
def eliminar_sede(id_sede: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT id_sede FROM sedes WHERE id_sede = %s", (id_sede,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Sede no encontrada")

        cur.execute("SELECT COUNT(*) AS total FROM usuarios WHERE id_sede = %s", (id_sede,))
        usuarios_en_uso = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM registros_cumplimiento WHERE id_sede = %s", (id_sede,))
        registros_en_uso = cur.fetchone()["total"]

        if usuarios_en_uso > 0 or registros_en_uso > 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "mensaje": f"No se puede eliminar: {usuarios_en_uso} usuario(s) y {registros_en_uso} registro(s) "
                            f"de actividad pertenecen a esta sede.",
                    "usuarios_en_uso": usuarios_en_uso,
                    "registros_en_uso": registros_en_uso,
                },
            )
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM sedes WHERE id_sede = %s", (id_sede,))

    return {"mensaje": "Sede eliminada permanentemente"}

@router.get("/{id_sede}/usuarios")
def listar_usuarios_de_sede(id_sede: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    """Lista los usuarios asignados a una sede, para poder reubicarlos antes de eliminarla."""
    with db_cursor() as cur:
        cur.execute("SELECT id_sede FROM sedes WHERE id_sede = %s", (id_sede,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Sede no encontrada")

        cur.execute(
            """SELECT u.id_usuario, u.nombre_completo, u.usuario, u.correo, r.nombre_rol
               FROM usuarios u
               JOIN roles r ON u.id_rol = r.id_rol
               WHERE u.id_sede = %s
               ORDER BY u.nombre_completo""",
            (id_sede,),
        )
        return cur.fetchall()


class MoverUsuarioRequest(BaseModel):
    id_usuario: int
    id_sede_destino: int
    correo: str = None  # Opcional, para enviar correo de notificación si se desea
    nombre_completo: str = None  # Opcional, para enviar correo de notificación si se desea

@router.post("/mover-usuario")
def mover_usuario_de_sede(data: MoverUsuarioRequest, usuario_actual: dict = Depends(requiere_rol_admin)):
    """Reasigna un usuario a otra sede (por ejemplo, antes de eliminar su sede actual)."""
    with db_cursor() as cur:
        cur.execute("SELECT id_usuario, nombre_completo, correo, id_sede FROM usuarios WHERE id_usuario = %s",
                     (data.id_usuario,))
        usuario = cur.fetchone()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    with db_cursor() as cur:
        cur.execute("SELECT id_sede, nombre_sede FROM sedes WHERE id_sede = %s AND activa = TRUE",
                     (data.id_sede_destino,))
        sede_destino = cur.fetchone()
    if not sede_destino:
        raise HTTPException(status_code=400, detail="La sede de destino no existe o no está activa")

    if usuario["id_sede"] == data.id_sede_destino:
        raise HTTPException(status_code=400, detail="El usuario ya pertenece a esa sede")

    # nombre de la sede de origen ANTES del UPDATE, si no tenía sede asignada aún
    nombre_sede_origen = "Sin sede asignada"
    if usuario["id_sede"]:
        with db_cursor() as cur:
            cur.execute("SELECT nombre_sede FROM sedes WHERE id_sede = %s", (usuario["id_sede"],))
            fila_origen = cur.fetchone()
        if fila_origen:
            nombre_sede_origen = fila_origen["nombre_sede"]

    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE usuarios SET id_sede = %s WHERE id_usuario = %s",
                     (data.id_sede_destino, data.id_usuario))
    try:
        enviar_correo_cuenta_reubicada(usuario["correo"], usuario["nombre_completo"],
                                        nombre_sede_origen, sede_destino["nombre_sede"])
    except Exception as e:
        # No interrumpir la operación si falla el envío de correo, pero registrar el error.
        print(f"Error al enviar correo de reubicación: {e}")

    return {"mensaje": f"{usuario['nombre_completo']} fue movido a {sede_destino['nombre_sede']}"}