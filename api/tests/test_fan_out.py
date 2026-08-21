"""One file, many dashboards, and the wall between them.

The platform's central promise is that a dashboard can be added, changed or
broken without any of that reaching another dashboard -- while they all read the
same uploaded exports. That is a claim about behaviour under failure, so it is
asserted here against a real database rather than described in a document.

These tests create and drop their own schemas, so they run against a scratch
database (the compose stack's local postgres by default), never the configured
one. Point TEST_DATABASE_URL somewhere else if that is not where you want them.
"""
import os
import sys
import uuid
from pathlib import Path

import pytest
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

sys.path.insert(0, "/srv/api")

from app import migrate, registry, storage  # noqa: E402
from app import db as db_module  # noqa: E402
from app.config import settings  # noqa: E402
from app.ingest import service  # noqa: E402

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://b2b:b2b@db:5432/b2bdash"
)

CSV = (
    b"Application Id,Application Introducer Name,Deposit Paid Status,Application Status\n"
    b"A-1,Acme Ltd,FullyPaid,Enrolled\n"
    b"A-2,Beta LLP,Unpaid,Applied\n"
    b"A-3,Acme Ltd,FullyPaid,Applied\n"
)

MANIFEST = """\
slug: {slug}
name: Dashboard {letter}
schema: {slug}
datasets:
  apps:
    display_name: Applications ({letter})
    source: applications
    table: apps
    natural_key: [uid]
"""

MIGRATION = """\
create table if not exists apps (
  load_id bigint not null, row_hash bigint not null,
  uid text not null, introducer text, status text
);
"""

# Two dashboards, same source, deliberately different readings of it: different
# columns kept, and one uppercases. If the fan-out ever shared a frame by
# reference rather than by value, this is what would catch it.
INGEST = '''\
import sys
import polars as pl
sys.path.insert(0, "/srv/api")
from app.ingest.reader import Col, clean

COLUMNS = {{"apps": [
    Col("uid", "application id", ("application", "id"), required=True),
    Col("introducer", "application introducer name", ("introducer", "name"), required=True),
    Col("status", {status!r}, ()),
]}}


def finalize(dataset, frame):
    out = frame.select(clean(pl.col(c)).alias(c) for c in ("uid", "introducer", "status"))
    return out.with_columns(pl.col("status").str.to_uppercase()) if {upper} else out
'''


def _write_dashboard(root: Path, slug: str, letter: str, status_column: str, upper: bool):
    directory = root / slug
    (directory / "migrations").mkdir(parents=True, exist_ok=True)
    (directory / "dashboard.yaml").write_text(MANIFEST.format(slug=slug, letter=letter))
    (directory / "migrations" / "001_init.sql").write_text(MIGRATION)
    (directory / "ingest.py").write_text(INGEST.format(status=status_column, upper=upper))
    return directory


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Two dashboards reading one source, on their own schemas, in a scratch db."""
    try:
        pool = ConnectionPool(TEST_DATABASE_URL, min_size=1, max_size=4, open=True,
                              kwargs={"row_factory": dict_row, "prepare_threshold": None},
                              check=ConnectionPool.check_connection, timeout=10)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no scratch database at {TEST_DATABASE_URL}: {exc}")

    # Every module that talks to the database holds its own reference to the
    # pool, so each one has to be pointed at the scratch database explicitly.
    for module in (db_module, service, migrate):
        monkeypatch.setattr(module, "pool", pool, raising=False)

    tag = uuid.uuid4().hex[:8]
    slugs = [f"fan_{tag}_a", f"fan_{tag}_b"]
    _write_dashboard(tmp_path, slugs[0], "A", "deposit paid status", upper=False)
    _write_dashboard(tmp_path, slugs[1], "B", "application status", upper=True)

    monkeypatch.setattr(settings, "dashboards_dir", str(tmp_path))
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "archive"))
    monkeypatch.setattr(storage, "_storage", None)
    registry._cache.cache_clear()
    registry._sources.cache_clear()

    migrate.run()
    with pool.connection() as conn:
        registry.sync(conn)

    yield SimpleSandbox(pool, tmp_path, slugs, tag)

    with pool.connection() as conn, conn.cursor() as cur:
        for slug in list(slugs) + [f"fan_{tag}_c"]:
            cur.execute(f'drop schema if exists "{slug}" cascade')
        cur.execute("delete from core.dashboards where slug like %s", (f"fan_{tag}_%",))
        cur.execute("delete from core.schema_migrations where scope like %s", (f"fan_{tag}_%",))
        cur.execute("delete from core.uploads where filename like %s", (f"{tag}%",))
        conn.commit()
    pool.close()
    storage._storage = None
    registry._cache.cache_clear()
    registry._sources.cache_clear()


class SimpleSandbox:
    def __init__(self, pool, root, slugs, tag):
        self.pool = pool
        self.root = root
        self.slugs = slugs
        self.tag = tag

    def rows(self, sql, *params):
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params or None)
            found = cur.fetchall() if cur.description else []
            conn.commit()
            return found

    def table(self, slug):
        """What this dashboard is currently serving, not every load it has kept."""
        return self.rows(
            f'''select uid, introducer, status from "{slug}".apps
                  where load_id = (select l.id from core.loads l
                                     join core.dashboards d on d.id = l.dashboard_id
                                    where d.slug = %s and l.is_current)
                  order by uid''',
            slug,
        )

    def current_loads(self):
        return {
            row["slug"]: (row["load_id"], row["row_count"])
            for row in self.rows(
                """select d.slug, l.id as load_id, l.row_count
                     from core.loads l join core.dashboards d on d.id = l.dashboard_id
                    where l.is_current and d.slug like %s""",
                f"fan_{self.tag}_%",
            )
        }

    def upload(self, content=CSV, name=None):
        return service.ingest_source("applications", name or f"{self.tag}.csv", content)


def test_one_upload_feeds_every_dashboard_that_declares_the_source(sandbox):
    a, b = sandbox.slugs
    assert {d.slug for d, _ in registry.consumers("applications")} >= {a, b}

    result = sandbox.upload()

    assert result["rows"] == 3
    assert {p["dashboard"]: p["status"] for p in result["projections"]} == {a: "ready", b: "ready"}
    # One file, one archive row, however many dashboards read it. Keyed on the
    # content rather than the name, which is also why uploading the same export
    # twice does not store it twice.
    assert len(sandbox.rows(
        "select id from core.uploads where sha256 = encode(sha256(%s), 'hex')", CSV
    )) == 1


def test_each_dashboard_reads_the_same_file_its_own_way(sandbox):
    """Same bytes, different tables, different values. If one dashboard's ingest
    could reach another's rows this is where it would show."""
    a, b = sandbox.slugs
    sandbox.upload()

    assert [r["status"] for r in sandbox.table(a)] == ["FullyPaid", "Unpaid", "FullyPaid"]
    assert [r["status"] for r in sandbox.table(b)] == ["ENROLLED", "APPLIED", "APPLIED"]


