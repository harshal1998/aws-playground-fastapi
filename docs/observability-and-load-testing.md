# Observability & Load-Testing Overview

How metrics flow from the FastAPI app through Prometheus into Grafana, and how Locust/the
standalone benchmark script generate the traffic worth watching.

## The metrics pipeline

```text
Browser/client request
        │
        ▼
PrometheusMetricsMiddleware (app/core/metrics.py)
  - records REQUEST_COUNT{method, endpoint, status}
  - records REQUEST_LATENCY{endpoint} (seconds, histogram)
        │
        ▼
GET /metrics  (app/main.py, prometheus_client.generate_latest())
        │
        ▼
Prometheus (docker/prometheus/prometheus.yml)
  - scrapes api:8000/metrics every 5s
  - job name: "fastapi-app"
        │
        ▼
Grafana (docker/grafana/provisioning/datasources/datasource.yml)
  - Prometheus datasource pre-provisioned, pointing at http://prometheus:9090
  - isDefault: true
```

Two custom metrics are emitted for **every** request, regardless of endpoint:
- `http_requests_total{method, endpoint, status}` — a `Counter`, labeled by the raw
  `request.url.path` (so `/items/1` and `/items/2` are counted as *different* endpoint labels —
  there's no path-template normalization, which matters if you're building a Grafana query
  expecting one series per route).
- `http_request_duration_seconds{endpoint}` — a `Histogram` of wall-clock latency per request.

Beyond these two, `prometheus_client` also auto-exposes its own process/GC metrics
(`python_gc_objects_collected_total`, etc.) — which is why
`app/tests/test_api.py::test_prometheus_metrics` checks for either metric name, since the custom
counter won't exist yet on a totally fresh instance that hasn't served a request.

## What you get out of the box vs. what you have to build

**Provisioned automatically:** the Prometheus datasource in Grafana (`isDefault: true`, so any new
panel defaults to querying it).

**Not provisioned — you build it yourself:** there is no `docker/grafana/provisioning/dashboards/`
directory and no dashboard JSON checked in. Opening Grafana at `http://localhost:3000` for the
first time shows an empty instance with a working datasource but zero dashboards. If you want
persistent dashboards across `docker compose down -v`, you'd need to either add a dashboard
provisioning config (a `dashboards.yml` provider pointing at a mounted directory of dashboard JSON)
or export/re-import manually — neither exists in this repo today.

Grafana's data itself (whatever dashboards you build interactively) *does* persist across
`docker compose down` via the `grafana_data` named volume in `compose.yml` — it's only lost on
`docker compose down -v`.

## Generating traffic to look at

Two independent ways to put load on the API, both hitting `http://api:8000` (or `localhost:8000`
from the host):

1. **Locust** (`docker/locust/locustfile.py`) — runs as its own Compose service on port 8089 with
   a web UI. `FastAPITestUser` runs three weighted tasks: read `/items?limit=10` (weight 5, i.e.
   most traffic), create an item via `POST /items` (weight 2), and hit `/` (weight 1). Requests are
   named explicitly (`name="/items [DB Read]"` etc.) so Locust's stats table groups by intent
   rather than raw path. Since `wait_time = between(0.01, 0.05)`, each simulated user fires
   requests roughly every 10–50ms — this is a stress test, not a realistic-pacing simulation.

2. **`scripts/load_test.py`** — a standalone, dependency-light (`requests` + `ThreadPoolExecutor`)
   benchmark for raw throughput numbers without spinning up Locust's UI. Configured via env vars
   (`BENCHMARK_URL`, `TOTAL_REQUESTS`, `CONCURRENCY`), defaulting to 10,000 requests at 1,000
   concurrency against `/`. It prints success/failure counts and req/s at the end — useful for a
   quick "did my change regress throughput" check, but it only checks `status == 200` and doesn't
   validate response bodies the way the Locust tasks implicitly do by hitting real CRUD endpoints.

Either generator's traffic will show up in Prometheus/Grafana within 5 seconds (the scrape
interval) and in the `/metrics` endpoint's `http_requests_total`/`http_request_duration_seconds`
series immediately.

## Practical tip: watching a specific endpoint

Because the `endpoint` label is the literal unnormalized path, if you're benchmarking
`/items/{id}` for many different IDs and want one aggregate series in Grafana, you'll need to sum
over a regex/prefix match (e.g. a query like `{endpoint=~"/items/.*"}`) rather than expecting
Prometheus to already group them — the middleware does no route-template extraction.
