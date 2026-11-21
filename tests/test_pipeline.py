"""Tests de las reglas críticas de limpieza, con archivos Excel sintéticos."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsm.lectura import nodo_en_nombre, tipo_por_columnas  # noqa: E402
from bsm.pipeline import procesar  # noqa: E402

IDENT = [
    ["INFORMACIÓN GENERAL DEL ESTUDIO"],
    ["Identificador de estudio", "Tipo de estudio", "Contratista", "Contrato", "Orden de trabajo"],
    ["999", "Volumen vehicular", "CONTRATISTA X", "C-1", "TIPICO"],
    ["Lugar de la toma de información", "AK_PRUEBA"],
    ["TIPOS DE VEHICULO DEL ESTUDIO"],
    ["CÓDIGO DE VEHICULO", "NOMBRE", "FACTOR"],
    ["L", "LIVIANOS", "1"],
    ["M", "MOTOS", "0.5"],
    ["OBSERVACIONES PREVIAS AL ESTUDIO"],
    ["ACCESO", "OBSERVACION"],
    ["Norte", "Lluvia de 17:00 a 18:00"],
]


def vol_data(nodo=100, fecha="2025-03-12", periodos=(500, 515, 530, 545), base=10, extra_cols=None):
    filas = []
    for p in periodos:
        f = pd.Timestamp(fecha) + (pd.Timedelta(days=1) if p < 500 else pd.Timedelta(0))
        filas.append({"NODO": nodo, "FECHA": f, "PERIODO": p, "SENTIDO": "NS", "ACCESO": "N",
                      "MOVIMIENTO": 1, "L": base, "M": base // 2, **(extra_cols or {})})
    return pd.DataFrame(filas)


def escribir(ruta: Path, vol: pd.DataFrame):
    with pd.ExcelWriter(ruta) as w:
        pd.DataFrame(IDENT).to_excel(w, sheet_name="Identificacion", header=False, index=False)
        vol.to_excel(w, sheet_name="vol-data", index=False)


def test_duplicado_semantico_se_descarta(tmp_path):
    escribir(tmp_path / "100_A_250312_VOL.xlsx", vol_data())
    v = vol_data()
    v["MOVIMIENTO"] = v["MOVIMIENTO"].astype(str)  # mismo contenido, distinto formato
    escribir(tmp_path / "100_A_250312_VOL_1.xlsx", v)
    r = procesar(tmp_path)
    assert r["aforos"].estudio.nunique() == 1
    assert "DUPLICADO_SEMANTICO" in r["auditoria"].conteo()


def test_misma_fecha_otros_datos_queda_como_variante(tmp_path):
    escribir(tmp_path / "100_A_250312_VOL.xlsx", vol_data(base=10))
    escribir(tmp_path / "100_B_250312_VOL.xlsx", vol_data(base=99))
    r = procesar(tmp_path)
    assert set(r["aforos"].estudio) == {"100_20250312_VOL", "100_20250312_VOL_v2"}


def test_estudio_que_cruza_medianoche_conserva_su_fecha(tmp_path):
    escribir(tmp_path / "100_A_250312_VOL.xlsx", vol_data(periodos=(2330, 2345, 0, 15)))
    r = procesar(tmp_path)
    df = r["aforos"]
    assert df.estudio.nunique() == 1
    assert df.fecha_estudio.nunique() == 1 and str(df.fecha_estudio.iloc[0].date()) == "2025-03-12"
    assert df.fecha.nunique() == 2  # la madrugada conserva su fecha real


def test_correccion_de_nodo_633_a_663(tmp_path):
    escribir(tmp_path / "663_A_260110_VOL.xlsx", vol_data(nodo=633))
    r = procesar(tmp_path)
    assert set(r["aforos"].nodo) == {663}
    assert "NODO_CORREGIDO" in r["auditoria"].conteo()


def test_fecha_futura_se_descarta(tmp_path):
    escribir(tmp_path / "100_A_250312_VOL.xlsx", vol_data())
    escribir(tmp_path / "100_A_271231_VOL.xlsx", vol_data(fecha="2099-12-31"))
    r = procesar(tmp_path)
    assert r["aforos"].fecha_estudio.max() < pd.Timestamp.today()
    assert "FECHA_IMPOSIBLE" in r["auditoria"].conteo()


def test_nodo_del_nombre_distinto_al_de_los_datos_se_reporta(tmp_path):
    escribir(tmp_path / "3493_A_230221_VOL.xlsx", vol_data(nodo=10029))
    r = procesar(tmp_path)
    assert set(r["aforos"].nodo) == {10029}
    assert "NODO_NO_COINCIDE" in r["auditoria"].conteo()


def test_contrato_rechaza_acceso_invalido(tmp_path):
    v = vol_data()
    v.loc[0, "ACCESO"] = "X"
    escribir(tmp_path / "100_A_250312_VOL.xlsx", v)
    escribir(tmp_path / "100_A_250313_VOL.xlsx", vol_data(fecha="2025-03-13"))
    r = procesar(tmp_path)
    assert "CONTRATO_INCUMPLIDO" in r["auditoria"].conteo()
    assert r["aforos"].estudio.nunique() == 1


def test_vacio_no_es_cero(tmp_path):
    v = vol_data()
    v["M"] = None  # categoría no aforada
    escribir(tmp_path / "100_A_250312_VOL.xlsx", v)
    df = procesar(tmp_path)["aforos"]
    assert df.loc[df.categoria == "MOTO", "conteo"].isna().all()


@pytest.mark.parametrize("cols, esperado", [
    (["L", "M", "BI"], "VOL"), (["BI"], "VOLB"), (["BI_CALZADA", "BICI_CICLORUTA"], "VOLB"),
    (["PT"], "VOLP"), (["PATINETAS"], "VOLPAT"), (["XYZ"], "OTRO"),
])
def test_tipo_por_columnas(cols, esperado):
    assert tipo_por_columnas(cols) == esperado


@pytest.mark.parametrize("nombre, esperado", [
    ("3493_AK_45_X_AC_170_230221_VOL_V0.xlsx", 3493),
    ("5339_23692_CL_102A_250817_VOL.xlsx", 23692),
    ("AK_45_X_CL_170_DOMINGO_OK.xlsx", None),
])
def test_nodo_en_nombre(nombre, esperado):
    assert nodo_en_nombre(nombre) == esperado
