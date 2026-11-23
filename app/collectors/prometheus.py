from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from app.collectors.prometheus_security import validate_prometheus_endpoint


class PrometheusError(RuntimeError):
    """Raised when Prometheus cannot return a valid query response."""


@dataclass(frozen=True)
class MetricSample:
    labels: dict[str, str]
    value: float
    timestamp: float


class PrometheusClient:
    """Small Prometheus HTTP API client with outbound endpoint validation."""

    MAX_RESPONSE_BYTES = 4 * 1024 * 1024

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
        # Do not silently route customer Prometheus traffic through proxy
        # environment variables. The configured endpoint is the destination.
        self.session.trust_env = False

    def query(self, promql: str, at: str | float | None = None) -> list[MetricSample]:
        if not self.base_url:
            raise ValueError("Prometheus base URL is required")
        if not promql.strip():
            raise ValueError("PromQL query must not be empty")

        try:
            validate_prometheus_endpoint(self.base_url)
        except ValueError as exc:
            raise PrometheusError(str(exc)) from exc

        params: dict[str, Any] = {"query": promql}
        if at is not None:
            params["time"] = at

        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/query",
                params=params,
                timeout=self.timeout_seconds,
                verify=self.verify_tls,
                allow_redirects=False,
                stream=True,
            )
            if response.is_redirect or response.is_permanent_redirect:
                response.close()
                raise PrometheusError("Prometheus endpoint redirects are not permitted")
            response.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.MAX_RESPONSE_BYTES:
                    raise PrometheusError("Prometheus response exceeded the 4 MiB limit")
                chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
        except PrometheusError:
            raise
        except requests.RequestException as exc:
            raise PrometheusError("Prometheus request failed") from exc
        except (ValueError, TypeError) as exc:
            raise PrometheusError("Prometheus returned invalid JSON") from exc
        finally:
            if "response" in locals():
                response.close()

        if not isinstance(payload, dict) or payload.get("status") != "success":
            detail = payload.get("error") or payload.get("errorType") or "unknown API error"
            raise PrometheusError(f"Prometheus query failed: {detail}")

        data = payload.get("data") or {}
        result = data.get("result", [])
        result_type = data.get("resultType")

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
