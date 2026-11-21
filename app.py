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
                     intencion, normalizar, responder_contexto)

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


@lru_cache(maxsize=1)
def cargar_extra():
    """Proporción de cada tipo de vehículo por hora y ubicación de los nodos."""
    mezcla = pd.read_parquet(APP_DATOS / "mezcla.parquet")
    nodos = pd.read_csv(APP_DATOS / "nodos.csv")
    nodos["lugar"] = nodos.nodo.map(ETIQUETA_NODO)
    return mezcla, nodos


COLORES_VEHICULO = {"Carros y camionetas": "#4C78A8", "Motos": "#F58518", "Buses": "#54A24B",
                    "Camiones": "#B279A2"}
ORDEN_VEHICULO = list(COLORES_VEHICULO)

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
from bsm.lenguaje import NINGUN_PERIODO, NOMBRE_PERIODO, UN_PERIODO, periodo_de  # noqa: E402

MIN_DIAS_PERIODO = 3   # un periodo con menos días medidos no se dibuja: sería poco confiable
MIN_DIAS_DESTACAR = 7  # solo se destaca (más/menos cargado) un periodo con al menos estos días
COMPARAR = {"No comparar": None, "Por año": "anio", "Por mes": "mes", "Por temporada": "temporada"}


@lru_cache(maxsize=1)
def cargar_mezcla_diaria():
    return pd.read_parquet(APP_DATOS / "mezcla_diaria.parquet")


def perfil_por_periodo(nodo, tipo, por):
    """Tráfico normal por hora en cada periodo. Devuelve (tabla, orden, periodos descartados)."""
    horas, *_ = cargar()
    h = horas[(horas.nodo == nodo) & (horas.tipo_dia == tipo)]
    dia = h.groupby(["estudio", "fecha", "hora"], as_index=False).veh.sum()
    dia["periodo"], orden = periodo_de(dia.fecha, por)
    dias = dia.groupby("periodo").estudio.nunique()
    validos = dias[dias >= MIN_DIAS_PERIODO]
    t = (dia[dia.periodo.isin(validos.index)].groupby(["periodo", "hora"], as_index=False)
            .veh.median().rename(columns={"veh": "mediana"}))
    t["dias"] = t.periodo.map(validos)
    return (t, [o for o in orden if o in validos.index],
            [o for o in orden if o in dias.index and o not in validos.index])  # en orden de calendario


def mezcla_por_periodo(nodo, tipo, por):
    """Porcentaje de cada tipo de vehículo en cada periodo (todo el día)."""
    m = cargar_mezcla_diaria()
    m = m[(m.nodo == nodo) & (m.tipo_dia == tipo)].copy()
    m["periodo"], orden = periodo_de(m.fecha, por)
    dias = m.groupby("periodo").fecha.nunique()
    validos = dias[dias >= MIN_DIAS_PERIODO]
    t = m[m.periodo.isin(validos.index)].groupby(["periodo", "grupo"], as_index=False).conteo.sum()
    t["porcentaje"] = 100 * t.conteo / t.groupby("periodo").conteo.transform("sum")
    t["dias"] = t.periodo.map(validos)
    return t, [o for o in orden if o in validos.index]


def etiqueta_periodo(periodo, dias):
    return f"{periodo} ({dias} días)"


def figura_periodos(t, orden, titulo):
    t = t.assign(serie=[etiqueta_periodo(p, d) for p, d in zip(t.periodo, t.dias)])
    orden_series = [etiqueta_periodo(o, t[t.periodo == o].dias.iloc[0]) for o in orden]
    fig = px.line(t, x="hora", y="mediana", color="serie", markers=True, title=titulo,
                  category_orders={"serie": orden_series},
                  labels={"mediana": "Vehículos por hora", "serie": ""})
    fig.update_traces(hovertemplate="%{fullData.name}: %{y:,.0f} vehículos<extra></extra>")
    fig.update_layout(hovermode="x unified", legend_title_text="")
    return eje_horas(fig)


