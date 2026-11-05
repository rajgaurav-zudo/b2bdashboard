"""The store: one copy of each source's latest file, and dashboards that keep
only what they serve.

Every upload used to stay in every dashboard that read it, so the tables grew by
a whole export per upload. Now a replaced load's rows are deleted, the raw file
lives once in store.<source>, and what moved between uploads is the store's
changelog. These tests hold that design to its promises: nothing is lost that
the old design could give back, while the archive is still there to give it.
"""
from datetime import timedelta

import polars as pl
import pytest

from app import registry
from app.ingest import service
from app.ingest.reader import IngestError, read_table
from app.storage import StorageError, storage

from test_fan_out import sandbox  # noqa: F401  (the fixture)

HEADER = b"Application Ref No,Application Id,Application Introducer Name,Deposit Paid Status,Application Status\n"

V1 = HEADER + (
    b"R-1,A-1,Acme Ltd,FullyPaid,Enrolled\n"
    b"R-2,A-2,Beta LLP,Unpaid,Applied\n"
    b"R-3,A-3,Acme Ltd,FullyPaid,Applied\n"
)
# R-2 changes, R-3 goes, R-4 arrives, R-1 stays as it was
V2 = HEADER + (
    b"R-1,A-1,Acme Ltd,FullyPaid,Enrolled\n"
    b"R-2,A-2,Beta LLP,FullyPaid,Applied\n"
    b"R-4,A-4,Gamma GmbH,Unpaid,Applied\n"
)
# values a postgres array literal has to escape, and an empty cell
AWKWARD = HEADER + (
    b'R-1,A-1,"Quote ""Q"" Ltd",Full\\Paid,\n'
    b'R-2,A-2,"Comma, Brace {x}",NULL,Caf\xc3\xa9\n'
)


def _loads(sb, slug):
    return sb.rows(
        """select l.id, l.is_current, l.purged_at, l.row_count from core.loads l
             join core.dashboards d on d.id = l.dashboard_id
            where d.slug = %s order by l.id""",
        slug,
    )


def _load_ids_in_table(sb, slug):
    return {r["load_id"] for r in sb.rows(f'select distinct load_id from "{slug}".apps')}


def _entry(sb, upload_id):
    found = sb.rows("select * from store.changelog where upload_id = %s and dashboard_id is null",
                    upload_id)
    assert len(found) == 1
    return found[0]


def test_a_replaced_load_is_deleted_from_the_dashboard(sandbox):
    a, b = sandbox.slugs
    sandbox.upload(V1, f"{sandbox.tag}-1.csv")
    sandbox.upload(V2, f"{sandbox.tag}-2.csv")

    for slug in (a, b):
        loads = _loads(sandbox, slug)
        assert [l["is_current"] for l in loads] == [False, True]
        assert loads[0]["purged_at"] is not None and loads[1]["purged_at"] is None
        # the table holds the current load and nothing else
        assert _load_ids_in_table(sandbox, slug) == {loads[1]["id"]}
    assert [r["uid"] for r in sandbox.table(a)] == ["A-1", "A-2", "A-4"]


def test_a_dashboard_that_retains_loads_keeps_them(sandbox):
    a, b = sandbox.slugs
    manifest = sandbox.root / a / "dashboard.yaml"
    manifest.write_text(manifest.read_text() + "retain_loads: true\n")
    registry.discover(refresh=True)

    sandbox.upload(V1, f"{sandbox.tag}-1.csv")
    sandbox.upload(V2, f"{sandbox.tag}-2.csv")

    kept = _loads(sandbox, a)
    assert all(l["purged_at"] is None for l in kept)
    assert _load_ids_in_table(sandbox, a) == {l["id"] for l in kept}
    assert len(_load_ids_in_table(sandbox, b)) == 1


def test_the_store_holds_the_latest_file_and_the_changelog_what_moved(sandbox):
    first = sandbox.upload(V1, f"{sandbox.tag}-1.csv")
    second = sandbox.upload(V2, f"{sandbox.tag}-2.csv")

    snap = sandbox.rows("select * from store.snapshots")
    assert [(s["upload_id"], s["row_count"], s["key_column"]) for s in snap] == \
        [(second["upload_id"], 3, "Application Ref No")]
    assert sorted(r["row_key"] for r in sandbox.rows("select row_key from store.applications")) == \
        ["R-1", "R-2", "R-4"]

    initial = _entry(sandbox, first["upload_id"])
    assert initial["rows_added"] == 3 and "initial upload" in initial["summary"]

    entry = _entry(sandbox, second["upload_id"])
    assert (entry["rows_added"], entry["rows_changed"],
            entry["rows_removed"], entry["rows_unchanged"]) == (1, 1, 1, 1)
    assert entry["previous_upload_id"] == first["upload_id"]
    rows = {r["natural_key"]: r for r in sandbox.rows(
        "select * from store.changelog_rows where changelog_id = %s", entry["id"])}
    assert {k: r["change_type"] for k, r in rows.items()} == \
        {"R-2": "changed", "R-3": "removed", "R-4": "added"}
    assert rows["R-2"]["changed_fields"] == ["Deposit Paid Status"]
    assert rows["R-2"]["before"]["Deposit Paid Status"] == "Unpaid"
    assert rows["R-2"]["after"]["Deposit Paid Status"] == "FullyPaid"


