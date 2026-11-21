"""Catálogos y constantes del proyecto.

Los códigos de vehículo y sus factores salen del diccionario oficial que trae cada
archivo del Observatorio en la hoja "Identificacion" (ver docs/diccionario_vehiculos.csv).
"""

# Nodos del alcance del proyecto (decisión del equipo, nov-2026).
NODOS_PROYECTO = {663, 695, 23692, 3493, 19513, 10122}

# Código de vehículo (columna del Excel) -> categoría canónica.
CATEGORIA = {
    # Livianos
    "L": "LIVIANO", "TAXI": "LIVIANO", "PT PAR": "LIVIANO", "PT IMPAR": "LIVIANO",
    # Buses (SITP, escolar, alimentador, otros) e intermunicipal
    "B": "BUS", "B_SITP": "BUS", "OB": "BUS", "BE": "BUS", "AL": "BUS",
    "INT": "INTERMUNICIPAL",
    # Troncales
    "AT": "ARTICULADO", "TM": "ARTICULADO", "BA": "ARTICULADO",
    # Camiones: cada contrato los desagrega distinto (C | C2,C3,>=C4 | C2G,C2P,C4,C5,>C5),
    # por eso se unifican en una sola categoría comparable.
    "C": "CAMION", "C2": "CAMION", "C2G": "CAMION", "C2P": "CAMION", "C3": "CAMION",
    ">=C4": "CAMION", "C4": "CAMION", "C5": "CAMION", ">C5": "CAMION", "CL2": "CAMION",
    "M": "MOTO",
    # Bicicletas: el lugar de conteo cambia entre contratos
    "BI": "BICI_SIN_DETALLE", "BI_CALZADA": "BICI_CALZADA",
    "BICI_BICICARRIL": "BICI_CICLOINFRA", "BICI_CICLORUTA": "BICI_CICLOINFRA",
    "BICIA": "BICI_CICLOINFRA",
    "BCM": "BICI_CON_MOTOR", "BICITAXI": "BICITAXI", "PATINETAS": "PATINETA",
    "PT": "PEATON",
    "DUAL": "OTRO", "Vehículos Mixtos": "OTRO",
}

# Factores de equivalencia a autos (ACE) de respaldo; se prefieren los del propio archivo.
FACTOR_ACE = {
    "LIVIANO": 1.0, "BUS": 2.0, "INTERMUNICIPAL": 2.0, "ARTICULADO": 2.5, "CAMION": 2.5,
    "MOTO": 0.5, "BICI_SIN_DETALLE": 0.3, "BICI_CALZADA": 0.3, "BICI_CICLOINFRA": 0.3,
    "BICI_CON_MOTOR": 0.3, "BICITAXI": 0.0, "PATINETA": 0.0, "PEATON": 0.0, "OTRO": 0.0,
}

# Correcciones de NODO verificadas contra el visor del Observatorio (nov-2026):
# el 663 (Vía a Cota x Kr 116) figura con 183 estudios; los archivos nombrados 663
# traen en la columna NODO 633 (3 fechas) o 9508 (1 fecha): 179 + 3 + 1 = 183.
# En el mapa, ese punto solo tiene los nodos 663 y 698.
CORRECCIONES_NODO = {633: 663, 9508: 663}

BICIS = ["BICI_SIN_DETALLE", "BICI_CALZADA", "BICI_CICLOINFRA"]
MOTORIZADOS = ["LIVIANO", "BUS", "ARTICULADO", "INTERMUNICIPAL", "CAMION", "MOTO"]
PESADOS = ["CAMION", "BUS", "ARTICULADO", "INTERMUNICIPAL"]
CLAVES = ["NODO", "FECHA", "PERIODO", "SENTIDO", "ACCESO", "MOVIMIENTO"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Ventana comparable entre estudios de 18 h y de 24 h (periodos HHMM).
VENTANA = (500, 2245)
MIN_PERIODOS_COMPLETO = 68  # 05:00-22:45 = 72 periodos; 68 si el estudio arranca a las 06:00

try:  # festivos de Colombia
    import holidays

    FESTIVOS = holidays.Colombia(years=range(2015, 2031))
except Exception:  # noqa: BLE001
    FESTIVOS = None
