import os
import uuid
from werkzeug.utils import secure_filename
from fastapi import UploadFile
from app.config import Config

EXTENSIONES_IMAGENES = {"png", "jpg", "jpeg"}

FORMATOS_EXTENSIONES = {
    "PDF": {"pdf"},
    "WORD": {"doc", "docx"},
    "EXCEL": {"xls", "xlsx"},
    "IMAGEN": {"png", "jpg", "jpeg"},
}


def extension_valida(nombre_archivo, extensiones_permitidas):
    return "." in nombre_archivo and \
        nombre_archivo.rsplit(".", 1)[1].lower() in extensiones_permitidas


def guardar_archivo(archivo: UploadFile, extensiones_permitidas=EXTENSIONES_IMAGENES) -> dict:
    """
    Guarda un UploadFile de FastAPI con nombre aleatorio (uuid4), lo escribe en
    disco Y retorna también sus bytes crudos, para guardarlos además en la base
    de datos (columna evidencias.contenido_archivo). Lanza ValueError si la
    extensión no está permitida.

    Nota: se usa archivo.file (objeto estándar de Python, síncrono) en vez de
    'await archivo.read()' para poder mantener toda la app con funciones
    síncronas, igual que en la versión Flask original.
    """
    if not archivo or not archivo.filename:
        raise ValueError("No se recibió ningún archivo")
    if not extension_valida(archivo.filename, extensiones_permitidas):
        raise ValueError(f"Extensión no permitida. Use: {extensiones_permitidas}")

    nombre_original = secure_filename(archivo.filename)
    extension = nombre_original.rsplit(".", 1)[1].lower()
    nombre_guardado = f"{uuid.uuid4().hex}.{extension}"

    contenido_bytes = archivo.file.read()
    archivo.file.seek(0)

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    ruta_completa = os.path.join(Config.UPLOAD_FOLDER, nombre_guardado)
    with open(ruta_completa, "wb") as destino:
        destino.write(contenido_bytes)

    return {
        "nombre_archivo": nombre_guardado,
        "nombre_original": nombre_original,
        "ruta_archivo": ruta_completa,
        "tipo_archivo": extension,
        "tamano_bytes": os.path.getsize(ruta_completa),
        "contenido_bytes": contenido_bytes,
    }
