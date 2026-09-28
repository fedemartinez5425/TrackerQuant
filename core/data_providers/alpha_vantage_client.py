from __future__ import annotations

import logging

import pandas as pd
import requests

from config.settings import settings
from core.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageProvider(BaseDataProvider):
    """Proveedor de respaldo. Requiere ALPHA_VANTAGE_API_KEY en .env
    (tier gratuito: 25 requests/día, 5/minuto — por eso es fallback, no primario)."""

    name = "alpha_vantage"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.ALPHA_VANTAGE_API_KEY

    def _enabled(self) -> bool:
        return bool(self.api_key)

    def get_price(self, ticker: str) -> float | None:
        if not self._enabled():
            return None
        try:
            resp = requests.get(
                BASE_URL,
                params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("Global Quote", {})
            price = data.get("05. price")
            return float(price) if price else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Alpha Vantage: error obteniendo precio de %s: %s", ticker, exc)
            return None

    def get_history(self, ticker: str, period: str = "2y") -> pd.DataFrame | None:
        if not self._enabled():
            return None
        try:
            resp = requests.get(
                BASE_URL,
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": ticker,
                    "outputsize": "full",
                    "apikey": self.api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            series = resp.json().get("Time Series (Daily)", {})
            if not series:
                return None
            df = pd.DataFrame(series).T
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            df = df[["4. close"]].rename(columns={"4. close": ticker}).astype(float)
            return df
        except Exception as exc:  # noqa: BLE001
            logger.warning("Alpha Vantage: error obteniendo histórico de %s: %s", ticker, exc)
            return None

    def get_info(self, ticker: str) -> dict:
        if not self._enabled():
            return {}
        try:
            resp = requests.get(
                BASE_URL,
                params={"function": "OVERVIEW", "symbol": ticker, "apikey": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return {}
            return {
                "nombre": data.get("Name", ticker),
                "sector": data.get("Sector", "N/D"),
                "industria": data.get("Industry", "N/D"),
                "pe_ratio": _safe_float(data.get("PERatio")),
                "pb_ratio": _safe_float(data.get("PriceToBookRatio")),
                "market_cap": _safe_float(data.get("MarketCapitalization")),
                "beta": _safe_float(data.get("Beta")),
                "moneda": data.get("Currency", "USD"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Alpha Vantage: error obteniendo info de %s: %s", ticker, exc)
            return {}


def _safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