def figura_mezcla_periodos(t, orden, titulo):
    t = t.assign(serie=[etiqueta_periodo(p, d) for p, d in zip(t.periodo, t.dias)])
    orden_series = [etiqueta_periodo(o, t[t.periodo == o].dias.iloc[0]) for o in orden]
    fig = px.bar(t, x="serie", y="porcentaje", color="grupo", title=titulo, text_auto=".0f",
                 category_orders={"serie": orden_series, "grupo": ORDEN_VEHICULO},
                 color_discrete_map=COLORES_VEHICULO,
                 labels={"serie": "", "porcentaje": "De cada 100 vehículos", "grupo": ""})
    fig.update_traces(hovertemplate="%{fullData.name}: %{y:.0f} de cada 100<extra></extra>")
    fig.update_layout(barmode="stack", yaxis_range=[0, 100], legend_title_text="")
    return fig


def texto_periodos(t, orden, descartados, por, lugar, tipo_txt):
    """Explicación en lenguaje claro de la comparación por periodos."""
    nombre = NOMBRE_PERIODO[por]
    if not orden:
        return (f"⚠️ En {lugar} ({tipo_txt}) no hay al menos {MIN_DIAS_PERIODO} días medidos en "
                f"{NINGUN_PERIODO[por]}, así que no se puede comparar por {nombre}. Prueba con otro tipo de día u otro punto.")
    picos = t.loc[t.groupby("periodo").mediana.idxmax()].set_index("periodo").reindex(orden)
    solidos, pocos = partir_por_dias(t, orden)
    txt = (f"Cada línea es {UN_PERIODO[por]}: muestra cuántos vehículos pasan normalmente en cada hora "
           f"en {lugar} ({tipo_txt}).")
    if len(solidos) > 1:
        p = picos.reindex(solidos)
        alto, bajo = p.mediana.idxmax(), p.mediana.idxmin()
        txt += (f" Entre los periodos con suficientes días medidos, la hora pico más cargada es en **{alto}** "
                f"(unos {aproximar(p.mediana[alto])} vehículos) y la más liviana en **{bajo}** "
                f"(unos {aproximar(p.mediana[bajo])}).")
    elif len(orden) > 1:
        txt += (f" Ningún par de periodos tiene suficientes días medidos (al menos {MIN_DIAS_DESTACAR}) para "
                "decir con confianza cuál es más cargado; mira las líneas solo como referencia.")
    txt += "\n\n" + aviso_pocos_dias(pocos, nombre)
    txt += (f"<small>Entre paréntesis está cuántos días se midieron en cada {nombre}.")
    if descartados:
        txt += (f" No se dibujan {enumerar([str(d) for d in descartados])} porque tienen menos de "
                f"{MIN_DIAS_PERIODO} días medidos.")
    return txt + "</small>"


def partir_por_dias(t, orden):
    """Separa los periodos con suficientes días para destacarlos de los que tienen pocos."""
    dias = t.groupby("periodo").dias.first()
    return ([o for o in orden if dias[o] >= MIN_DIAS_DESTACAR],
            [(o, int(dias[o])) for o in orden if dias[o] < MIN_DIAS_DESTACAR])


def aviso_pocos_dias(pocos, nombre, marca="la línea") -> str:
    if not pocos:
        return ""
    lista = enumerar([f"{o} ({d} días)" for o, d in pocos])
    return (f"⚠️ **Con pocos días medidos:** {lista}. Con menos de {MIN_DIAS_DESTACAR} días, {marca} puede "
            "reflejar un día particular (un cierre, la lluvia, un evento) más que lo normal, así que tómala con "
            "cautela; por eso no se usa para destacar.\n\n")


