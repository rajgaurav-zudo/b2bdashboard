"""Dependency-free probes of pure application helpers; no app imports or services."""
from __future__ import annotations

import ast
from datetime import date, timedelta
import gzip
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ViewError(Exception):
    pass


def extracted(path: str, names: set[str], extra: dict | None = None) -> dict:
    source = ROOT / path
    tree = ast.parse(source.read_text(), filename=str(source))
    functions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    assert {node.name for node in functions} == names
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    namespace = dict(extra or {})
    module = ast.fix_missing_locations(ast.Module(body=[future, *functions], type_ignores=[]))
    exec(compile(module, str(source), "exec"), namespace)
    return namespace


LOGS = extracted(
    "dashboards/logs/metrics.py",
    {"week_start", "pick_current_week", "_int", "_capped", "_teams"},
    {"date": date, "timedelta": timedelta, "ViewError": ViewError},
)

INTRO_360 = extracted(
    "dashboards/introducer_360/metrics.py",
    {"week_start", "_month_end", "last_year", "_range_label", "_names", "_intake", "_cell", "_delta"},
    {"date": date, "timedelta": timedelta, "ViewError": ViewError},
)

PERFORMANCE = extracted(
    "dashboards/introducer_performance/metrics.py",
    {"pick_current_year"},
)

SERVICE = extracted(
    "api/app/ingest/service.py",
    {"_q", "_changed_fields"},
)

STORAGE = extracted(
    "api/app/storage.py",
    {"_maybe_gunzip"},
    {"gzip": gzip, "_GZIP_MAGIC": b"\x1f\x8b"},
)


class LogMetricHelpers(unittest.TestCase):
    def test_every_day_maps_to_the_preceding_saturday(self):
        expected = date(2026, 9, 12)
        for offset in range(7):
            with self.subTest(offset=offset):
                self.assertEqual(LOGS["week_start"](expected + timedelta(days=offset)), expected)

    def test_current_week_ignores_a_future_week(self):
        weeks = [date(2026, 9, 5), date(2026, 9, 12), date(2026, 9, 19)]
        self.assertEqual(LOGS["pick_current_week"](weeks, date(2026, 9, 17)), date(2026, 9, 12))
        self.assertIsNone(LOGS["pick_current_week"]([], date(2026, 9, 17)))

    def test_numeric_parameters_are_bounded_and_bad_values_fail(self):
        self.assertEqual(LOGS["_int"]({"weeks": "0"}, "weeks", 8, 1, 260), 1)
        self.assertEqual(LOGS["_int"]({"weeks": "999"}, "weeks", 8, 1, 260), 260)
        self.assertEqual(LOGS["_int"]({}, "weeks", 8, 1, 260), 8)
        with self.assertRaises(ViewError):
            LOGS["_int"]({"weeks": "two"}, "weeks", 8, 1, 260)

    def test_team_and_summary_helpers(self):
        self.assertEqual(LOGS["_teams"]({"team": " North | | South "}), ["North", "South"])
        self.assertEqual(LOGS["_capped"](["Z", "A", "M", ""]), (["A", "M"], 1))


class Introducer360Helpers(unittest.TestCase):
    def test_week_month_and_leap_boundaries(self):
        self.assertEqual(INTRO_360["week_start"](date(2026, 9, 17)), date(2026, 9, 14))
        self.assertEqual(INTRO_360["_month_end"](date(2024, 2, 1)), date(2024, 2, 29))
        self.assertEqual(INTRO_360["last_year"](date(2024, 2, 29)), date(2023, 2, 28))

    def test_range_and_filter_helpers(self):
        self.assertEqual(
            INTRO_360["_range_label"](date(2025, 12, 30), date(2026, 1, 2)),
            "30 Dec 2025 – 2 Jan 2026",
        )
        self.assertEqual(INTRO_360["_names"]({"introducers": "A | | B"}), ["A", "B"])
        self.assertEqual(INTRO_360["_intake"]({}), (0, -1))
        self.assertEqual(INTRO_360["_intake"]({"intake_year": "2026", "intake_cycle": "2"}), (2026, 2))
        with self.assertRaises(ViewError):
            INTRO_360["_intake"]({"intake_cycle": "1"})

    def test_percentage_shaping_handles_zero_and_delta(self):
        self.assertEqual(
            INTRO_360["_cell"](0, 0, 0),
            {"created": 0, "active": 0, "closed": 0, "active_pct": 0, "closed_pct": 0},
        )
        self.assertIsNone(INTRO_360["_delta"](5, 0))
        self.assertEqual(INTRO_360["_delta"](15, 10), 50.0)


class GeneralHelpers(unittest.TestCase):
    def test_current_intake_year_floor_and_bounds(self):
        choose = PERFORMANCE["pick_current_year"]
        self.assertEqual(choose([(2025, 40), (2026, 87), (2027, 8)]), 2026)
        self.assertEqual(choose([(2025, 40), (2026, 87), (2027, 9)]), 2027)
        self.assertEqual(choose([(1900, 999), (2026, 3), (2100, 999)]), 2026)
        self.assertIsNone(choose([]))

    def test_sql_identifier_and_change_helpers(self):
        self.assertEqual(SERVICE["_q"]('a"b'), '"a""b"')
        self.assertEqual(SERVICE["_changed_fields"]({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4}), ["b", "c"])
        self.assertEqual(SERVICE["_changed_fields"](None, {"a": 1}), [])

    def test_archive_payload_round_trip_and_plain_bytes(self):
        payload = b"synthetic,data\n1,2\n"
        self.assertEqual(STORAGE["_maybe_gunzip"](gzip.compress(payload)), payload)
        self.assertIs(STORAGE["_maybe_gunzip"](payload), payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
