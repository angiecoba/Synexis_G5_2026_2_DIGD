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
import re
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
from bsm.lenguaje import (EXPLICA_MEDIANA, EXPLICA_RANGO, CATEGORIAS, aproximar,  # noqa: E402
                          de_cada_10, explicar_error, hora_amigable)
from bsm.modelo import predecir_dia  # noqa: E402
from bsm.rag import (ETIQUETA_NODO, Buscador, construir_corpus, detectar_nodo,  # noqa: E402
                     intencion, responder_contexto)

APP_DATOS = Path(os.getenv("BSM_APP", RAIZ / "data" / "app"))
OPCIONES_NODO = [f"{n} · {e}" for n, e in ETIQUETA_NODO.items()]
TIPOS_DIA = {"Día hábil": "habil", "Fin de semana": "finde", "Festivo": "festivo"}
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NOMBRE_TIPO = {"habil": "día hábil", "finde": "fin de semana", "festivo": "festivo"}
COLUMNAS_ESTUDIOS = {
    "fecha_estudio": "Fecha", "dia_semana": "Día", "veh_motorizados_5a23": "Vehículos en el día (5 a. m.–11 p. m.)",
    "hora_pico": "Hora con más tráfico", "pct_motos": "% motos", "pct_pesados": "% buses y camiones",
    "cobertura_tipo": "¿Se contó todo el día?", "alerta_calidad": "Alerta de calidad", "estudio": "Código del estudio"}
