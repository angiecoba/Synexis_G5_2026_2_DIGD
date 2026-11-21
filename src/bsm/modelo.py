"""Modelo de volumen horario por movimiento, validado contra el futuro y contra un rival.

Unidad de predicción: vehículos motorizados en una hora, en un movimiento (nodo-acceso-
movimiento). Así el modelo no depende de cuántos movimientos aforó cada estudio.

Uso:
    python -m bsm.modelo [--datos data/processed] [--modelos models] [--corte 2026-01-01]

Reglas anti-fuga (guía "Pipelines que no mienten"):
    - Corte temporal: se entrena con el pasado y se evalúa con el futuro.
    - Todo el preprocesamiento vive dentro del Pipeline de sklearn.
    - Rival: promedio histórico por serie x hora x tipo de día. Si el modelo no le gana
      en un nodo, en ese nodo se usa el rival (decisión documentada en metricas.json).
"""
import argparse
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from .catalogo import MOTORIZADOS

log = logging.getLogger("bsm.modelo")
CATS = ["serie", "tipo_dia", "sentido"]
NUMS = ["hora", "dow", "mes", "anio"]


def tipo_dia(fecha: pd.Series, festivo: pd.Series) -> pd.Series:
    return pd.Series(np.where(festivo.fillna(False).astype(bool), "festivo",
                              np.where(fecha.dt.dayofweek >= 5, "finde", "habil")), index=fecha.index)


def tabla_horaria(aforos: pd.DataFrame) -> pd.DataFrame:
    """Agrega a hora x movimiento, solo estudios vehiculares, sin variantes dudosas y
    solo horas completas (los 4 cuartos de hora aforados)."""
    d = aforos[(aforos.tipo_estudio == "VOL") & aforos.categoria.isin(MOTORIZADOS)
               & ~aforos.estudio.str.contains("_v")]
    h = (d.groupby(["nodo", "estudio", "fecha", "hora", "acceso", "movimiento", "sentido"], as_index=False)
          .agg(veh=("conteo", "sum"), festivo=("festivo", "first"), n15=("periodo", "nunique")))
    h = h[h.n15 == 4].drop(columns="n15").copy()
    h["fecha"] = pd.to_datetime(h.fecha)
    h["dow"], h["mes"], h["anio"] = h.fecha.dt.dayofweek, h.fecha.dt.month, h.fecha.dt.year
    h["tipo_dia"] = tipo_dia(h.fecha, h.festivo)
    h["serie"] = h.nodo.astype(str) + "|" + h.acceso.astype(str) + "|" + h.movimiento.astype(str)
    h["hora"] = h.hora.astype(int)
    return h


