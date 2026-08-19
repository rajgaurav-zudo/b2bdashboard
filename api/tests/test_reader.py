"""Core file-reading rules. Not tied to any dashboard.

The cases here are the ones a real CRM export actually broke on, not
hypotheticals: lone-CR record separators, and a parse that quietly kept a
fraction of the rows.
"""
import sys

import pytest

sys.path.insert(0, "/srv/api")

from app.ingest.reader import (  # noqa: E402
    IngestError,
    count_records,
    normalize_newlines,
    read_table,
)

HEADER = b"name,city,note"


def _csv(rows: list[bytes], sep: bytes = b"\n") -> bytes:
    return HEADER + sep + sep.join(rows) + sep


def test_lone_cr_records_are_split_like_newlines():
    """Excel for Mac ends records with \\r. Polars only breaks on \\n.

    Left alone, the whole file reads as a single header row -- which is how a
    227k-row export once arrived as one 2,907-column header.
    """
    mac = _csv([b"ana,lisbon,x", b"bo,porto,y", b"cy,braga,z"], sep=b"\r")
    assert mac.count(b"\n") == 0
    frame = read_table("export.csv", mac)
    assert frame.shape == (3, 3)
    assert frame["name"].to_list() == ["ana", "bo", "cy"]


def test_crlf_does_not_produce_blank_rows():
    frame = read_table("export.csv", _csv([b"ana,lisbon,x", b"bo,porto,y"], sep=b"\r\n"))
    assert frame.shape == (2, 3)


def test_newlines_inside_quoted_fields_stay_in_the_field():
    """A CR inside quotes is text, not a record break -- it must not split the row."""
    body = HEADER + b'\r' + b'ana,lisbon,"line one\rline two"' + b'\r'
    frame = read_table("export.csv", body)
    assert frame.height == 1
    assert frame["note"][0] == "line one\nline two"


def test_normalize_leaves_a_clean_file_untouched():
    clean = _csv([b"ana,lisbon,x"])
    assert normalize_newlines(clean) is clean


@pytest.mark.parametrize(
    "content,expected",
    [
        (b"h,x\na,1\nb,2\n", 2),                 # trailing newline
        (b"h,x\na,1\nb,2", 2),                   # no trailing newline
        (b"h,x\na,1\nb,2\n\n\n", 2),             # blank lines at EOF
        (b'h,x\na,"multi\nline"\nb,2\n', 2),     # newline inside quotes is not a record
        (b'h,x\na,"say ""hi""\nagain"\n', 1),    # escaped quotes keep the parity right
        (b"h,x\n", 0),                           # header only
    ],
)
def test_record_count_matches_the_parser(content, expected):
    assert count_records(content) == expected


def test_an_unbalanced_quote_is_refused_rather_than_half_read():
    """A stray quote swallows the rest of the file. Polars refuses it, and so do we.

    Loading a partial file is worse than failing: the dashboard would look
    healthy and be wrong.
    """
    body = HEADER + b'\n' + b'ana,lisbon,"oops\n' + b"\n".join(
        b"n%d,city,note" % i for i in range(50)
    ) + b"\n"
    with pytest.raises(IngestError):
        read_table("export.csv", body)


def test_the_row_guard_fires_when_the_parser_returns_fewer_rows(monkeypatch):
    """truncate_ragged_lines tolerates junk rows; it must never drop good ones.

    Polars keeps every row today, so this drives the shortfall directly -- the
    guard is a tripwire on that flag, not on any file we can currently write.
    """
    import polars as pl

    from app.ingest import reader

    full = _csv([b"n%d,city,note" % i for i in range(100)])
    monkeypatch.setattr(reader.pl, "read_csv", lambda *a, **k: pl.DataFrame(
        {"name": ["n0"], "city": ["city"], "note": ["note"]}
    ))
    with pytest.raises(IngestError) as err:
        reader.read_table("export.csv", full)
    assert "read 1 of 100 rows" in str(err.value)


def test_a_clean_file_passes_the_row_guard():
    frame = read_table("export.csv", _csv([b"n%d,city,note" % i for i in range(500)]))
    assert frame.height == 500
