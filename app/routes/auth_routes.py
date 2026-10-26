from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from app.db import db_cursor
from app.auth import (
    login,
    correo_existe,
    generar_codigo_recuperacion,
    validar_codigo_recuperacion,
    restablecer_password,
    registrar_usuario,
    listar_usuarios_pendientes,
    listar_roles_publicos,
    listar_roles,
    token_requerido,
    requiere_rol_admin,
)
from app.schemas import (
    LoginRequest, RegistroCuentaRequest, ResolverPendienteRequest,
    SolicitarCodigoRequest, VerificarCodigoRequest, RestablecerRequest,
)
from app.services.email_services import enviar_correo_recuperacion, enviar_correo_cambios_usuario
from typing import Optional
from app.auth import crear_usuario_por_admin
from app.services.email_services import enviar_correo_credenciales
class CrearUsuarioRequest(BaseModel):
    nombre_completo: str
    correo: str
    usuario: str
    id_rol: int
    id_sede: Optional[int] = None
    cargo: Optional[str] = None


class EditarUsuarioRequest(BaseModel):
    nombre_completo: Optional[str] = None
    correo: Optional[str] = None
    cargo: Optional[str] = None
    id_rol: Optional[int] = None
    id_sede: Optional[int] = None
    activo: Optional[bool] = None

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def ruta_login(data: LoginRequest):
    usuario = data.usuario.strip()
    password = data.password.strip()

    token, datos = login(usuario, password)
    if not token:
        if datos and "error" in datos:
            raise HTTPException(status_code=403, detail=datos["error"])
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    return {
        "token": token,
        "usuario": {
            "id_usuario": datos["id_usuario"],
            "nombre_completo": datos["nombre_completo"],
            "rol": datos["nombre_rol"],
        },
    }


@router.get("/roles-publicos")
def ruta_roles_publicos():
    return listar_roles_publicos()


@router.get("/roles")
def ruta_roles(usuario_actual: dict = Depends(requiere_rol_admin)):
    return listar_roles()


@router.post("/recuperacion/solicitar-codigo")
def solicitar_codigo(data: SolicitarCodigoRequest):
    correo = data.correo.strip().lower()
    usuario = correo_existe(correo)
    if not usuario:
        raise HTTPException(status_code=404, detail="El correo no está registrado en el sistema")

    codigo = generar_codigo_recuperacion(usuario["id_usuario"])
    try:
        enviar_correo_recuperacion(correo, usuario["nombre_completo"], codigo)
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo enviar el correo. Intente de nuevo más tarde")

    return {"mensaje": "Código enviado al correo registrado"}


@router.post("/recuperacion/verificar-codigo")
def verificar_codigo(data: VerificarCodigoRequest):
    registro = validar_codigo_recuperacion(data.correo.strip().lower(), data.codigo.strip())
    if not registro:
        raise HTTPException(status_code=400, detail="Código inválido o expirado")
    return {"mensaje": "Código válido"}


