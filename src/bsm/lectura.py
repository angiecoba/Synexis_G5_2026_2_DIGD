"""Lectura de los Excel del Observatorio de Movilidad (hojas vol-data e Identificacion)."""
import hashlib
import re
from pathlib import Path

import pandas as pd

from .catalogo import BICIS, CATEGORIA, MOTORIZADOS


def md5_archivo(path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def firma_contenido(vol: pd.DataFrame) -> str:
    """Huella de los conteos: dos archivos distintos con los mismos datos dan la misma firma."""
    num = vol.drop(columns=["OBSERVACIONES"], errors="ignore").copy()
    num["PERIODO"] = pd.to_numeric(num["PERIODO"], errors="coerce")
    num = num.sort_values(list(num.columns[:6])).reset_index(drop=True)
    return hashlib.md5(pd.util.hash_pandas_object(num, index=False).values).hexdigest()


def leer_identificacion(path):
    """Extrae metadatos, factores de equivalencia y observaciones de la hoja 'Identificacion'.

    Devuelve (meta, factores, observaciones). Lee los campos del contrato por posición
    de columna, porque las celdas vacías corren los valores si se leen por orden.
    """
    hoja = pd.read_excel(path, sheet_name="Identificacion", header=None)
    crudas = [[("" if str(x) == "nan" else str(x).strip()) for x in r] for r in hoja.values.tolist()]
    filas = [[x for x in r if x] for r in crudas]
    meta, factores, obs = {}, {}, []
    seccion = None
    for i, r in enumerate(filas):
        if not r:
            continue
        k = r[0]
        if k == "Identificador de estudio" and i + 1 < len(crudas):
            enc, v = crudas[i], crudas[i + 1]
            pos = {n: j for j, n in enumerate(enc) if n}

            def dato(n, pos=pos, v=v):
                return (v[pos[n]] or None) if n in pos and pos[n] < len(v) else None

            meta.update(estudio_id=dato("Identificador de estudio"), contratista=dato("Contratista"),
                        contrato=dato("Contrato"), orden_trabajo=dato("Orden de trabajo"))
        elif k == "Nodo número" and len(r) > 1:
            meta["nodo_ficha"] = r[1]
        elif k.startswith("Lugar de la toma"):
            meta["lugar"] = r[1] if len(r) > 1 else None
        elif k.startswith("Coordenadas") and len(r) > 1:
            nums = re.findall(r"-?\d+\.\d+", r[1])
            if len(nums) == 2:
                meta["lon"], meta["lat"] = float(nums[0]), float(nums[1])
        elif k == "TIPOS DE VEHICULO DEL ESTUDIO":
            seccion = "veh"
            continue
        elif k == "OBSERVACIONES PREVIAS AL ESTUDIO":
            seccion = "obs"
            continue
        elif k.isupper() and len(r) == 1:
            seccion = None
        if seccion == "veh" and k != "CÓDIGO DE VEHICULO" and len(r) >= 3:
            try:
                factores[k] = float(r[2].replace(",", "."))
            except ValueError:
                pass
        if seccion == "obs" and k != "ACCESO" and len(r) >= 2:
            obs.append({"acceso_nombre": r[0], "observacion": r[1]})
    return meta, factores, obs


def tipo_por_columnas(cols) -> str:
    """El tipo de estudio se decide por lo que se contó, no por el nombre del archivo."""
    cats = {CATEGORIA[c] for c in cols if c in CATEGORIA}
    if cats & set(MOTORIZADOS):
        return "VOL"      # vehicular (incluye EYS y ESB)
    if cats == {"PEATON"}:
        return "VOLP"     # peatonal
    if cats and cats <= set(BICIS):
        return "VOLB"     # solo bicicletas
    if cats == {"PATINETA"}:
        return "VOLPAT"   # solo patinetas
    return "OTRO"


def nodo_en_nombre(nombre_archivo: str):
    """Nodo que declara el nombre del archivo (p. ej. '3493_...' o '5339_23692_...')."""
    m = re.match(r"^(?:\d{3,6}_)?(\d{3,6})_", nombre_archivo)
    return int(m.group(1)) if m else None


def leer_estudio(path):
    vol = pd.read_excel(path, sheet_name="vol-data")
    meta, factores, obs = leer_identificacion(path)
    return vol, meta, factores, obs
