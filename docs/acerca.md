# Acerca de Bogotá se Mueve

Proyecto académico para el reto de datos de la Alcaldía de Bogotá sobre confianza y apropiación de los datos públicos. Toma los aforos que publica la Secretaría Distrital de Movilidad y los presenta en lenguaje claro, con la fuente de cada cifra.

## Puntos analizados
| Nodo | Lugar |
|---|---|
| 663 | Vía a Cota con Carrera 116 |
| 695 | Avenida Carrera 7 con Calle 208 |
| 23692 | Calle 102A con Transversal 13A Este |
| 3493 | Autopista Norte con Calle 170 |
| 19513 | Avenida 68 con Calle 72 |
| 10122 | Calle 171 con Carrera 111 |

## Fuentes
- Aforos vehiculares: visor de volúmenes del Observatorio de Movilidad, Secretaría Distrital de Movilidad.
- Festivos: calendario oficial de Colombia.

## Cómo se calculan las estimaciones
Para los nodos con muchos estudios (663, 695 y 23692) se usa un modelo de aprendizaje automático entrenado con los estudios hasta 2025 y probado con los de 2026, que no había visto. Para los demás se usa el promedio histórico de la misma hora y tipo de día, porque con pocos estudios el modelo no lo supera. Cada estimación muestra su error típico.

## Limitaciones
- Los aforos son días puntuales, no un conteo continuo: las estimaciones describen un día típico, no el tráfico de hoy.
- Los archivos oficiales tienen problemas de calidad documentados en la pestaña "Calidad de datos".
- La herramienta no publica nombres de personas que aparecen en los archivos de la SDM.

## Autores
Proyecto académico de la **Mesa 1** de la asignatura **DIGD**, con el docente **Nelson Gustavo Fajardo Belmonte**, presentado en **Synexis · Tech Innovate Summit** de la Escuela Colombiana de Ingeniería Julio Garavito.

Integrantes:

- Angie Valentina Coba Perdomo
- Diego Alejandro Sánchez Parra
- Laura Ximena Cifuentes Chauta
- Luis Alejandro Flórez Rivera
- Luwin Alfonso Ruiz Pinzón
