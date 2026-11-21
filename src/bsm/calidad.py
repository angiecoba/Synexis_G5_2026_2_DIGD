"""Contratos de datos (pandera) y alertas de calidad.

Principio: las anomalías del dato oficial se DOCUMENTAN como alertas, no se corrigen
en silencio. Son evidencia para el componente de confianza del reto.
"""
import pandas as pd
import pandera.pandas as pa

from .catalogo import CATEGORIA

# Contrato de la hoja vol-data a la entrada del pipeline.
ESQUEMA_VOL_DATA = pa.DataFrameSchema(
    {
        "NODO": pa.Column(int, pa.Check.gt(0), coerce=True),
        "FECHA": pa.Column("datetime64[ns]", coerce=True, nullable=False),
        "PERIODO": pa.Column(int, [pa.Check.in_range(0, 2345),
                                    pa.Check(lambda s: (s % 100).isin([0, 15, 30, 45]),
                                             element_wise=False, error="minutos no múltiplos de 15")],
                             coerce=True),
        "ACCESO": pa.Column(str, pa.Check.isin(["N", "S", "E", "W"]), coerce=True),
        "MOVIMIENTO": pa.Column(str, coerce=True),
        "SENTIDO": pa.Column(str, coerce=True),
    },
    strict=False,
)


def validar_vol_data(vol: pd.DataFrame):
    """Valida la hoja vol-data. Devuelve (vol_validado, errores_df o None).

    Usa lazy=True para reportar TODOS los errores de una vez. Los conteos se revisan
    aparte (no negativos) porque sus columnas cambian de un contrato a otro.
    """
    errores = []
    try:
        vol = ESQUEMA_VOL_DATA.validate(vol, lazy=True)
    except pa.errors.SchemaErrors as e:
        errores.append(e.failure_cases[["column", "check", "failure_case"]].head(20))
    cols_veh = [c for c in vol.columns if c in CATEGORIA]
    negativos = (vol[cols_veh].apply(pd.to_numeric, errors="coerce") < 0).sum()
    negativos = negativos[negativos > 0]
    if len(negativos):
        errores.append(pd.DataFrame({"column": negativos.index, "check": "conteo >= 0",
                                     "failure_case": negativos.values}))
    return vol, (pd.concat(errores, ignore_index=True) if errores else None)


def validar_plausibilidad(df: pd.DataFrame, umbral: float = 4.0, minimo: int = 500) -> pd.DataFrame:
    """Compara la participación de cada categoría en un estudio contra la mediana de los
    demás estudios del mismo nodo. Marca desviaciones > `umbral` veces (con al menos
    `minimo` vehículos). Detecta columnas corridas o mal etiquetadas; NO corrige nada."""
    v = df[(df.tipo_estudio == "VOL") & (df.fecha == df.fecha_estudio)
           & df.periodo.between(500, 2245)].copy()
    # Bicis en calzada como un solo grupo; la ciclorruta se reporta aparte (cambio de método).
    cicloinfra = v[v.categoria == "BICI_CICLOINFRA"].groupby(["nodo", "estudio"])["conteo"].sum()
    v = v[v.categoria != "BICI_CICLOINFRA"]
    v["categoria"] = v["categoria"].replace({"BICI_SIN_DETALLE": "BICI_CALZADA"})
    tab = v.pivot_table(index=["nodo", "estudio"], columns="categoria",
                        values="conteo", aggfunc="sum").fillna(0)
    part = tab.div(tab.sum(axis=1), axis=0)
    filas = []
    for nodo, sub in part.groupby(level=0):
        if len(sub) < 3:
            continue
        for est in sub.index:
            otros = sub.drop(index=est).median()
            for cat in sub.columns:
                obs, ref = sub.loc[est, cat], otros[cat]
                if max(tab.loc[est, cat], ref * tab.loc[est].sum()) < minimo:
                    continue
                razon = (obs + 1e-4) / (ref + 1e-4)
                if razon > umbral or razon < 1 / umbral:
                    filas.append({"nodo": nodo, "estudio": est[1], "categoria": cat,
                                  "tipo_alerta": "PARTICIPACION_ATIPICA",
                                  "detalle": f"{cat} {100*obs:.1f}% vs {100*ref:.1f}% típico"})
    for (nodo, est), n in cicloinfra.items():
        if n > 0:
            filas.append({"nodo": nodo, "estudio": est, "categoria": "BICI_CICLOINFRA",
                          "tipo_alerta": "CAMBIO_DE_METODO",
                          "detalle": f"se contaron {int(n):,} bicis en ciclorruta/bicicarril; "
                                     "no comparar total de bicis con otros estudios"})
    return pd.DataFrame(filas, columns=["nodo", "estudio", "categoria", "tipo_alerta", "detalle"])


def ids_repetidos(resumen: pd.DataFrame) -> pd.DataFrame:
    """Estudios cuyo ID de la SDM se repite en fechas distintas del mismo nodo."""
    n = resumen.groupby(["nodo", "estudio_id_sdm"])["fecha_estudio"].transform("nunique")
    r = resumen[n > 1]
    return pd.DataFrame({"nodo": r.nodo, "estudio": r.estudio, "categoria": "ID",
                         "tipo_alerta": "ID_REPETIDO",
                         "detalle": "ID SDM " + r.estudio_id_sdm.astype(str) + " repetido en varias fechas"})
