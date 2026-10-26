"""
Script de arranque: crea el primer usuario ADMIN del sistema.
Ejecutar una sola vez después de correr schema.sql:
    cd backend
    python scripts/crear_usuario_admin.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db import db_cursor
from app.auth import hash_password


def crear_admin(usuario, correo, password, nombre_completo):
    with db_cursor() as cur:
        cur.execute("SELECT id_rol FROM roles WHERE nombre_rol = 'ADMIN'")
        rol = cur.fetchone()
        if not rol:
            raise RuntimeError("No existe el rol ADMIN. Ejecute primero database/schema.sql")

        cur.execute("SELECT id_usuario FROM usuarios WHERE usuario = %s", (usuario,))
        if cur.fetchone():
            print(f"El usuario '{usuario}' ya existe. No se creó nada.")
            return

    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO usuarios (nombre_completo, correo, usuario, password_hash, id_rol)
               VALUES (%s, %s, %s, %s, %s)""",
            (nombre_completo, correo, usuario, hash_password(password), rol["id_rol"]),
        )
    print(f"Usuario administrador '{usuario}' creado correctamente.")


if __name__ == "__main__":
    # Cambiar estos valores antes de ejecutar en un ambiente real
    crear_admin(
        usuario="david.tecnico",
        correo="davidsantiagoochoavalencia498@gmail.com",
        password="18/06/2025-TyS",
        nombre_completo="David Santiago Ochoa Valencia",
    )
