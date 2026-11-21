# Bogotá se Mueve

Proyecto de la Mesa 1 de la asignatura DIGD (docente Nelson Gustavo Fajardo Belmonte) para el reto de datos de la Alcaldía de Bogotá (DDIPEA) sobre **confianza y apropiación de los datos públicos**, presentado en **Synexis · Tech Innovate Summit** (Escuela Colombiana de Ingeniería Julio Garavito).

App publicada: https://bogota-se-mueve.onrender.com

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
  preparar_app.py    carpeta liviana de la app  ->  python -m bsm.preparar_app
  rag.py             enrutador, búsqueda con cita y LLM opcional
  evaluar.py         califica el asistente con evaluacion/preguntas.csv -> python -m bsm.evaluar
app.py               app Gradio (Asistente · Explorar · Predecir · Calidad · Acerca de)
tests/               reglas críticas de limpieza (pytest)
docs/                glosario, diagnóstico y acerca de (el asistente los cita)
docs/equipo/         convenciones, próximos pasos, diccionario de vehículos
scripts/             descarga de siniestros del SIMUR
data/app/           datos livianos de la app (~3 MB, SÍ en Git)
data/raw, data/processed, models/   fuera de Git (ver data/README.md)
render.yaml         configuración del despliegue en Render
```

## Uso
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export PYTHONPATH=src                                   # Windows: set PYTHONPATH=src

python -m bsm.pipeline data/raw/Nodos.zip --salida data/processed   # ~1 min
python -m bsm.modelo --datos data/processed --modelos models        # ~1 min
python -m bsm.preparar_app                                          # actualiza data/app/
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

## Evaluación del asistente
`evaluacion/preguntas.csv` tiene 10 preguntas con su respuesta esperada (calculada con los datos) y criterios verificables. `python -m bsm.evaluar` califica al asistente con la escala 2 = correcta y con fuente, 1 = parcial o sin fuente, 0 = incorrecta o inventada, y guarda `evaluacion/resultados_asistente.csv`. La misma escala se aplica a mano al Buscador inteligente del portal Datos Abiertos Bogotá.

Línea base (2026-11-21): **17 / 20**. Fallas: P05 (la búsqueda prioriza el nombre del lugar sobre el tema) y P07 (sinónimos: "errores" vs "problemas"). Las mejoras del buscador se validan con preguntas nuevas, no ajustando estas.

## Despliegue (Render, plan gratuito)
1. Entrar a https://render.com con la cuenta de GitHub del repositorio.
2. **New → Blueprint** → elegir este repositorio. Render lee `render.yaml` y crea el servicio.
3. (Opcional) En **Environment**, agregar `LLM_API_KEY`, `LLM_BASE_URL` y `LLM_MODEL` para que un LLM redacte las respuestas. Sin ellos, el asistente responde con los fragmentos encontrados y su cita.

La app usa solo `data/app/` (~380 MB de memoria; el plan gratuito da 512 MB). El servicio gratuito se duerme tras 15 minutos sin visitas y tarda alrededor de un minuto en despertar: abrirlo unos minutos antes de una demo.

Cada vez que se actualicen los datos: `pipeline` → `modelo` → `preparar_app`, y hacer commit de `data/app/`. Render redespliega solo al recibir el push.

## Autores
Proyecto académico de la **Mesa 1** de la asignatura **DIGD**, con el docente **Nelson Gustavo Fajardo Belmonte**, presentado en **Synexis · Tech Innovate Summit** de la Escuela Colombiana de Ingeniería Julio Garavito.

| Integrantes |
|---|
| Angie Valentina Coba Perdomo |
| Diego Alejandro Sánchez Parra |
| Laura Ximena Cifuentes Chauta |
| Luis Alejandro Flórez Rivera |
| Luwin Alfonso Ruiz Pinzón |

## Convenciones
Ver `docs/equipo/convenciones.md`. Son una referencia, no una camisa de fuerza.