def texto_mezcla(t, orden, por):
    if not orden:
        return ""
    solidos, pocos = partir_por_dias(t, orden)
    motos = t[t.grupo == "Motos"].set_index("periodo").porcentaje.reindex(solidos).dropna()
    txt = "**¿Cambian los tipos de vehículo?** Cada barra suma 100: de cada 100 vehículos, cuántos son de cada tipo."
    if len(motos) > 1:
        txt += (f" Entre los periodos con suficientes días medidos, las motos van de **{motos.min():.0f} de cada "
                f"100** en {motos.idxmin()} a **{motos.max():.0f} de cada 100** en {motos.idxmax()}.")
    return txt + ("\n\n" + aviso_pocos_dias(pocos, NOMBRE_PERIODO[por], "la barra").rstrip() if pocos else "")


def nodo_de(opcion: str) -> int:
    return int(str(opcion).split("·")[0].strip())


def perfil_historico(horas, nodo, tipo):
    h = horas[(horas.nodo == nodo) & (horas.tipo_dia == tipo)]
    por_estudio = h.groupby(["estudio", "hora"]).veh.sum().reset_index()
    return (por_estudio.groupby("hora").veh.agg(mediana="median", p25=lambda s: s.quantile(.25),
                                                 p75=lambda s: s.quantile(.75), estudios="count")
            .reset_index())


def figura_mapa(nodo=None):
    """Mapa de los 6 puntos; si se indica un nodo, se resalta."""
    _, nodos = cargar_extra()
    n = nodos.assign(resaltado=nodos.nodo.eq(nodo) if nodo else True)
    n["tamano"] = n.resaltado.map({True: 18, False: 10})
    n["texto"] = [f"{r.lugar}<br>Nodo {r.nodo} · {r.dias} días medidos" for r in n.itertuples()]
    centro = n[n.nodo == nodo].iloc[0] if nodo else n[["lat", "lon"]].mean()
    fig = px.scatter_map(n, lat="lat", lon="lon", size="tamano", size_max=18,
                         color="resaltado" if nodo else None, hover_name="texto",
                         hover_data={"lat": False, "lon": False, "tamano": False, "resaltado": False},
                         color_discrete_map={True: "#E4572E", False: "#7F7F7F"},
                         zoom=14 if nodo else 10.5, center={"lat": centro.lat, "lon": centro.lon},
                         map_style="carto-positron", height=420)
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), showlegend=False,
                      title=(f"Ubicación · {ETIQUETA_NODO[nodo]}" if nodo else "Los 6 puntos de Bogotá con datos"))
    return fig


def figura_perfil(nodo, tipo):
    horas, *_ = cargar()
    p = perfil_historico(horas, nodo, tipo)
    fig = px.bar(p, x="hora", y="mediana", labels={"mediana": "Vehículos por hora"},
                 title=f"Tráfico normal por hora · {ETIQUETA_NODO[nodo]} · {NOMBRE_TIPO[tipo]}")
    pico = p.mediana.idxmax() if len(p) else None
    fig.update_traces(marker_color=["#E4572E" if i == pico else "#4C78A8" for i in p.index],
                      customdata=[hora_amigable(h) for h in p.hora],
                      hovertemplate="%{customdata}<br>Normalmente: %{y:,.0f} vehículos<extra></extra>")
    return eje_horas(fig), p


def desglose(nodo, tipo, total_por_hora: pd.DataFrame):
    """Reparte un total por hora según la proporción histórica de cada tipo de vehículo
    en días parecidos del mismo punto. Devuelve (tabla larga, tipo de día usado)."""
    mezcla, _ = cargar_extra()
    m = mezcla[(mezcla.nodo == nodo) & (mezcla.tipo_dia == tipo)]
    usado = tipo
    if m.empty:  # sin días de ese tipo: se usan los días hábiles, y se avisa
        m, usado = mezcla[(mezcla.nodo == nodo) & (mezcla.tipo_dia == "habil")], "habil"
    d = total_por_hora.merge(m[["hora", "grupo", "proporcion"]], on="hora", how="left")
    d["vehiculos"] = d.total * d.proporcion
    return d.dropna(subset=["grupo"]), usado


