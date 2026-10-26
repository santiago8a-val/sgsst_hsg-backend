import os
import ssl
import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
from app.config import Config


def get_connection():
    """Abre una conexión nueva a MySQL. Usar siempre dentro de un 'with'."""
    if not Config.DB_SSL_CA:
        raise RuntimeError("DB_SSL_CA debe apuntar al certificado CA de MySQL.")
    if not os.path.isfile(Config.DB_SSL_CA):
        raise FileNotFoundError(
            f"No se encontró el certificado CA configurado: {Config.DB_SSL_CA}"
        )

    return pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        port=Config.DB_PORT,
        cursorclass=DictCursor,
        autocommit=False,
        charset="utf8mb4",
        ssl={
            "ca": Config.DB_SSL_CA,
            "check_hostname": True,
            "verify_mode": ssl.CERT_REQUIRED,
        },
    )


@contextmanager
def db_cursor(commit: bool = False):
    """
    Context manager que entrega un cursor y cierra/commitea automáticamente.
    Uso:
        with db_cursor(commit=True) as cur:
            cur.execute("INSERT INTO ...", (...))
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
