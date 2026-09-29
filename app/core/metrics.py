import time
from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
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


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Tracks latency and HTTP status codes for incoming requests into Prometheus."""

    async def dispatch(self, request: Request, call_next):
        endpoint = request.url.path
        start_time = time.time()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(
                method=request.method, endpoint=endpoint, status=status
            ).inc()
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)


def get_metrics_response() -> Response:
    """Returns the generated Prometheus metrics payload."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