def test_a_dashboard_added_later_is_built_from_the_archive(sandbox):
    """The reason every upload is kept. A dashboard written next week reads the
    export that arrived today, without anyone finding the file again."""
    a, b = sandbox.slugs
    upload_id = sandbox.upload()["upload_id"]
    before = sandbox.current_loads()

    c = f"fan_{sandbox.tag}_c"
    _write_dashboard(sandbox.root, c, "C", "application status", upper=False)
    registry._cache.cache_clear()
    migrate.run()
    with sandbox.pool.connection() as conn:
        registry.sync(conn)

    replay = service.project_upload(upload_id, c)

    assert [p["status"] for p in replay["projections"]] == ["ready"]
    assert len(sandbox.table(c)) == 3
    # and the dashboards that were already there did not move
    after = sandbox.current_loads()
    assert {k: v for k, v in after.items() if k in before} == before


def test_a_broken_dashboard_does_not_cost_the_others_their_load(sandbox):
    """The wall. One dashboard's ingest raises and another's table is missing;
    the third still advances, and the broken two keep serving what they had."""
    a, b = sandbox.slugs
    sandbox.upload()
    before = sandbox.current_loads()

    (sandbox.root / b / "ingest.py").write_text(
        (sandbox.root / b / "ingest.py").read_text().replace(
            "def finalize(dataset, frame):",
            "def finalize(dataset, frame):\n    raise ValueError('mapping is broken')\n    ",
        )
    )
    registry._cache.cache_clear()
    registry.discover(refresh=True)

    result = sandbox.upload(CSV + b"A-4,Gamma GmbH,FullyPaid,Enrolled\n", name=f"{sandbox.tag}-2.csv")
    outcome = {p["dashboard"]: p["status"] for p in result["projections"]}

    assert outcome[a] == "ready"
    assert outcome[b] == "failed"
    after = sandbox.current_loads()
    assert after[a] != before[a], "the healthy dashboard should have advanced"
    assert after[b] == before[b], "the broken one must still serve its last good load"
    assert len(sandbox.table(a)) == 4


def test_a_missing_table_fails_only_that_projection(sandbox):
    """A dashboard whose migrations have not run has nothing to clean up when it
    fails. That second error must not escape and take the others with it."""
    a, b = sandbox.slugs
    sandbox.upload()
    before = sandbox.current_loads()
    sandbox.rows(f'drop table "{b}".apps')

    result = sandbox.upload(CSV + b"A-4,Gamma GmbH,FullyPaid,Enrolled\n", name=f"{sandbox.tag}-3.csv")
    outcome = {p["dashboard"]: p["status"] for p in result["projections"]}

    assert outcome[a] == "ready"
    assert outcome[b] == "failed"
    assert sandbox.current_loads()[a] != before[a]


def test_the_wrong_file_is_refused_before_anything_is_stored(sandbox):
    """An upload no longer names a dashboard, so the source is the only thing in
    a position to notice that the wrong export arrived."""
    from app.ingest.reader import IngestError

    introducers = b"Partner Name,Lifecycle Stage\nAcme Ltd,Customer\n"
    with pytest.raises(IngestError) as err:
        service.ingest_source("applications", f"{sandbox.tag}-wrong.csv", introducers)

    assert "not the Applications file" in str(err.value)
    assert "Introducers master" in str(err.value), "it should say what the file looks like instead"
    assert sandbox.rows("select id from core.uploads where filename = %s",
                        f"{sandbox.tag}-wrong.csv") == []
