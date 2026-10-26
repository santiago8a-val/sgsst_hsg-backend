import jwt
import datetime
import secrets
import string
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from werkzeug.security import generate_password_hash, check_password_hash
from app.config import Config
from app.db import db_cursor
from app.services.email_services import enviar_correo_cuenta_aprobada, enviar_correo_cuenta_rechazada

security = HTTPBearer()


# ---------- Utilidades de contraseña ----------
def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


# ---------- Generación / validación de token ----------
def generar_token(usuario: dict) -> str:
    payload = {
        "id_usuario": usuario["id_usuario"],
        "usuario": usuario["usuario"],
        "rol": usuario["nombre_rol"],
        "id_sede": usuario.get("id_sede"),
        "permisos": {
            "crear": bool(usuario["puede_crear"]),
            "editar": bool(usuario["puede_editar"]),
            "eliminar": bool(usuario["puede_eliminar"]),
            "aprobar": bool(usuario["puede_aprobar"]),
            "exportar": bool(usuario["puede_exportar"]),
        },
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=Config.JWT_EXP_HOURS),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def login(usuario_input: str, password: str):
    """Valida credenciales contra MySQL y retorna (token, datos_usuario) o (None, None/dict_error)."""
    with db_cursor() as cur:
        cur.execute(
            """
                SELECT u.id_usuario, u.usuario, u.password_hash, u.nombre_completo,
                    u.activo, u.estado_cuenta, u.id_sede,
                    r.nombre_rol, r.puede_crear, r.puede_editar, r.puede_eliminar,
                    r.puede_aprobar, r.puede_exportar
                FROM usuarios u
                JOIN roles r ON u.id_rol = r.id_rol
                WHERE u.usuario = %s OR u.correo = %s
            """,
            (usuario_input, usuario_input),
        )
        usuario = cur.fetchone()

        if not usuario:
            return None, None

        if not usuario["activo"]:
            return None, None

        if usuario["estado_cuenta"] == "PENDIENTE":
            return None, {"error": "Su cuenta está pendiente de aprobación por el administrador"}

        if usuario["estado_cuenta"] == "RECHAZADO":
            return None, {"error": "Su cuenta ha sido rechazada por el administrador"}

        if not verificar_password(password, usuario["password_hash"]):
            return None, None

    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE usuarios SET ultimo_acceso = NOW() WHERE id_usuario = %s",
            (usuario["id_usuario"],),
        )

    token = generar_token(usuario)
    return token, usuario


# ---------- Registro de cuenta (queda pendiente de aprobación) ----------
def registrar_usuario(nombre_completo: str, correo: str, usuario: str, password: str, id_rol: int, id_sede: int):
    """Crea una cuenta nueva en estado PENDIENTE, a la espera de aprobación del admin."""
    with db_cursor() as cur:
        cur.execute("SELECT id_usuario FROM usuarios WHERE correo = %s", (correo,))
        if cur.fetchone():
            return None, "El correo ya está registrado"

        cur.execute("SELECT id_usuario FROM usuarios WHERE usuario = %s", (usuario,))
        if cur.fetchone():
            return None, "El nombre de usuario ya está en uso"
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO usuarios (nombre_completo, correo, usuario, password_hash, id_rol, id_sede, activo, estado_cuenta)
               VALUES (%s, %s, %s, %s, %s, %s, TRUE, 'PENDIENTE')""",
            (nombre_completo, correo, usuario, hash_password(password), id_rol, id_sede),
        )
        id_usuario = cur.lastrowid

    return id_usuario, None


def listar_usuarios_pendientes():
    with db_cursor() as cur:
        cur.execute(
            """SELECT u.id_usuario, u.nombre_completo, u.correo, u.usuario, u.fecha_creacion,
                      u.id_rol, r.nombre_rol, u.id_sede, s.nombre_sede
               FROM usuarios u
               JOIN roles r ON u.id_rol = r.id_rol
               LEFT JOIN sedes s ON u.id_sede = s.id_sede
               WHERE u.estado_cuenta = 'PENDIENTE'
               ORDER BY u.fecha_creacion ASC"""
        )
        return cur.fetchall()


def listar_roles_publicos():
    """Roles que un usuario puede solicitar al registrarse. Nunca incluye ADMIN."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT id_rol, nombre_rol, descripcion FROM roles WHERE nombre_rol != 'ADMIN' ORDER BY id_rol"
        )
        return cur.fetchall()


def listar_roles():
    """Todos los roles, incluido ADMIN. Solo para uso del panel de administrador."""
    with db_cursor() as cur:
        cur.execute("SELECT id_rol, nombre_rol, descripcion FROM roles ORDER BY id_rol")
        return cur.fetchall()


