import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Lucas", docs_url="/api/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from server.middleware import UserContextMiddleware
    app.add_middleware(UserContextMiddleware)
    from server.routers import wiki, chat
    app.include_router(wiki.router, prefix="/api/wiki")
    app.include_router(chat.router, prefix="/api")
    dist_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
    if os.path.isdir(dist_dir):
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True,
    )
