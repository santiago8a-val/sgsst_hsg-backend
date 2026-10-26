from app.db import db_cursor


def _filtro_periodo(tipo_corte: str, valor_periodo: str):
    """
    Formatos aceptados:
      MENSUAL:     2026-07
      TRIMESTRAL:  2026-3
      SEMESTRAL:   2026-1
      ANUAL:       2026
    """

    tipo_corte = (tipo_corte or "").strip().upper()
    valor_periodo = (valor_periodo or "").strip()

    if tipo_corte == "MENSUAL":
        partes = valor_periodo.split("-")

        if len(partes) != 2:
            raise ValueError("Para corte MENSUAL use el formato AAAA-MM, por ejemplo 2026-09")

        anio, mes = partes

        if not anio.isdigit() or len(anio) != 4:
            raise ValueError("El año debe tener 4 dígitos")

        if not mes.isdigit() or not 1 <= int(mes) <= 12:
            raise ValueError("El mes debe estar entre 01 y 12")

        return "r.periodo_anio = %s AND r.periodo_mes = %s", [int(anio), int(mes)]

    if tipo_corte == "TRIMESTRAL":
        partes = valor_periodo.split("-")

        if len(partes) != 2:
            raise ValueError("Para corte TRIMESTRAL use el formato AAAA-T, por ejemplo 2026-3")

        anio, trimestre = partes

        if not anio.isdigit() or len(anio) != 4:
            raise ValueError("El año debe tener 4 dígitos")

        if not trimestre.isdigit() or not 1 <= int(trimestre) <= 4:
            raise ValueError("El trimestre debe estar entre 1 y 4")

        return "r.periodo_anio = %s AND r.periodo_trimestre = %s", [
            int(anio),
            int(trimestre),
        ]

    if tipo_corte == "SEMESTRAL":
        partes = valor_periodo.split("-")

        if len(partes) != 2:
            raise ValueError("Para corte SEMESTRAL use el formato AAAA-S, por ejemplo 2026-1")

        anio, semestre = partes

        if not anio.isdigit() or len(anio) != 4:
            raise ValueError("El año debe tener 4 dígitos")

        if not semestre.isdigit() or not 1 <= int(semestre) <= 2:
            raise ValueError("El semestre debe ser 1 o 2")

        return "r.periodo_anio = %s AND r.periodo_semestre = %s", [
            int(anio),
            int(semestre),
        ]

    if tipo_corte == "ANUAL":
        if not valor_periodo.isdigit() or len(valor_periodo) != 4:
            raise ValueError("Para corte ANUAL use un año de 4 dígitos, por ejemplo 2026")

        return "r.periodo_anio = %s", [int(valor_periodo)]

    raise ValueError("Tipo de corte inválido")


