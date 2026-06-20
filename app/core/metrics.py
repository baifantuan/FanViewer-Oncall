"""Prometheus 指标暴露模块

为 FastAPI 提供 /metrics 端点，暴露请求计数、延迟直方图等，
供 Prometheus 定期抓取。
"""

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import time


# ── 指标定义 ──────────────────────────────────────────────

# 请求总数（按 method + path + status 分维度）
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

# 请求延迟（秒）
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# 当前处理中的请求数（Gauge 可增可减，Counter 只能递增）
REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Requests currently being processed",
    ["method"],
)


# ── 中间件：自动采集每个请求 ──────────────────────────────

class PrometheusMiddleware(BaseHTTPMiddleware):
    """自动记录每个 HTTP 请求的计数和延迟"""

    async def dispatch(self, request: Request, call_next: Callable):
        method = request.method
        path = request.url.path

        REQUESTS_IN_PROGRESS.labels(method=method).inc()

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        REQUESTS_IN_PROGRESS.labels(method=method).dec()
        REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)
        REQUEST_COUNT.labels(
            method=method, path=path, status_code=str(response.status_code)
        ).inc()

        return response


# ── /metrics 端点处理器 ────────────────────────────────────

async def metrics_endpoint(request: Request) -> Response:
    """暴露 Prometheus 文本格式的指标数据"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
