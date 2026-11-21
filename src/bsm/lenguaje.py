"""Lenguaje ciudadano: convierte cifras técnicas en frases claras y cercanas.

Pensado para personas sin formación técnica: horas como se dicen en la calle,
cifras redondeadas, proporciones "de cada 10" y explicaciones de qué significa
cada número y de dónde sale.
"""
import pandas as pd

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
ACCESOS = {"N": "norte", "S": "sur", "E": "oriente", "W": "occidente",
           "ACCESO NORTE": "norte", "ACCESO SUR": "sur", "ACCESO ESTE": "oriente",
           "ACCESO OESTE": "occidente"}
CATEGORIAS = {"LIVIANO": "carros y camionetas", "MOTO": "motos", "BUS": "buses",
              "ARTICULADO": "buses articulados", "INTERMUNICIPAL": "buses intermunicipales",
              "CAMION": "camiones", "BICI_CALZADA": "bicicletas", "BICI_SIN_DETALLE": "bicicletas",
              "BICI_CICLOINFRA": "bicicletas en ciclorruta", "PATINETA": "patinetas",
              "BICITAXI": "bicitaxis", "BICI_CON_MOTOR": "bicicletas con motor", "OTRO": "otros"}


def _h12(h: int) -> int:
    return h % 12 or 12


def momento_del_dia(h: int) -> str:
    h = int(h) % 24
    if h < 5:
        return "de la madrugada"
    if h < 12:
        return "de la mañana"
    if h < 19:
        return "de la tarde"
    return "de la noche"


def hora_amigable(h) -> str:
    """17 -> 'de 5 a 6 de la tarde (17:00–18:00)'."""
    h = int(h)
    return f"de {_h12(h)} a {_h12(h + 1)} {momento_del_dia(h)} ({h:02d}:00–{(h + 1) % 24:02d}:00)"


def miles(x) -> str:
    return f"{x:,.0f}".replace(",", ".")


def aproximar(x) -> str:
    """Cifra redondeada para leer rápido: 17.687 -> '17.700'; 1.190 -> '1.200'; 87 -> '90'."""
    x = float(x)
    paso = 100 if x >= 1000 else 10
    return miles(round(x / paso) * paso)


def de_cada_10(pct) -> str:
    """23 -> 'unos 2 de cada 10'; 6 -> 'menos de 1 de cada 10'."""
    if pd.isna(pct):
        return "sin dato"
    n = round(float(pct) / 10)
    if n == 0:
        return "menos de 1 de cada 10"
    if n == 1:
        return "cerca de 1 de cada 10"
    if n == 10:
        return "casi todos"
    return f"unos {n} de cada 10"


def fecha_larga(fecha) -> str:
    """'2025-03-21' -> '21 de marzo de 2025'."""
    f = pd.Timestamp(fecha)
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def acceso_amigable(acceso) -> str:
    a = str(acceso).strip().upper()
    return ACCESOS.get(a, str(acceso).strip().lower())


def explicar_error(wape) -> str:
    """Traduce el error relativo (WAPE, %) a un ejemplo concreto."""
    w = float(wape) / 100
    return (f"en promedio se desvió un {round(w * 100)} % de lo que realmente pasó "
            f"(por ejemplo, si estima 10.000 vehículos, lo real suele andar entre "
            f"{aproximar(10000 * (1 - w))} y {aproximar(10000 * (1 + w))})")


EXPLICA_MEDIANA = (
    "«Normalmente» quiere decir la **mediana**: si se ordenan los días medidos de menor a mayor, "
    "es el valor del día que queda en la mitad. Se usa en lugar del promedio porque un día raro "
    "(un accidente, un cierre, un puente festivo) casi no la mueve.")

EXPLICA_RANGO = (
    "El **rango habitual** es la mitad central de los días medidos: una cuarta parte de los días "
    "tuvo menos tráfico que eso y otra cuarta parte tuvo más.")
