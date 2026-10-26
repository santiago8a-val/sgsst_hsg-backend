from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from app.auth import token_requerido, es_admin_general, sede_del_usuario_actual
from app.services.consolidado_service import obtener_consolidado

router = APIRouter(prefix="/api/consolidado", tags=["consolidado"])


@router.get("")
def ver_consolidado(tipo: str = "MENSUAL", periodo: str = None, sede: Optional[int] = None,
                     usuario_actual: dict = Depends(token_requerido)):
    """
    Ejemplos:
    /api/consolidado?tipo=MENSUAL&periodo=2026-07
    /api/consolidado?tipo=TRIMESTRAL&periodo=2026-3
    /api/consolidado?tipo=SEMESTRAL&periodo=2026-1
    /api/consolidado?tipo=ANUAL&periodo=2026

    Un usuario que NO es admin general siempre queda forzado a su propia sede,
    sin importar qué mande en 'sede' (si es que manda algo). Solo el admin
    general puede elegir una sede específica o dejarlo vacío para ver todas.
    """
    if not periodo:
        raise HTTPException(status_code=400, detail="Parámetro 'periodo' es obligatorio")

    if not es_admin_general(usuario_actual):
        id_sede = sede_del_usuario_actual(usuario_actual)
        if not id_sede:
            raise HTTPException(status_code=400, detail="Su usuario no tiene una sede asignada")
    else:
        id_sede = sede

    try:
        return obtener_consolidado(tipo.upper(), periodo, id_sede)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))