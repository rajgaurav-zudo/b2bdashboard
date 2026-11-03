"""Dependency-free region/report regressions; no application startup or services."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date, timedelta
import io
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "api"))
from app import regions
from app.reports.xlsx import Formula, Workbook, col_letter


def extract(path, names, namespace):
    source = ROOT / path
    nodes = [node for node in ast.parse(source.read_text()).body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    assert {node.name for node in nodes} == names
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(module, str(source), "exec"), namespace)
    return namespace


region_tests = extract("api/tests/test_regions.py", {
    "test_every_team_sits_in_exactly_one_region", "test_narrow",
    "test_options_total_each_region_and_keep_the_order", "test_split_uses_pipes",
}, {"regions": regions})
report = extract("api/app/reports/weekly_summary.py", {"Periods"}, {
    "dataclass": dataclass, "date": date, "timedelta": timedelta,
})
writer_test = extract("api/tests/test_weekly_summary.py", {
    "test_writer_escapes_text_and_caches_formula_values",
}, {"Workbook": Workbook, "Formula": Formula, "date": date, "zipfile": zipfile,
    "io": io, "ET": ET, "col_letter": col_letter})


class PureChecks(unittest.TestCase):
    def test_region_original_regressions(self):
        for name in sorted(n for n in region_tests if n.startswith("test_")):
            with self.subTest(name=name):
                region_tests[name]()

    def test_periods_week_leap_and_year_boundaries(self):
        Periods = report["Periods"]
        for today in (date(2024, 2, 29), date(2026, 1, 1), date(2026, 12, 31)):
            with self.subTest(today=today):
                p = Periods(today)
                self.assertEqual(p.week[0].weekday(), 5)
                self.assertEqual(p.week[1].weekday(), 4)
                self.assertLessEqual(p.week[0], today)
                self.assertGreaterEqual(p.week[1], today)
                self.assertEqual(p.last_week[1] + timedelta(1), p.week[0])
                closed = Periods.last_week_of(today)
                self.assertEqual(closed.today, p.last_week[1])
                self.assertTrue(closed.closed)
                self.assertEqual(closed.cur, "Last week")
                self.assertEqual(closed.prev, "Week before")
        self.assertEqual(Periods(date(2024, 2, 29)).lytd,
                         (date(2023, 1, 1), date(2023, 2, 28)))

    def test_writer_original_regression(self):
        writer_test["test_writer_escapes_text_and_caches_formula_values"]()


if __name__ == "__main__":
    unittest.main(verbosity=2)
