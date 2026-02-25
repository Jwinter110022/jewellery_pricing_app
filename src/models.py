from dataclasses import dataclass
from typing import Optional


@dataclass
class Stone:
    id: Optional[int]
    stone_type: str
    size_mm_or_carat: str
    grade: str
    supplier: str
    cost_gbp: float
    default_markup_pct: float
    notes: str


@dataclass
class PricePoint:
    symbol: str
    price_gbp_per_oz: float
    fetched_at: str


@dataclass
class QuoteStoneItem:
    stone_id: int
    qty: int
    applied_markup_pct: float
    unit_cost_gbp: float
