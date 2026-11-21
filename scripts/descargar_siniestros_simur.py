"""
Descarga siniestros del SIMUR (SDM Bogotá) alrededor de los nodos de aforo.
Fuente: Accidentalidad/WSAcidentalidad_Publico (servicio público, solo lectura).
Uso en Colab:  !python descargar_siniestros_simur.py   (o pegar en una celda)

Solo usa operaciones de consulta (query). No modifica nada en el servidor.
"""
import time
import requests
import pandas as pd

BASE = ("https://sig.simur.gov.co/arcgis/rest/services/"
        "Accidentalidad/WSAcidentalidad_Publico/FeatureServer")
CAPA_SINIESTRO = 0          # 0 Siniestro | 1 Con muerto | 2 Con herido
RADIO_M = 300               # radio alrededor de cada nodo, en metros
PAGINA = 2000               # maxRecordCount del servicio

# Nodos de aforo del corredor: (id_nodo, longitud, latitud)
# Las coordenadas salen de la hoja "Identificacion" de cada Excel del Observatorio.
NODOS = [
    (14816, -74.0538722222222, 4.70673055555556),  # AK 45 x AC 127
    # (xxxxx, lon, lat),
]


def campos():
    """Imprime los campos de la capa para saber cómo se llama la fecha, etc."""
    r = requests.get(f"{BASE}/{CAPA_SINIESTRO}", params={"f": "json"}, timeout=60)
    r.raise_for_status()
    for c in r.json()["fields"]:
        print(f'{c["name"]:<30} {c["type"]:<25} {c.get("alias", "")}')


def siniestros_cerca(nodo, lon, lat, radio=RADIO_M):
    """Devuelve todos los siniestros a <radio> metros del punto, paginando."""
    filas, offset = [], 0
    while True:
        params = {
            "where": "1=1",
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "distance": radio,
            "units": "esriSRUnit_Meter",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": PAGINA,
            "f": "json",
        }
        r = requests.get(f"{BASE}/{CAPA_SINIESTRO}/query", params=params, timeout=120)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        feats = data.get("features", [])
        for f in feats:
            fila = dict(f["attributes"])
            geom = f.get("geometry") or {}
            fila["lon"], fila["lat"] = geom.get("x"), geom.get("y")
            fila["NODO"] = nodo
            filas.append(fila)
        if not data.get("exceededTransferLimit") and len(feats) < PAGINA:
            break
        offset += PAGINA
        time.sleep(0.5)  # ser amables con el servidor
    return filas


def fechas_a_datetime(df):
    """ArcGIS entrega fechas en milisegundos desde 1970; las convierte."""
    for col in df.columns:
        if "FECHA" in col.upper() and pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_datetime(df[col], unit="ms", errors="coerce")
    return df


if __name__ == "__main__":
    print("== Campos de la capa Siniestro ==")
    campos()

    todas = []
    for nodo, lon, lat in NODOS:
        filas = siniestros_cerca(nodo, lon, lat)
        print(f"Nodo {nodo}: {len(filas)} siniestros a {RADIO_M} m")
        todas.extend(filas)

    df = fechas_a_datetime(pd.DataFrame(todas))
    df.to_csv("siniestros_nodos.csv", index=False, encoding="utf-8-sig")
    print(f"\nGuardado siniestros_nodos.csv ({len(df)} filas)")

    # Resumen rápido por año y gravedad (ajustar nombres si difieren)
    col_fecha = next((c for c in df.columns if "FECHA" in c.upper()), None)
    if col_fecha is not None and "GRAVEDAD" in df.columns:
        print(df.groupby([df[col_fecha].dt.year, "GRAVEDAD"]).size().unstack(fill_value=0))
