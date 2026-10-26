from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    usuario: str
    password: str


class RegistroCuentaRequest(BaseModel):
    nombre_completo: str
    correo: str
    usuario: str
    password: str
    id_rol: int
    id_sede: int


class ResolverPendienteRequest(BaseModel):
    accion: str
    id_rol: Optional[int] = None
    motivo: Optional[str] = None


class SolicitarCodigoRequest(BaseModel):
    correo: str


class VerificarCodigoRequest(BaseModel):
    correo: str
    codigo: str


class RestablecerRequest(BaseModel):
    correo: str
    codigo: str
    nueva_password: str


class ItemCreate(BaseModel):
    codigo_item: str
    id_fase: int
    descripcion_item: str
    evidencia_requerida: Optional[str] = None
    recursos_necesarios: Optional[str] = None
    peso_porcentual: Optional[float] = 0


class ItemUpdate(BaseModel):
    codigo_item: Optional[str] = None
    id_fase: Optional[int] = None
    descripcion_item: Optional[str] = None
    evidencia_requerida: Optional[str] = None
    recursos_necesarios: Optional[str] = None
    peso_porcentual: Optional[float] = None
    activo: Optional[bool] = None


class RechazarRegistroRequest(BaseModel):
    motivo: str


class SedeCreate(BaseModel):
    nombre_sede: str
    ciudad: Optional[str] = ""
    direccion: Optional[str] = ""


class SedeUpdate(BaseModel):
    nombre_sede: str
    ciudad: Optional[str] = ""
    direccion: Optional[str] = ""


class GenerarReporteRequest(BaseModel):
    tipo_corte: str = "MENSUAL"
    periodo: str
    formato: str = "PDF"
