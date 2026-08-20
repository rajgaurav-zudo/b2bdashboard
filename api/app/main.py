from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from . import auth, migrate, registry, storage
from .config import settings
from .db import pool
from .ingest.service import reconcile_interrupted
from .routers import api


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open()
    pool.wait(timeout=30)
    migrate.run()                       # dev convenience; in prod run `make migrate` as a release step
    with pool.connection() as conn:
        registry.sync(conn)
    if stranded := reconcile_interrupted():
        print(f"marked {stranded} interrupted upload(s) as failed")

    # Misconfigured auth is worse than none: it looks protected. Refuse to boot.
    if problems := auth.preflight():
        raise RuntimeError("auth misconfigured -- " + "; ".join(problems))
    print(f"storage: {storage.storage().label}")
    if settings.auth_required:
        print(f"auth: verifying Supabase tokens, {auth.warmup()}")
    else:
        print("auth: DISABLED (AUTH_REQUIRED=false) -- every endpoint is open")
    yield
    pool.close()


app = FastAPI(title="B2B dashboards", version="0.1.0", lifespan=lifespan)
# drill-downs ship the whole member list so the pane can regroup without a
# round trip; the largest is ~1.7MB of very repetitive JSON.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api.router, prefix="/api")


@app.get("/healthz")
def healthz():
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("select 1 as ok")
        return {"ok": cur.fetchone()["ok"] == 1}


# --- the built frontend -------------------------------------------------------
# Serving the SPA from the same process as the API means one deployable, one
# origin and no CORS. Mounted last so /api and /healthz always win, and only when
# a build is present: in development Vite serves it and proxies /api here.
_dist = Path(settings.web_dist) if settings.web_dist else None
if _dist and _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        """Any unknown path returns index.html so client-side routes survive a
        reload; /api is excluded so a wrong endpoint 404s as JSON rather than
        silently returning the app shell."""
        if path.startswith("api/"):
            raise HTTPException(404, "no such endpoint")
        candidate = (_dist / path).resolve()
        if path and _dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
