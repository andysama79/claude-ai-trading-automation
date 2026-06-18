from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TradeSignal:
    symbol: str
    exchange: str = "NSE"
    amount: float | None = None
    tsl_mode: str | None = None
    tsl_pct: float | None = None
    tsl_tiers: list[tuple[float, float]] | None = None
    tsl_k: float | None = None


@dataclass
class Position:
    symbol: str
    exchange: str
    qty: int
    fill_price: float
    order_id: str
    opened_at: datetime
    peak_price: float = field(init=False)

    def __post_init__(self) -> None:
        self.peak_price = self.fill_price


@dataclass
class TradeRecord:
    symbol: str
    exchange: str
    qty: int
    buy_price: float
    sell_price: float
    pnl: float
    tsl_mode: str
    opened_at: datetime
    closed_at: datetime
    fundamentals: dict
