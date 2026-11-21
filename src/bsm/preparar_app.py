"""Prepara la carpeta liviana que usa la app desplegada (data/app/, ~5 MB).

La app NO carga el dataset completo (750.000 filas, ~1 GB en memoria): solo la tabla
horaria agregada, los resúmenes, las alertas, las notas de campo y el modelo.
Así cabe en hosting gratuito (Render: 512 MB).

Uso:
    python -m bsm.preparar_app [--datos data/processed] [--modelos models] [--salida data/app]
"""
import argparse
import shutil
from pathlib import Path

import pandas as pd

from bsm.modelo import tabla_horaria


def preparar(datos="data/processed", modelos="models", salida="data/app"):
    datos, modelos, salida = Path(datos), Path(modelos), Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    h = tabla_horaria(pd.read_parquet(datos / "aforos_largo.parquet"))
    h.drop(columns=["festivo"]).to_parquet(salida / "horas.parquet", index=False)
    for f in ["estudios_resumen.csv", "alertas_calidad.csv", "observaciones_campo.csv"]:
        shutil.copy(datos / f, salida / f)
    for f in ["modelo_volumen.joblib", "metricas.json"]:
        shutil.copy(modelos / f, salida / f)
    return sorted(p.name for p in salida.iterdir())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="data/processed")
    ap.add_argument("--modelos", default="models")
    ap.add_argument("--salida", default="data/app")
    a = ap.parse_args()
    print(preparar(a.datos, a.modelos, a.salida))
