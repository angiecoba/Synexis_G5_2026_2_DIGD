"""App Gradio de Bogotá se Mueve (base).

Pestañas: Asistente · Explorar nodo · Predecir · Calidad de datos · Acerca de.
Lee la carpeta liviana data/app/ (se genera con `python -m bsm.preparar_app`).
Variables de entorno (en Render: Environment):
  BSM_APP     carpeta de datos de la app (por defecto data/app)
  PORT        puerto (Render lo define solo; por defecto 7860)
  LLM_API_KEY, LLM_BASE_URL, LLM_MODEL  (opcionales) para redactar las respuestas
"""
import json
import os
import sys
from functools import lru_cache
from pathlib import Path

import gradio as gr
import joblib
import pandas as pd
import plotly.express as px

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ / "src"))

from bsm.catalogo import FESTIVOS  # noqa: E402
from bsm.modelo import predecir_dia  # noqa: E402
from bsm.rag import (ETIQUETA_NODO, Buscador, construir_corpus, detectar_nodo,  # noqa: E402
                     intencion, responder_contexto)

APP_DATOS = Path(os.getenv("BSM_APP", RAIZ / "data" / "app"))
OPCIONES_NODO = [f"{n} · {e}" for n, e in ETIQUETA_NODO.items()]
TIPOS_DIA = {"Día hábil": "habil", "Fin de semana": "finde", "Festivo": "festivo"}
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NOMBRE_TIPO = {"habil": "día hábil", "finde": "fin de semana", "festivo": "festivo"}
COLUMNAS_ESTUDIOS = {
    "estudio": "Estudio", "fecha_estudio": "Fecha", "dia_semana": "Día", "cobertura_tipo": "Cobertura",
    "veh_motorizados_5a23": "Vehículos motorizados (5:00–23:00)", "hora_pico": "Hora pico",
    "pct_motos": "% motos", "pct_pesados": "% pesados", "alerta_calidad": "Alerta de calidad"}
EXPLICACION_ALERTA = {
    "ID_REPETIDO": "El mismo número de estudio de la SDM aparece en varias fechas",
    "PARTICIPACION_ATIPICA": "Un tipo de vehículo tiene una participación muy distinta a la habitual del nodo "
                             "(posibles columnas corridas o mal etiquetadas)",
    "CAMBIO_DE_METODO": "Se empezaron a contar bicicletas en ciclorruta: el total de bicis no es comparable",
}


@lru_cache(maxsize=1)
def cargar():
    horas = pd.read_parquet(APP_DATOS / "horas.parquet")
    resumen = pd.read_csv(APP_DATOS / "estudios_resumen.csv")
    alertas = pd.read_csv(APP_DATOS / "alertas_calidad.csv")
    artefacto = joblib.load(APP_DATOS / "modelo_volumen.joblib")
    metricas = json.loads((APP_DATOS / "metricas.json").read_text())
    buscador = Buscador(construir_corpus(APP_DATOS, RAIZ / "docs"))
    return horas, resumen, alertas, artefacto, metricas, buscador


HORAS_24 = [f"{h:02d}:00" for h in range(24)]


def eje_horas(fig, titulo="Hora del día (formato 24 horas)"):
    """Eje X con todas las horas en formato 24 h y separadores colombianos (17.933)."""
    fig.update_xaxes(tickmode="array", tickvals=list(range(24)), ticktext=HORAS_24,
                     tickangle=-45, title=titulo, range=[-0.5, 23.5])
    fig.update_layout(separators=",.", hoverlabel=dict(font_size=14))
    return fig


def franja(h) -> str:
    h = int(h)
    return f"{h:02d}:00–{(h + 1) % 24:02d}:00"


def miles(x) -> str:
    """Formato colombiano: 17.687 (punto de miles)."""
    return f"{x:,.0f}".replace(",", ".")


def nodo_de(opcion: str) -> int:
    return int(str(opcion).split("·")[0].strip())


def perfil_historico(horas, nodo, tipo):
    h = horas[(horas.nodo == nodo) & (horas.tipo_dia == tipo)]
    por_estudio = h.groupby(["estudio", "hora"]).veh.sum().reset_index()
    return (por_estudio.groupby("hora").veh.agg(mediana="median", p25=lambda s: s.quantile(.25),
                                                 p75=lambda s: s.quantile(.75), estudios="count")
            .reset_index())


