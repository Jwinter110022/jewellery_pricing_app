from abc import ABC, abstractmethod


class MetalPriceProvider(ABC):
    provider_name: str

    @abstractmethod
    def fetch_latest_gbp_per_oz(self, symbols: list[str]) -> dict[str, float]:
        """Returns {symbol: price_gbp_per_oz}."""
        raise NotImplementedError
