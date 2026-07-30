from __future__ import annotations

import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import Counter, Histogram, generate_latest

from src.config import settings
from src.models.database import init_db, close_db
from src.routes.proxy import router as proxy_router
from src.routes.admin import router as admin_router
from src.services.cache import ResponseCache
from src.services.metrics import MetricsCollector

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

REQUEST_COUNT = Counter("llm_gateway_requests_total", "Total requests", ["provider", "model", "status"])
REQUEST_LATENCY = Histogram(
    "llm_gateway_request_duration_seconds", "Latency", ["provider", "model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LLM API Gateway")
    await init_db()
    app.state.cache = ResponseCache()
    app.state.metrics = MetricsCollector()
    await app.state.cache.connect()
    yield
    await app.state.cache.disconnect()
    await close_db()


app = FastAPI(title="LLM Cost Router", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def track_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    if request.url.path.startswith("/v1/"):
        provider = getattr(request.state, "provider", "unknown")
        model = getattr(request.state, "model", "unknown")
        status = "ok" if response.status_code < 400 else "error"
        REQUEST_COUNT.labels(provider=provider, model=model, status=status).inc()
        REQUEST_LATENCY.labels(provider=provider, model=model).observe(elapsed)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "internal_server_error"})


app.include_router(proxy_router, prefix="/v1")
app.include_router(admin_router, prefix="/admin")


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/metrics")
async def metrics():
    return StreamingResponse(generate_latest(), media_type="text/plain")