# ------------------------------------------------------------------ asistente
def responder_calculo(pregunta: str) -> str:
    horas, resumen, *_ = cargar()
    nodo = detectar_nodo(pregunta)
    if nodo is None:
        return ("¿Sobre qué punto preguntas? Tengo datos de: "
                + "; ".join(f"{n} ({e})" for n, e in ETIQUETA_NODO.items()) + ".")
    q = pregunta.lower()
    tipo = "finde" if any(w in q for w in ["sábado", "sabado", "domingo", "fin de semana"]) else (
        "festivo" if "festivo" in q else "habil")
    p = perfil_historico(horas, nodo, tipo)
    if p.empty:
        return f"No tengo estudios de tipo '{tipo}' para el nodo {nodo}."
    pico = p.loc[p.mediana.idxmax()]
    r = resumen[(resumen.nodo == nodo) & (resumen.cobertura_tipo == "completa")]
    texto = (f"**{ETIQUETA_NODO[nodo]} (nodo {nodo})**, {dict((v, k) for k, v in TIPOS_DIA.items())[tipo].lower()}:\n\n"
             f"- Hora de mayor tráfico: **{int(pico.hora)}:00–{int(pico.hora)+1}:00**, con una mediana de "
             f"**{miles(pico.mediana)} vehículos motorizados** (entre {miles(pico.p25)} y {miles(pico.p75)} "
             f"en la mitad central de los días), según {int(pico.estudios)} estudios.\n")
    if len(r):
        texto += (f"- Participación de motos: mediana **{r.pct_motos.median():.0f} %**; vehículos pesados: "
                  f"**{r.pct_pesados.median():.0f} %**.\n")
    fechas = r.fecha_estudio.sort_values()
    if len(fechas):
        texto += f"\nFuente: {len(r)} estudios completos del Observatorio de Movilidad (SDM), {fechas.iloc[0]} a {fechas.iloc[-1]}."
    return texto


def chat(pregunta, historial):
    *_, buscador = cargar()
    if intencion(pregunta) == "calculo":
        return responder_calculo(pregunta)
    return responder_contexto(buscador, pregunta)


# ------------------------------------------------------------------ explorar / predecir
def explorar(opcion, tipo_txt):
    horas, resumen, *_ = cargar()
    nodo, tipo = nodo_de(opcion), TIPOS_DIA[tipo_txt]
    p = perfil_historico(horas, nodo, tipo)
    n_est = int(p.estudios.max()) if len(p) else 0
    fig = px.line(p, x="hora", y="mediana", markers=True,
                  labels={"hora": "Hora del día", "mediana": "Vehículos por hora"},
                  title=f"Perfil horario · {ETIQUETA_NODO[nodo]} · {tipo_txt} · {n_est} estudios"
                        if n_est else f"Sin estudios de tipo «{tipo_txt}» para {ETIQUETA_NODO[nodo]}")
    fig.update_traces(customdata=[franja(h) for h in p.hora],
                      hovertemplate="%{customdata}<br>%{y:,.0f} vehículos por hora (mediana)<extra></extra>")
    eje_horas(fig)
    fig.add_scatter(x=p.hora, y=p.p75, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=p.hora, y=p.p25, mode="lines", line=dict(width=0), fill="tonexty",
                    name="50 % central de los días", hoverinfo="skip")
    cols = ["estudio", "fecha_estudio", "dia_semana", "cobertura_tipo", "veh_motorizados_5a23",
            "hora_pico", "pct_motos", "pct_pesados", "alerta_calidad"]
    tabla = resumen[resumen.nodo == nodo][cols].sort_values("fecha_estudio", ascending=False).copy()
    tabla["hora_pico"] = tabla["hora_pico"].map(lambda h: franja(h) if pd.notna(h) else "")
    tabla["veh_motorizados_5a23"] = tabla["veh_motorizados_5a23"].map(lambda x: miles(x) if pd.notna(x) else "")
    tabla["alerta_calidad"] = tabla["alerta_calidad"].fillna("")
    return fig, tabla.rename(columns=COLUMNAS_ESTUDIOS)


def predecir(opcion, fecha, festivo):
    horas, *_, artefacto, metricas, _ = cargar()
    nodo = nodo_de(opcion)
    try:
        f = pd.Timestamp(fecha)
    except ValueError:
        return None, "Escribe la fecha como AAAA-MM-DD, por ejemplo 2026-12-08."
    es_festivo_oficial = bool(FESTIVOS and f in FESTIVOS)
    festivo = bool(festivo) or es_festivo_oficial
    tipo = "festivo" if festivo else ("finde" if f.dayofweek >= 5 else "habil")
    n_tipo = horas[(horas.nodo == nodo) & (horas.tipo_dia == tipo)].estudio.nunique()
    X = predecir_dia(artefacto, nodo, f, festivo)
    tot = X.groupby("hora").prediccion.sum().reset_index()
    metodo = X.metodo.iloc[0]
    fig = px.bar(tot, x="hora", y="prediccion",
                 labels={"hora": "Hora", "prediccion": "Vehículos estimados"},
                 title=f"Estimación · {ETIQUETA_NODO[nodo]} · {DIAS_ES[f.dayofweek]} {f:%d-%m-%Y}"
                       + (" (festivo)" if festivo else ""))
    fig.update_traces(customdata=[franja(h) for h in tot.hora],
                      hovertemplate="%{customdata}<br>%{y:,.0f} vehículos estimados<extra></extra>")
    eje_horas(fig, "Hora del día (formato 24 h; cada barra es la hora que empieza ahí)")
    pico = tot.loc[tot.prediccion.idxmax()]
    m = metricas["por_nodo"].get(str(nodo), {})
    aviso = ""
    if es_festivo_oficial:
        aviso += "📅 Esta fecha es festivo en Colombia; se estimó como festivo.\n\n"
    if n_tipo == 0:
        aviso += (f"⚠️ **No hay ningún estudio de tipo «{NOMBRE_TIPO[tipo]}» en este nodo.** La estimación "
                  "usa el patrón de los otros tipos de día y puede no representar ese día. Tómala con cautela.\n\n")
    elif n_tipo < 5:
        aviso += f"⚠️ Solo hay {n_tipo} estudio(s) de tipo «{NOMBRE_TIPO[tipo]}» en este nodo: la estimación es poco robusta.\n\n"
    aviso += (f"**Hora de más tráfico estimada: {franja(pico.hora)}**, con unos "
              f"**{miles(pico.prediccion)} vehículos**.\n\n")
    nota = aviso + (f"Método: **{'modelo (gradient boosting)' if metodo == 'modelo' else 'promedio histórico'}**. "
            + (f"Error típico en la prueba con 2026: {str(m.get('wape_modelo' if metodo == 'modelo' else 'wape_rival')).replace('.', ',')} % "
               f"del volumen ({m.get('estudios_test')} {'estudio no visto' if m.get('estudios_test') == 1 else 'estudios no vistos'} al entrenar)." if m else
               "Este nodo no tiene estudios de 2026 para medir el error; úsese como referencia.")
            + " Es una estimación del patrón típico, no un conteo real.")
    return fig, nota


