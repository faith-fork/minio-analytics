from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any

import urllib3
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util import Timeout
from urllib3.util.connection import create_connection

from app.collectors.prometheus_security import resolve_prometheus_endpoint


class PrometheusError(RuntimeError):
    """Raised when Prometheus cannot return a valid query response."""


@dataclass(frozen=True)
class MetricSample:
    labels: dict[str, str]
    value: float
    timestamp: float


class _PinnedHTTPConnection(HTTPConnection):
    def __init__(self, *args, pinned_ip: str, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        return create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            source_address=self.source_address,
            socket_options=self.socket_options,
        )


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, pinned_ip: str, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        return create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            source_address=self.source_address,
            socket_options=self.socket_options,
        )


class _PinnedHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection


class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class PrometheusClient:
    """Prometheus API client with address-pinned outbound connections."""

    MAX_RESPONSE_BYTES = 4 * 1024 * 1024

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15.0,
        verify_tls: bool = True,
        session: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls
        # Retained for call-site compatibility. Requests sessions are not used:
        # the pinned urllib3 transport deliberately has no proxy/environment path.
        self._legacy_session = session

    def query(self, promql: str, at: str | float | None = None) -> list[MetricSample]:
        if not self.base_url:
            raise ValueError("Prometheus base URL is required")
        if not promql.strip():
            raise ValueError("PromQL query must not be empty")

        try:
            host, port, addresses, scheme = resolve_prometheus_endpoint(self.base_url)
        except ValueError as exc:
            raise PrometheusError(str(exc)) from exc

        params: dict[str, Any] = {"query": promql}
        if at is not None:
            params["time"] = at

        pool = None
        response = None
        try:
            # One validated IP is selected for this request. The connection
            # socket goes to that literal IP while Host, TLS SNI and certificate
            # hostname validation continue to use the configured hostname.
            pinned_ip = addresses[0]
            if scheme == "https":
                pool = _PinnedHTTPSConnectionPool(
                    host=host,
                    port=port,
                    pinned_ip=pinned_ip,
                    # HTTPS is always verified. Keep verify_tls in the constructor for
                    # call-site compatibility, but never permit insecure TLS.
                    cert_reqs=ssl.CERT_REQUIRED,
                    assert_hostname=host,
                    server_hostname=host,
                    maxsize=1,
                    block=True,
                )
            else:
                pool = _PinnedHTTPConnectionPool(
                    host=host, port=port, pinned_ip=pinned_ip, maxsize=1, block=True
                )

            response = pool.request(
                "GET",
                "/api/v1/query",
                fields=params,
                timeout=Timeout(total=self.timeout_seconds),
                retries=False,
                redirect=False,
                preload_content=False,
            )
            if response.status in {301, 302, 303, 307, 308}:
                raise PrometheusError("Prometheus endpoint redirects are not permitted")
            if response.status < 200 or response.status >= 300:
                raise PrometheusError(f"Prometheus returned HTTP status {response.status}")

            chunks: list[bytes] = []
            total = 0
            for chunk in response.stream(amt=65536, decode_content=True):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.MAX_RESPONSE_BYTES:
                    raise PrometheusError("Prometheus response exceeded the 4 MiB limit")
                chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
        except PrometheusError:
            raise
        except (urllib3.exceptions.HTTPError, OSError, ValueError, TypeError) as exc:
            raise PrometheusError("Prometheus request failed or returned invalid JSON") from exc
        finally:
            if response is not None:
                response.close()
            if pool is not None:
                pool.close()

        if not isinstance(payload, dict):
            raise PrometheusError("Prometheus returned an invalid API response")
        if payload.get("status") != "success":
            detail = payload.get("error") or payload.get("errorType") or "unknown API error"
            raise PrometheusError(f"Prometheus query failed: {detail}")

        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise PrometheusError("Prometheus returned malformed API data")
        result = data.get("result", [])
        result_type = data.get("resultType")

        if result_type == "scalar":
            try:
                timestamp, value = result
                return [MetricSample(labels={}, value=float(value), timestamp=float(timestamp))]
            except (TypeError, ValueError) as exc:
                raise PrometheusError("Prometheus returned a malformed scalar sample") from exc

        if result_type != "vector" or not isinstance(result, list):
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
        if self._legacy_session is not None:
            self._legacy_session.close()
