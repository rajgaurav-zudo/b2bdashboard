"""Log dashboard: how the activity-log export maps onto this dashboard's table.

Everything here is specific to this dashboard. Nothing imports it except the
registry, and no other dashboard is affected by changes to it.
See context.md for the definitions these columns exist to serve.

Two things are decided here rather than at read time, because both must be
identical for every query and neither is cheap to recompute per request:

  * `week_start`, the Saturday a log belongs to. A week runs Saturday to Friday.
  * `note_score`, the keyword-lexicon sentiment of the note.

Both are functions of the file, so changing either means re-projecting the
archived upload (POST /uploads/{id}/project?dashboard=logs&force=true) rather
than asking for a fresh export.
"""
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, "/srv/api")
from app.ingest.reader import Col, clean, normalize_header  # noqa: E402

# What the live CRM exports: JavaScript's Date.toString(), offset and all.
JS_DATE_FORMAT = "%a %b %d %Y %H:%M:%S GMT%z"

# Log Time arrives as a timestamp in most exports and a bare date in some.
# Datetime formats are tried first so "2026-08-12 14:33" does not fall through
# to a date parser that would reject it.
DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
                    "%m/%d/%Y %H:%M", "%d-%m-%Y %H:%M", "%d %b %Y %H:%M",
                    "%b %d, %Y %H:%M", "%d/%m/%Y %I:%M %p", "%m/%d/%Y %I:%M %p")
# Day-first before month-first, matching the introducer_performance ingest: the
# same CRM produces both files, so they must not disagree about 03/04/2026.
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y",
                "%d %b %Y", "%b %d, %Y", "%d-%b-%Y")

COLUMNS = {
    "logs": [
        # `_id` is the CRM's own log id. It is not in the six columns the spec
        # names, but it is in the export, and a real id beats a content hash:
        # an edited note then shows up as a changed row rather than as a
        # removal plus an addition.
        Col("log_id", "_id", ("_id",)),
        # 'call type' before 'log type': both end in "type", and the looser
        # token match would otherwise let one take the other's column.
        Col("call_type", "call type", ("call", "type")),
        # log_type and log_time are resolved before `note`: 'note' is a short
        # enough fragment to be stolen by a longer header if it goes first.
        Col("log_type", "log type", ("log", "type"), required=True),
        Col("log_time", "log time", ("log", "time"), required=True),
        Col("introducer_name", "introducers name", ("introducer", "name"), required=True),
        Col("outcome", "outcome", ("outcome",)),
        Col("managed_by_team", "managed by team", ("managed", "team")),
        Col("created_by", "created by", ("created", "by")),
        Col("note", "note", ("note",)),
    ],
}

# --------------------------------------------------------------------------
# note sentiment
# --------------------------------------------------------------------------
# A keyword lexicon, not a model: the point is that anyone can read the rule that
# produced a score and argue with it. Negatives are counted first and then struck
# out of the text, so "not interested" scores -1 instead of cancelling itself
# against the "interested" inside it.
#
# Terms are matched on word boundaries against the lowercased note. A trailing
# '*' makes a term a prefix ("escalat*" catches escalate/escalated/escalation);
# without one the whole word must match, so "win" cannot fire on "window".

POSITIVE_TERMS = (
    "interested", "keen", "excited", "enthusiastic", "positive", "promising",
    "good", "great", "excellent", "strong", "happy", "pleased", "confident",
    "productive", "helpful", "supportive", "committed", "agreed", "agreement",
    "signed", "onboarded", "onboarding", "confirmed", "confirms", "will send",
    "sending", "shared", "referred", "referral*",
    "converted", "conversion", "growth", "growing",
    "increase", "increased", "expand*", "collaborat*", "partnership",
    "follow up scheduled", "meeting scheduled", "resolved",
    "smooth", "on track", "ready", "welcomed", "appreciate*",
    "thanks", "thank you", "successful", "success", "won",
)

