from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from .. import registry, views
from ..db import pool
from ..ingest.reader import IngestError
from ..ingest.service import activate, ingest

router = APIRouter()


@router.get("/dashboards")
def list_dashboards():
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select d.slug, d.name, d.version, d.db_schema, d.context_sha,
                      coalesce(json_agg(json_build_object(
                        'slug', ds.slug, 'display_name', ds.display_name,
                        'table', ds.table_name, 'natural_key', ds.natural_key
                      ) order by ds.slug) filter (where ds.id is not null), '[]') as datasets
               from core.dashboards d
               left join core.datasets ds on ds.dashboard_id = d.id
              group by d.id order by d.name"""
        )
        return cur.fetchall()


@router.get("/dashboards/{slug}")
def get_dashboard(slug: str):
    try:
        dash = registry.get(slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select ds.slug as dataset, l.id as load_id, l.row_count, l.created_at,
                      u.filename, u.sha256, u.uploaded_by
                 from core.datasets ds
                 join core.dashboards d on d.id = ds.dashboard_id and d.slug = %s
                 left join core.loads l on l.dataset_id = ds.id and l.is_current
                 left join core.uploads u on u.id = l.upload_id
                order by ds.slug""",
            (slug,),
        )
        current = cur.fetchall()
    return {
        "slug": dash.slug, "name": dash.name, "version": dash.version,
        "schema": dash.db_schema, "context_sha": dash.context_sha,
        "dimensions": dash.manifest.get("dimensions", []),
        "views": views.available(dash),
        "datasets": [
            {"slug": ds.slug, "display_name": ds.display_name,
             "natural_key": ds.natural_key, "required_columns": ds.required_columns}
            for ds in dash.datasets.values()
        ],
        "current_loads": current,
    }


@router.get("/dashboards/{slug}/views/{view}")
def view(slug: str, view: str, request: Request):
    """Dashboard-owned read model. Query params are passed through untouched."""
    try:
        dash = registry.get(slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        return views.render(dash, view, dict(request.query_params))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except views.ViewError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/dashboards/{slug}/datasets/{dataset}/uploads")
async def upload(slug: str, dataset: str, file: UploadFile = File(...),
                 uploaded_by: str | None = Query(default=None)):
    try:
        dash = registry.get(slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if dataset not in dash.datasets:
        raise HTTPException(404, f"{slug} has no dataset '{dataset}'")
    content = await file.read()
    if not content:
        raise HTTPException(400, "empty file")
    try:
        return ingest(dash, dataset, file.filename or "upload.csv", content, uploaded_by)
    except IngestError as exc:
        raise HTTPException(422, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/dashboards/{slug}/loads/{load_id}/activate")
def activate_load(slug: str, load_id: int):
    """Roll back to an earlier load. Nothing is deleted; the current flag moves."""
    try:
        dash = registry.get(slug)
        return activate(dash, load_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/dashboards/{slug}/changelog")
def changelog(slug: str, limit: int = Query(50, le=500)):
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select c.id, c.entity, c.summary, c.rows_added, c.rows_removed, c.rows_changed,
                      c.rows_unchanged, c.rows_sampled, c.occurred_at, c.load_id, c.previous_load_id,
                      u.filename, u.status, u.uploaded_by, c.details
                 from core.changelog c
                 join core.dashboards d on d.id = c.dashboard_id and d.slug = %s
                 left join core.uploads u on u.id = c.upload_id
                order by c.occurred_at desc, c.id desc limit %s""",
            (slug, limit),
        )
        return cur.fetchall()


@router.get("/changelog/{changelog_id}/rows")
def changelog_rows(changelog_id: int, change_type: str | None = None, limit: int = Query(100, le=2000)):
    sql = """select id, change_type, natural_key, changed_fields, before, after
               from core.changelog_rows where changelog_id = %s"""
    params: list = [changelog_id]
    if change_type:
        sql += " and change_type = %s"
        params.append(change_type)
    sql += " order by id limit %s"
    params.append(limit)
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


@router.get("/dashboards/{slug}/loads")
def loads(slug: str, limit: int = Query(50, le=500)):
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select l.id, ds.slug as dataset, l.row_count, l.is_current, l.created_at, l.superseded_at,
                      u.filename, u.sha256, u.uploaded_by
                 from core.loads l
                 join core.dashboards d on d.id = l.dashboard_id and d.slug = %s
                 join core.datasets ds on ds.id = l.dataset_id
                 join core.uploads u on u.id = l.upload_id
                order by l.created_at desc limit %s""",
            (slug, limit),
        )
        return cur.fetchall()
