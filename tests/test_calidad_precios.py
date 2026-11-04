import numpy as np
import pandas as pd

from core.data_providers.calidad import controlar_precios

IDX = pd.bdate_range("2026-01-01", periods=200)


def _matriz(**cols):
    return pd.DataFrame(cols, index=IDX)


def _suave(n=200, base=100.0):
    return base * np.exp(np.linspace(0, 0.1, n))


def test_serie_sana_no_tiene_problemas():
    assert controlar_precios(_matriz(AAA=_suave()), ["AAA"]) == []


def test_faltante():
    probs = controlar_precios(_matriz(AAA=_suave()), ["AAA", "ZZZ"])
    assert [(p.ticker, p.tipo, p.severidad) for p in probs] == [("ZZZ", "faltante", "alto")]


def test_desactualizado():
    congelada = _suave()
    congelada[-10:] = np.nan
    probs = controlar_precios(_matriz(AAA=_suave(), BBB=congelada), ["AAA", "BBB"])
    assert [(p.ticker, p.tipo) for p in probs] == [("BBB", "desactualizado")]


def test_salto_por_split():
    serie = _suave()
    serie[100:] = serie[100:] / 10
    probs = controlar_precios(_matriz(AAA=serie), ["AAA"])
    assert [(p.ticker, p.tipo) for p in probs] == [("AAA", "salto")]
    assert "-90%" in probs[0].detalle


def test_hueco():
    serie = _suave()
    serie[50:65] = np.nan
    probs = controlar_precios(_matriz(AAA=serie), ["AAA"])
    assert [p.tipo for p in probs] == ["hueco"]


def test_ccl_detecta_el_par_con_ratio_mal_cargado():
    # GGAL y PAMP dan CCL 1500; YPF con ratio 1 da 150 (el ratio real sería 10).
    m = _matriz(**{
        "GGAL.BA": np.full(200, 6000.0), "GGAL": np.full(200, 40.0),
        "PAMP.BA": np.full(200, 3000.0), "PAM": np.full(200, 50.0),
        "YPFD.BA": np.full(200, 4500.0), "YPF": np.full(200, 30.0),
    })
    pares = (("GGAL.BA", "GGAL", 10.0), ("YPFD.BA", "YPF", 1.0), ("PAMP.BA", "PAM", 25.0))
    probs = controlar_precios(m, [], pares)
    assert len(probs) == 1
    assert probs[0].tipo == "ccl" and probs[0].ticker.startswith("YPFD.BA/YPF")


def test_matriz_vacia():
    assert controlar_precios(pd.DataFrame(), ["AAA"])[0].tipo == "faltante"