NEGATIVE_TERMS = (
    "not interested", "no interest", "not responding", "no response", "unresponsive",
    "not reachable", "unreachable", "no answer", "did not answer", "didn't answer",
    "not available", "unavailable", "not happy", "unhappy", "not satisfied",
    "dissatisfied", "disappoint*", "frustrat*",
    "angry", "upset", "complain*", "complaint*", "escalat*",
    "issue*", "problem*", "concern*",
    "delay*", "pending", "stuck", "blocked", "blocker*",
    "reject*", "refused", "declined", "cancel*",
    "lost", "closed lost", "dormant", "inactive", "no longer",
    "stopped", "dropped", "poor", "bad", "weak", "slow", "difficult", "struggl*",
    "no update*", "chase", "chasing", "followed up again",
    "still waiting", "nothing yet", "not yet", "failed", "failure", "mistake",
    "error*", "wrong", "dispute", "unpaid", "refund",
)


def _boundary(terms: tuple[str, ...]) -> str:
    """One alternation, longest term first so 'not interested' wins over 'interested'.

    A term ending in '*' matches as a prefix; every other term is closed with a
    word boundary, so short words do not fire inside longer ones.
    """
    parts = []
    for term in sorted(terms, key=len, reverse=True):
        stem = term.endswith("*")
        body = term[:-1] if stem else term
        parts.append(body.replace(" ", r"\s+") + ("" if stem else r"\b"))
    return r"(?i)\b(?:" + "|".join(parts) + r")"


NEGATIVE_RE = _boundary(NEGATIVE_TERMS)
POSITIVE_RE = _boundary(POSITIVE_TERMS)


def wrong_file_hint(dataset: str, headers: list[str]) -> str:
    normalized = [normalize_header(h) for h in headers]
    if any("lifecycle" in h for h in normalized):
        return "This looks like the introducers master."
    if any("deposit paid" in h for h in normalized):
        return "This looks like the applications export."
    return ""


def _parse_day(col: str) -> pl.Expr:
    """The date a log happened, in UTC, time of day discarded.

    The live export writes JavaScript's own `Date.toString()`:

        Mon Aug 24 2026 10:55:45 GMT+0000 (Coordinated Universal Time)

    so that is tried first. The trailing "(...)" name is dropped because it is
    a localised label, not an offset -- the offset is the `GMT+0000`, and it is
    honoured rather than assumed: a row exported at +0530 converts to the UTC
    day, which is what the browser version's getUTC* calls did.
    """
    raw = clean(pl.col(col))
    js = raw.str.replace(r"\s*\(.*\)\s*$", "").str.to_datetime(
        JS_DATE_FORMAT, strict=False
    ).dt.convert_time_zone("UTC").dt.date()

    src = raw.str.slice(0, 40)
    expr = pl.lit(None, dtype=pl.Datetime(time_unit="us"))
    for fmt in DATETIME_FORMATS:
        expr = pl.coalesce(expr, src.str.to_datetime(fmt, strict=False))
    day = pl.coalesce(js, expr.dt.date())
    for fmt in DATE_FORMATS:
        day = pl.coalesce(day, src.str.to_date(fmt, strict=False))
    return day


def _week_start(day: pl.Expr) -> pl.Expr:
    """The Saturday on or before `day`. A week runs Saturday -> Friday.

    polars weekday() is 1=Monday..7=Sunday; the rule is written against
    JavaScript's 0=Sunday..6=Saturday, so it is converted rather than
    re-derived: `(js_dow + 1) % 7` days back lands on Saturday from any day.
    """
    js_dow = day.dt.weekday() % 7
    return day - pl.duration(days=(js_dow + 1) % 7)


