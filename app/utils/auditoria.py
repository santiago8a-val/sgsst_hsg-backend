import json
from app.db import db_cursor


def registrar_auditoria(tabla, id_registro, accion, id_usuario, anteriores=None, nuevos=None, ip="0.0.0.0"):
    """
    Guarda una fila de auditoría. Se llama tras CREAR / EDITAR / ELIMINAR / APROBAR
    sobre cualquier tabla relevante (registros_cumplimiento, evidencias, items_sgsst...).
    """
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO auditoria_cambios
                (tabla_afectada, id_registro_afectado, accion, id_usuario,
                 valores_anteriores, valores_nuevos, ip_origen)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tabla, id_registro, accion, id_usuario,
                json.dumps(anteriores, default=str) if anteriores else None,
                json.dumps(nuevos, default=str) if nuevos else None,
                ip,
            ),
        )
