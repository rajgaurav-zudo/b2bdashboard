"""The overview and records views over synthetic rows in a rolled-back load."""
from datetime import date

import pytest


def test_default_range_is_the_edvoy_week(metrics):
    # Tuesday 6 Oct 2026 -> Saturday 3 Oct
    assert metrics._edvoy_week_start(date(2026, 10, 6)) == date(2026, 10, 3)
    assert metrics._edvoy_week_start(date(2026, 10, 3)) == date(2026, 10, 3)
    assert metrics._edvoy_week_start(date(2026, 10, 2)) == date(2026, 9, 26)


def test_each_stage_counts_by_its_own_date(book):
    book.introducer("Acme", became="2026-10-04")
    book.introducer("Old", became="2026-09-30")
    book.application("a1", introducer_name="Acme", at_applied="2026-10-03", at_offer="2026-10-05")
    book.application("a2", introducer_name="Acme", at_applied="2026-09-29", at_deposit="2026-10-06")
    book.log("l1", "Acme", "2026-10-05")
    got = book.values(**{"from": "2026-10-03", "to": "2026-10-09"})
    assert got == {"onboarded": 1, "logs": 1, "applied": 1, "offer": 1, "deposit": 1,
                   "coe": 0, "visa": 0, "enrolled": 0, "closed": 0}
    prev = {m["id"]: m["previous"] for m in book.overview(**{"from": "2026-10-03", "to": "2026-10-09"})["metrics"]}
    assert prev["onboarded"] == 1 and prev["applied"] == 1


def test_scope_filters_and_logs_take_the_masters_scope(book):
    book.introducer("Acme", became="2026-10-04", region="MENA-B2B", team="UAE")
    book.log("l1", "Acme", "2026-10-05")
    book.log("l2", "Stranger", "2026-10-05")                    # not on the master
    book.application("a1", at_applied="2026-10-04", region="MENA-B2B", team="UAE")
    book.application("a2", at_applied="2026-10-04")
    got = book.values(**{"from": "2026-10-03", "to": "2026-10-09", "regions": "MENA-B2B"})
    assert (got["onboarded"], got["logs"], got["applied"]) == (1, 1, 1)
    got = book.values(**{"from": "2026-10-03", "to": "2026-10-09", "regions": "Africa B2B"})
    assert (got["applied"], got["logs"]) == (1, 0)
    got = book.values(**{"from": "2026-10-03", "to": "2026-10-09"})
    assert got["logs"] == 1                                     # l2 has no master row, so no B2B area


def test_only_b2b_is_counted_whatever_is_asked(book):
    book.introducer("Acme", became="2026-10-04")
    book.introducer("Retail", became="2026-10-04", area="B2C")
    book.application("a1", at_applied="2026-10-04", intake_ym=202609)
    book.application("a2", at_applied="2026-10-04", area="B2C", intake_ym=202701)
    week = {"from": "2026-10-03", "to": "2026-10-09"}
    assert book.values(**week, areas="B2C") == book.values(**week)
    got = book.values(**week)
    assert (got["onboarded"], got["applied"]) == (1, 1)
    view = book.overview(**week)
    assert [a["name"] for a in view["options"]["areas"]] == ["B2B"]
    assert [i["id"] for i in view["options"]["intakes"]] == [202609]
    assert book.records(**week, metric="applied")["total"] == 1


def test_intake_narrows_applications_only(book):
    book.introducer("Acme", became="2026-10-04")
    book.application("a1", at_applied="2026-10-04", intake_ym=202609)
    book.application("a2", at_applied="2026-10-04", intake_ym=202701)
    got = book.values(**{"from": "2026-10-03", "to": "2026-10-09", "intakes": "202701"})
    assert (got["applied"], got["onboarded"]) == (1, 1)


def test_breakdown_and_records_agree(book):
    book.application("a1", at_offer="2026-10-04", team="T1", application_id="A-1")
    book.application("a2", at_offer="2026-10-05", team="T2", application_id="A-2")
    view = book.overview(**{"from": "2026-10-03", "to": "2026-10-09", "by": "team"})
    rows = {r["key"]: r["offer"] for r in view["breakdown"]["rows"]}
    assert rows == {"T1": 1, "T2": 1}
    rec = book.records(**{"from": "2026-10-03", "to": "2026-10-09", "metric": "offer", "dim": "team", "key": "T2"})
    assert rec["total"] == 1 and rec["rows"][0]["application_id"] == "A-2"


def test_bad_params_are_refused(book, metrics):
    with pytest.raises(metrics.ViewError):
        book.records(metric="nope")
    with pytest.raises(metrics.ViewError):
        book.overview(**{"from": "yesterday"})