def enumerar(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def figura_desglose(d, titulo):
    fig = px.bar(d, x="hora", y="vehiculos", color="grupo", title=titulo,
                 category_orders={"grupo": ORDEN_VEHICULO}, color_discrete_map=COLORES_VEHICULO,
                 labels={"vehiculos": "Vehículos", "grupo": "Tipo de vehículo"})
    fig.update_traces(hovertemplate="%{fullData.name}: %{y:,.0f}<extra></extra>")
    fig.update_layout(barmode="stack", hovermode="x unified", legend_title_text="")
    return eje_horas(fig)


CAPACIDADES = (
    "Puedo ayudarte con estos 6 puntos de Bogotá: " + ", ".join(ETIQUETA_NODO.values()) + ".\n\n"
    "Prueba, por ejemplo:\n"
    "- «¿A qué hora hay más tráfico en la Autopista Norte con 170?»\n"
    "- «Muéstrame una gráfica de las horas de la Av. 68 con 72»\n"
    "- «¿Qué tipos de vehículos pasan por la Vía a Cota?»\n"
    "- «Muéstrame el mapa de los puntos»\n"
    "- «¿Qué pasó en la carrera 7 con 208 los días de lluvia?»\n"
    "- «¿Qué es un auto equivalente?»\n\n"
    "No tengo tráfico en vivo, precios, rutas ni datos de otros puntos de la ciudad.")


def que_pide(pregunta: str):
    """Pedidos de visualización que el asistente resuelve con datos (sin LLM)."""
    q = normalizar(pregunta)
    if re.search(r"\bmapa\b", q):
        return "mapa"
    if re.search(r"grafic|curva|dibuj|visualiz", q):
        return "grafica"
    if re.search(r"tipos? de vehiculo|que vehiculos|desglose|composicion|cuantos carros|cuantos buses|"
                 r"cuantos camiones|cuantas motos", q):
        return "vehiculos"
    if re.search(r"ubicacion|donde (queda|esta|estan)|localiza", q):
        return "mapa"
    if re.search(r"que puedes|que sabes|ayuda|como te uso|que preguntas", q):
        return "ayuda"
    return None


def periodo_en(pregunta: str):
    q = normalizar(pregunta)
    if re.search(r"por anos?\b|cada ano|entre anos|ano a ano|anual|ha cambiado|evolucion|a lo largo de los anos", q):
        return "anio"
    if re.search(r"por mes|\bmeses\b|mensual|cada mes", q):
        return "mes"
    if re.search(r"temporada|vacaciones|epoca del ano", q):
        return "temporada"
    return None


def tipo_de_dia_en(pregunta: str) -> str:
    q = normalizar(pregunta)
    if re.search(r"sabado|domingo|fin de semana", q):
        return "finde"
    return "festivo" if "festivo" in q else "habil"


def responder_periodos(pedido, nodo, tipo, por):
    lugar, tipo_txt, nombre = ETIQUETA_NODO[nodo], NOMBRE_TIPO[tipo], NOMBRE_PERIODO[por]
    if pedido == "vehiculos":
        t, orden = mezcla_por_periodo(nodo, tipo, por)
        if not orden:
            return texto_periodos(t, orden, [], por, lugar, tipo_txt)
        return [texto_mezcla(t, orden, por) + f"\n\n<small>{lugar} · {tipo_txt}. Entre paréntesis, los días "
                "medidos en cada periodo.</small>",
                gr.Plot(figura_mezcla_periodos(t, orden, f"Tipos de vehículo por {nombre} · {lugar} · {tipo_txt}"))]
    t, orden, desc = perfil_por_periodo(nodo, tipo, por)
    texto = texto_periodos(t, orden, desc, por, lugar, tipo_txt)
    if not orden:
        return texto
    return [texto, gr.Plot(figura_periodos(t, orden, f"Tráfico por hora en cada {nombre} · {lugar} · {tipo_txt}"))]


def pedir_punto(accion: str) -> str:
    return (f"¿De qué punto quieres {accion}? Escríbelo nombrando uno de estos lugares:\n\n"
            + "\n".join(f"- {e}" for e in ETIQUETA_NODO.values()))


def responder_visual(pedido: str, pregunta: str):
    nodo, tipo = detectar_nodo(pregunta), tipo_de_dia_en(pregunta)
    if pedido == "ayuda":
        return CAPACIDADES
    if pedido == "mapa":
        texto = (f"Este es **{ETIQUETA_NODO[nodo]}** (en rojo) junto a los otros puntos con datos. "
                 "Pasa el mouse sobre cada punto para ver su nombre y cuántos días se midió."
                 if nodo else "Estos son los **6 puntos de Bogotá** donde la Secretaría de Movilidad ha contado "
                              "vehículos y que analiza esta herramienta. Pasa el mouse sobre cada punto para ver "
                              "su nombre y cuántos días se midió.")
        return [texto + "\n\n<small>La ubicación sale de las fichas de los estudios de la Secretaría.</small>",
                gr.Plot(figura_mapa(nodo))]
    por = periodo_en(pregunta)
    if nodo is None:
        extra = f" por {NOMBRE_PERIODO[por]}" if por else ""
        return pedir_punto(("ver la gráfica" if pedido == "grafica" else "ver los tipos de vehículo") + extra)
    if por:
        return responder_periodos(pedido, nodo, tipo, por)
    fig, p = figura_perfil(nodo, tipo)
    if p.empty:
        return (f"Todavía no hay días medidos de tipo «{NOMBRE_TIPO[tipo]}» en {ETIQUETA_NODO[nodo]}. "
                "Prueba con otro tipo de día.")
    pico = p.loc[p.mediana.idxmax()]
    if pedido == "grafica":
        return [f"Tráfico normal en **{ETIQUETA_NODO[nodo]}** ({NOMBRE_TIPO[tipo]}), hora por hora. La barra roja "
                f"es la hora con más tráfico: **{hora_amigable(pico.hora)}**, con unos "
                f"**{aproximar(pico.mediana)} vehículos**. Se basa en {int(pico.estudios)} días medidos.",
                gr.Plot(fig)]
    d, usado = desglose(nodo, tipo, p.rename(columns={"mediana": "total"})[["hora", "total"]])
    en_pico = d[d.hora == pico.hora].set_index("grupo").vehiculos.reindex(ORDEN_VEHICULO).dropna()
    partes = enumerar([f"unos {aproximar(v)} {g.lower()}" for g, v in en_pico.items()])
    return [f"En **{ETIQUETA_NODO[nodo]}** ({NOMBRE_TIPO[tipo]}), en la hora con más tráfico "
            f"({hora_amigable(pico.hora)}) pasan normalmente {partes}.\n\n"
            "<small>Cada color es un tipo de vehículo; la altura total de la barra es el tráfico normal de esa hora.</small>",
            gr.Plot(figura_desglose(d, f"Tipos de vehículo por hora · {ETIQUETA_NODO[nodo]} · {NOMBRE_TIPO[tipo]}"))]


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


def responder(pregunta, historial):
    """Respuesta del asistente: texto, o [texto, gráfico]."""
    *_, buscador = cargar()
    pedido = que_pide(pregunta)
    if pedido is None and detectar_nodo(pregunta) is not None:  # respuesta a «¿De qué punto…?»
        ultimo = next((str(m.get("content", "")) for m in reversed(historial or [])
                       if isinstance(m, dict) and m.get("role") == "assistant"), "")
        if "¿De qué punto quieres ver la gráfica" in ultimo:
            pedido = "grafica"
        elif "¿De qué punto quieres ver los tipos de vehículo" in ultimo:
            pedido = "vehiculos"
        if pedido and periodo_en(pregunta) is None and periodo_en(ultimo.split("?")[0]):
            pregunta += " " + {"anio": "por año", "mes": "por mes",
                               "temporada": "por temporada"}[periodo_en(ultimo.split("?")[0])]
    if pedido is None and periodo_en(pregunta) and detectar_nodo(pregunta) is not None:
        pedido = "grafica"
    if pedido:
        return responder_visual(pedido, pregunta)
    if intencion(pregunta) == "calculo":
        if detectar_nodo(pregunta) is None and not re.search(
                r"trafic|vehicul|carro|moto|bus|camion|bici|hora|pico|congest|movil|aforo|flujo", normalizar(pregunta)):
            return "No tengo ese dato en las fuentes disponibles.\n\n" + CAPACIDADES
        return responder_calculo(pregunta)
    r = responder_contexto(buscador, pregunta)
    if r.startswith("No tengo ese dato"):
        return "No tengo ese dato en las fuentes disponibles.\n\n" + CAPACIDADES
    return r


def ultimo_nodo(pregunta, historial):
    """Nodo de la pregunta o, si no lo nombra, el último que se mencionó en la conversación."""
    nodo = detectar_nodo(pregunta)
    for m in reversed(historial or []):
        if nodo is not None:
            break
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
            nodo = detectar_nodo(m["content"])
    return nodo


def sugerencias(pregunta, historial) -> list[str]:
    """3 preguntas para seguir la conversación, sobre el mismo punto si ya se habló de uno."""
    q, nodo = normalizar(pregunta), ultimo_nodo(pregunta, historial)
    if nodo is None:
        opciones = ["Muéstrame el mapa de los puntos",
                    "¿A qué hora hay más tráfico en la Autopista Norte con 170?",
                    "¿Qué tipos de vehículos pasan por la Av. 68 con 72?",
                    "¿Los datos de aforos tienen errores?"]
    else:
        lugar = ETIQUETA_NODO[nodo]
        opciones = [f"¿A qué hora hay más tráfico en {lugar}?",
                    f"Muéstrame una gráfica de las horas de {lugar}",
                    f"¿Cómo ha cambiado el tráfico en {lugar} por año?",
                    f"¿Qué tipos de vehículos pasan por {lugar}?",
                    f"¿Cambian los tipos de vehículo en {lugar} en vacaciones?",
                    f"¿A qué hora hay más tráfico en {lugar} el sábado?",
                    f"¿Dónde queda {lugar}?",
                    "¿Qué es la mediana?"]
    def clase(x):
        pedido = que_pide(x) or ("grafica" if periodo_en(x) else None)
        return (pedido or ("calculo" if intencion(x) == "calculo" else None), tipo_de_dia_en(x), periodo_en(x))
    hecho = clase(pregunta)

    preguntadas = {normalizar(m["content"]) for m in (historial or [])
                   if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)}

    def ya_respondida(o):
        return normalizar(o) in preguntadas | {q} or (hecho[0] is not None and clase(o) == hecho)
    return [o for o in opciones if not ya_respondida(o)][:3]


