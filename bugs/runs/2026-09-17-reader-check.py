"""Dependency-free tests of the actual pure CSV helper bodies; no app imports."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "api/app/ingest/reader.py"
tree = ast.parse(SOURCE.read_text())
names = {"_sniff_separator", "normalize_newlines", "count_records"}
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert {node.name for node in functions} == names
helpers = {}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), helpers)


class ReaderHelpers(unittest.TestCase):
    def test_plain_separators(self):
        for separator in (",", "\t", ";", "|"):
            with self.subTest(separator=separator):
                content = f"name{separator}city\nAna{separator}Porto\n".encode()
                self.assertEqual(helpers["_sniff_separator"](content), separator)

    def test_record_counts(self):
        cases = [
            (b"h,x\na,1\nb,2\n", 2),
            (b"h,x\na,1\nb,2", 2),
            (b"h,x\na,1\nb,2\n\n\n", 2),
            (b'h,x\na,"multi\nline"\nb,2\n', 2),
            (b'h,x\na,"say ""hi""\nagain"\n', 1),
            (b"h,x\n", 0),
        ]
        for content, expected in cases:
            with self.subTest(content=content):
                self.assertEqual(helpers["count_records"](content), expected)

    def test_newline_normalization(self):
        self.assertEqual(helpers["normalize_newlines"](b"h\ra\r\nb\n"), b"h\na\nb\n")
        clean = b"h\na\n"
        self.assertIs(helpers["normalize_newlines"](clean), clean)

    def test_bug_001_quoted_header_delimiters(self):
        content = b'"Last, First, Middle";city\n"Doe, Jane, M";Lisbon\n'
        self.assertEqual(helpers["_sniff_separator"](content), ";")


if __name__ == "__main__":
    unittest.main(verbosity=2)