NOMBRE_ALERTA = {
    "ID_REPETIDO": "Número de estudio repetido",
    "PARTICIPACION_ATIPICA": "Cifra sospechosa",
    "CAMBIO_DE_METODO": "Cambió la forma de contar",
}
EXPLICACION_ALERTA = {
    "ID_REPETIDO": "La Secretaría usó el mismo número para identificar estudios de días distintos. "
                   "No cambia los conteos, pero complica rastrear de dónde sale cada dato.",
    "PARTICIPACION_ATIPICA": "Ese día, un tipo de vehículo aparece en una proporción muy distinta a la de días "
                             "parecidos (por ejemplo, casi sin carros y lleno de bicicletas). Puede ser un error del "
                             "archivo, como números en la columna equivocada, o un día realmente especial. "
                             "Hay que revisarlo antes de usar esa cifra.",
    "CAMBIO_DE_METODO": "Desde ese día también se contaron las bicicletas de la ciclorruta. Por eso parece "
                        "que hay muchas más bicis, pero es porque se contó un lugar más.",
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


from bsm.lenguaje import miles  # noqa: E402,F811  (formato 17.687)


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
        return ("No tengo datos de ese punto. Puedo contarte sobre el tráfico en estos 6 lugares de Bogotá:\n\n"
                + "\n".join(f"- {e}" for e in ETIQUETA_NODO.values())
                + "\n\nEscribe tu pregunta nombrando uno de ellos.")
    q = pregunta.lower()
    tipo = "finde" if any(w in q for w in ["sábado", "sabado", "domingo", "fin de semana"]) else (
        "festivo" if "festivo" in q else "habil")
    cuando = {"habil": "entre semana (de lunes a viernes)", "finde": "los fines de semana",
              "festivo": "los festivos"}[tipo]
    p = perfil_historico(horas, nodo, tipo)
    if p.empty:
        return (f"Todavía no hay días medidos {cuando} en {ETIQUETA_NODO[nodo]}, así que no puedo "
                "darte una cifra confiable. Prueba con otro tipo de día.")
    pico = p.loc[p.mediana.idxmax()]
    r = resumen[(resumen.nodo == nodo) & (resumen.cobertura_tipo == "completa")]
    fechas = r.fecha_estudio.sort_values()
    texto = (f"### 🚗 {ETIQUETA_NODO[nodo]}, {cuando}\n\n"
             f"**La hora con más tráfico es {hora_amigable(pico.hora)}.** "
             f"En esa hora pasan normalmente **unos {aproximar(pico.mediana)} vehículos** con motor "
             f"(carros, motos, buses y camiones). Es decir, unos {aproximar(pico.mediana / 60)} por minuto.\n\n"
             f"- En la mitad de los días medidos, esa hora tuvo **entre {aproximar(pico.p25)} y "
             f"{aproximar(pico.p75)} vehículos**.\n")
    if len(r):
        texto += (f"- **{de_cada_10(r.pct_motos.median()).capitalize()} son motos** "
                  f"({r.pct_motos.median():.0f} %), y **{de_cada_10(r.pct_pesados.median())} son buses o "
                  f"camiones** ({r.pct_pesados.median():.0f} %).\n")
    texto += (f"\nℹ️ **¿De dónde salen estas cifras?** De {int(pico.estudios)} días en que la Secretaría "
              f"Distrital de Movilidad contó, uno por uno, los vehículos que pasaron por este cruce"
              + (f" (entre {fechas.iloc[0][:4]} y {fechas.iloc[-1][:4]})" if len(fechas) else "")
              + f". {EXPLICA_MEDIANA}\n\n"
              f"<small>Fuente: Observatorio de Movilidad de Bogotá (SDM), nodo {nodo}.</small>")
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
                  title=f"{ETIQUETA_NODO[nodo]} · {tipo_txt.lower()}" if n_est
                        else f"Sin días medidos de tipo «{tipo_txt.lower()}» en {ETIQUETA_NODO[nodo]}")
    fig.update_traces(name="Lo normal (mediana)", showlegend=True,
                      customdata=[hora_amigable(h) for h in p.hora],
                      hovertemplate="%{customdata}<br>Normalmente: %{y:,.0f} vehículos<extra></extra>")
    eje_horas(fig)
    fig.add_scatter(x=p.hora, y=p.p75, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=p.hora, y=p.p25, mode="lines", line=dict(width=0), fill="tonexty",
                    name="Rango habitual (la mitad de los días)", hoverinfo="skip")
    if n_est:
        pico = p.loc[p.mediana.idxmax()]
        guia = (f"**Cómo leer el gráfico:** la **línea azul** muestra cuántos vehículos pasan normalmente en "
                f"cada hora; la **franja verde** es el rango habitual. Se basa en **{n_est} días medidos**. "
                f"La hora con más tráfico es **{hora_amigable(pico.hora)}**, con unos "
                f"**{aproximar(pico.mediana)} vehículos**.\n\n"
                f"<small>{EXPLICA_MEDIANA} {EXPLICA_RANGO}</small>")
    else:
        guia = (f"⚠️ **No hay días medidos de tipo «{tipo_txt.lower()}» en este punto**, por eso el gráfico "
                "está vacío. Prueba con otro tipo de día.")
    cols = ["fecha_estudio", "dia_semana", "veh_motorizados_5a23", "hora_pico", "pct_motos", "pct_pesados",
            "cobertura_tipo", "alerta_calidad", "estudio"]
    tabla = resumen[resumen.nodo == nodo][cols].sort_values("fecha_estudio", ascending=False).copy()
    tabla["hora_pico"] = tabla["hora_pico"].map(lambda h: hora_amigable(h) if pd.notna(h) else "")
    tabla["veh_motorizados_5a23"] = tabla["veh_motorizados_5a23"].map(lambda x: miles(x) if pd.notna(x) else "—")
    for c in ["pct_motos", "pct_pesados"]:
        tabla[c] = tabla[c].map(lambda x: f"{x:.0f} %" if pd.notna(x) else "")
    tabla["cobertura_tipo"] = tabla["cobertura_tipo"].map({"completa": "Sí", "parcial": "No, solo algunas horas"})
    tabla["alerta_calidad"] = tabla["alerta_calidad"].fillna("")
    return guia, fig, tabla.rename(columns=COLUMNAS_ESTUDIOS)


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
    dias_nodo = horas[horas.nodo == nodo].estudio.nunique()
    nota = ""
    if es_festivo_oficial:
        nota += "📅 Esta fecha es **festivo** en Colombia, así que se calculó como festivo.\n\n"
    if n_tipo == 0:
        nota += (f"⚠️ **Ojo: en este punto nunca se ha medido el tráfico en un {NOMBRE_TIPO[tipo]}.** "
                 "Por eso el cálculo usa lo que pasa en otros días y puede no parecerse a la realidad. "
                 "Tómalo solo como una idea general.\n\n")
    elif n_tipo < 5:
        nota += (f"⚠️ Solo hay {n_tipo} {'día medido' if n_tipo == 1 else 'días medidos'} de tipo "
                 f"«{NOMBRE_TIPO[tipo]}» en este punto: el cálculo puede fallar más de lo normal.\n\n")
    nota += (f"### Se espera más tráfico {hora_amigable(pico.hora)}: unos **{aproximar(pico.prediccion)} "
             f"vehículos** en esa hora.\n\n")
    if metodo == "modelo":
        como = (f"**¿Cómo se calcula?** Con un modelo de inteligencia artificial que aprendió, a partir de "
                f"{dias_nodo} días medidos en este punto, cómo cambia el tráfico según la hora, el día de la "
                "semana, el mes y los festivos.")
    else:
        como = (f"**¿Cómo se calcula?** Con el promedio de lo que pasó, hora por hora, en los días medidos "
                f"parecidos ({dias_nodo} días en este punto). Aquí funciona mejor que un modelo más complejo "
                "porque hay pocos días medidos.")
    if m:
        w = m.get("wape_modelo" if metodo == "modelo" else "wape_rival")
        n_test = m.get("estudios_test")
        confianza = (f"**¿Qué tan confiable es?** Lo probamos con {n_test} "
                     f"{'día' if n_test == 1 else 'días'} de 2026 que el cálculo no conocía: "
                     f"{explicar_error(w)}." + (" Como solo se probó con un día, tómalo con cautela."
                                                 if n_test == 1 else ""))
    else:
        confianza = ("**¿Qué tan confiable es?** No hay días de 2026 en este punto para comprobarlo, "
                     "así que úsalo solo como referencia.")
    nota += f"{como}\n\n{confianza}\n\n<small>Es lo esperado en un día típico, no el tráfico en vivo.</small>"
    return fig, nota


