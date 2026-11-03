"""Isolated header helper probes; synthetic frames, no Polars or app imports."""
from __future__ import annotations

import ast
import csv
import io
from pathlib import Path
import re
import unittest


SOURCE = Path(__file__).resolve().parents[2] / "api/app/ingest/reader.py"
tree = ast.parse(SOURCE.read_text(), filename=str(SOURCE))
names = {"_unescape_header", "normalize_header", "resolve_index"}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
quotes = next(n for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "_QUOTES" for t in n.targets))
assert {n.name for n in nodes} == names
future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
helpers = {"csv": csv, "io": io, "re": re}
exec(compile(ast.fix_missing_locations(ast.Module(body=[future, quotes, *nodes],
                                                type_ignores=[])), str(SOURCE), "exec"), helpers)


class Frame:
    """Only the column-name interface used by the actual helper."""
    def __init__(self, columns):
        self.columns = columns
        self.width = len(columns)

    def rename(self, mapping):
        return Frame([mapping.get(name, name) for name in self.columns])


class HeaderChecks(unittest.TestCase):
    def test_escaped_header_all_separators(self):
        for sep in (",", "\t", ";", "|"):
            stream = io.StringIO(newline="")
            writer = csv.writer(stream, delimiter=sep)
            writer.writerow(['say "hi"', "city"])
            writer.writerow(["synthetic", "Porto"])
            result = helpers["_unescape_header"](Frame(['say ""hi""', "city"]),
                                                   stream.getvalue().encode(), sep)
            self.assertEqual(result.columns, ['say "hi"', "city"])

    def test_unescaped_header_is_unchanged(self):
        frame = Frame(["name", "name_duplicated_0"])
        self.assertIs(helpers["_unescape_header"](frame, b"name,name\n1,2\n", ","), frame)

    def test_column_count_mismatch_is_unchanged(self):
        frame = Frame(['say ""hi""', "city"])
        self.assertIs(helpers["_unescape_header"](frame, b'"say ""hi"""\n1\n', ","), frame)

    def test_rename_collision_is_unchanged(self):
        frame = Frame(['say ""hi""', 'say "hi"'])
        self.assertIs(helpers["_unescape_header"](
            frame, b'"say ""hi""","say ""hi"""\n1,2\n', ","), frame)

    def test_unrelated_doubled_quote_name_is_unchanged(self):
        frame = Frame(['other ""name""', "city"])
        result = helpers["_unescape_header"](frame, b'"say ""hi""",city\n1,2\n', ",")
        self.assertEqual(result.columns, frame.columns)

    def test_multiline_header_quote_unescape(self):
        result = helpers["_unescape_header"](
            Frame(['say ""hi""\nagain', "city"]),
            b'"say ""hi""\nagain",city\n1,2\n', ",")
        self.assertEqual(result.columns, ['say "hi"\nagain', "city"])

    def test_header_normalization(self):
        self.assertEqual(helpers["normalize_header"]('  “Name”\tO’Brien\n'), '"name" o\'brien')
        self.assertEqual(helpers["normalize_header"](""), "")

    def test_resolution_precedence_and_missing(self):
        class Col:
            exact = "name"
            tokens = ("other",)
        resolve = helpers["resolve_index"]
        self.assertEqual(resolve(["other name", "name"], Col()), 1)
        self.assertEqual(resolve(["other name"], Col()), 0)
        self.assertEqual(resolve(["other value"], Col()), 0)
        self.assertIsNone(resolve(["unrelated"], Col()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
