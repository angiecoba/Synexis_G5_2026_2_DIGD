# Convenciones del equipo

Referencia tomada de las guías del curso DataOps & MLOps. **No es una camisa de fuerza**: cada práctica se aplica solo si sirve al reto (apropiación de datos y confianza) y al producto (modelo + asistente en Gradio).

| Práctica | ¿Aplica? | Por qué |
|---|---|---|
| Este repositorio como referente global | Sí | 5 personas, 764 archivos, pipeline que cambia; issues = tablero de próximos pasos |
| Código en `src/bsm/` (notebooks solo para explorar) | Sí | La app, el modelo y Colab reutilizan el mismo código |
| Contrato de datos con pandera (`calidad.py`) | Sí | La calidad del dato oficial es parte del hallazgo de confianza |
| Pipeline sklearn + corte temporal + rival | Sí | Sin esto la métrica miente |
| Modelo serializado con joblib | Sí | La app carga el modelo sin reentrenar |
| Tests de reglas de limpieza (`tests/`) | Ligero | Solo las reglas críticas |
| CI en GitHub Actions | Opcional | Corre los tests en cada push; no bloquea a nadie |
| FastAPI / Docker | No por ahora | Gradio en Render ya cubre la app |
| Logging estructurado | Ligero | Auditoría del pipeline en JSONL; registrar preguntas del asistente para la prueba con usuarios |

## Reglas prácticas
- Funciones puras: `df = df.copy()` al entrar; nada de defaults mutables.
- Rutas con `pathlib`, relativas al repositorio. Nunca `C:\Users\...`.
- Datos crudos y procesados **no** van en Git; solo `data/app/` (ver `data/README.md`).
- Secretos (claves del LLM) solo como variables de entorno en Render, nunca en el código.
- Commits pequeños con qué y por qué: `corrige nodo 633→663 verificado en el visor`.
- Las anomalías del dato oficial se documentan como alertas; no se corrigen en silencio.
- No exponer nombres de funcionarios que aparecen en la hoja "Identificacion".
