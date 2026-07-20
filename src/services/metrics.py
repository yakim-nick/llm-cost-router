from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge

latency_histogram = Histogram(
    "llm_provider_latency_seconds", "Per-provider latency", ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)
cost_total = Counter("llm_cost_usd_total", "Total cost in USD", ["provider", "model"])
tokens_total = Counter("llm_tokens_total", "Total tokens", ["provider", "model", "type"])
active_keys = Gauge("llm_active_api_keys", "Number of active API keys")


class MetricsCollector:
    def record_latency(self, provider: str, model: str, seconds: float) -> None:
        latency_histogram.labels(provider=provider, model=model).observe(seconds)

    def record_cost(self, provider: str, model: str, cost: float) -> None:
        cost_total.labels(provider=provider, model=model).inc(cost)

    def record_tokens(self, provider: str, model: str, token_type: str, count: int) -> None:
        tokens_total.labels(provider=provider, model=model, type=token_type).inc(count)
