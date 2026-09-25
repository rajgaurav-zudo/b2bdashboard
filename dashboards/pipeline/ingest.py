"""Pipeline: how the applications export maps onto this dashboard's table.

Everything here is specific to this dashboard. Nothing imports it except the
registry. It deliberately keeps every row -- direct, indirect, every course
level -- because the page is about the whole intake, and filtering belongs to
the reader, not to the loader.

Two things are computed once, here, rather than in every query:

  * `stage`, the furthest stage this application has reached, from its stage
    dates and, where the CRM recorded a state without a date, its status.
  * `on_*`, the date it first reached each stage, backfilled from the stages
    after it. The export carries an Offer date for most applications and an
    Applied date for nearly all, but 3,834 have a later date and no Applied one;
    reaching Offer on 3 March means having applied by 3 March, so that is what
    is stored rather than a gap.
"""
import sys

import polars as pl

sys.path.insert(0, "/srv/api")
from app.ingest.reader import Col, clean, normalize_header  # noqa: E402

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y",
                "%Y/%m/%d", "%d-%m-%Y", "%d %b %Y", "%b %d, %Y", "%d-%b-%Y")

# The stage timestamps this dashboard reads. Same resolution rule as Introducer
# 360: the headers arrive with mojibake quotes, so the tokens are what find them,
# and the stricter visa headers are claimed before the looser `applied`.
STAGE_COLUMNS = [
    ("at_offer", "timestamp of 'offer' status", ("timestamp", "offer")),
    ("at_coe", "timestamp of 'coe received' status", ("timestamp", "coe")),
    ("at_visa_applied", "timestamp of 'visa| applied' status", ("timestamp", "visa", "applied")),
    ("at_visa_granted", "timestamp of 'visa| granted' status", ("timestamp", "visa", "granted")),
    ("at_enrolled", "timestamp of 'enrolled' status", ("timestamp", "enrolled")),
    ("at_deposit", "timestamp of 'deposit fully paid' status", ("timestamp", "deposit")),
    ("at_applied", "timestamp of 'applied' status", ("timestamp", "applied")),
]

COLUMNS = {
    "introducers": [
        Col("partner_name", "partner name", ("partner", "name"), required=True),
        Col("srm_team", "partner managed by team(srm)", ("managed", "team")),
    ],
    "applications": [
        Col("application_id", "application ref no", ("application", "ref")),
        Col("student_ref", "student ref id", ("student", "ref", "id"), required=True),
        Col("introducer_name", "application introducer name", ("introducer", "name")),
        Col("recruitment_type", "recruitment type", ("recruitment", "type")),
        Col("application_status", "application status", (), required=True),
        Col("deposit_paid_status", "deposit paid status", ("deposit", "paid")),
        Col("course_level", "application course level", ("course", "level")),
        Col("closed_lost_raw", "application closed lost", ("closed", "lost")),
        Col("intake_month_raw", "actual intake month", ("actual", "intake", "month")),
        Col("intake_year_raw", "actual intake year", ("actual", "intake", "year")),
        *[Col(f"{target}_raw", exact, tokens) for target, exact, tokens in STAGE_COLUMNS],
    ],
}

# The ladder, lowest first. Its index + 1 is the stored `stage`.
LADDER = ["applied", "offer", "deposit", "coe", "visa", "enrolled"]

# What a status says about how far an application got when no date says so.
# Conservative: `Visa` may mean applied rather than granted, so it only proves
# CoE; `Closed Won` and `Final Decision` prove the application was submitted and
# nothing past it.
STATUS_FLOOR = {"applied": 1, "finaldecision": 1, "closedwon": 1, "offered": 2,
                "coereceived": 4, "visa": 4, "enrolled": 6}
DEPOSIT_PAID = ("fullypaid", "fullypaidwaitingforapproval")


def wrong_file_hint(dataset: str, headers: list[str]) -> str:
    normalized = [normalize_header(h) for h in headers]
    if dataset == "applications" and any("lifecycle" in h for h in normalized):
        return "This looks like the introducers master."
    if dataset == "introducers" and any("application status" in h for h in normalized):
        return "This looks like the applications export."
    return ""


def _parse_date(col: str) -> pl.Expr:
    expr = pl.lit(None, dtype=pl.Date)
    src = clean(pl.col(col)).str.slice(0, 30)
    for fmt in DATE_FORMATS:
        parsed = src.str.to_datetime(fmt, strict=False) if "%H" in fmt else src.str.to_date(fmt, strict=False)
        expr = pl.coalesce(expr, parsed.cast(pl.Date))
    return expr


def _month_number() -> pl.Expr:
    raw = clean(pl.col("intake_month_raw"))
    text = raw.str.to_lowercase().str.slice(0, 3)
    numeric = raw.str.extract(r"^(\d{1,2})$", 1).cast(pl.Int16, strict=False)
    mapped = pl.lit(None, dtype=pl.Int16)
    for name, number in MONTHS.items():
        mapped = pl.when(text == name).then(pl.lit(number, dtype=pl.Int16)).otherwise(mapped)
    month = pl.coalesce(numeric, mapped)
    return pl.when(month.is_between(1, 12)).then(month).otherwise(None)