def test_the_store_gives_back_exactly_the_frame_the_file_did(sandbox):
    upload = sandbox.upload(AWKWARD, f"{sandbox.tag}-awkward.csv")
    from_store = service._from_store("applications", upload["upload_id"])
    from_file = read_table(f"{sandbox.tag}-awkward.csv", AWKWARD)

    assert from_store.columns == from_file.columns
    assert from_store.equals(from_file, null_equal=True)
    assert from_store.dtypes == [pl.Utf8] * from_file.width


def test_a_purged_load_is_restored_from_the_archive(sandbox):
    a, _ = sandbox.slugs
    sandbox.upload(V1, f"{sandbox.tag}-1.csv")
    sandbox.upload(V2, f"{sandbox.tag}-2.csv")
    old = _loads(sandbox, a)[0]

    result = service.activate(registry.get(a), old["id"], "tester")

    assert result["changed"] and result["load_id"] != old["id"]
    assert [r["uid"] for r in sandbox.table(a)] == ["A-1", "A-2", "A-3"]
    assert len(_load_ids_in_table(sandbox, a)) == 1
    logged = sandbox.rows("select details from store.changelog where load_id = %s", result["load_id"])
    assert logged[0]["details"]["action"] == "restore"
    assert logged[0]["details"]["from"] == "archive"


def test_the_latest_upload_replays_from_the_store_once_its_file_is_gone(sandbox):
    a, _ = sandbox.slugs
    upload = sandbox.upload(V2, f"{sandbox.tag}-2.csv")
    path = sandbox.rows("select stored_path from core.uploads where id = %s",
                        upload["upload_id"])[0]["stored_path"]
    storage().delete(path)
    sandbox.rows("update core.uploads set stored_path = null where id = %s", upload["upload_id"])

    replay = service.project_upload(upload["upload_id"], a, force=True)

    assert replay["read_from"] == "store"
    assert [p["status"] for p in replay["projections"]] == ["ready"]
    assert [r["uid"] for r in sandbox.table(a)] == ["A-1", "A-2", "A-4"]


def test_a_load_whose_file_has_expired_cannot_be_restored(sandbox):
    a, _ = sandbox.slugs
    first = sandbox.upload(V1, f"{sandbox.tag}-1.csv")
    sandbox.upload(V2, f"{sandbox.tag}-2.csv")
    sandbox.rows("update core.uploads set stored_path = null where id = %s", first["upload_id"])
    old = _loads(sandbox, a)[0]

    with pytest.raises(IngestError, match="no longer kept"):
        service.activate(registry.get(a), old["id"])
    assert [r["uid"] for r in sandbox.table(a)] == ["A-1", "A-2", "A-4"], "still serving V2"


def test_the_archive_drops_old_files_but_never_the_latest(sandbox):
    v3 = V2 + b"R-5,A-5,Delta SA,Unpaid,Applied\n"
    ids = [sandbox.upload(c, f"{sandbox.tag}-{i}.csv")["upload_id"]
           for i, c in enumerate((V1, V2, v3), start=1)]
    sandbox.rows("update core.uploads set started_at = started_at - %s where id = any(%s)",
                 timedelta(days=40), ids)
    paths = {r["id"]: r["stored_path"] for r in sandbox.rows(
        "select id, stored_path from core.uploads where id = any(%s)", ids)}

    assert service.purge_archive() == 2

    after = {r["id"]: r["stored_path"] for r in sandbox.rows(
        "select id, stored_path from core.uploads where id = any(%s)", ids)}
    assert after == {ids[0]: None, ids[1]: None, ids[2]: paths[ids[2]]}
    for upload_id in ids[:2]:
        with pytest.raises(StorageError):
            storage().get(paths[upload_id])
    assert storage().get(paths[ids[2]]) == v3
