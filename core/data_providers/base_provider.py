from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseDataProvider(ABC):
    """Contrato común para cualquier fuente de datos de mercado."""

    name: str = "base"

    @abstractmethod
    def get_price(self, ticker: str) -> float | None: ...

    @abstractmethod
    def get_history(self, ticker: str, period: str = "2y") -> pd.DataFrame | None:
        """Debe devolver un DataFrame con al menos columna 'Close', indexado por fecha."""
        ...

    @abstractmethod
    def get_info(self, ticker: str) -> dict: ...
