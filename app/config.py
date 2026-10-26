import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Base de datos ---
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "Santiago")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "sgsst_db")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))
    DB_SSL_CA = os.environ.get("DB_SSL_CA", "").strip()
    if DB_SSL_CA and not os.path.isabs(DB_SSL_CA):
        DB_SSL_CA = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", DB_SSL_CA)
        )

    # --- Seguridad ---
    JWT_SECRET = os.environ.get("JWT_SECRET", "cambiar_este_secreto_en_produccion")
    JWT_EXP_HOURS = 8

    # --- Archivos ---
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "..", "uploads")
    REPORTS_FOLDER = os.path.join(os.path.dirname(__file__), "..", "reports_generados")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB por archivo
    EXTENSIONES_PERMITIDAS = {"pdf", "docx", "doc", "xlsx", "xls", "jpg", "jpeg", "png"}

       # --- Correo (recuperación de contraseña) ---
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER", "tu_correo@gmail.com")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "clave_de_aplicacion")
    SMTP_REMITENTE_NOMBRE = os.environ.get("SMTP_REMITENTE_NOMBRE", "Sistema SG-SST")
    CODIGO_RECUPERACION_MINUTOS = 15  # minutos de validez del código
