import os
import time

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.middleware.base import BaseHTTPMiddleware

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


def _route_template(request: Request) -> str:
    """Returns the matched route template (e.g. "/items/{item_id}").

    Labelling by template instead of the raw path keeps per-ID URLs and 404
    probes from creating an unbounded number of series. Must be called after
    call_next, once the router has populated the scope.
    """
    route = request.scope.get("route")
    if route is None:
        return UNMATCHED_ENDPOINT
    # FastAPI keeps included routers nested, so scope["route"] holds the
    # template relative to the router prefix ("/{item_id}"). The full
    # template lives on FastAPI's effective route context; fall back to the
    # route's own path if that internal ever changes (still bounded).
    context = request.scope.get("fastapi", {}).get("effective_route_context")
    return getattr(context, "path_format", None) or getattr(route, "path", None) or UNMATCHED_ENDPOINT


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Tracks latency and HTTP status codes for incoming requests into Prometheus."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration = time.time() - start_time
            endpoint = _route_template(request)
            REQUEST_COUNT.labels(
                method=request.method, endpoint=endpoint, status=status
            ).inc()
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)


def get_metrics_response() -> Response:
    """Returns the generated Prometheus metrics payload.

    With several uvicorn workers each process has its own registry, so a
    scrape would only see one random worker. When PROMETHEUS_MULTIPROC_DIR
    is set (see compose.yml), every worker writes its samples to that
    directory and the response aggregates all of them.
    """
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
