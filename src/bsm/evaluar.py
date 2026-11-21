"""Evalúa el asistente con el set de preguntas de prueba (evaluacion/preguntas.csv).

Escala (la misma para el asistente y para el buscador del portal):
    2 = correcta y con fuente      1 = parcial o sin fuente      0 = incorrecta, irrelevante o inventada

Criterios de cada pregunta (columnas criterio_correcta / criterio_parcial):
    "a & b"  -> deben aparecer todos los términos;   "a|b" -> basta uno.

Uso:
    python -m bsm.evaluar            # escribe evaluacion/resultados_asistente.csv
"""
import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]


def cumple(criterio, texto: str) -> bool:
    if not isinstance(criterio, str) or not criterio.strip():
        return False
    t = texto.lower()
    return all(any(op.strip().lower() in t for op in grupo.split("|")) for grupo in criterio.split("&"))


def tiene_fuente(texto: str) -> bool:
    return bool(re.search(r"fuente|\[estudio|estudio \d+_|\[[\w_]+\.md\]|observatorio", texto, re.I))


def calificar(fila, respuesta: str):
    rechazo = fila.tipo in ("fuera de alcance", "fuera de cobertura")
    if cumple(fila.criterio_correcta, respuesta) and (rechazo or tiene_fuente(respuesta)):
        return 2
    if cumple(fila.criterio_correcta, respuesta) or cumple(fila.criterio_parcial, respuesta):
        return 1
    return 0


def main():
    sys.path.insert(0, str(RAIZ))
    import app  # noqa: PLC0415 - la app carga datos y modelo al importarse

    preguntas = pd.read_csv(RAIZ / "evaluacion" / "preguntas.csv")
    filas = []
    for f in preguntas.itertuples():
        r = app.responder(f.pregunta, [])
        if isinstance(r, list):  # respuestas con gráfico: se califica el texto
            r = "\n".join(x for x in r if isinstance(x, str))
        filas.append({"id": f.id, "tipo": f.tipo, "pregunta": f.pregunta, "respuesta": r,
                      "puntaje": calificar(f, r), "tiene_fuente": tiene_fuente(r)})
    res = pd.DataFrame(filas)
    res.to_csv(RAIZ / "evaluacion" / "resultados_asistente.csv", index=False, encoding="utf-8-sig")
    print(res[["id", "tipo", "puntaje", "tiene_fuente"]].to_string(index=False))
    print(f"\nTotal: {res.puntaje.sum()} / {2 * len(res)}")
    return res


if __name__ == "__main__":
    main()