@router.post("/recuperacion/restablecer")
def restablecer(data: RestablecerRequest):
    if len(data.nueva_password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")

    exito = restablecer_password(data.correo.strip().lower(), data.codigo.strip(), data.nueva_password)
    if not exito:
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    return {"mensaje": "Contraseña actualizada correctamente"}

@router.post("/crear-usuario", status_code=201)
def crear_usuario_admin(data: CrearUsuarioRequest, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT nombre_rol FROM roles WHERE id_rol = %s", (data.id_rol,))
        rol = cur.fetchone()
    if not rol:
        raise HTTPException(status_code=400, detail="Rol inválido")

    if rol["nombre_rol"] != "ADMIN" and not data.id_sede:
        raise HTTPException(status_code=400, detail="Debe asignar una sede para este rol")

    nombre_sede = None
    if data.id_sede:
        with db_cursor() as cur:
            cur.execute("SELECT nombre_sede FROM sedes WHERE id_sede = %s AND activa = TRUE", (data.id_sede,))
            fila_sede = cur.fetchone()
        if not fila_sede:
            raise HTTPException(status_code=400, detail="Sede inválida o inactiva")
        nombre_sede = fila_sede["nombre_sede"]

    id_usuario, password_generada, error = crear_usuario_por_admin(
        data.nombre_completo.strip(), data.correo.strip().lower(), data.usuario.strip(),
        data.id_rol, data.id_sede, data.cargo,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)

    try:
        enviar_correo_credenciales(data.correo.strip().lower(), data.nombre_completo, data.usuario,
                                    password_generada, rol["nombre_rol"], nombre_sede)
    except Exception:
        raise HTTPException(status_code=500, detail="Usuario creado, pero no se pudo enviar el correo con las credenciales")

    return {"mensaje": "Usuario creado. Sus credenciales fueron enviadas por correo.", "id_usuario": id_usuario}


@router.get("/usuarios")
def listar_usuarios(sede: Optional[int] = None, activo: Optional[bool] = None,
                     usuario_actual: dict = Depends(requiere_rol_admin)):
    condiciones, params = ["1=1"], []
    if sede:
        condiciones.append("u.id_sede = %s"); params.append(sede)
    if activo is not None:
        condiciones.append("u.activo = %s"); params.append(activo)

    query = f"""
        SELECT u.id_usuario, u.nombre_completo, u.correo, u.usuario, u.cargo, u.activo,
               r.nombre_rol, u.id_rol, s.nombre_sede, u.id_sede, u.fecha_creacion, u.ultimo_acceso
        FROM usuarios u
        JOIN roles r ON u.id_rol = r.id_rol
        LEFT JOIN sedes s ON u.id_sede = s.id_sede
        WHERE {' AND '.join(condiciones)}
        ORDER BY u.nombre_completo
    """
    with db_cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


@router.get("/usuarios/{id_usuario}")
def obtener_usuario(id_usuario: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute(
            """SELECT u.id_usuario, u.nombre_completo, u.correo, u.usuario, u.cargo, u.activo,
                      r.nombre_rol, u.id_rol, s.nombre_sede, u.id_sede
               FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol
               LEFT JOIN sedes s ON u.id_sede = s.id_sede
               WHERE u.id_usuario = %s""",
            (id_usuario,),
        )
        usuario = cur.fetchone()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario

def _nombre_rol(cur, id_rol):
    if id_rol is None:
        return "N/A"
    cur.execute("SELECT nombre_rol FROM roles WHERE id_rol = %s", (id_rol,))
    fila = cur.fetchone()
    return fila["nombre_rol"] if fila else "N/A"


def _nombre_sede(cur, id_sede):
    if id_sede is None:
        return "N/A"
    cur.execute("SELECT nombre_sede FROM sedes WHERE id_sede = %s", (id_sede,))
    fila = cur.fetchone()
    return fila["nombre_sede"] if fila else "N/A"

@router.put("/usuarios/{id_usuario}")
def editar_usuario(id_usuario: int, data: EditarUsuarioRequest, usuario_actual: dict = Depends(requiere_rol_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        anterior = cur.fetchone()
    if not anterior:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    nuevo_nombre = data.nombre_completo if data.nombre_completo is not None else anterior["nombre_completo"]
    nuevo_correo = data.correo if data.correo is not None else anterior["correo"]
    nuevo_cargo = data.cargo if data.cargo is not None else anterior["cargo"]
    nuevo_id_rol = data.id_rol if data.id_rol is not None else anterior["id_rol"]
    nuevo_id_sede = data.id_sede if data.id_sede is not None else anterior["id_sede"]
    nuevo_activo = data.activo if data.activo is not None else anterior["activo"]

    # --- arma la lista de cambios legibles ANTES de actualizar, comparando contra los valores anteriores ---
    cambios = []
    with db_cursor() as cur:
        if nuevo_nombre != anterior["nombre_completo"]:
            cambios.append(f"Nombre: {anterior['nombre_completo']} → {nuevo_nombre}")
        if nuevo_correo != anterior["correo"]:
            cambios.append(f"Correo: {anterior['correo']} → {nuevo_correo}")
        if nuevo_cargo != anterior["cargo"]:
            cambios.append(f"Cargo: {anterior['cargo'] or 'N/A'} → {nuevo_cargo or 'N/A'}")
        if nuevo_id_rol != anterior["id_rol"]:
            cambios.append(f"Rol: {_nombre_rol(cur, anterior['id_rol'])} → {_nombre_rol(cur, nuevo_id_rol)}")
        if nuevo_id_sede != anterior["id_sede"]:
            cambios.append(f"Sede: {_nombre_sede(cur, anterior['id_sede'])} → {_nombre_sede(cur, nuevo_id_sede)}")
        if nuevo_activo != anterior["activo"]:
            cambios.append(f"Estado: {'Activo' if anterior['activo'] else 'Inactivo'} → {'Activo' if nuevo_activo else 'Inactivo'}")

    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE usuarios SET nombre_completo=%s, correo=%s, cargo=%s,
                                    id_rol=%s, id_sede=%s, activo=%s
               WHERE id_usuario=%s""",
            (nuevo_nombre, nuevo_correo, nuevo_cargo, nuevo_id_rol, nuevo_id_sede, nuevo_activo, id_usuario),
        )

    if cambios:
        # el correo se envía al correo NUEVO (por si justamente el correo fue lo que cambió)
        try:
            enviar_correo_cambios_usuario(nuevo_correo, nuevo_nombre, cambios)
        except Exception:
            return {"mensaje": "Usuario actualizado, pero no se pudo enviar el correo de notificación"}

    return {"mensaje": "Usuario actualizado"}

@router.delete("/usuarios/{id_usuario}")
def desactivar_usuario(id_usuario: int, usuario_actual: dict = Depends(requiere_rol_admin)):
    """Baja lógica (activo=FALSE): un usuario puede tener registros, evidencias y
    reportes asociados en varias tablas, borrarlo de verdad rompería ese historial."""
    if id_usuario == usuario_actual.get("id_usuario"):
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    with db_cursor() as cur:
        cur.execute("SELECT id_usuario FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE usuarios SET activo = FALSE WHERE id_usuario = %s", (id_usuario,))

    return {"mensaje": "Usuario desactivado"}

  # (ver nota abajo sobre el prefijo del router)