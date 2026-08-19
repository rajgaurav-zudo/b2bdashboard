from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import migrate, registry
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
    yield
    pool.close()


app = FastAPI(title="B2B dashboards", version="0.1.0", lifespan=lifespan)
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
