from app.db import db_cursor

VALOR_ESTADO = {
    "APROBADA": 100.0,
    "REGULAR": 50.0,
    "RECHAZADA": 0.0,
    "PENDIENTE": 0.0,
    "NO_REALIZADA": 0.0,
}


def _estado_ejecucion(fila):
    if not fila:
        return "NO_REALIZADA"
    estado = fila.get("estado_revision")
    if estado:
        return str(estado).upper()
    if fila.get("aprobado"):
        return "APROBADA"
    if fila.get("rechazado"):
        return "RECHAZADA"
    return "PENDIENTE"


def calcular_cumplimiento_sede_mes(id_sede: int, anio: int, mes: int) -> dict:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT pa.id_actividad, pa.descripcion_actividad,
                   pp.id_programa, pp.nombre_programa,
                   ps.id_subprograma, ps.nombre_subprograma
            FROM plan_actividad_meses pam
            JOIN plan_actividades pa ON pam.id_actividad = pa.id_actividad
            JOIN plan_subprogramas ps ON pa.id_subprograma = ps.id_subprograma
            JOIN plan_programas pp ON ps.id_programa = pp.id_programa
            WHERE pam.mes = %s AND pa.activo = TRUE
            ORDER BY pp.nombre_programa, ps.nombre_subprograma, pa.id_actividad
            """,
            (mes,),
        )
        programadas = cur.fetchall()

        cur.execute(
            """
            SELECT id_actividad, aprobado, rechazado, estado_revision
            FROM plan_ejecuciones
            WHERE id_sede = %s AND anio = %s AND mes = %s
            """,
            (id_sede, anio, mes),
        )
        ejecuciones = {fila["id_actividad"]: fila for fila in cur.fetchall()}

    detalle = []
    puntaje = 0.0
    realizadas = 0
    aprobadas = 0
    regulares = 0
    rechazadas = 0

    for actividad in programadas:
        ejecucion = ejecuciones.get(actividad["id_actividad"])
        estado = _estado_ejecucion(ejecucion)
        valor = VALOR_ESTADO[estado]
        puntaje += valor
        if ejecucion:
            realizadas += 1
        if estado == "APROBADA":
            aprobadas += 1
        elif estado == "REGULAR":
            regulares += 1
        elif estado == "RECHAZADA":
            rechazadas += 1
        detalle.append({**actividad, "estado": estado, "porcentaje": valor})

    total = len(programadas)
    porcentaje = round(puntaje / total, 2) if total else 0.0

    return {
        "id_sede": id_sede,
        "anio": anio,
        "mes": mes,
        "total_actividades_programadas": total,
        "actividades_realizadas": realizadas,
        "actividades_pendientes": max(total - realizadas, 0),
        "actividades_aprobadas": aprobadas,
        "actividades_regulares": regulares,
        "actividades_rechazadas": rechazadas,
        "actividades_cumplidas": aprobadas,
        "porcentaje_cumplimiento": porcentaje,
        "cumple_el_mes": total > 0 and porcentaje == 100.0,
        "detalle": detalle,
    }


def calcular_cumplimiento_todas_las_sedes(anio: int, mes: int) -> list:
    with db_cursor() as cur:
        cur.execute(
            "SELECT id_sede, nombre_sede FROM sedes WHERE activa = TRUE ORDER BY nombre_sede"
        )
        sedes = cur.fetchall()

    resultado = []
    for sede in sedes:
        calculo = calcular_cumplimiento_sede_mes(sede["id_sede"], anio, mes)
        resultado.append({
            "id_sede": sede["id_sede"],
            "nombre_sede": sede["nombre_sede"],
            "porcentaje_cumplimiento": calculo["porcentaje_cumplimiento"],
            "total_actividades_programadas": calculo["total_actividades_programadas"],
            "actividades_realizadas": calculo["actividades_realizadas"],
            "actividades_pendientes": calculo["actividades_pendientes"],
            "actividades_aprobadas": calculo["actividades_aprobadas"],
            "actividades_regulares": calculo["actividades_regulares"],
            "actividades_rechazadas": calculo["actividades_rechazadas"],
            "cumple_el_mes": calculo["cumple_el_mes"],
        })
    return resultado
