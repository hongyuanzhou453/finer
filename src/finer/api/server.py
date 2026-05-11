import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from finer.api.routes import files, review, stats, integrations, streams, sources, enrichment, bilibili, wechat, rlhf, extraction, aggregation, system, opinions, metrics, lineage, sentiment, backtest, bbdown, text_analysis, kol, f0_index
from finer.api.middleware import setup_auth_middleware
from finer.errors import register_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="Finer OS Canonical API",
        description="Lightweight routing for frontend communication.",
        version="0.1.0",
    )
    register_error_handlers(app)

    # Configure CORS from environment variable (comma-separated origins)
    # Default to localhost:3000 for development
    allowed_origins = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in allowed_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    # Setup authentication middleware (disabled by default)
    setup_auth_middleware(app)

    @app.get("/api/health")
    def health_check():
        return {"status": "ok", "service": "finer-canonic-api"}

    app.include_router(files.router, prefix="/api/files", tags=["files"])
    app.include_router(review.router, prefix="/api/review", tags=["review"])
    app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
    app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])
    app.include_router(streams.router, prefix="/api/streams", tags=["streams"])
    app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
    app.include_router(enrichment.router, prefix="/api/enrichment", tags=["enrichment"])
    app.include_router(bilibili.router, prefix="/api/bilibili", tags=["bilibili"])
    app.include_router(wechat.router, prefix="/api/wechat", tags=["wechat"])
    app.include_router(rlhf.router, prefix="/api/rlhf", tags=["rlhf"])
    app.include_router(extraction.router, prefix="/api/extraction", tags=["extraction"])
    app.include_router(aggregation.router, prefix="/api/aggregation", tags=["aggregation"])
    app.include_router(system.router, prefix="/api/system", tags=["system"])
    app.include_router(opinions.router, prefix="/api/opinions", tags=["opinions"])
    app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
    app.include_router(lineage.router, prefix="/api/lineage", tags=["lineage"])
    app.include_router(sentiment.router, prefix="/api/sentiment", tags=["sentiment"])
    app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
    app.include_router(bbdown.router, prefix="/api/bbdown", tags=["bbdown"])
    app.include_router(text_analysis.router, prefix="/api/text-analysis", tags=["text-analysis"])
    app.include_router(kol.router, prefix="/api/kol", tags=["kol"])
    app.include_router(f0_index.router)

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("finer.api.server:app", host="127.0.0.1", port=8000, reload=True)
