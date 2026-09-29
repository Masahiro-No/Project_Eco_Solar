from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from api.auth.router import router as auth_router
from api.dashboard.router import router as dashboard_router
from api.inference.router import router as inference_router
from api.ingestion.router import router as ingestion_router
from api.jobs.router import router as jobs_router
from api.label_studio.router import router as label_studio_router
from api.stations.router import router as stations_router
from api.storage.router import router as storage_router
from api.users.router import router as users_router
from core.config import settings
from db.database import create_database_schema, seed_default_stations

# ── OpenTelemetry Setup ───────────────────────────────────────────────────────
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
_service_name  = os.environ.get("OTEL_SERVICE_NAME", "fastapi")

resource = Resource.create({"service.name": _service_name})

# Traces
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=_otel_endpoint, insecure=True))
)
trace.set_tracer_provider(tracer_provider)

# Metrics
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[
        PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=_otel_endpoint, insecure=True),
            export_interval_millis=15000,  # ส่งทุก 15 วินาที
        )
    ],
)
metrics.set_meter_provider(meter_provider)

# Instrument logging — แทรก trace_id เข้าไปใน log ทุกบรรทัดอัตโนมัติ
LoggingInstrumentor().instrument(set_logging_format=True)
# ─────────────────────────────────────────────────────────────────────────────

tags_metadata = [
    {"name": "auth", "description": "Authentication — register, login, JWT token"},
    {"name": "users", "description": "User CRUD operations"},
    {"name": "stations", "description": "Solar Stations — station specs, panel area, efficiency, soft-delete & restore"},
    {"name": "dashboard", "description": "Dashboard & Analytics — system KPI summary, station detail, alert feeds"},
    {"name": "storage", "description": "MinIO object storage — buckets, upload, download"},
    {"name": "label-studio", "description": "Label Studio — projects & tasks"},
    {"name": "jobs", "description": "Redis Task Queue Management — queues overview, cancel, retry, clear"},
    {"name": "inference", "description": "Solar Forecast Inference & Decision Support"},
    {"name": "ingestion", "description": "Weather & Satellite Ingestion Data Pipeline"},
    {"name": "system", "description": "Health check & system info"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Convenient for a new project; replace with Alembic migrations in production.
    await create_database_schema()
    try:
        await seed_default_stations()
    except Exception as e:
        # Fallback if DB not yet connected during local dev tools
        print(f"[Seed Warning] Could not seed default station: {e}")
    yield


app = FastAPI(
    title="Solar Forecast DSS API",
    description="Central API Server for Solar Power Forecasting & Decision Support System",
    version="0.2.0",
    debug=settings.DEBUG_MODE,
    lifespan=lifespan,
    docs_url="/",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
)

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(stations_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(storage_router, prefix="/api")
app.include_router(label_studio_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(inference_router, prefix="/api")
app.include_router(ingestion_router, prefix="/api")

# ── Instrument FastAPI — สร้าง Span & Metrics อัตโนมัติทุก HTTP Request ─────
FastAPIInstrumentor.instrument_app(
    app,
    tracer_provider=tracer_provider,
    meter_provider=meter_provider,
)


@app.get("/health", tags=["system"], summary="Health Check", description="ตรวจสอบว่า API server ทำงานปกติ")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)