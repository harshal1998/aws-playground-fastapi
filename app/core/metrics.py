import os
import time

from fastapi import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# In multiprocess mode prometheus_client writes each worker's samples to
# PROMETHEUS_MULTIPROC_DIR and fails if it is missing. compose.yml wipes and
# recreates it before uvicorn forks; this only guards other entrypoints
# (e.g. an overridden command). Never clean it here: workers share it.
_MULTIPROC_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
if _MULTIPROC_DIR:
    os.makedirs(_MULTIPROC_DIR, exist_ok=True)

# Prometheus Metrics Definitions
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP Requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP Request Latency in seconds",
    ["endpoint"],
)

# Fixed endpoint label for requests that matched no route (404s)
UNMATCHED_ENDPOINT = "unmatched"


def _route_template(scope: Scope) -> str:
    """Returns the matched route template (e.g. "/items/{item_id}").

    Labelling by template instead of the raw path keeps per-ID URLs and 404
    probes from creating an unbounded number of series. Must be called after
    the app has handled the request, once the router has populated the scope.
    """
    route = scope.get("route")
    if route is None:
        return UNMATCHED_ENDPOINT
    # FastAPI keeps included routers nested, so scope["route"] holds the
    # template relative to the router prefix ("/{item_id}"). The full
    # template lives on FastAPI's effective route context; fall back to the
    # route's own path if that internal ever changes (still bounded).
    context = scope.get("fastapi", {}).get("effective_route_context")
    return getattr(context, "path_format", None) or getattr(route, "path", None) or UNMATCHED_ENDPOINT


class PrometheusMetricsMiddleware:
    """Tracks latency and HTTP status codes for incoming requests into Prometheus.

    A pure ASGI middleware: unlike BaseHTTPMiddleware it doesn't wrap the
    request/response in extra tasks and streams, it only watches the
    response start message for the status code.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        # Stays 500 if the app raises before sending a response.
        status = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            duration = time.perf_counter() - start_time
            endpoint = _route_template(scope)
            REQUEST_COUNT.labels(method=scope["method"], endpoint=endpoint, status=status).inc()
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)


def get_metrics_response() -> Response:
    """Returns the generated Prometheus metrics payload.

    With several uvicorn workers each process has its own registry, so a
    scrape would only see one random worker. When PROMETHEUS_MULTIPROC_DIR
    is set (see compose.yml), every worker writes its samples to that
    directory and the response aggregates all of them.
    """
    if _MULTIPROC_DIR:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
