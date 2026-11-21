# Acerca de Bogotá se Mueve

Proyecto académico para el reto de datos de la Alcaldía de Bogotá sobre confianza y apropiación de los datos públicos. Toma los conteos de vehículos que publica la Secretaría Distrital de Movilidad y los presenta en lenguaje claro, con la fuente de cada cifra.

## ¿Qué zonas de Bogotá cubre? Puntos analizados
Son 6 cruces del **norte y noroccidente de Bogotá**. Tres son entradas o salidas de la ciudad.

| Nodo | Lugar | Zona aproximada | Días medidos |
|---|---|---|---|
| 663 | Vía a Cota con Carrera 116 | Suba | 193 |
| 695 | Avenida Carrera 7 con Calle 208 | Usaquén | 188 |
| 23692 | Calle 102A con Transversal 13A Este | Usaquén | 177 |
| 3493 | Autopista Norte con Calle 170 | Límite Usaquén–Suba | 20 |
| 19513 | Avenida 68 con Calle 72 | Límite Engativá–Barrios Unidos | 8 |
| 10122 | Calle 171 con Carrera 111 | Suba | 13 |

No hay datos del sur, el centro, el occidente ni el oriente de la ciudad, ni de otros cruces.

## ¿Qué años se usan?
Los análisis usan los conteos del **9 de septiembre de 2021 al 16 de noviembre de 2026**: 599 días medidos en total. En los tres últimos puntos de la tabla hay pocos días, y la herramienta lo avisa cada vez que los usa.

## Fuentes
- Conteos de vehículos (aforos): visor de volúmenes del Observatorio de Movilidad, Secretaría Distrital de Movilidad.
- Festivos: calendario oficial de Colombia.
- Mapa base: © OpenStreetMap y © CARTO.

## ¿Cómo funciona la herramienta?
1. **Descargamos** los archivos oficiales de cada día medido: 764 archivos de Excel.
2. **Los revisamos.** Encontramos duplicados, archivos de otro punto, fechas imposibles y columnas corridas. No los escondemos: están en la pestaña «Calidad de datos».
3. **Los ordenamos** en una sola tabla con el número de vehículos de cada hora.
4. **Entrenamos un modelo** que aprende cómo cambia el tráfico según la hora, el día, el mes y los festivos. Lo comparamos con el promedio histórico y en cada punto usamos el que menos se equivoca.
5. **Lo mostramos** en esta herramienta, con gráficos, mapas y un asistente que responde preguntas.

## ¿Cómo funciona el asistente?
Primero mira qué le preguntas:
- si pides una cifra, la calcula con los datos;
- si preguntas qué pasó (lluvia, accidentes, obras), busca en las notas de las personas que hicieron los conteos y te dice de qué día salen;
- si pides un mapa o una gráfica, la dibuja;
- si no tiene el dato, te lo dice en lugar de inventarlo.

## Cómo se calculan las estimaciones
Para medir el modelo, lo entrenamos con los conteos de 2021 a 2025 y lo probamos con los de 2026, que no había visto. En los puntos con muchos días medidos (663, 695 y 23692) se equivoca menos que el promedio histórico, así que ahí se usa el modelo. En los demás se usa el promedio histórico de la misma hora y tipo de día. Cada estimación muestra su error típico. La cantidad de carros, motos, buses y camiones se calcula repartiendo el total según lo que se ha visto en días parecidos.

## ¿Cuánto tarda en responder?
- **Si nadie ha usado la herramienta en los últimos 15 minutos**, la primera visita puede tardar **un minuto o más**: el servidor gratuito se estaba «durmiendo».
- **Después**, la mayoría de respuestas llegan en **1 a 3 segundos**. Las que traen gráfico tardan un poco más.

## ¿Se puede usar en el celular?
Sí, desde el navegador del teléfono, sin instalar nada. Los gráficos se ven más pequeños: puedes girar el teléfono o hacer zoom con dos dedos. Para ver la cifra exacta de una barra, tócala. Las tablas anchas se desplazan hacia el lado.

## Limitaciones
- Los conteos son de días puntuales, no continuos: las cifras describen **un día típico**, no el tráfico de hoy.
- Solo hay datos de estos 6 puntos del norte y noroccidente de la ciudad.
- Tres puntos tienen pocos días medidos; ahí las cifras son menos seguras.
- La estimación no conoce la lluvia, los accidentes, las obras ni los eventos de un día específico.
- Los archivos oficiales tienen problemas de calidad, documentados en la pestaña «Calidad de datos».
- El asistente entiende preguntas sobre tráfico, tipos de vehículo, horas, notas de campo y calidad de los datos. No sabe de rutas, precios ni TransMilenio.
- La herramienta no publica nombres de personas que aparecen en los archivos de la SDM.

## Próximos pasos
Agregar puntos del sur, el centro y el occidente; cruzar con los siniestros viales y la lluvia; analizar las bicicletas; usar datos continuos para saber cómo está el tráfico ahora; y mejorar el asistente para que entienda más formas de preguntar.

## Autores
Proyecto académico de la **Mesa 1** de la asignatura **DIGD**, con el docente **Nelson Gustavo Fajardo Belmonte**, presentado en **Synexis · Tech Innovate Summit** de la Escuela Colombiana de Ingeniería Julio Garavito.

Integrantes:

- Angie Valentina Coba Perdomo
- Diego Alejandro Sánchez Parra
- Laura Ximena Cifuentes Chauta
- Luis Alejandro Flórez Rivera
- Luwin Alfonso Ruiz Pinzón

El detalle técnico (arquitectura, archivos, métodos y evaluación) está en el README del repositorio en GitHub: https://github.com/angiecoba/Synexis_G5_2026_2_DIGD

## ¿Qué es «Usar vía API»?
Al pie de la página aparece el enlace «Usar vía API». Es una puerta para que **otros programas** (no personas) consulten esta herramienta de forma automática: por ejemplo, un sistema de la Alcaldía o la app de otra persona podría preguntar la hora de más tráfico de un punto y recibir la respuesta sin abrir esta página. Al hacer clic se ven ejemplos de código para hacerlo. Para usar la herramienta normalmente no hace falta.

## Palabras que usamos
- **Normalmente (mediana):** si se ordenan los días medidos de menor a mayor, es el valor del día que queda en la mitad. Un día raro casi no la mueve.
- **Rango habitual:** lo que pasó en la mitad central de los días medidos.
- **Día medido (estudio):** un día en que la Secretaría de Movilidad contó, uno por uno, los vehículos de un cruce.
- **Aforador:** la persona que hace ese conteo en la calle.
