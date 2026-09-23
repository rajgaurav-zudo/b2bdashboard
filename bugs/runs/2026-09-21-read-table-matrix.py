"""The 288-case CSV matrix, run through the real Polars-backed `read_table`.

Needs the API's dependencies, so run it inside the API container, which does
not mount `bugs/`; feed the script on stdin:

    docker compose exec -T api python - < bugs/runs/2026-09-21-read-table-matrix.py

Reports separator, header-name and row failures separately, so a header-name
failure (BUG-003) cannot hide or be mistaken for a separator one (BUG-002).
"""
import collections
import csv
import io
import sys

sys.path.insert(0, "/srv/api")
from app.ingest.reader import _sniff_separator, normalize_newlines, read_table  # noqa: E402

cases = 0
separator_bad, header_bad, rows_bad = [], collections.Counter(), []
for delimiter in (",", "\t", ";", "|"):
    for ending in ("\n", "\r\n", "\r"):
        for quoted in (csv.QUOTE_MINIMAL, csv.QUOTE_ALL):
            for header in ("name", "Last, First, Middle", 'say "hello"', "multi\r\nline"):
                for row_count in (1, 2, 10):
                    stream = io.StringIO(newline="")
                    writer = csv.writer(stream, delimiter=delimiter, lineterminator=ending,
                                        quoting=quoted)
                    writer.writerow([header, "city", "note"])
                    rows = [[f"person{i}", "Lisbon", 'a,b;c|d\t"quoted"'] for i in range(row_count)]
                    writer.writerows(rows)
                    payload = stream.getvalue().encode()
                    context = (delimiter, ending, quoted, header, row_count)
                    cases += 1
                    if _sniff_separator(normalize_newlines(payload)) != delimiter:
                        separator_bad.append(context)
                    frame = read_table("export.csv", payload)
                    if frame.columns != [header.replace("\r\n", "\n"), "city", "note"]:
                        header_bad[header] += 1
                    if frame.rows() != [tuple(r) for r in rows]:
                        rows_bad.append(context)

print(f"{cases} cases through read_table")
print(f"separator failures: {len(separator_bad)}")
print(f"row failures: {len(rows_bad)}")
print(f"header-name failures by header: {dict(header_bad)}")
if separator_bad or rows_bad:
    raise SystemExit(1)