def obtener_consolidado(tipo_corte: str, valor_periodo: str, id_sede: int = None) -> dict:
    condicion, params = _filtro_periodo(tipo_corte, valor_periodo)

    # Solo se cuentan registros ya APROBADOS: mientras un registro está pendiente
    # o fue rechazado, no debe reflejarse en las estadísticas del dashboard/reportes.
    condicion += " AND r.aprobado = TRUE"

    if id_sede:
        condicion += " AND r.id_sede = %s"
        params.append(id_sede)

    with db_cursor() as cur:
        # Totales generales.
        # porcentaje_avance = SUM(puntaje_item) / total * 100  (fórmula oficial: pondera
        # Cumple=1, Parcial=0.5, No cumple=0; NO es solo el conteo de "Cumple").
        cur.execute(
            f"""SELECT
                    COUNT(*) AS total,
                    SUM(estado_cumplimiento='CUMPLE') AS cumplidos,
                    SUM(estado_cumplimiento='PARCIAL') AS parciales,
                    SUM(estado_cumplimiento='NO_CUMPLE') AS no_cumplidos,
                    SUM(puntaje_item) AS suma_puntajes
                FROM registros_cumplimiento r WHERE {condicion}""",
            params,
        )
        totales = cur.fetchone()

        # Cumplimiento por fase PHVA (misma fórmula, aplicada por fase)
        cur.execute(
            f"""SELECT f.codigo_fase, f.nombre_fase,
                    COUNT(*) AS total,
                    SUM(r.estado_cumplimiento='CUMPLE') AS cumplidos,
                    SUM(r.estado_cumplimiento='PARCIAL') AS parciales,
                    SUM(r.estado_cumplimiento='NO_CUMPLE') AS no_cumplidos,
                    SUM(r.puntaje_item) AS suma_puntajes
                FROM registros_cumplimiento r
                JOIN items_sgsst i ON r.id_item = i.id_item
                JOIN fases_phva f ON i.id_fase = f.id_fase
                WHERE {condicion}
                GROUP BY f.codigo_fase, f.nombre_fase, f.orden
                ORDER BY f.orden""",
            params,
        )
        por_fase = cur.fetchall()

        # Cumplimiento por sede (misma fórmula, aplicada por sede)
        cur.execute(
            f"""SELECT s.id_sede, s.nombre_sede,
                    COUNT(*) AS total,
                    SUM(r.estado_cumplimiento='CUMPLE') AS cumplidos,
                    SUM(r.estado_cumplimiento='PARCIAL') AS parciales,
                    SUM(r.estado_cumplimiento='NO_CUMPLE') AS no_cumplidos,
                    SUM(r.puntaje_item) AS suma_puntajes
                FROM registros_cumplimiento r
                JOIN sedes s ON r.id_sede = s.id_sede
                WHERE {condicion}
                GROUP BY s.id_sede, s.nombre_sede
                ORDER BY s.nombre_sede""",
            params,
        )
        por_sede = cur.fetchall()

        # Detalle por item (para el reporte y el modal), incluye puntaje,
        # porcentaje individual, id_registro (para pedir su evidencia) y
        # el formato de evidencia que exige el ítem.
        cur.execute(
            f"""SELECT r.id_registro, i.codigo_item, f.nombre_fase, i.descripcion_item,
                    i.evidencia_requerida,
                    r.estado_cumplimiento, r.puntaje_item, r.porcentaje_item, r.observacion,
                    u.nombre_completo AS responsable, r.fecha_registro, s.nombre_sede
                FROM registros_cumplimiento r
                JOIN items_sgsst i ON r.id_item = i.id_item
                JOIN fases_phva f ON i.id_fase = f.id_fase
                JOIN usuarios u ON r.id_responsable = u.id_usuario
                JOIN sedes s ON r.id_sede = s.id_sede
                WHERE {condicion}
                ORDER BY f.orden, i.codigo_item""",
            params,
        )
        detalle = cur.fetchall()

    total = totales["total"] or 0
    cumplidos = totales["cumplidos"] or 0
    suma_puntajes = float(totales["suma_puntajes"] or 0)
    porcentaje_avance = round((suma_puntajes / total) * 100, 2) if total else 0.0

    for fase in por_fase:
        t = fase["total"] or 0
        suma_f = float(fase["suma_puntajes"] or 0)
        fase["porcentaje_avance"] = round((suma_f / t) * 100, 2) if t else 0.0

    for sede in por_sede:
        t = sede["total"] or 0
        suma_s = float(sede["suma_puntajes"] or 0)
        sede["porcentaje_avance"] = round((suma_s / t) * 100, 2) if t else 0.0

    return {
        "tipo_corte": tipo_corte,
        "periodo": valor_periodo,
        "totales": {
            "total_registros": total,
            "cumplidos": cumplidos,
            "parciales": totales["parciales"] or 0,
            "no_cumplidos": totales["no_cumplidos"] or 0,
            "porcentaje_avance": porcentaje_avance,
        },
        "por_fase": por_fase,
        "por_sede": por_sede,
        "detalle": detalle,
    }


def calcular_cumplimiento_items_sede_mes(id_sede: int, anio: int, mes: int) -> dict:
    """
    Cumplimiento mensual del catálogo de ítems SG-SST para una sede. Se calcula
    en el momento (no se guarda ningún estado permanente), por lo que al
    consultar un mes distinto el cálculo es automáticamente sobre ese nuevo
    periodo: no hace falta ningún proceso de 'reinicio'.
    """
    with db_cursor() as cur:
        cur.execute("SELECT id_item FROM items_sgsst WHERE activo = TRUE")
        items_activos = {fila["id_item"] for fila in cur.fetchall()}

        cur.execute(
            """SELECT id_item FROM registros_cumplimiento
               WHERE id_sede = %s AND periodo_anio = %s AND periodo_mes = %s
                     AND aprobado = TRUE AND estado_cumplimiento = 'CUMPLE'""",
            (id_sede, anio, mes),
        )
        items_cumplidos_ids = {fila["id_item"] for fila in cur.fetchall()}

    total = len(items_activos)
    cumplidos = len(items_activos & items_cumplidos_ids)

    return {
        "id_sede": id_sede,
        "anio": anio,
        "mes": mes,
        "total_items": total,
        "items_cumplidos": cumplidos,
        "porcentaje_cumplimiento": round((cumplidos / total) * 100, 2) if total else 100.0,
        "cumple_el_mes": total > 0 and cumplidos == total,
    }


def calcular_cumplimiento_items_todas_las_sedes(anio: int, mes: int, solo_incumplidas: bool = False) -> list:
    """Para el ADMIN: cumplimiento de ítems de cada sede en un mes dado.
    Si solo_incumplidas=True, filtra y deja solo las sedes que NO cumplen."""
    with db_cursor() as cur:
        cur.execute("SELECT id_sede, nombre_sede FROM sedes WHERE activa = TRUE ORDER BY nombre_sede")
        sedes = cur.fetchall()

    resultado = []
    for s in sedes:
        calculo = calcular_cumplimiento_items_sede_mes(s["id_sede"], anio, mes)
        if solo_incumplidas and calculo["cumple_el_mes"]:
            continue
        resultado.append({**calculo, "nombre_sede": s["nombre_sede"]})
    return resultado