"""
Mide cuánto tarda la app publicada en responder cada tipo de pregunta.

Uso (desde cualquier computador con las librerías del proyecto instaladas):
    python scripts/medir_tiempos.py https://bogota-se-mueve.onrender.com

La primera llamada incluye el tiempo de "despertar" del servidor gratuito si estaba dormido;
por eso se reporta aparte. Los tiempos no incluyen dibujar el gráfico en el navegador.
"""
import statistics
import sys
import time

from gradio_client import Client

CASOS = {
    "Concepto (glosario)": "¿Qué es un auto equivalente (ACE)?",
    "Fuera de alcance": "¿Cuánto cuesta el pasaje?",
    "Contexto (notas de campo)": "¿Qué pasó en la Vía a Cota con 116 los días de lluvia?",
    "Cálculo (hora pico)": "¿A qué hora hay más tráfico en la Autopista Norte con 170?",
    "Mapa": "Muéstrame el mapa de los puntos",
    "Gráfica de horas": "Muéstrame una gráfica de las horas de la Av. 68 con 72",
    "Tipos de vehículo": "¿Qué tipos de vehículos pasan por la Vía a Cota?",
    "Comparación por año": "¿Cómo ha cambiado el tráfico en la Vía a Cota por año?",
}


def main(url: str, repeticiones: int = 3) -> None:
    t0 = time.perf_counter()
    cliente = Client(url, verbose=False)
    print(f"Conexión inicial (incluye despertar el servidor si dormía): {time.perf_counter() - t0:.1f} s\n")
    print(f"{'Tipo de pregunta':<28} mediana   (de {repeticiones} intentos)")
    for tipo, pregunta in CASOS.items():
        tiempos = []
        for _ in range(repeticiones):
            t = time.perf_counter()
            cliente.predict(pregunta, api_name="/chat")
            tiempos.append(time.perf_counter() - t)
        print(f"{tipo:<28} {statistics.median(tiempos):5.1f} s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7860")
