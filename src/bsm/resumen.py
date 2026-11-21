"""Indicadores por estudio, comparables entre estudios de 18 h y de 24 h."""
import pandas as pd

from .catalogo import BICIS, MIN_PERIODOS_COMPLETO, MOTORIZADOS, PESADOS, VENTANA


def resumen_estudio(g: pd.DataFrame) -> pd.Series:
    # Ventana comparable: 05:00-22:45 del día del estudio (sin la madrugada siguiente).
    v = g[(g["fecha"] == g["fecha_estudio"]) & g["periodo"].between(*VENTANA)]
    mot = v[v["categoria"].isin(MOTORIZADOS)]
    por_hora = mot.groupby("hora")["ace"].sum()
    tot_mot = mot["conteo"].sum()
    completo = v["periodo"].nunique() >= MIN_PERIODOS_COMPLETO
    g0 = g[g["fecha"] == g["fecha_estudio"]]

    def pct(mask):
        return round(100 * mot.loc[mask, "conteo"].sum() / tot_mot, 1) if tot_mot else pd.NA

    return pd.Series({
        "estudio_id_sdm": g["estudio_id"].iloc[0],
        "fecha_estudio": g["fecha_estudio"].iloc[0],
        "dia_semana": g0["dia_semana"].iloc[0],
        "festivo": g0["festivo"].iloc[0],
        "orden_trabajo": g["orden_trabajo"].iloc[0],
        "cobertura_h": round(g["periodo"].nunique() / 4, 1),
        "periodos_en_ventana": v["periodo"].nunique(),
        "cobertura_tipo": "completa" if completo else "parcial",
        "veh_motorizados_5a23": tot_mot if (tot_mot > 0 and completo) else pd.NA,
        "ace_5a23": mot["ace"].sum() if (tot_mot > 0 and completo) else pd.NA,
        "hora_pico": por_hora.idxmax() if len(por_hora) else pd.NA,
        "ace_hora_pico": por_hora.max() if len(por_hora) else pd.NA,
        "pct_motos": pct(mot.categoria == "MOTO"),
        "pct_pesados": pct(mot.categoria.isin(PESADOS)),
        "bicis_total_5a23": v.loc[v.categoria.isin(BICIS), "conteo"].sum(min_count=1),
        "bicis_cicloinfra_5a23": v.loc[v.categoria == "BICI_CICLOINFRA", "conteo"].sum(min_count=1),
    })


def resumir(df: pd.DataFrame) -> pd.DataFrame:
    vol = df[df.tipo_estudio == "VOL"]
    return (vol.groupby(["nodo", "estudio"]).apply(resumen_estudio, include_groups=False)
               .reset_index().sort_values(["nodo", "fecha_estudio"]))
