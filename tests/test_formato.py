import math

from core.viz import formato as f


def test_moneda_y_pct_en_formato_argentino():
    assert f.moneda(1234567.891) == "$ 1.234.567,89"
    assert f.moneda(1234.5, "USD") == "US$ 1.234,50"
    assert f.moneda(None) == "—"
    assert f.pct(0.12345) == "12,35 %"
    assert f.pct(-0.05, 1, signo=True) == "-5,0 %"
    assert f.pct(0.05, 1, signo=True) == "+5,0 %"


def test_fmt_y_vacios():
    assert f.fmt(1.5, ".2f") == "1,50"
    assert f.fmt(None, ".2f") == "—"
    assert f.fmt(math.nan, ".2f") == "—"


def test_estilo_para_styler():
    assert f.estilo("$ {:,.2f}")(15000) == "$ 15.000,00"
    assert f.estilo("{:+.2%}")(0.0123) == "+1,23 %"
    assert f.estilo("{:.1%}")(None) == "—"
    assert f.estilo("{:.1%}")("texto") == "texto"
