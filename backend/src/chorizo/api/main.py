from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chorizo.api.routes import assets, auth, benchmarks, billing, listings, market, watchlist
from chorizo.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Chorizo API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[get_settings().web_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (auth, assets, benchmarks, listings, market, watchlist, billing):
        app.include_router(module.router, prefix="/v1")

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