# ---------- Dependencias de FastAPI (equivalen a los decoradores @token_requerido, etc.) ----------
def token_requerido(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Valida el JWT del header Authorization y retorna su payload (equivale a 'g.usuario_actual')."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado, inicie sesión de nuevo")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    return payload


def requiere_permiso(nombre_permiso: str):
    """Uso: usuario_actual: dict = Depends(requiere_permiso("eliminar"))"""
    def dependencia(usuario_actual: dict = Depends(token_requerido)) -> dict:
        permisos = usuario_actual.get("permisos", {})
        if not permisos.get(nombre_permiso, False):
            raise HTTPException(status_code=403, detail=f"No tiene permiso para '{nombre_permiso}'")
        return usuario_actual
    return dependencia


def requiere_rol_admin(usuario_actual: dict = Depends(token_requerido)) -> dict:
    """Restringe el acceso solo al rol ADMIN (administrador general)."""
    if usuario_actual.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="Solo el administrador general puede acceder a este recurso")
    return usuario_actual


# ---------- Recuperación de contraseña ----------
def correo_existe(correo: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id_usuario, nombre_completo, activo FROM usuarios WHERE correo = %s",
            (correo,),
        )
        usuario = cur.fetchone()
    if not usuario or not usuario["activo"]:
        return None
    return usuario


def generar_codigo_recuperacion(id_usuario: int) -> str:
    codigo = "".join(secrets.choice(string.digits) for _ in range(6))
    expiracion = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=Config.CODIGO_RECUPERACION_MINUTOS
    )
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE codigos_recuperacion SET usado = TRUE WHERE id_usuario = %s AND usado = FALSE",
            (id_usuario,),
        )
        cur.execute(
            """INSERT INTO codigos_recuperacion (id_usuario, codigo, fecha_expiracion)
               VALUES (%s, %s, %s)""",
            (id_usuario, codigo, expiracion),
        )
    return codigo


def validar_codigo_recuperacion(correo: str, codigo: str):
    with db_cursor() as cur:
        cur.execute(
            """SELECT c.id_codigo, c.id_usuario, c.fecha_expiracion, c.usado
               FROM codigos_recuperacion c
               JOIN usuarios u ON c.id_usuario = u.id_usuario
               WHERE u.correo = %s AND c.codigo = %s
               ORDER BY c.fecha_creacion DESC LIMIT 1""",
            (correo, codigo),
        )
        registro = cur.fetchone()

    if not registro or registro["usado"]:
        return None
    if registro["fecha_expiracion"] < datetime.datetime.utcnow():
        return None
    return registro


def restablecer_password(correo: str, codigo: str, nueva_password: str) -> bool:
    registro = validar_codigo_recuperacion(correo, codigo)
    if not registro:
        return False

    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s",
            (hash_password(nueva_password), registro["id_usuario"]),
        )
        cur.execute(
            "UPDATE codigos_recuperacion SET usado = TRUE WHERE id_codigo = %s",
            (registro["id_codigo"],),
        )
    return True


# ---------- Helpers de sede (ahora reciben el usuario_actual explícito, no hay 'g' en FastAPI) ----------
def es_admin_general(usuario_actual: dict) -> bool:
    return usuario_actual.get("rol") == "ADMIN"


def sede_del_usuario_actual(usuario_actual: dict):
    return usuario_actual.get("id_sede")

def generar_password_temporal(longitud: int = 12) -> str:
    """Genera una contraseña aleatoria y segura (con secrets, no random)."""
    alfabeto = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alfabeto) for _ in range(longitud))


def crear_usuario_por_admin(nombre_completo, correo, usuario, id_rol, id_sede, cargo=None):
    """
    El administrador general crea la cuenta directamente: queda activa y
    aprobada de inmediato (ya NO pasa por el flujo de solicitud/pendiente).
    Retorna (id_usuario, password_generada, error).
    """
    with db_cursor() as cur:
        cur.execute(
            "SELECT id_usuario FROM usuarios WHERE usuario = %s OR correo = %s",
            (usuario, correo),
        )
        if cur.fetchone():
            return None, None, "Ese usuario o correo ya está registrado"

    password_generada = generar_password_temporal()

    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO usuarios
               (nombre_completo, correo, usuario, password_hash, id_rol, id_sede,
                cargo, activo, estado_cuenta)
               VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,'APROBADO')""",
            (nombre_completo, correo, usuario, hash_password(password_generada),
             id_rol, id_sede, cargo),
        )
        nuevo_id = cur.lastrowid

    return nuevo_id, password_generada, None

