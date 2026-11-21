"""Asistente base: enrutador + recuperación con cita + LLM opcional.

Principios (clase "LLM, RAG y App"):
  1. Si la respuesta es un CÁLCULO, se resuelve con datos (funciones), no con el LLM.
  2. Si es CONCEPTUAL o de contexto, se recupera texto (notas de campo, glosario,
     diagnóstico) y se responde SOLO con lo recuperado, citando la fuente.
  3. Si no está en los datos, se dice "no tengo ese dato".

El LLM es opcional: si no hay LLM_API_KEY, se devuelve la respuesta extractiva con
citas. Cualquier proveedor compatible con la API de chat de OpenAI sirve
(variables LLM_API_KEY, LLM_BASE_URL, LLM_MODEL), configuradas como Secrets.
"""
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer

from .catalogo import NODOS_PROYECTO

NOMBRES_NODO = {
    663: ["via a cota", "cota", "116", "carrera 116"],
    695: ["carrera 7", "septima", "kr 7", "ak 7", "calle 208", "208"],
    23692: ["102a", "calle 102", "transversal 13a"],
    3493: ["autopista norte", "autonorte", "calle 170", "170"],
    19513: ["avenida 68", "av 68", "calle 72", "72"],
    10122: ["calle 171", "171", "carrera 111", "111"],
}
ETIQUETA_NODO = {663: "Vía a Cota con Cra 116", 695: "AK 7 con Calle 208",
                 23692: "Calle 102A con Tv 13A Este", 3493: "Autopista Norte con Calle 170",
                 19513: "Av. 68 con Calle 72", 10122: "Calle 171 con Cra 111"}


def normalizar(t: str) -> str:
    """Minúsculas, sin tildes y sin puntuación ('Av. 68' -> 'av 68')."""
    t = unicodedata.normalize("NFKD", str(t).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]", " ", t)).strip()


# Palabras vacías: español común + términos que aparecen en casi todas las notas.
VACIAS = set("""a al algo como con cual cuales cuando de del donde el ella en entre es esa ese
esta este hay la las lo los mas me mi no o para pero por que se sin sobre su sus un una uno
y ya qué cuál pasa paso paso fue son era estan esta dia dias via vias nodo acceso hora horas
calle carrera cra kr ak av avenida hubo ha han tiene ocurre ocurrio ocurren registro registra""".split())

# Sinónimos mínimos para que la pregunta encuentre cómo lo escriben los aforadores.
SINONIMOS = {
    "lluvia": "lluvia llover llueve llovio llovizna aguacero",
    "llover": "lluvia llover llueve llovio llovizna",
    "accidente": "accidente accidentes choque siniestro",
    "accidentes": "accidente accidentes choque siniestro",
    "trancon": "trancon congestion represamiento cola",
    "congestion": "trancon congestion represamiento cola",
    "obra": "obra obras cierre desvio pmt",
    "cierre": "obra obras cierre desvio cerrada",
}


def expandir(pregunta: str) -> str:
    palabras = normalizar(pregunta).split()
    return " ".join(SINONIMOS.get(w, w) for w in palabras)


def detectar_nodo(pregunta: str):
    q = f" {normalizar(pregunta)} "
    for n in NODOS_PROYECTO:
        if re.search(rf"\b{n}\b", q):
            return n
    for n, alias in NOMBRES_NODO.items():
        if any(f" {a} " in q for a in alias if len(a) > 3):
            return n
    return None


def intencion(pregunta: str) -> str:
    """Enrutador simple y transparente (reglas). 'calculo' -> funciones; 'contexto' -> RAG."""
    q = normalizar(pregunta)
    if re.search(r"hora pico|a que hora|cuant|volumen|cuantos|predic|cuanto trafico|motos|porcentaje|pesados", q):
        return "calculo"
    return "contexto"


@dataclass
class Fragmento:
    texto: str
    fuente: str


def construir_corpus(datos: Path, docs: Path) -> list:
    frs = []
    obs_path = datos / "observaciones_campo.csv"
    if obs_path.exists():
        obs = pd.read_csv(obs_path)
        for r in obs.itertuples():
            nodo = ETIQUETA_NODO.get(int(r.nodo), r.nodo)
            frs.append(Fragmento(f"Nodo {r.nodo} ({nodo}), {r.fecha}, acceso {r.acceso_nombre}: {r.observacion}",
                                 f"Estudio {r.estudio} (nota de campo)"))
    alertas_path = datos / "alertas_calidad.csv"
    if alertas_path.exists():
        for r in pd.read_csv(alertas_path).itertuples():
            frs.append(Fragmento(f"Alerta de calidad nodo {r.nodo}: {r.tipo_alerta} {r.detalle}",
                                 f"Estudio {r.estudio} (alerta de calidad)"))
    for md in sorted(docs.glob("*.md")):
        for bloque in re.split(r"\n(?=#+ )", md.read_text(encoding="utf-8")):
            if bloque.strip():
                frs.append(Fragmento(bloque.strip(), f"{md.name}"))
    return frs


