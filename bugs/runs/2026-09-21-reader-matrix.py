"""Synthetic CSV helper regression matrix; no app imports or services."""
import ast
import csv
import io
from pathlib import Path


source = Path(__file__).resolve().parents[2] / "api/app/ingest/reader.py"
names = {"_sniff_separator", "normalize_newlines", "count_records"}
tree = ast.parse(source.read_text())
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
assert {n.name for n in functions} == names
helpers = {}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), helpers)

cases = 0
failures = []
for delimiter in (",", "\t", ";", "|"):
    for ending in ("\n", "\r\n", "\r"):
        for quoted in (csv.QUOTE_MINIMAL, csv.QUOTE_ALL):
            for header in ("name", "Last, First, Middle", 'say "hello"', "multi\r\nline"):
                for row_count in (1, 2, 10):
                    stream = io.StringIO(newline="")
                    writer = csv.writer(stream, delimiter=delimiter, lineterminator=ending,
                                        quoting=quoted)
                    writer.writerow([header, "city", "note"])
                    for row in range(row_count):
                        writer.writerow([f"person{row}", "Lisbon", 'a,b;c|d\t"quoted"'])
                    payload = helpers["normalize_newlines"](stream.getvalue().encode())
                    actual = helpers["_sniff_separator"](payload)
                    context = (delimiter, ending, quoted, header, row_count)
                    if actual != delimiter:
                        failures.append((context, actual))
                    assert helpers["count_records"](payload) == row_count, context
                    cases += 1
print(f"{cases} synthetic CSV cases; {len(failures)} separator failures; all record counts passed")
if failures:
    print(f"First separator failure: {failures[0]!r}")
    raise SystemExit(1)