def construir_modelo(random_state: int = 42) -> Pipeline:
    pre = ColumnTransformer(
        [("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CATS)],
        remainder="passthrough")
    gbm = HistGradientBoostingRegressor(loss="poisson", max_iter=400, learning_rate=0.05,
                                        categorical_features=[0, 1, 2], random_state=random_state)
    return Pipeline([("pre", pre), ("gbm", gbm)])


class Rival:
    """Promedio histórico por serie x hora x tipo de día (con respaldo serie x hora)."""

    def fit(self, h: pd.DataFrame):
        self.fino = h.groupby(["serie", "hora", "tipo_dia"]).veh.mean()
        self.grueso = h.groupby(["serie", "hora"]).veh.mean()
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        f = X.join(self.fino.rename("p"), on=["serie", "hora", "tipo_dia"])["p"]
        g = X.join(self.grueso.rename("p"), on=["serie", "hora"])["p"]
        return f.fillna(g).to_numpy()


def wape(y, p) -> float:
    return float(100 * np.abs(y - p).sum() / np.sum(y))


def evaluar(h: pd.DataFrame, corte: str):
    tr, te = h[h.fecha < corte], h[h.fecha >= corte]
    te = te[te.serie.isin(tr.serie)].copy()
    modelo = construir_modelo().fit(tr[CATS + NUMS], tr.veh)
    rival = Rival().fit(tr)
    te["p_modelo"], te["p_rival"] = modelo.predict(te[CATS + NUMS]), rival.predict(te)
    te = te.dropna(subset=["p_rival"])
    por_nodo = {}
    for n, g in te.groupby("nodo"):
        wm, wr = wape(g.veh, g.p_modelo), wape(g.veh, g.p_rival)
        por_nodo[int(n)] = {"horas_test": len(g), "estudios_test": int(g.estudio.nunique()),
                            "wape_modelo": round(wm, 1), "wape_rival": round(wr, 1),
                            "usar": "modelo" if wm < wr else "rival"}
    return {"corte": corte, "horas_train": len(tr), "horas_test": len(te),
            "wape_modelo": round(wape(te.veh, te.p_modelo), 1),
            "wape_rival": round(wape(te.veh, te.p_rival), 1),
            "mae_modelo": round(float(np.abs(te.veh - te.p_modelo).mean()), 1),
            "mae_rival": round(float(np.abs(te.veh - te.p_rival).mean()), 1),
            "por_nodo": por_nodo}


def entrenar(datos="data/processed", modelos="models", corte="2026-01-01"):
    datos, modelos = Path(datos), Path(modelos)
    modelos.mkdir(parents=True, exist_ok=True)
    h = tabla_horaria(pd.read_parquet(datos / "aforos_largo.parquet"))
    metricas = evaluar(h, corte)
    log.info("Test >= %s | WAPE modelo %.1f%% vs rival %.1f%%", corte,
             metricas["wape_modelo"], metricas["wape_rival"])
    # Modelo final: se reentrena con TODO el historial (la evaluación ya se hizo con el corte).
    final = construir_modelo().fit(h[CATS + NUMS], h.veh)
    rival = Rival().fit(h)
    series = (h.groupby("serie").agg(nodo=("nodo", "first"), acceso=("acceso", "first"),
                                     movimiento=("movimiento", "first"), sentido=("sentido", "first"))
               .reset_index())
    joblib.dump({"modelo": final, "rival": rival, "series": series,
                 "usar_por_nodo": {n: v["usar"] for n, v in metricas["por_nodo"].items()},
                 "features": {"cat": CATS, "num": NUMS}}, modelos / "modelo_volumen.joblib")
    (modelos / "metricas.json").write_text(json.dumps(metricas, indent=2, ensure_ascii=False))
    return metricas


def predecir_dia(artefacto: dict, nodo: int, fecha, festivo: bool = False) -> pd.DataFrame:
    """Perfil de 24 horas por movimiento para un nodo y una fecha."""
    fecha = pd.Timestamp(fecha)
    s = artefacto["series"][artefacto["series"].nodo == nodo]
    X = s.merge(pd.DataFrame({"hora": range(24)}), how="cross")
    X["dow"], X["mes"], X["anio"] = fecha.dayofweek, fecha.month, fecha.year
    X["tipo_dia"] = "festivo" if festivo else ("finde" if fecha.dayofweek >= 5 else "habil")
    usar = artefacto["usar_por_nodo"].get(nodo, "rival")
    if usar == "modelo":
        X["prediccion"] = artefacto["modelo"].predict(X[CATS + NUMS])
    else:
        X["prediccion"] = artefacto["rival"].predict(X)
    X["metodo"] = usar
    return X


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="data/processed")
    ap.add_argument("--modelos", default="models")
    ap.add_argument("--corte", default="2026-01-01")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    m = entrenar(a.datos, a.modelos, a.corte)
    print(json.dumps(m, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    # Importar desde el paquete para que joblib guarde las clases como bsm.modelo.*
    # (si se guardan como __main__.*, la app no puede cargar el modelo).
    from bsm.modelo import main as _main

    _main()
