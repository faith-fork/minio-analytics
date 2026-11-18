from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class PrometheusError(RuntimeError):
    """Raised when Prometheus cannot return a valid query response."""


@dataclass(frozen=True)
class MetricSample:
    labels: dict[str, str]
    value: float
    timestamp: float


class PrometheusClient:
    """Small Prometheus HTTP API client.

    This client deliberately returns labelled samples rather than reducing vectors
    to a scalar, so bucket and cluster labels remain available to callers.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15.0,
        verify_tls: bool = True,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls
        self.session = session or requests.Session()

    def query(self, promql: str, at: str | float | None = None) -> list[MetricSample]:
        if not self.base_url:
            raise ValueError("Prometheus base URL is required")
        if not promql.strip():
            raise ValueError("PromQL query must not be empty")

        params: dict[str, Any] = {"query": promql}
        if at is not None:
            params["time"] = at

        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/query",
                params=params,
                timeout=self.timeout_seconds,
                verify=self.verify_tls,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PrometheusError(f"Prometheus request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise PrometheusError("Prometheus returned invalid JSON") from exc

        if payload.get("status") != "success":
            detail = payload.get("error") or payload.get("errorType") or "unknown API error"
            raise PrometheusError(f"Prometheus query failed: {detail}")

        result = payload.get("data", {}).get("result", [])
        result_type = payload.get("data", {}).get("resultType")

        if result_type == "scalar":
            timestamp, value = result
            return [MetricSample(labels={}, value=float(value), timestamp=float(timestamp))]

        if result_type != "vector":
            raise PrometheusError(f"Unsupported Prometheus result type: {result_type}")

        samples: list[MetricSample] = []
        for item in result:
            try:
                timestamp, value = item["value"]
                samples.append(
                    MetricSample(
                        labels={str(k): str(v) for k, v in item.get("metric", {}).items()},
                        value=float(value),
                        timestamp=float(timestamp),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PrometheusError("Prometheus returned a malformed vector sample") from exc

        return samples

    def close(self) -> None:
        self.session.close()