def chat(pregunta, historial):
    """Agrega, debajo de cada respuesta, botones con preguntas para seguir."""
    r = responder(pregunta, historial)
    partes = r if isinstance(r, list) else [r]
    opciones = [{"value": o, "label": o} for o in sugerencias(pregunta, historial)]
    mensajes = [gr.ChatMessage(content=x) for x in partes[:-1]]
    mensajes.append(gr.ChatMessage(content=partes[-1], options=opciones))
    return mensajes


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


def comparar(opcion, tipo_txt, comparar_txt):
    por = COMPARAR[comparar_txt]
    if por is None:
        return (gr.update(value="", visible=False), gr.update(value=None, visible=False),
                gr.update(value="", visible=False), gr.update(value=None, visible=False))
    nodo, tipo = nodo_de(opcion), TIPOS_DIA[tipo_txt]
    nombre, lugar = NOMBRE_PERIODO[por], ETIQUETA_NODO[nodo]
    t, orden, desc = perfil_por_periodo(nodo, tipo, por)
    m, orden_m = mezcla_por_periodo(nodo, tipo, por)
    texto = texto_periodos(t, orden, desc, por, lugar, tipo_txt.lower())
    fig = figura_periodos(t, orden, f"Tráfico por hora en cada {nombre}") if orden else None
    fig_m = figura_mezcla_periodos(m, orden_m, f"Tipos de vehículo por {nombre}") if orden_m else None
    return (gr.update(value=texto, visible=True), gr.update(value=fig, visible=fig is not None),
            gr.update(value=texto_mezcla(m, orden_m, por), visible=fig_m is not None),
            gr.update(value=fig_m, visible=fig_m is not None))


