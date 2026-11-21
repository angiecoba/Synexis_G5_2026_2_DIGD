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

from bsm.catalogo import MOTORIZADOS, NODOS_PROYECTO
from bsm.modelo import tabla_horaria, tipo_dia

# Grupos que entiende un ciudadano (los buses troncales e intermunicipales van con los buses).
GRUPO_VEHICULO = {"LIVIANO": "Carros y camionetas", "MOTO": "Motos", "BUS": "Buses",
                  "ARTICULADO": "Buses", "INTERMUNICIPAL": "Buses", "CAMION": "Camiones"}


def mezcla_por_hora(aforos: pd.DataFrame) -> pd.DataFrame:
    """Proporción histórica de cada grupo de vehículo por nodo, tipo de día y hora."""
    d = aforos[(aforos.tipo_estudio == "VOL") & aforos.categoria.isin(MOTORIZADOS)
               & ~aforos.estudio.str.contains("_v")].copy()
    d["tipo_dia"] = tipo_dia(pd.to_datetime(d.fecha), d.festivo)
    d["grupo"] = d.categoria.map(GRUPO_VEHICULO)
    t = d.groupby(["nodo", "tipo_dia", "hora", "grupo"], as_index=False).conteo.sum()
    t["proporcion"] = t.conteo / t.groupby(["nodo", "tipo_dia", "hora"]).conteo.transform("sum")
    return t.drop(columns="conteo")


def ubicacion_nodos(aforos: pd.DataFrame) -> pd.DataFrame:
    """Coordenadas de cada nodo (mediana de las fichas de sus estudios) y días medidos."""
    d = aforos[aforos.nodo.isin(NODOS_PROYECTO) & aforos.lon.notna()]
    return (d.groupby("nodo").agg(lon=("lon", "median"), lat=("lat", "median"),
                                  dias=("estudio", "nunique")).reset_index())


def preparar(datos="data/processed", modelos="models", salida="data/app"):
    datos, modelos, salida = Path(datos), Path(modelos), Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    aforos = pd.read_parquet(datos / "aforos_largo.parquet")
    h = tabla_horaria(aforos)
    h.drop(columns=["festivo"]).to_parquet(salida / "horas.parquet", index=False)
    mezcla_por_hora(aforos).to_parquet(salida / "mezcla.parquet", index=False)
    ubicacion_nodos(aforos).to_csv(salida / "nodos.csv", index=False)
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
