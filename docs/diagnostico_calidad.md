# Diagnóstico de disponibilidad y calidad de los datos de movilidad

Revisión hecha en noviembre de 2026 por el equipo Bogotá se Mueve.

## Dónde están los datos de aforos
Los aforos vehiculares de la SDM se publican en el visor de volúmenes del Observatorio de Movilidad (observatorio.movilidadbogota.gov.co), donde se descargan archivo por archivo. No aparecen como conjunto de datos en el portal Datos Abiertos Bogotá ni en el hub de datos abiertos de la SDM, y el Catálogo de Objetos de la SDM (versión 1.1, abril de 2026) no los incluye.

## Datos que existen pero no están catalogados
El servidor de mapas del SIMUR publica servicios consultables sin iniciar sesión, por ejemplo siniestros viales georreferenciados (906.374 registros) y alertas de congestión de Waze de 2026 (88.210.870 registros). No aparecen enlazados desde el portal de datos abiertos.

## Problemas encontrados en los archivos de aforos
- Archivos con datos de otro nodo: un archivo nombrado como nodo 3493 contiene datos del nodo 10029.
- Números de nodo mal digitados: archivos del nodo 663 traen en la columna NODO los números 633 o 9508. Se corrigió a 663 tras verificar en el visor que ese punto solo tiene los nodos 663 y 698.
- Nombre del archivo y datos no coinciden: hay 40 archivos donde el nodo o la fecha del nombre no corresponden con los datos.
- Fecha imposible: un estudio del nodo 695 registra el 31 de diciembre de 2027.
- Archivos dañados: 5 archivos no se pueden abrir.
- Columnas corridas: en el estudio del 10 de mayo de 2025 del nodo 19513 los valores de cada tipo de vehículo aparecen en la columna equivocada (por ejemplo, 32 % de patinetas y 3 % de motos, cuando lo típico es 0,1 % y 37 %).
- Identificadores repetidos: el mismo ID de estudio de la SDM aparece en varias fechas del nodo 3493.
- Cambios de método sin aviso: desde septiembre de 2025 algunos estudios cuentan también las bicicletas en ciclorruta, lo que multiplica el total de bicicletas sin que haya más ciclistas. Los camiones se desagregan distinto según el contrato.
- Mismo nodo y fecha con datos distintos: 19 casos.
- El resumen del "estudio más reciente" que muestra el visor no se pudo reproducir con los archivos que el mismo visor permite descargar.

## Cómo se trataron
Los duplicados se descartaron, el nodo 633/9508 se corrigió a 663, la fecha imposible y los archivos dañados se excluyeron, y las demás anomalías quedaron marcadas como alertas visibles en la pestaña "Calidad de datos". Ninguna se corrigió en silencio.
