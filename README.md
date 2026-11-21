---
title: Bogotá se Mueve
emoji: 🚦
colorFrom: green
colorTo: gray
sdk: gradio
sdk_version: 6.32.0
app_file: app.py
pinned: false
---

# Bogotá se Mueve

Proyecto del equipo **Synexis** para el reto de datos de la Alcaldía de Bogotá (DDIPEA) sobre **confianza y apropiación de los datos públicos**.

Toma los aforos vehiculares que publica la Secretaría Distrital de Movilidad en el Observatorio de Movilidad y:

1. **Los limpia y audita**: detecta duplicados, archivos con datos de otro nodo, columnas corridas, fechas imposibles y cambios de método, y los documenta en vez de esconderlos.
2. **Estima el volumen por hora** en 6 nodos, validado contra el futuro y contra un rival simple (el promedio histórico).
3. **Responde preguntas ciudadanas** en lenguaje claro, con cifras, gráficos y la fuente de cada dato, a través de una app en Gradio.

## Nodos del proyecto
| Nodo | Lugar | Estudios |
|---|---|---|
| 663 | Vía a Cota con Cra 116 | 193 |
| 695 | AK 7 con Calle 208 | 189 |
| 23692 | Calle 102A con Tv 13A Este | 177 |
| 3493 | Autopista Norte con Calle 170 | 20 |
| 19513 | Av. 68 con Calle 72 | 8 |
| 10122 | Calle 171 con Cra 111 | 13 |

## Estructura
```
src/bsm/
  catalogo.py        códigos de vehículo, factores, nodos, correcciones verificadas
  lectura.py         lectura de los Excel (vol-data e Identificacion)
  calidad.py         contrato de datos (pandera) y alertas de calidad
  transformacion.py  de formato ancho a largo
  resumen.py         indicadores comparables por estudio
  pipeline.py        orquestación + auditoría   ->  python -m bsm.pipeline
  modelo.py          modelo + rival + métricas  ->  python -m bsm.modelo
  rag.py             enrutador, búsqueda con cita y LLM opcional
app.py               app Gradio (Asistente · Explorar · Predecir · Calidad · Acerca de)
tests/               reglas críticas de limpieza (pytest)
docs/                glosario, diagnóstico y acerca de (el asistente los cita)
docs/equipo/         convenciones, próximos pasos, diccionario de vehículos
scripts/             descarga de siniestros del SIMUR
data/  models/       fuera de Git (ver data/README.md)
```

## Uso
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export PYTHONPATH=src                                   # Windows: set PYTHONPATH=src

python -m bsm.pipeline data/raw/Nodos.zip --salida data/processed   # ~1 min
python -m bsm.modelo --datos data/processed --modelos models        # ~1 min
pytest -q
python app.py                                                       # http://127.0.0.1:7860
```

En Colab: `!git clone <url>`, `%cd bogota-se-mueve`, `!pip install -r requirements.txt` y los mismos comandos con `!`.

## Resultados actuales (prueba con estudios de 2026, no vistos al entrenar)
| | Error relativo (WAPE) |
|---|---|
| Promedio histórico (rival) | 28,7 % |
| Modelo (gradient boosting) | **24,2 %** |

El modelo gana en 663, 695 y 23692. En 3493 y 10122 gana el promedio histórico (pocos estudios), así que la app usa el promedio en esos nodos. Detalle en `models/metricas.json`.

## Despliegue
Hugging Face Space con Gradio (el encabezado de este README es su configuración). Los datos procesados y el modelo se suben como dataset/modelo en el Hub, y las claves del LLM (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`) van como **Secrets** del Space. Sin LLM, el asistente responde con los fragmentos encontrados y su cita.

## Convenciones
Ver `docs/equipo/convenciones.md`. Son una referencia, no una camisa de fuerza.
