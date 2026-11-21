"""Pipeline de aforos: de los Excel del Observatorio a un dataset limpio y auditado.

Uso:
    python -m bsm.pipeline <carpeta_o_zip> [--salida data/processed] [--nodos 663,695,...] [--todos]

Salidas (en --salida):
    aforos_largo.parquet      una fila por nodo-fecha-periodo-acceso-movimiento-categoría
    estudios_resumen.csv      una fila por estudio (totales comparables, hora pico, mezcla)
    observaciones_campo.csv   notas de campo (lluvia, accidentes, obras) -> insumo del RAG
    alertas_calidad.csv       anomalías del dato oficial (no se corrigen en silencio)
    auditoria.jsonl           un evento por archivo: OK, duplicado, corregido, descartado...

Reglas de limpieza:
    1. Duplicado exacto (mismo hash) y duplicado semántico (mismos conteos) se descartan.
    2. Mismo nodo y fecha con conteos distintos: se conserva como variante (_v2).
    3. El nodo y la fecha se toman de los DATOS, no del nombre del archivo.
    4. Correcciones de nodo verificadas en el visor (catalogo.CORRECCIONES_NODO).
    5. Fechas futuras y archivos dañados se descartan y se reportan.
    6. El tipo de estudio (VOL, VOLB, VOLP, VOLPAT) se decide por las columnas aforadas.
"""
import argparse
import json
import logging
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from .calidad import ids_repetidos, validar_plausibilidad, validar_vol_data
from .catalogo import CORRECCIONES_NODO, NODOS_PROYECTO
from .lectura import firma_contenido, leer_estudio, md5_archivo, nodo_en_nombre, tipo_por_columnas
from .resumen import resumir
from .transformacion import a_largo

log = logging.getLogger("bsm.pipeline")


class Auditoria:
    """Bitácora estructurada: cada evento es una fila consultable (y además va al log)."""

    def __init__(self):
        self.eventos = []

    def __call__(self, evento: str, archivo: str = "", nivel: int = logging.INFO, **datos):
        self.eventos.append({"evento": evento, "archivo": archivo, **datos})
        log.log(nivel, "%s | %s | %s", evento, archivo, datos or "")

    def guardar(self, ruta: Path):
        with open(ruta, "w", encoding="utf-8") as f:
            for e in self.eventos:
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")

    def conteo(self) -> dict:
        return pd.Series([e["evento"] for e in self.eventos]).value_counts().to_dict()


def _preparar_entrada(entrada: Path) -> Path:
    if entrada.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="aforos_"))
        with zipfile.ZipFile(entrada) as z:
            z.extractall(tmp)  # conserva subcarpetas: hay nombres de archivo repetidos
        return tmp
    return entrada


def _listar_archivos(entrada: Path, aud: Auditoria):
    archivos = []
    for p in sorted(entrada.rglob("*.xlsx")):
        nombre = str(p.relative_to(entrada))
        if p.name.startswith(("~", ".")):
            continue
        if "CONSOLIDADO" in p.name.upper():
            aud("OMITIDO_CONSOLIDADO", nombre)
            continue
        try:
            hojas = pd.ExcelFile(p).sheet_names
        except Exception as e:  # noqa: BLE001 - un Excel dañado no debe tumbar el pipeline
            aud("ARCHIVO_DANADO", nombre, logging.WARNING, error=str(e)[:100])
            continue
        if "vol-data" not in hojas:
            aud("SIN_HOJA_VOL_DATA", nombre, logging.WARNING)
            continue
        archivos.append((p, nombre))
    return archivos


