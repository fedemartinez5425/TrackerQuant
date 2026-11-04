from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

from core.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

# Segundos por request. Sin timeout explícito, un Yahoo lento dejaba el
# script de Streamlit colgado y la app mostraba el spinner para siempre.
TIMEOUT_SEGUNDOS = 10


def _es_rate_limit(exc: Exception) -> bool:
    nombre = type(exc).__name__
    return nombre == "YFRateLimitError" or "Too Many Requests" in str(exc) or "429" in str(exc)


class YFinanceProvider(BaseDataProvider):
    name = "yfinance"

    def __init__(self):
        # Último error de red/API (None si la última llamada no falló). Lo usa
        # el cortacircuito de core/data_providers para dejar de insistir.
        self.ultimo_error: Exception | None = None

    def _registrar(self, exc: Exception | None) -> None:
        self.ultimo_error = exc

    @property
    def rate_limit(self) -> bool:
        return self.ultimo_error is not None and _es_rate_limit(self.ultimo_error)

    def get_price(self, ticker: str) -> float | None:
        try:
            hist = yf.Ticker(ticker).history(period="5d", timeout=TIMEOUT_SEGUNDOS)
            self._registrar(None)
            if hist is None or hist.empty:
                return None
            return float(hist["Close"].dropna().iloc[-1])
        except Exception as exc:  # noqa: BLE001
            self._registrar(exc)
            logger.warning("yfinance: error obteniendo precio de %s: %s", ticker, exc)
            return None

    def get_history(self, ticker: str, period: str = "2y") -> pd.DataFrame | None:
        try:
            hist = yf.Ticker(ticker).history(period=period, timeout=TIMEOUT_SEGUNDOS)
            self._registrar(None)
            if hist is None or hist.empty:
                return None
            hist = hist[["Close"]].rename(columns={"Close": ticker})
            hist.index = pd.to_datetime(hist.index).tz_localize(None)
            return hist
        except Exception as exc:  # noqa: BLE001
            self._registrar(exc)
            logger.warning("yfinance: error obteniendo histórico de %s: %s", ticker, exc)
            return None

    def get_history_lote(self, tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
        """Históricos de varios tickers en UNA descarga (yf.download).
        Devuelve {ticker: DataFrame con columna ticker}; los tickers sin datos
        no aparecen. Antes se hacía una request por ticker, en serie."""
        if not tickers:
            return {}
        try:
            df = yf.download(
                tickers, period=period, auto_adjust=True, progress=False,
                threads=True, timeout=TIMEOUT_SEGUNDOS, group_by="column",
            )
            self._registrar(None)
        except Exception as exc:  # noqa: BLE001
            self._registrar(exc)
            logger.warning("yfinance: error en descarga en lote (%d tickers): %s", len(tickers), exc)
            return {}
        if df is None or df.empty:
            return {}
        cierres = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": tickers[0]})
        if isinstance(cierres, pd.Series):
            cierres = cierres.to_frame(tickers[0])
        cierres.index = pd.to_datetime(cierres.index).tz_localize(None)
        resultado = {}
        for t in tickers:
            if t in cierres.columns:
                serie = cierres[t].dropna()
                if not serie.empty:
                    resultado[t] = serie.to_frame(t)
        return resultado

    def get_info(self, ticker: str) -> dict:
        try:
            info = yf.Ticker(ticker).info or {}
            self._registrar(None)
            return {
                "nombre": info.get("longName") or info.get("shortName") or ticker,
                "sector": info.get("sector", "N/D"),
                "industria": info.get("industry", "N/D"),
                "pe_ratio": info.get("trailingPE"),
                "pb_ratio": info.get("priceToBook"),
                "market_cap": info.get("marketCap"),
                "beta": info.get("beta"),
                "moneda": info.get("currency", "USD"),
            }
        except Exception as exc:  # noqa: BLE001
            self._registrar(exc)
            logger.warning("yfinance: error obteniendo info de %s: %s", ticker, exc)
            return {}