def calidad():
    _, resumen, alertas, *_ = cargar()
    a = alertas.assign(explicacion=alertas.tipo_alerta.map(EXPLICACION_ALERTA))
    conteo = (a.groupby(["nodo", "tipo_alerta", "explicacion"]).estudio.nunique()
                .reset_index(name="estudios")
                .rename(columns={"nodo": "Nodo", "tipo_alerta": "Tipo", "explicacion": "Qué significa",
                                 "estudios": "Estudios afectados"}))
    detalle = a[["nodo", "estudio", "tipo_alerta", "detalle"]].rename(
        columns={"nodo": "Nodo", "estudio": "Estudio", "tipo_alerta": "Tipo", "detalle": "Detalle"})
    return conteo, detalle


# ------------------------------------------------------------------ interfaz
with gr.Blocks(title="Bogotá se Mueve") as demo:
    gr.Markdown("# Bogotá se Mueve\nDatos de aforos del Observatorio de Movilidad de Bogotá, "
                "explicados en lenguaje claro y con su fuente.\n\n"
                "<small>Mesa 1 · DIGD · Docente: Nelson Gustavo Fajardo Belmonte · Angie Valentina Coba Perdomo, "
                "Diego Alejandro Sánchez Parra, Laura Ximena Cifuentes Chauta, Luis Alejandro Flórez Rivera, "
                "Luwin Alfonso Ruiz Pinzón · Synexis · Tech Innovate Summit, Escuela Colombiana de Ingeniería "
                "Julio Garavito</small>")
    with gr.Tab("Asistente"):
        gr.ChatInterface(chat, textbox=gr.Textbox(placeholder="Escribe tu pregunta sobre el tráfico en estos puntos…",
                                                  submit_btn=True), examples=[
            "¿A qué hora hay más tráfico en la Autopista Norte con 170 un día hábil?",
            "¿Qué pasó en la Vía a Cota con 116 los días de lluvia?",
            "¿Qué porcentaje de motos pasa por la Av. 68 con 72?",
            "¿Qué es un auto equivalente (ACE)?"])
    with gr.Tab("Explorar nodo"):
        with gr.Row():
            n1 = gr.Dropdown(OPCIONES_NODO, value=OPCIONES_NODO[0], label="Nodo")
            t1 = gr.Radio(list(TIPOS_DIA), value="Día hábil", label="Tipo de día")
        g1, tab1 = gr.Plot(), gr.Dataframe(wrap=True)
        for c in (n1, t1):
            c.change(explorar, [n1, t1], [g1, tab1])
        demo.load(explorar, [n1, t1], [g1, tab1])
    with gr.Tab("Predecir"):
        with gr.Row():
            n2 = gr.Dropdown(OPCIONES_NODO, value=OPCIONES_NODO[0], label="Nodo")
            f2 = gr.Textbox(value=str(pd.Timestamp.today().date()), label="Fecha (AAAA-MM-DD)")
            fe2 = gr.Checkbox(label="Es festivo (los festivos oficiales se detectan solos)")
        b2 = gr.Button("Estimar")
        nota2 = gr.Markdown()   # el aviso va ARRIBA del gráfico, para que se lea sin bajar
        g2 = gr.Plot()
        b2.click(predecir, [n2, f2, fe2], [g2, nota2])
    with gr.Tab("Calidad de datos"):
        gr.Markdown("Anomalías encontradas en los archivos oficiales. Se documentan; no se corrigen en silencio.")
        c1, c2 = gr.Dataframe(label="Resumen"), gr.Dataframe(label="Detalle", wrap=True)
        demo.load(calidad, None, [c1, c2])
    with gr.Tab("Acerca de"):
        gr.Markdown((RAIZ / "docs" / "acerca.md").read_text(encoding="utf-8"))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", 7860)))
