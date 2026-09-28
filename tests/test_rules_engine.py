import pandas as pd

from core.insights.rules_engine import generar_insights, generar_reporte_markdown


class PosicionFake:
    def __init__(self, ticker, peso):
        self.ticker = ticker
        self.peso = peso


def _riesgo_base(**overrides):
    base = {
        "semaforo": "🟢 RIESGO BAJO",
        "volatilidad_anualizada": 0.15,
        "concentracion_top2": 0.40,
        "correlacion_ponderada": 0.20,
        "beta_cartera": 0.9,
        "var_95_pct": -0.02,
        "cvar_95_pct": -0.025,
        "contribucion_riesgo": pd.Series({"AAA": 0.3, "BBB": 0.3, "CCC": 0.4}),
    }
    base.update(overrides)
    return base


def test_cartera_saludable_no_dispara_alertas_altas():
    riesgo = _riesgo_base()
    posiciones = [PosicionFake("AAA", 0.33), PosicionFake("BBB", 0.33), PosicionFake("CCC", 0.34)]
    insights = generar_insights(riesgo, posiciones, "SPY")
    altos = [i for i in insights if i.severidad == "alto"]
    assert not altos


def test_volatilidad_alta_dispara_alerta_con_recomendacion_defensiva():
    riesgo = _riesgo_base(volatilidad_anualizada=0.55)
    insights = generar_insights(riesgo, [], "SPY")
    vol_insight = next(i for i in insights if i.categoria == "Volatilidad")
    assert vol_insight.severidad == "alto"
    assert "defensiv" in vol_insight.recomendacion.lower() or "capitalización" in vol_insight.recomendacion.lower()


def test_correlacion_alta_recomienda_baja_correlacion():
    riesgo = _riesgo_base(correlacion_ponderada=0.85)
    insights = generar_insights(riesgo, [], "SPY")
    corr_insight = next(i for i in insights if i.categoria == "Correlación")
    assert corr_insight.severidad == "alto"
    assert "correlación" in corr_insight.recomendacion.lower()


def test_beta_alto_recomienda_beta_bajo():
    riesgo = _riesgo_base(beta_cartera=1.5)
    insights = generar_insights(riesgo, [], "SPY")
    beta_insight = next(i for i in insights if i.categoria == "Beta / Sensibilidad al mercado")
    assert beta_insight.severidad == "alto"
    assert "beta bajo" in beta_insight.recomendacion.lower()


def test_contribucion_desproporcionada_detecta_candidato_a_reducir():
    riesgo = _riesgo_base(contribucion_riesgo=pd.Series({"AAA": 0.7, "BBB": 0.2, "CCC": 0.1}))
    posiciones = [PosicionFake("AAA", 0.2), PosicionFake("BBB", 0.4), PosicionFake("CCC", 0.4)]
    insights = generar_insights(riesgo, posiciones, "SPY")
    desproporcionados = [i for i in insights if i.categoria == "Contribución desproporcionada"]
    assert any("AAA" in i.diagnostico for i in desproporcionados)


def test_reporte_markdown_incluye_secciones_clave():
    riesgo = _riesgo_base(volatilidad_anualizada=0.5, beta_cartera=1.4)
    posiciones = [PosicionFake("AAA", 0.5), PosicionFake("BBB", 0.5)]
    resumen = {"valor_actual_total": 100000, "cantidad_posiciones": 2}
    reporte = generar_reporte_markdown(riesgo, posiciones, resumen, "SPY")
    assert "# Reporte de Riesgo de Cartera" in reporte
    assert "🔴 Alertas" in reporte
    assert "Qué priorizar" in reporte
    assert "no es un modelo de IA ni asesoramiento financiero" in reporte
