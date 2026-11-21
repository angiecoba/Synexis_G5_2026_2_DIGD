"""De la hoja vol-data (ancha, una columna por vehículo) a formato largo."""
import pandas as pd

from .catalogo import CATEGORIA, CLAVES, DIAS, FACTOR_ACE, FESTIVOS


def a_largo(vol: pd.DataFrame, meta: dict, factores: dict, tipo: str, archivo: str, estudio: str):
    """Una fila por nodo-fecha-periodo-sentido-acceso-movimiento-categoría.

    Reglas: un vacío NO es un cero (categoría no aforada queda vacía); los códigos se
    agregan a su categoría canónica; FECHA conserva la fecha real de cada periodo y
    `fecha_estudio` es la primera fecha del archivo (los estudios de 24 h cruzan la
    medianoche). Devuelve (largo, columnas_no_mapeadas).
    """
    vol = vol.copy()
    vol["PERIODO"] = pd.to_numeric(vol["PERIODO"], errors="coerce").astype("Int64")
    vol["MOVIMIENTO"] = vol["MOVIMIENTO"].astype(str).str.strip()
    vol["FECHA"] = pd.to_datetime(vol["FECHA"]).dt.normalize()
    cols_veh = [c for c in vol.columns if c in CATEGORIA]
    desconocidas = [c for c in vol.columns if c not in CATEGORIA and c not in CLAVES + ["OBSERVACIONES"]]

    largo = vol.melt(id_vars=CLAVES, value_vars=cols_veh, var_name="codigo", value_name="conteo")
    largo["conteo"] = pd.to_numeric(largo["conteo"], errors="coerce")
    largo["categoria"] = largo["codigo"].map(CATEGORIA)
    largo["factor_ace"] = largo["codigo"].map(factores).fillna(largo["categoria"].map(FACTOR_ACE))
    largo = (largo.groupby(CLAVES + ["categoria"], dropna=False)
                  .agg(conteo=("conteo", lambda s: s.sum(min_count=1)),
                       factor_ace=("factor_ace", "first"))
                  .reset_index())
    largo["ace"] = largo["conteo"] * largo["factor_ace"]

    largo["hora"] = (largo["PERIODO"] // 100).astype("Int64")
    largo["minuto"] = (largo["PERIODO"] % 100).astype("Int64")
    largo["dia_semana"] = largo["FECHA"].dt.dayofweek.map(dict(enumerate(DIAS)))
    largo["fin_de_semana"] = largo["FECHA"].dt.dayofweek >= 5
    largo["festivo"] = largo["FECHA"].map(lambda d: d in FESTIVOS) if FESTIVOS else pd.NA
    largo["anio"], largo["mes"] = largo["FECHA"].dt.year, largo["FECHA"].dt.month
    largo["fecha_estudio"] = largo["FECHA"].min()
    largo["estudio"] = estudio
    largo["tipo_estudio"] = tipo
    largo["archivo"] = archivo
    for k in ["estudio_id", "contratista", "orden_trabajo", "lugar", "lon", "lat"]:
        largo[k] = meta.get(k)
    largo.columns = [c.lower() for c in largo.columns]
    return largo, desconocidas