def detalle_claro(tipo, detalle) -> str:
    """'CAMION 0.8% vs 5.4% típico' -> 'Camiones: 0,8 % ese día, cuando lo normal es 5,4 %'."""
    m = re.match(r"(\w+) ([\d.]+)% vs ([\d.]+)% típico(?: \((.*)\))?", str(detalle))
    if tipo == "PARTICIPACION_ATIPICA" and m:
        cat, hoy, normal, base = m.groups()
        comparado = "en días del mismo tipo" if base == "mismo tipo de día" else "en este punto"
        return (f"{CATEGORIAS.get(cat, cat.lower()).capitalize()}: {hoy.replace('.', ',')} % ese día, "
                f"cuando lo normal {comparado} es {normal.replace('.', ',')} %")
    if tipo == "CAMBIO_DE_METODO":
        return "Se sumaron las bicicletas de la ciclorruta: el total de bicis no se puede comparar con otros días"
    if tipo == "ID_REPETIDO":
        return str(detalle).replace("ID SDM", "El número de estudio").replace("repetido en varias fechas",
                                                                           "se usó también en otras fechas")
    return str(detalle)


def calidad():
    _, resumen, alertas, *_ = cargar()
    a = alertas.assign(nombre=alertas.tipo_alerta.map(NOMBRE_ALERTA),
                       explicacion=alertas.tipo_alerta.map(EXPLICACION_ALERTA),
                       lugar=alertas.nodo.map(ETIQUETA_NODO))
    conteo = (a.groupby(["lugar", "nombre", "explicacion"]).estudio.nunique()
                .reset_index(name="dias")
                .rename(columns={"lugar": "Lugar", "nombre": "Problema", "explicacion": "Qué significa",
                                 "dias": "Días afectados"}))
    a["detalle_claro"] = [detalle_claro(t, d) for t, d in zip(a.tipo_alerta, a.detalle)]
    a["fecha"] = a.estudio.str.extract(r"_(\d{8})_")[0].map(lambda x: f"{x[:4]}-{x[4:6]}-{x[6:]}")
    detalle = a[["lugar", "fecha", "nombre", "detalle_claro", "estudio"]].rename(
        columns={"lugar": "Lugar", "fecha": "Fecha", "nombre": "Problema", "detalle_claro": "Qué se encontró",
                 "estudio": "Código del estudio"})
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
            "¿Qué es un auto equivalente (ACE)?",
            "¿Los datos de aforos tienen errores?"])
    with gr.Tab("Explorar un punto"):
        with gr.Row():
            n1 = gr.Dropdown(OPCIONES_NODO, value=OPCIONES_NODO[0], label="Punto de la ciudad (nodo)")
            t1 = gr.Radio(list(TIPOS_DIA), value="Día hábil", label="Tipo de día")
        guia1 = gr.Markdown()
        g1 = gr.Plot()
        gr.Markdown("**Días medidos en este punto.** Cada fila es un día en que la Secretaría de Movilidad "
                    "contó los vehículos. Si dice «No, solo algunas horas», ese día no se contó completo y por "
                    "eso no tiene total.")
        tab1 = gr.Dataframe(wrap=True)
        for c in (n1, t1):
            c.change(explorar, [n1, t1], [guia1, g1, tab1])
        demo.load(explorar, [n1, t1], [guia1, g1, tab1])
    with gr.Tab("¿Cómo estará?"):
        gr.Markdown("Elige un punto y una fecha para ver cuánto tráfico se espera en cada hora de un día típico.")
        with gr.Row():
            n2 = gr.Dropdown(OPCIONES_NODO, value=OPCIONES_NODO[0], label="Punto de la ciudad (nodo)")
            f2 = gr.Textbox(value=str(pd.Timestamp.today().date()), label="Fecha (AAAA-MM-DD)")
            fe2 = gr.Checkbox(label="Es festivo (los festivos oficiales se detectan solos)")
        b2 = gr.Button("Ver el tráfico esperado", variant="primary")
        nota2 = gr.Markdown()   # el aviso va ARRIBA del gráfico, para que se lea sin bajar
        g2 = gr.Plot()
        b2.click(predecir, [n2, f2, fe2], [g2, nota2])
    with gr.Tab("Calidad de datos"):
        gr.Markdown("### ¿Qué tan confiables son los datos?\n"
                    "Al revisar los archivos oficiales de la Secretaría de Movilidad encontramos errores. "
                    "**No los escondemos ni los corregimos a escondidas:** los mostramos aquí para que sepas "
                    "qué tan confiable es cada cifra. Cuando un día tiene una alerta, también aparece en la tabla "
                    "de «Explorar nodo».")
        c1 = gr.Dataframe(label="Resumen por lugar", wrap=True)
        c2 = gr.Dataframe(label="Detalle día por día", wrap=True)
        demo.load(calidad, None, [c1, c2])
    with gr.Tab("Acerca de"):
        gr.Markdown((RAIZ / "docs" / "acerca.md").read_text(encoding="utf-8"))

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", 7860)))
