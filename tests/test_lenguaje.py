"""Tests del lenguaje ciudadano: lo que lee la gente no puede estar mal escrito."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsm.lenguaje import (acceso_amigable, aproximar, de_cada_10, explicar_error,  # noqa: E402
                          fecha_larga, hora_amigable)


@pytest.mark.parametrize("h, esperado", [
    (17, "de 5 a 6 de la tarde (17:00–18:00)"),
    (6, "de 6 a 7 de la mañana (06:00–07:00)"),
    (0, "de 12 a 1 de la madrugada (00:00–01:00)"),
    (12, "de 12 a 1 de la tarde (12:00–13:00)"),
    (23, "de 11 a 12 de la noche (23:00–00:00)"),
])
def test_hora_amigable(h, esperado):
    assert hora_amigable(h) == esperado


@pytest.mark.parametrize("x, esperado", [(17687, "17.700"), (1190, "1.200"), (87, "90"), (16808, "16.800")])
def test_aproximar(x, esperado):
    assert aproximar(x) == esperado


@pytest.mark.parametrize("pct, esperado", [(23, "unos 2 de cada 10"), (38, "unos 4 de cada 10"),
                                           (3, "menos de 1 de cada 10"), (13, "cerca de 1 de cada 10")])
def test_de_cada_10(pct, esperado):
    assert de_cada_10(pct) == esperado


def test_fecha_larga_y_acceso():
    assert fecha_larga("2025-03-21") == "21 de marzo de 2025"
    assert acceso_amigable("W") == "occidente"
    assert acceso_amigable("Acceso Este") == "oriente"


def test_explicar_error():
    assert "entre 8.600 y 11.400" in explicar_error(13.8)
