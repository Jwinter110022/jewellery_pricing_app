import sqlite3
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from src.providers.metals_api import get_prices_with_cache

SYMBOLS = ["XAG", "XAU", "XPT"]


def _format_gmt_timestamp(timestamp_iso: str) -> str:
    try:
        parsed = datetime.fromisoformat(timestamp_iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S GMT")
    except ValueError:
        return timestamp_iso


def _format_gbp_price_per_oz(value: float | None) -> str:
    if value is None:
        return "No data"
    return f"£{value:,.2f}"


def render(conn: sqlite3.Connection) -> None:
    st.subheader("Dashboard")
    st.caption("Latest cached precious metal prices in GBP per troy ounce")

    refresh_now = st.button("Refresh prices now", type="primary")
    prices, warning = get_prices_with_cache(conn, SYMBOLS, force_refresh=refresh_now)

    if warning:
        st.warning(warning)

    rows = []
    for symbol in SYMBOLS:
        row = prices.get(symbol)
        if row is None:
            rows.append(
                {
                    "Metal": symbol,
                    "Spot Price (GBP per troy oz)": _format_gbp_price_per_oz(None),
                    "Fetched at (GMT)": "No data",
                    "Provider": "-",
                }
            )
        else:
            rows.append(
                {
                    "Metal": symbol,
                    "Spot Price (GBP per troy oz)": _format_gbp_price_per_oz(
                        float(row["price_gbp_per_oz"])
                    ),
                    "Fetched at (GMT)": _format_gmt_timestamp(row["fetched_at"]),
                    "Provider": row["provider"],
                }
            )

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)

    st.info(
        "If API refresh fails, cached DB prices are used automatically. "
        "Set cache age in Settings."
    )
