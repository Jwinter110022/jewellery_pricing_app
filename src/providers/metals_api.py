import os
import sqlite3
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.db import get_all_settings, get_cached_prices, is_price_fresh, save_price
from src.providers.base import MetalPriceProvider


class MetalPriceAPIProvider(MetalPriceProvider):
    """
    Provider implementation for metalpriceapi.com.

    The endpoint returns rates in the shape 'metal units per GBP' when base=GBP,
    so we invert each rate to get GBP per troy ounce.
    """

    provider_name = "metalpriceapi"
    endpoint = "https://api.metalpriceapi.com/v1/latest"

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 10):
        self.api_key = api_key or os.getenv("METALPRICEAPI_KEY", "")
        self.timeout_seconds = timeout_seconds

    def fetch_latest_gbp_per_oz(self, symbols: list[str]) -> dict[str, float]:
        if not self.api_key:
            raise RuntimeError("Missing METALPRICEAPI_KEY in .env")

        currencies = ",".join(symbols)
        response = requests.get(
            self.endpoint,
            params={
                "api_key": self.api_key,
                "base": "GBP",
                "currencies": currencies,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        payload: dict[str, Any] = response.json()
        if payload.get("success") is False:
            raise RuntimeError(payload.get("error", "Provider returned unsuccessful response"))

        rates = payload.get("rates", {})
        result: dict[str, float] = {}

        for symbol in symbols:
            rate = rates.get(symbol)
            if rate is None:
                continue
            if float(rate) <= 0:
                raise RuntimeError(f"Invalid {symbol} rate from provider")
            # Invert rate (oz per GBP) -> GBP per oz.
            result[symbol] = 1 / float(rate)

        return result


class GoldAPIProvider(MetalPriceProvider):
    """
    Provider implementation for gold-api.com.

    Expected endpoint pattern:
    GET https://api.gold-api.com/price/{symbol}

    Expected response to include a numeric `price` that is GBP per troy ounce.
    If a currency field is present and not GBP, the value is rejected to avoid
    silent mispricing.
    """

    provider_name = "goldapi"
    endpoint_base = "https://api.gold-api.com/price"

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 10):
        self.api_key = api_key or os.getenv("GOLDAPI_KEY", "")
        self.timeout_seconds = timeout_seconds
        override_base = os.getenv("GOLDAPI_BASE_URL", "").strip()
        self.base_urls = [override_base] if override_base else [self.endpoint_base]

        fallback_raw = os.getenv("GOLDAPI_FALLBACK_BASE_URLS", "").strip()
        if fallback_raw:
            self.base_urls.extend(
                [url.strip().rstrip("/") for url in fallback_raw.split(",") if url.strip()]
            )

        unique_urls: list[str] = []
        for base_url in self.base_urls:
            cleaned = base_url.rstrip("/")
            if cleaned and cleaned not in unique_urls:
                unique_urls.append(cleaned)
        self.base_urls = unique_urls

        self.session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def fetch_latest_gbp_per_oz(self, symbols: list[str]) -> dict[str, float]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-access-token"] = self.api_key

        result: dict[str, float] = {}
        for symbol in symbols:
            payload: dict[str, Any] | None = None
            last_error: Exception | None = None
            for base_url in self.base_urls:
                try:
                    response = self.session.get(
                        f"{base_url}/{symbol}",
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    break
                except Exception as exc:
                    last_error = exc

            if payload is None:
                raise RuntimeError(
                    f"Gold API request failed for {symbol} across configured URLs. Last error: {last_error}"
                )

            if "price" not in payload:
                raise RuntimeError(f"Missing price field for {symbol} from Gold API")

            currency = str(payload.get("currency", "GBP")).upper()
            if currency != "GBP":
                raise RuntimeError(
                    f"Gold API returned {currency} for {symbol}. Expected GBP pricing."
                )

            price_value = float(payload["price"])
            if price_value <= 0:
                raise RuntimeError(f"Invalid {symbol} price from Gold API")

            result[symbol] = price_value

        return result


def _build_provider_from_env() -> MetalPriceProvider:
    provider_name = os.getenv("PRICE_PROVIDER", "goldapi").strip().lower()
    if provider_name == "metalpriceapi":
        return MetalPriceAPIProvider()
    if provider_name == "goldapi":
        return GoldAPIProvider()
    raise RuntimeError(
        "Unsupported PRICE_PROVIDER. Use 'goldapi' or 'metalpriceapi'."
    )


def get_prices_with_cache(
    conn: sqlite3.Connection,
    symbols: list[str],
    force_refresh: bool = False,
) -> tuple[dict[str, sqlite3.Row], str | None]:
    """
    Returns latest prices from cache and refreshes stale data when needed.

    If API fails, function falls back to existing cached values and returns a warning message.
    """
    settings = get_all_settings(conn)
    ttl = settings["price_cache_ttl_minutes"]
    cached = get_cached_prices(conn, symbols)

    need_refresh = force_refresh
    for symbol in symbols:
        row = cached.get(symbol)
        if row is None or not is_price_fresh(row["fetched_at"], ttl):
            need_refresh = True
            break

    warning = None
    if need_refresh:
        try:
            provider = _build_provider_from_env()
            fresh = provider.fetch_latest_gbp_per_oz(symbols)
            for symbol, value in fresh.items():
                save_price(conn, symbol, value, provider.provider_name)
            cached = get_cached_prices(conn, symbols)
        except Exception as exc:
            if cached:
                warning = f"Price API unavailable. Using cached prices. Details: {exc}"
            else:
                warning = f"Price API unavailable and no cached prices yet. Details: {exc}"

    return cached, warning