def _squash(col: str) -> pl.Expr:
    return clean(pl.col(col)).str.to_lowercase().str.replace_all(r"[^a-z]", "")


def finalize(dataset: str, frame: pl.DataFrame) -> pl.DataFrame:
    if dataset == "introducers":
        out = frame.with_columns(clean(pl.col("partner_name")).alias("partner_name"),
                                 clean(pl.col("srm_team")).alias("srm_team"))
        out = out.filter(pl.col("partner_name").is_not_null()).unique(subset=["partner_name"], keep="first")
        return out.select("partner_name", "srm_team")
    if dataset != "applications":
        raise KeyError(f"unknown dataset '{dataset}'")

    out = frame.with_columns([
        *[_parse_date(f"{target}_raw").alias(target) for target, _, _ in STAGE_COLUMNS],
        _month_number().alias("intake_month"),
        clean(pl.col("intake_year_raw")).str.extract(r"((?:19|20)\d{2})", 1)
            .cast(pl.Int32, strict=False).alias("intake_year"),
    ])

    # first reached, backfilled from the top down: each stage is no later than
    # the earliest date of any stage after it. CoE also takes the Visa applied
    # date -- a visa application needs the CoE in hand.
    out = out.with_columns(pl.col("at_enrolled").alias("on_enrolled"))
    out = out.with_columns(pl.min_horizontal("at_visa_granted", "on_enrolled").alias("on_visa"))
    out = out.with_columns(pl.min_horizontal("at_coe", "at_visa_applied", "on_visa").alias("on_coe"))
    out = out.with_columns(pl.min_horizontal("at_deposit", "on_coe").alias("on_deposit"))
    out = out.with_columns(pl.min_horizontal("at_offer", "on_deposit").alias("on_offer"))
    out = out.with_columns(pl.min_horizontal("at_applied", "on_offer").alias("on_applied"))

    by_date = pl.lit(0, dtype=pl.Int16)
    for rank, name in enumerate(LADDER, start=1):
        by_date = pl.when(pl.col(f"on_{name}").is_not_null()).then(pl.lit(rank, dtype=pl.Int16)).otherwise(by_date)
    status = _squash("application_status")
    by_status = pl.lit(0, dtype=pl.Int16)
    for name, rank in STATUS_FLOOR.items():
        by_status = pl.when(status == name).then(pl.lit(rank, dtype=pl.Int16)).otherwise(by_status)
    by_deposit = pl.when(_squash("deposit_paid_status").is_in(DEPOSIT_PAID)) \
        .then(pl.lit(3, dtype=pl.Int16)).otherwise(pl.lit(0, dtype=pl.Int16))

    out = out.with_columns([
        pl.max_horizontal(by_date, by_status, by_deposit).cast(pl.Int16).alias("stage"),
        clean(pl.col("application_id")).alias("application_id"),
        clean(pl.col("student_ref")).alias("student_ref"),
        clean(pl.col("introducer_name")).alias("introducer_name"),
        clean(pl.col("recruitment_type")).alias("recruitment_type"),
        pl.coalesce(clean(pl.col("course_level")), pl.lit("Unspecified")).alias("course_level"),
        clean(pl.col("application_status")).alias("application_status"),
        clean(pl.col("deposit_paid_status")).alias("deposit_paid_status"),
        _squash("closed_lost_raw").eq("yes").fill_null(False).alias("closed_lost"),
        pl.when(pl.col("intake_month").is_not_null() & pl.col("intake_year").is_not_null())
          .then(pl.col("intake_year") * 100 + pl.col("intake_month").cast(pl.Int32))
          .otherwise(None).alias("intake_ym"),
    ])

    content = pl.concat_str([
        pl.col(c).cast(pl.Utf8).fill_null("\x00") for c in
        ("student_ref", "course_level", "application_status", "intake_ym", "on_applied", "on_offer")
    ], separator="\x1f").hash().cast(pl.Utf8)
    out = out.with_columns(pl.coalesce(pl.col("application_id"), content).alias("_k"))
    out = out.with_columns(
        pl.when(pl.len().over("_k") == 1).then(pl.col("_k"))
        .otherwise(pl.col("_k") + pl.lit("#") + pl.col("_k").cum_count().over("_k").cast(pl.Utf8))
        .alias("app_uid")
    )
    out = out.with_columns(
        pl.coalesce(pl.col("student_ref"), pl.lit("app:") + pl.col("app_uid")).alias("student_key")
    )
    return out.select(
        "app_uid", "application_id", "student_key", "introducer_name", "recruitment_type", "course_level",
        "application_status", "deposit_paid_status", "closed_lost",
        "intake_year", "intake_month", "intake_ym", "stage",
        *[f"on_{name}" for name in LADDER],
    )


def stats(dataset: str, raw: pl.DataFrame, final: pl.DataFrame) -> dict:
    """Counts worth keeping on the load: rows the page cannot place."""
    if dataset == "introducers":
        return {"input_rows": raw.height, "partners": final.height}
    return {
        "input_rows": raw.height,
        "no_student_ref": int(final.select(pl.col("student_key").str.starts_with("app:").sum()).item()),
        "no_intake": int(final.select(pl.col("intake_ym").is_null().sum()).item()),
        "no_stage": int(final.select((pl.col("stage") == 0).sum()).item()),
    }
