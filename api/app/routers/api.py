from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from .. import registry, views
from ..auth import User, audit_actor, current_user
from ..db import pool
from ..ingest.reader import IngestError
from ..ingest.service import activate, ingest_source, project_upload
from ..storage import StorageError

# Applied to the whole router rather than per route: a new endpoint is then
# protected by default, and forgetting to add a dependency cannot open a hole.
router = APIRouter(dependencies=[Depends(current_user)])


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
            {"slug": ds.slug, "display_name": ds.display_name, "source": ds.source,
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


# --- sources: files, uploaded once, read by every dashboard that wants them ----

@router.get("/sources")
def list_sources():
    """What can be uploaded, and who reads it.

    `dashboards` is what makes the fan-out visible before it happens: uploading
    the applications export feeds exactly the dashboards listed against it.
    """
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select s.slug, s.display_name, s.description,
                      (select count(*) from core.uploads u
                        where u.source_id = s.id and u.status = 'ready') as uploads,
                      (select max(u.started_at) from core.uploads u
                        where u.source_id = s.id and u.status = 'ready') as last_upload
                 from core.sources s order by s.display_name"""
        )
        rows = cur.fetchall()
    for row in rows:
        row["dashboards"] = [
            {"slug": dash.slug, "name": dash.name, "dataset": ds.slug,
             "display_name": ds.display_name}
            for dash, ds in registry.consumers(row["slug"])
        ]
    return rows


@router.post("/sources/{source}/uploads")
async def upload_source(source: str, file: UploadFile = File(...),
                        uploaded_by: str | None = Query(default=None),
                        user: User | None = Depends(current_user)):
    """Upload one file. It is archived once and projected into every dashboard
    that declares this source, each into its own tables."""
    try:
        registry.source(source)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    content = await file.read()
    if not content:
        raise HTTPException(400, "empty file")
    try:
        # the signed-in identity wins: who uploaded is not the client's to assert
        return ingest_source(source, file.filename or "upload.csv", content,
                             audit_actor(user) or uploaded_by)
    except IngestError as exc:
        raise HTTPException(422, str(exc)) from exc
    # The archive is part of the contract, so a failure here fails the upload --
    # but it is not a bug in the server, and a stack trace is the wrong answer.
    # 413 when the file simply cannot be stored on this plan, 502 when the
    # storage service itself is the problem.
    except StorageError as exc:
        raise HTTPException(413 if exc.too_large else 502, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/sources/{source}/uploads")
def source_uploads(source: str, limit: int = Query(25, le=200)):
    """Every file that arrived for this source, with what each dashboard made
    of it."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select u.id, u.filename, u.byte_size, u.row_count, u.status, u.error,
                      u.started_at, u.finished_at, u.uploaded_by, u.sha256,
                      coalesce(json_agg(json_build_object(
                        'dashboard', d.slug, 'dataset', ds.slug, 'status', p.status,
                        'rows', p.row_count, 'load_id', p.load_id, 'error', p.error
                      ) order by d.slug, ds.slug) filter (where p.id is not null), '[]')
                        as projections
                 from core.uploads u
                 join core.sources s on s.id = u.source_id and s.slug = %s
                 left join core.projections p on p.upload_id = u.id
                 left join core.dashboards d on d.id = p.dashboard_id
                 left join core.datasets ds on ds.id = p.dataset_id
                group by u.id
                order by u.started_at desc limit %s""",
            (source, limit),
        )
        return cur.fetchall()


@router.post("/uploads/{upload_id}/project")
def project(upload_id: int, dashboard: str | None = Query(default=None),
            force: bool = Query(default=False)):
    """Build a dashboard's tables from a file already uploaded.

    This is how a dashboard added today reads the export that arrived last week,
    and how a corrected ingest.py is applied to the exact bytes that were loaded
    rather than to a fresh export that has since moved on. `force` re-runs a
    projection that is already ready.
    """
    try:
        return project_upload(upload_id, dashboard, force=force)
    except IngestError as exc:
        raise HTTPException(422, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/dashboards/{slug}/uploads")
def uploads(slug: str, limit: int = Query(25, le=200)):
    """What this dashboard made of every file it was given, failures included.

    One row per projection rather than per upload: the same file feeds several
    dashboards now, and a file that loaded cleanly here may have failed next
    door. A failed projection is otherwise invisible -- it produces no load and
    no changelog entry, so the dashboard keeps serving the previous file and
    looks fine.
    """
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """select p.id, ds.slug as dataset, u.filename, u.byte_size,
                      p.row_count, p.status, p.error, p.started_at, p.finished_at,
                      u.uploaded_by, u.id as upload_id, s.slug as source
                 from core.projections p
                 join core.dashboards d on d.id = p.dashboard_id and d.slug = %s
                 join core.datasets ds on ds.id = p.dataset_id
                 join core.uploads u on u.id = p.upload_id
                 join core.sources s on s.id = u.source_id
                order by p.started_at desc limit %s""",
            (slug, limit),
        )
        return cur.fetchall()


@router.post("/dashboards/{slug}/loads/{load_id}/activate")
def activate_load(slug: str, load_id: int, user: User | None = Depends(current_user)):
    """Roll back to an earlier load. Nothing is deleted; the current flag moves."""
    try:
        dash = registry.get(slug)
        return activate(dash, load_id, audit_actor(user))
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