class Buscador:
    """Recuperación TF-IDF (línea base). Reemplazable por embeddings para comparar."""

    def __init__(self, fragmentos: list):
        self.frs = fragmentos
        self.vec = TfidfVectorizer(preprocessor=normalizar, stop_words=sorted(VACIAS),
                                   ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        self.M = self.vec.fit_transform([f.texto for f in fragmentos])

    def buscar(self, pregunta: str, k: int = 5, nodo=None, minimo: float = 0.15):
        """Top-k fragmentos. Si la pregunta nombra un nodo, solo busca en ese nodo y en
        los documentos generales. Por debajo de `minimo` no se devuelve nada."""
        s = (self.M @ self.vec.transform([expandir(pregunta)]).T).toarray().ravel()
        if nodo is not None:
            s = s * np.array([1.0 if (f"Nodo {nodo} " in f.texto or f"nodo {nodo}:" in f.texto
                                      or not f.texto.lower().startswith(("nodo", "alerta"))) else 0.0
                              for f in self.frs])
        idx = [i for i in np.argsort(-s)[:k] if s[i] >= minimo]
        return [(self.frs[i], float(s[i])) for i in idx]


PROMPT_SISTEMA = (
    "Eres el asistente de 'Bogotá se Mueve'. Respondes en español claro a ciudadanos. "
    "Usa SOLO la información de los fragmentos entregados. Cita la fuente entre corchetes "
    "después de cada afirmación. Si la información no está en los fragmentos, responde "
    "exactamente: 'No tengo ese dato en las fuentes disponibles.' No inventes cifras."
)


def llamar_llm(pregunta: str, contexto: str):
    clave = os.getenv("LLM_API_KEY")
    if not clave:
        return None
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    r = requests.post(f"{base}/chat/completions", timeout=60,
                      headers={"Authorization": f"Bearer {clave}"},
                      json={"model": os.getenv("LLM_MODEL", "gpt-4o-mini"), "temperature": 0,
                            "messages": [{"role": "system", "content": PROMPT_SISTEMA},
                                         {"role": "user", "content": f"Fragmentos:\n{contexto}\n\nPregunta: {pregunta}"}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


PALABRAS_LUGAR = {w for et in ETIQUETA_NODO.values() for w in normalizar(et).split()} | {
    w for al in NOMBRES_NODO.values() for a in al for w in normalizar(a).split()} | {
    str(n) for n in NODOS_PROYECTO}


def cobertura(pregunta: str, texto: str) -> float:
    """Fracción de términos TEMÁTICOS de la pregunta (sin el nombre del lugar) que aparecen,
    o sus sinónimos, en el contenido del fragmento (sin su encabezado de nodo)."""
    terminos = [w for w in normalizar(pregunta).split()
                if w not in VACIAS and w not in PALABRAS_LUGAR and len(w) > 2]
    if not terminos:
        return 0.0
    contenido = texto.split(": ", 1)[1] if texto.lower().startswith(("nodo", "alerta")) else texto
    t = f" {normalizar(contenido)} "
    return sum(any(f" {x}" in t for x in SINONIMOS.get(w, w).split()) for w in terminos) / len(terminos)


def responder_contexto(buscador: Buscador, pregunta: str, k: int = 5) -> str:
    nodo = detectar_nodo(pregunta)
    vistos, hits = set(), []
    for f, sc in buscador.buscar(pregunta, k=4 * k, nodo=nodo):
        if f.texto not in vistos and cobertura(pregunta, f.texto) >= 0.5:
            vistos.add(f.texto)
            hits.append((f, sc))
    hits = hits[:k]
    if not hits:
        return "No tengo ese dato en las fuentes disponibles."
    contexto = "\n".join(f"- {f.texto} [{f.fuente}]" for f, _ in hits)
    try:
        r = llamar_llm(pregunta, contexto)
    except Exception as e:  # noqa: BLE001 - si el LLM falla, se responde extractivo
        r = None
        contexto += f"\n\n(El modelo de lenguaje no respondió: {type(e).__name__})"
    return r or ("Esto es lo que encontré en las fuentes:\n\n" + contexto)
