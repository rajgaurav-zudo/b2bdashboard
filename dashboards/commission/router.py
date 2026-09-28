"""HTTP endpoints for the commission configurator, mounted by api/app/main.py at
/api/modules/commission behind the same current_user dependency as /api.

Each request opens one connection, points search_path at the dashboard's
schema, and commits once at the end, so a write and its audit rows land
together or not at all.
"""
from contextlib import contextmanager
from datetime import date

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from app.auth import User, audit_actor, current_user
from app.db import pool
from app.registry import get as _dashboard

_dash = _dashboard("commission")
store = _dash.load_module("store")
model = _dash.load_module("model")

router = APIRouter()


@contextmanager
def _cursor(write: bool = False):
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(f'set local search_path to "{_dash.db_schema}", public')
        try:
            yield cur
        except store.CommissionError as exc:
            conn.rollback()
            raise HTTPException(exc.status, {"message": str(exc), **exc.detail}) from exc
        except Exception:
            conn.rollback()
            raise
        if write:
            conn.commit()
        else:
            conn.rollback()


def _today(today: str | None) -> date:
    """`?today=` lets the UI and tests look at the screens as of another day."""
    return date.fromisoformat(today) if today else date.today()


def _intake(value: str) -> str:
    try:
        model.intake_start(value)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, f"intake should look like 2026-09, not {value!r}") from exc
    return value


# --- reference data -----------------------------------------------------------

@router.get("/meta")
def meta(today: str | None = None):
    t = _today(today)
    with _cursor() as cur:
        return {**store.masters(cur), "today": t.isoformat(),
                "intakes_default": model.major_intakes_around(t, 2, 4)}


@router.get("/institutions")
def institutions():
    with _cursor() as cur:
        return store.institutions(cur)


# --- contracts ----------------------------------------------------------------

@router.get("/contracts")
def list_contracts(today: str | None = None):
    with _cursor() as cur:
        return store.list_contracts(cur, _today(today))


@router.post("/contracts")
def create_contract(data: dict = Body(...), user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        return store.create_contract(cur, data, audit_actor(user))


@router.get("/contracts/{contract_id}")
def get_contract(contract_id: int, today: str | None = None):
    with _cursor() as cur:
        return store.contract_detail(cur, contract_id, _today(today))


@router.put("/contracts/{contract_id}")
def update_contract(contract_id: int, data: dict = Body(...), user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        return store.update_contract(cur, contract_id, data, audit_actor(user))


@router.delete("/contracts/{contract_id}")
def delete_contract(contract_id: int, user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        store.delete_draft_contract(cur, contract_id, audit_actor(user))
        return {"deleted": contract_id}


@router.post("/contracts/{contract_id}/publish")
def publish_contract(contract_id: int, data: dict = Body(default={}), today: str | None = None,
                     user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        return store.publish_contract(cur, contract_id, audit_actor(user), data.get("effective_from"), _today(today))


@router.post("/contracts/{contract_id}/status")
def set_status(contract_id: int, data: dict = Body(...), user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        return store.set_status(cur, contract_id, data.get("status"), data.get("reason"),
                                data.get("effective_date"), audit_actor(user))


@router.get("/contracts/{contract_id}/versions/{version}")
def get_version(contract_id: int, version: int):
    with _cursor() as cur:
        for v in store.versions_of(cur, contract_id):
            if v["version"] == version:
                return v
    raise HTTPException(404, f"no version {version}")


@router.get("/contracts/{contract_id}/timeline")
def timeline(contract_id: int, today: str | None = None):
    with _cursor() as cur:
        return store.timeline(cur, contract_id, _today(today))


@router.get("/contracts/{contract_id}/effective")
def effective(contract_id: int, intake: str = Query(...)):
    with _cursor() as cur:
        return store.effective(cur, contract_id, _intake(intake))


@router.post("/contracts/{contract_id}/simulate")
def simulate(contract_id: int, data: dict = Body(...)):
    with _cursor() as cur:
        return store.simulate(cur, contract_id, _intake(data.get("intake") or ""), data)


@router.get("/contracts/{contract_id}/audit")
def audit(contract_id: int, entity: str | None = None, action: str | None = None):
    with _cursor() as cur:
        return store.audit_entries(cur, contract_id, entity, action)


@router.get("/resolve")
def resolve_terms(institution_id: int, intake: str):
    """resolveTerms(institution, intake) as the spec names it."""
    with _cursor() as cur:
        return store.resolve_terms(cur, institution_id, _intake(intake))


# --- amendments ---------------------------------------------------------------

@router.post("/contracts/{contract_id}/amendments")
def create_amendment(contract_id: int, data: dict = Body(...), user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        return store.create_amendment(cur, contract_id, data, audit_actor(user))


@router.put("/amendments/{amendment_id}")
def update_amendment(amendment_id: int, data: dict = Body(...), user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        return store.update_amendment(cur, amendment_id, data, audit_actor(user))


@router.delete("/amendments/{amendment_id}")
def delete_amendment(amendment_id: int, user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        store.delete_amendment(cur, amendment_id, audit_actor(user))
        return {"deleted": amendment_id}


@router.get("/amendments/{amendment_id}/preview")
def preview_amendment(amendment_id: int, today: str | None = None):
    with _cursor() as cur:
        return store.amendment_preview(cur, amendment_id, _today(today))


@router.post("/amendments/{amendment_id}/publish")
def publish_amendment(amendment_id: int, today: str | None = None, user: User | None = Depends(current_user)):
    with _cursor(write=True) as cur:
        return store.publish_amendment(cur, amendment_id, audit_actor(user), _today(today))


# --- import -------------------------------------------------------------------

@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), user: User | None = Depends(current_user)):
    importer = _dash.load_module("importer")
    body = await file.read()
    with _cursor(write=True) as cur:
        return importer.preview(cur, file.filename or "workbook.xlsx", body, audit_actor(user))


@router.get("/import/{batch_id}")
def import_batch(batch_id: int):
    importer = _dash.load_module("importer")
    with _cursor() as cur:
        return importer.batch(cur, batch_id)


@router.post("/import/{batch_id}/commit")
def import_commit(batch_id: int, data: dict = Body(default={}), user: User | None = Depends(current_user)):
    importer = _dash.load_module("importer")
    with _cursor(write=True) as cur:
        return importer.commit(cur, batch_id, audit_actor(user), data.get("skip") or [])