def procesar(entrada, nodos=None):
    """Procesa todos los Excel de `entrada` (carpeta o .zip). Devuelve un dict de DataFrames."""
    entrada = _preparar_entrada(Path(entrada))
    aud = Auditoria()
    hoy = pd.Timestamp.today().normalize()
    vistos_hash, vistos_contenido, llaves = {}, {}, {}
    partes, observaciones = [], []

    for p, nombre in _listar_archivos(entrada, aud):
        h = md5_archivo(p)
        if h in vistos_hash:
            aud("DUPLICADO_EXACTO", nombre, igual_a=vistos_hash[h])
            continue
        vistos_hash[h] = nombre
        try:
            vol_todo, meta, factores, obs = leer_estudio(p)
        except Exception as e:  # noqa: BLE001
            aud("ERROR_LECTURA", nombre, logging.ERROR, error=str(e)[:150])
            continue

        vol_todo, errores = validar_vol_data(vol_todo)
        if errores is not None:
            aud("CONTRATO_INCUMPLIDO", nombre, logging.WARNING,
                errores=errores.astype(str).to_dict("records")[:5])
            continue

        tipo = tipo_por_columnas(vol_todo.columns)
        for malo, bueno in CORRECCIONES_NODO.items():
            if (vol_todo["NODO"] == malo).any():
                aud("NODO_CORREGIDO", nombre, de=malo, a=bueno)
        vol_todo["NODO"] = vol_todo["NODO"].replace(CORRECCIONES_NODO)
        nodos_archivo = sorted(vol_todo["NODO"].unique().tolist())
        nodo_nombre = nodo_en_nombre(p.name)
        if nodo_nombre and nodo_nombre not in nodos_archivo:
            aud("NODO_NO_COINCIDE", nombre, logging.WARNING, nombre_dice=nodo_nombre,
                datos_dicen=nodos_archivo, lugar=meta.get("lugar"))
        if len(nodos_archivo) > 1:
            aud("VARIOS_NODOS", nombre, nodos=nodos_archivo)

        for nodo in nodos_archivo:
            vol = vol_todo[vol_todo["NODO"] == nodo].copy()
            if nodos and nodo not in nodos:
                aud("FUERA_DE_ALCANCE", nombre, nodo=nodo)
                continue
            fecha = vol["FECHA"].min()
            if fecha > hoy:
                aud("FECHA_IMPOSIBLE", nombre, logging.WARNING, nodo=nodo, fecha=fecha)
                continue
            firma = firma_contenido(vol)
            if firma in vistos_contenido:
                aud("DUPLICADO_SEMANTICO", nombre, nodo=nodo, igual_a=vistos_contenido[firma])
                continue
            vistos_contenido[firma] = nombre
            llave = f"{nodo}_{fecha:%Y%m%d}_{tipo}"
            if llave in llaves:
                llaves[llave] += 1
                llave_final = f"{llave}_v{llaves[llave]}"
                aud("MISMA_FECHA_OTROS_DATOS", nombre, logging.WARNING, estudio=llave_final)
            else:
                llaves[llave] = 1
                llave_final = llave
            largo, desconocidas = a_largo(vol, meta, factores, tipo, nombre, llave_final)
            if desconocidas:
                aud("COLUMNA_NO_MAPEADA", nombre, logging.WARNING, columnas=desconocidas)
            aud("OK", nombre, logging.DEBUG, nodo=nodo, tipo=tipo, estudio=llave_final,
                periodos=int(vol["PERIODO"].nunique()))
            partes.append(largo)

            base = {"nodo": nodo, "fecha": fecha.date(), "estudio": llave_final,
                    "estudio_id_sdm": meta.get("estudio_id")}
            observaciones += [{**base, "fuente": "Identificacion", **o} for o in obs]
            if "OBSERVACIONES" in vol.columns:
                notas = vol[vol["OBSERVACIONES"].notna()
                            & (vol["OBSERVACIONES"].astype(str).str.strip() != "")]
                observaciones += [{**base, "fuente": "vol-data", "acceso_nombre": r.ACCESO,
                                   "periodo": r.PERIODO, "observacion": str(r.OBSERVACIONES).strip()}
                                  for r in notas.itertuples()]

    if not partes:
        raise ValueError("No quedó ningún estudio válido; revise la auditoría.")
    df = pd.concat(partes, ignore_index=True)
    resumen = resumir(df)
    alertas = pd.concat([validar_plausibilidad(df), ids_repetidos(resumen)], ignore_index=True)
    resumen["alerta_calidad"] = resumen["estudio"].map(
        alertas.groupby("estudio")["detalle"].apply(" | ".join)).fillna("")
    for a in alertas.itertuples():
        aud("ALERTA_CALIDAD", a.estudio, logging.DEBUG, tipo=a.tipo_alerta, detalle=a.detalle)
    return {"aforos": df, "resumen": resumen, "alertas": alertas,
            "observaciones": pd.DataFrame(observaciones), "auditoria": aud}


def guardar(resultado: dict, salida) -> None:
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    df = resultado["aforos"].copy()
    for c in ["sentido", "acceso", "movimiento", "estudio_id", "contratista", "orden_trabajo", "lugar"]:
        df[c] = df[c].astype("string")
    df.to_parquet(salida / "aforos_largo.parquet", index=False)
    resultado["resumen"].to_csv(salida / "estudios_resumen.csv", index=False, encoding="utf-8-sig")
    resultado["alertas"].to_csv(salida / "alertas_calidad.csv", index=False, encoding="utf-8-sig")
    resultado["observaciones"].to_csv(salida / "observaciones_campo.csv", index=False, encoding="utf-8-sig")
    resultado["auditoria"].guardar(salida / "auditoria.jsonl")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", help="carpeta o .zip con los Excel del Observatorio")
    ap.add_argument("--salida", default="data/processed")
    ap.add_argument("--nodos", help="lista separada por comas (por defecto: NODOS_PROYECTO)")
    ap.add_argument("--todos", action="store_true", help="procesar todos los nodos encontrados")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    nodos = None if a.todos else ({int(n) for n in a.nodos.split(",")} if a.nodos else NODOS_PROYECTO)
    r = procesar(a.entrada, nodos)
    guardar(r, a.salida)
    log.info("Eventos: %s", r["auditoria"].conteo())
    log.info("Estudios vehiculares: %d | filas: %d | alertas: %d",
             len(r["resumen"]), len(r["aforos"]), len(r["alertas"]))


if __name__ == "__main__":
    main()