def predecir(opcion, fecha, festivo):
    horas, *_, artefacto, metricas, _ = cargar()
    nodo = nodo_de(opcion)
    try:
        f = pd.Timestamp(fecha)
    except ValueError:
        return None, "Escribe la fecha como AAAA-MM-DD, por ejemplo 2026-12-08.", "", None
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
    d, usado = desglose(nodo, tipo, tot.rename(columns={"prediccion": "total"}))
    en_pico = d[d.hora == pico.hora].set_index("grupo").vehiculos.reindex(ORDEN_VEHICULO).dropna()
    nota_v = ("### ¿Qué vehículos serían?\n"
              "En la hora de más tráfico serían " + enumerar([f"unos **{aproximar(v)} {g.lower()}**"
                                                         for g, v in en_pico.items()]) + ".\n\n"
              "<small>**Cómo se calcula:** el total estimado de cada hora se reparte según la proporción de "
              "carros, motos, buses y camiones que se ha observado en días parecidos en este punto."
              + (f" Como no hay días medidos de tipo «{NOMBRE_TIPO[tipo]}», se usó la proporción de los días "
                 "hábiles." if usado != tipo else "") + "</small>")
    fig_v = figura_desglose(d, "Tipos de vehículo por hora (estimado)")
    return fig, nota, nota_v, fig_v


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
            "Muéstrame el mapa de los puntos",
            "¿Qué tipos de vehículos pasan por la Vía a Cota?",
            "Muéstrame una gráfica de las horas de la Av. 68 con 72"])
    with gr.Tab("Explorar un punto"):
        with gr.Row():
            n1 = gr.Dropdown(OPCIONES_NODO, value=OPCIONES_NODO[0], label="Punto de la ciudad (nodo)")
            t1 = gr.Radio(list(TIPOS_DIA), value="Día hábil", label="Tipo de día")
        guia1 = gr.Markdown()
        g1 = gr.Plot()
        c1 = gr.Radio(list(COMPARAR), value="No comparar", label="Comparar por periodo",
                      info="Mira si el tráfico cambia entre años, meses o temporadas (vacaciones y época escolar).")
        guia_p = gr.Markdown(visible=False)
        g_p = gr.Plot(visible=False)
        guia_m = gr.Markdown(visible=False)
        g_m = gr.Plot(visible=False)
        gr.Markdown("**Días medidos en este punto.** Cada fila es un día en que la Secretaría de Movilidad "
                    "contó los vehículos. Si dice «No, solo algunas horas», ese día no se contó completo y por "
                    "eso no tiene total.")
        tab1 = gr.Dataframe(wrap=True)
        for c in (n1, t1):
            c.change(explorar, [n1, t1], [guia1, g1, tab1])
        for c in (n1, t1, c1):
            c.change(comparar, [n1, t1, c1], [guia_p, g_p, guia_m, g_m])
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
        nota3 = gr.Markdown()
        g3 = gr.Plot()
        b2.click(predecir, [n2, f2, fe2], [g2, nota2, nota3, g3])
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