def finalize(dataset: str, frame: pl.DataFrame) -> pl.DataFrame:
    if dataset != "logs":
        raise KeyError(f"unknown dataset '{dataset}'")

    day = _parse_day("log_time")
    note = clean(pl.col("note"))
    lower = note.str.to_lowercase()
    # count_matches returns UInt32, and (positives - negatives) on an unsigned
    # type wraps to ~4.3 billion instead of going negative -- which reads as a
    # spectacularly positive note. Cast before any arithmetic touches them.
    negatives = lower.str.count_matches(NEGATIVE_RE).fill_null(0).cast(pl.Int32)
    # strike the negative phrases out before counting positives, so the
    # "interested" inside "not interested" is not scored twice with the sign
    # flipped in between
    positives = (
        lower.str.replace_all(NEGATIVE_RE, " ").str.count_matches(POSITIVE_RE)
        .fill_null(0).cast(pl.Int32)
    )
    hits = positives + negatives

    out = frame.with_columns([
        day.alias("logged_on"),
        clean(pl.col("log_id")).alias("log_id"),
        clean(pl.col("log_type")).alias("log_type"),
        clean(pl.col("call_type")).alias("call_type"),
        clean(pl.col("outcome")).alias("outcome"),
        clean(pl.col("introducer_name")).alias("introducer_name"),
        clean(pl.col("managed_by_team")).alias("managed_by_team"),
        clean(pl.col("created_by")).alias("created_by"),
        note.alias("note"),
        note.str.count_matches(r"\S+").fill_null(0).cast(pl.Int32).alias("note_words"),
        hits.cast(pl.Int32).alias("note_hits"),
        pl.when(hits > 0)
        .then((positives - negatives) / hits)
        .otherwise(None)
        .cast(pl.Float32)
        .alias("note_score"),
    ])

    # A log with no readable date cannot be put in a week, and every figure on
    # this dashboard is a week. Dropped here and counted in stats().
    out = out.filter(pl.col("logged_on").is_not_null())
    out = out.with_columns(_week_start(pl.col("logged_on")).alias("week_start"))

    # The CRM's own `_id` when the export carries one -- it is the only key that
    # survives someone editing a note. Otherwise a content hash plus its
    # occurrence index, which is stable across re-uploads as long as the same row
    # appears the same number of times. Either way the changelog diff stays
    # meaningful, which is the whole point of having a natural key.
    content = pl.concat_str([
        pl.col(c).cast(pl.Utf8).fill_null("\x00") for c in
        ("logged_on", "log_type", "introducer_name", "managed_by_team", "created_by", "note")
    ], separator="\x1f").hash().cast(pl.Utf8)
    out = out.with_columns(content.alias("_c"))
    out = out.with_columns(
        pl.coalesce(
            pl.col("log_id"),
            pl.col("_c") + pl.lit("#") + pl.col("_c").cum_count().over("_c").cast(pl.Utf8),
        ).alias("log_uid")
    )
    # A duplicated id would break the primary key, and the export is not ours to
    # trust on that: keep the first occurrence, and count the rest in stats().
    out = out.unique(subset=["log_uid"], keep="first", maintain_order=True)

    return out.select(
        "log_uid", "log_id", "logged_on", "week_start", "log_type", "call_type",
        "outcome", "introducer_name", "managed_by_team", "created_by",
        "note", "note_words", "note_score", "note_hits",
    )


def stats(dataset: str, raw: pl.DataFrame, final: pl.DataFrame) -> dict:
    """Counts that disappear once undated rows are dropped, recorded on the load.

    Everything else the data notes need is recoverable from the loaded rows;
    the skipped rows are not, because they are gone by then.
    """
    dated = raw.filter(_parse_day("log_time").is_not_null()).height
    return {
        "input_rows": raw.height,
        "undated_rows": raw.height - dated,
        "duplicate_ids": dated - final.height,
        "blank_note_rows": final.filter(pl.col("note").is_null()).height,
        "blank_introducer_rows": final.filter(pl.col("introducer_name").is_null()).height,
    }
