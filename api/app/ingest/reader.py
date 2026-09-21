"""File reading and column resolution.

Export headers arrive mangled: curly quotes, mojibake from a bad decode, stray
whitespace. Normalise hard, then match on exact name, substring, and finally
tokens -- never on a hard-coded header string.
"""
import csv
import io
import re
from dataclasses import dataclass, field

import polars as pl

_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "ʼ": "'", "′": "'", "´": "'",
    "“": '"', "”": '"', "″": '"',
})


def normalize_header(value: str) -> str:
    text = (value or "").translate(_QUOTES)
    text = re.sub(r"[^\x20-\x7E]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class Col:
    """One target column and how to find it in an arbitrary export."""
    target: str
    exact: str = ""
    tokens: tuple[str, ...] = ()
    required: bool = False


@dataclass
class Resolution:
    frame: pl.DataFrame
    mapping: dict[str, str] = field(default_factory=dict)   # target -> source header
    missing: list[str] = field(default_factory=list)        # required targets not found


class IngestError(Exception):
    pass


def _sniff_separator(head: bytes, sample_rows: int = 50) -> str:
    """The delimiter the header shares with the rows under it, outside quotes.

    A quoted header such as "Last, First";city carries commas that belong to
    the field, not the file. The even segments of a split on the quote
    character are the text outside quotes (as in count_records), so each line
    of that outside text is one record.

    Counting the header alone is not enough: a tab file may leave
    `Last, First, Middle` unquoted, and then its two commas tie with its two
    tabs. The real delimiter is the one every row repeats as often as the
    header does, so candidates are ranked by how many rows agree with the
    header first, and by how often the header carries them second. Rows may be
    ragged -- the reader tolerates junk lines -- which is why this is a share
    of rows rather than a demand that every row agree.
    """
    outside = b"".join(head.split(b'"')[::2]).decode("utf-8", "replace")
    lines = outside.split("\n")
    if len(lines) > 1:
        lines = lines[:-1]            # cut mid-record by the 64k head, or the empty tail
    header, rows = lines[0], [line for line in lines[1:sample_rows + 1] if line.strip()]

    def score(sep: str) -> tuple[int, int]:
        width = header.count(sep)
        if not width:
            return (0, 0)
        return (sum(row.count(sep) == width for row in rows), width)

    return max([",", "\t", ";", "|"], key=score)


def normalize_newlines(content: bytes) -> bytes:
    """Terminate every record with \n.

    Excel for Mac and several CRM exporters end records with a lone CR. Polars
    breaks rows on \n only, so such a file parses as one gigantic header: a
    114MB, 227k-row export arrived as a 2,907-column header and exhausted
    memory before a single row was read. Converting CRs inside quoted fields
    too is harmless -- a newline there is ordinary text under either byte.
    """
    if b"\r" not in content:
        return content
    return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def count_records(content: bytes) -> int:
    """Data rows in a newline-normalised csv, ignoring newlines inside quotes.

    Splitting on the quote character alternates outside/inside segments, so the
    even ones hold exactly the newlines that end a record.

    This shares polars' view of quoting, so it will not catch a file both agree
    to read wrongly. It is a tripwire on truncate_ragged_lines: that flag exists
    to tolerate junk rows, and the day it starts dropping good ones instead, the
    load fails loudly rather than serving a dashboard built on half the export.
    """
    trailing = 0                                     # blank lines at EOF are not records
    while trailing < len(content) and content[len(content) - 1 - trailing] == 0x0A:
        trailing += 1
    outside = sum(segment.count(b"\n") for segment in content.split(b'"')[::2])
    return max(outside - trailing, 0)                # the remaining header line cancels the last row


def _unescape_header(frame: pl.DataFrame, content: bytes, separator: str) -> pl.DataFrame:
    """Undo the doubled quotes polars leaves in header names.

    A quote inside a quoted field is written twice, so the field `"say ""hi""`
    followed by its closing quote is the name `say "hi"`. Polars unescapes that in rows but not in the header, and a
    spec searching for the quote would then miss the column. The csv module
    reads the header record the standard way; its spelling is taken only where
    polars kept a doubled quote, so polars' names for duplicate or blank
    headers stay as they are.
    """
    if not any('""' in name for name in frame.columns):
        return frame
    head = content[:64_000].decode("utf-8", "replace")
    header = next(csv.reader(io.StringIO(head), delimiter=separator), [])
    if len(header) != frame.width:
        return frame
    names = [ours if '""' in theirs and ours == theirs.replace('""', '"') else theirs
             for theirs, ours in zip(frame.columns, header)]
    if len(set(names)) != len(names):   # never rename onto another column
        return frame
    return frame.rename(dict(zip(frame.columns, names)))


def read_table(filename: str, content: bytes) -> pl.DataFrame:
    """Read csv/xls/xlsx into an all-strings frame. Never infers types."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xls", ".xlsb")):
        try:
            frame = pl.read_excel(io.BytesIO(content), infer_schema_length=0)
        except Exception as exc:  # noqa: BLE001
            raise IngestError(f"could not read the workbook: {exc}") from exc
    else:
        content = normalize_newlines(content)
        separator = _sniff_separator(content[:64_000])
        try:
            frame = pl.read_csv(
                io.BytesIO(content),
                separator=separator,
                encoding="utf8-lossy",
                infer_schema_length=0,
                has_header=True,
                truncate_ragged_lines=True,
                quote_char='"',
            )
        except Exception as exc:  # noqa: BLE001
            raise IngestError(f"could not read the file as CSV: {exc}") from exc
        # truncate_ragged_lines keeps junk rows from failing a good export, but it
        # also means a misparse loses rows in silence. Refuse the load instead.
        expected = count_records(content)
        if frame.height != expected:
            raise IngestError(
                f"read {frame.height:,} of {expected:,} rows -- the file did not parse cleanly. "
                "Check the delimiter and quoting, then re-export it."
            )
        frame = _unescape_header(frame, content, separator)
    if frame.height == 0:
        raise IngestError("the file has a header but no rows")
    return frame.with_columns(pl.all().cast(pl.Utf8))


def resolve_index(headers: list[str], col: Col) -> int | None:
    want = normalize_header(col.exact)
    if want:
        for i, head in enumerate(headers):
            if head == want:
                return i
        for i, head in enumerate(headers):
            if want in head:
                return i
    if col.tokens:
        for i, head in enumerate(headers):
            if all(token in head for token in col.tokens):
                return i
    return None


def apply_spec(frame: pl.DataFrame, cols: list[Col]) -> Resolution:
    """Select and rename the columns a dataset needs; report what is missing."""
    sources = list(frame.columns)
    headers = [normalize_header(c) for c in sources]
    used: set[int] = set()
    mapping: dict[str, str] = {}
    missing: list[str] = []
    exprs: list[pl.Expr] = []

    for col in cols:
        idx = resolve_index(headers, col)
        if idx is not None and idx in used:      # a second target must not steal the same column
            idx = None
        if idx is None:
            if col.required:
                missing.append(col.target)
            exprs.append(pl.lit(None, dtype=pl.Utf8).alias(col.target))
            continue
        used.add(idx)
        mapping[col.target] = sources[idx]
        exprs.append(pl.col(sources[idx]).alias(col.target))

    return Resolution(frame=frame.select(exprs), mapping=mapping, missing=missing)


def clean(expr: pl.Expr) -> pl.Expr:
    """Trim, and treat empty / '-' / 'null' as missing."""
    trimmed = expr.cast(pl.Utf8).str.strip_chars()
    return (
        pl.when(trimmed.is_null() | trimmed.eq("") | trimmed.eq("-") | trimmed.str.to_lowercase().eq("null"))
        .then(None)
        .otherwise(trimmed)
    )
