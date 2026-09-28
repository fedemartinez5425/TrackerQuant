from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

from core.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)


class YFinanceProvider(BaseDataProvider):
    name = "yfinance"

    def get_price(self, ticker: str) -> float | None:
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="5d")
            if hist is None or hist.empty:
                return None
            return float(hist["Close"].dropna().iloc[-1])
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance: error obteniendo precio de %s: %s", ticker, exc)
            return None

    def get_history(self, ticker: str, period: str = "2y") -> pd.DataFrame | None:
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period=period)
            if hist is None or hist.empty:
                return None
            hist = hist[["Close"]].rename(columns={"Close": ticker})
            hist.index = pd.to_datetime(hist.index).tz_localize(None)
            return hist
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance: error obteniendo histórico de %s: %s", ticker, exc)
            return None

    def get_info(self, ticker: str) -> dict:
        try:
            tk = yf.Ticker(ticker)
            info = tk.info or {}
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
            logger.warning("yfinance: error obteniendo info de %s: %s", ticker, exc)
            return {}
