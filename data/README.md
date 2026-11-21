# Datos

Los datos **no se guardan en Git** (son cientos de archivos y cambian).

## Crudos (`data/raw/`)
Excel descargados del visor de volúmenes del Observatorio de Movilidad
(https://observatorio.movilidadbogota.gov.co/mapas/volumenes-vehiculares): clic en el nodo →
"Ver estudios del nodo" → descargar, o "Seleccionar área" para varios nodos.
El equipo los tiene consolidados en `Nodos.zip` (carpeta compartida).

## Procesados (`data/processed/`)
Se generan con:

    python -m bsm.pipeline data/raw/Nodos.zip --salida data/processed

| Archivo | Contenido |
|---|---|
| `aforos_largo.parquet` | una fila por nodo-fecha-periodo-acceso-movimiento-categoría |
| `estudios_resumen.csv` | una fila por estudio: total comparable, hora pico, % motos y pesados, alertas |
| `observaciones_campo.csv` | notas de campo de los aforadores (lluvia, accidentes, obras) |
| `alertas_calidad.csv` | anomalías del dato oficial |
| `auditoria.jsonl` | qué pasó con cada archivo (OK, duplicado, corregido, descartado) |

## App (`data/app/`) — sí va en Git
Versión liviana (~3 MB) con lo que necesita la app desplegada: tabla horaria agregada,
resúmenes, alertas, notas de campo y el modelo. Se genera con `python -m bsm.preparar_app`.
No contiene nombres de personas.
