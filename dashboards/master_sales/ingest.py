"""Master Sales: how the applications export maps onto this dashboard's table.

Everything here is specific to this dashboard. Nothing imports it except the
registry. Every row is kept; filtering belongs to the reader.

Computed once, here, rather than in every query:

  * `stage`, the furthest rung of Applied -> Offered -> CoE -> Visa applied ->
    Visa granted -> Enrolled this application has reached, from its stage
    dates and, where the CRM recorded a state without a date, its status.
  * `on_*`, the date it first reached each rung, backfilled from the rungs
    after it: reaching CoE on 3 March means having been offered by 3 March.
  * `level_group`, Application Course Level as Academic, Language or Other,
    on the weekly summary's lists (app/reports/weekly_summary.py).
  * `deposit` and `on_deposit`, kept off the ladder. A deposit can be paid at
    any point from Offered on, so it proves an offer but nothing after it, and
    a CoE proves nothing about a deposit. A partial deposit proves an offer too,
    and its date (`on_pd`) dates the offer like a full one's.
  * `on_deferral_initiated` / `on_deferral_approved` and the two Yes/No flags,
    for DAA.
  * `deposit_state`, as the weekly summary's YTD sheets class it: a deposit
    paid in full is DAA when Deferred Initiated and Deferred Approved differ (a
    deferral awaiting approval) and Active when they agree; PartiallyPaid is
    PD. An export without the deferral columns reads as never deferred.
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

# Same resolution rule as Pipeline: the headers arrive with mojibake quotes, so
# the tokens are what find them, and the stricter visa headers are claimed
# before the looser `applied`. Part payment is claimed before the full one, and
# the deferral dates ride along: every one of these is parsed as a date.
STAGE_COLUMNS = [
    ("at_offered", "timestamp of 'offer' status", ("timestamp", "offer")),
    ("at_coe", "timestamp of 'coe received' status", ("timestamp", "coe")),
    ("at_visa_applied", "timestamp of 'visa| applied' status", ("timestamp", "visa", "applied")),
    ("at_visa_granted", "timestamp of 'visa| granted' status", ("timestamp", "visa", "granted")),
    ("at_enrolled", "timestamp of 'enrolled' status", ("timestamp", "enrolled")),
    ("at_pd", "timestamp of 'depositpaid| partiallypaid' status", ("timestamp", "partially")),
    ("at_deposit", "timestamp of 'deposit fully paid' status", ("timestamp", "deposit", "fully")),
    ("at_deferral_initiated", "timestamp deferral initiated", ("timestamp", "deferral", "initiated")),
    ("at_deferral_approved", "timestamp deferral approved", ("timestamp", "deferral", "approved")),
    ("at_applied", "timestamp of 'applied' status", ("timestamp", "applied")),
]

COLUMNS = {
    "applications": [
        Col("application_id", "application ref no", ("application", "ref")),
        Col("student_ref", "student ref id", ("student", "ref", "id"), required=True),
        Col("business_area", "studentassignedtobusinessarea"),
        Col("business_region", "studentassignedtobusinessregion"),
        Col("business_team", "currentlyassignedtobusinessteam"),
        Col("application_status", "application status", (), required=True),
        Col("deposit_paid_status", "deposit paid status", ("deposit", "paid")),
        Col("closed_lost_raw", "application closed lost", ("closed", "lost")),
        Col("deferral_initiated", "deferred initiated (no/yes/all)", ("deferred", "initiated")),
        Col("deferral_approved", "deferred approved (no/yes/all)", ("deferred", "approved")),
        Col("course_level", "application course level", ("course", "level")),
        Col("intake_month_raw", "actual intake month", ("actual", "intake", "month")),
        Col("intake_year_raw", "actual intake year", ("actual", "intake", "year")),
        *[Col(f"{target}_raw", exact, tokens) for target, exact, tokens in STAGE_COLUMNS],
    ],
}

# The ladder, lowest first. Its index + 1 is the stored `stage`.
LADDER = ["applied", "offered", "coe", "visa_applied", "visa_granted", "enrolled"]

# What a status says about how far an application got when no date says so.
# Conservative, as on Pipeline: `Visa` may mean the visa is being prepared, so it
# only proves CoE; `Closed Won` and `Final Decision` prove the application was
# submitted and nothing past it.
STATUS_FLOOR = {"applied": 1, "finaldecision": 1, "closedwon": 1, "offered": 2,
                "coereceived": 3, "visa": 3, "enrolled": 6}
DEPOSIT_PAID = ("fullypaid", "fullypaidwaitingforapproval")
UNASSIGNED = "Unassigned"

# The weekly summary's groups, matched on letters only and in any case.
ACADEMIC = ("alevel", "aslevel", "doctorate", "foundation", "gcsegradesac", "postgraduate",
            "premasters", "undergraduate")
LANGUAGE = ("language", "presessionalenglish")


def wrong_file_hint(dataset: str, headers: list[str]) -> str:
    normalized = [normalize_header(h) for h in headers]
    if dataset == "applications" and any("lifecycle" in h for h in normalized):
        return "This looks like the introducers master."
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
    if dataset != "applications":
        raise KeyError(f"unknown dataset '{dataset}'")

    out = frame.with_columns([
        *[_parse_date(f"{target}_raw").alias(target) for target, _, _ in STAGE_COLUMNS],
        _month_number().alias("intake_month"),
        clean(pl.col("intake_year_raw")).str.extract(r"((?:19|20)\d{2})", 1)
            .cast(pl.Int32, strict=False).alias("intake_year"),
    ])

    # first reached, backfilled from the top down. A deposit date proves an
    # offer (a deposit is paid against one), so Offered takes it too.
    out = out.with_columns(pl.col("at_enrolled").alias("on_enrolled"))
    out = out.with_columns(pl.min_horizontal("at_visa_granted", "on_enrolled").alias("on_visa_granted"))
    out = out.with_columns(pl.min_horizontal("at_visa_applied", "on_visa_granted").alias("on_visa_applied"))
    out = out.with_columns(pl.min_horizontal("at_coe", "on_visa_applied").alias("on_coe"))
    out = out.with_columns(pl.min_horizontal("at_offered", "at_deposit", "at_pd", "on_coe").alias("on_offered"))
    out = out.with_columns(pl.min_horizontal("at_applied", "on_offered").alias("on_applied"))

    deposit = pl.col("at_deposit").is_not_null() | _squash("deposit_paid_status").is_in(DEPOSIT_PAID).fill_null(False)
    partial = _squash("deposit_paid_status").eq("partiallypaid").fill_null(False)
    initiated = _squash("deferral_initiated").fill_null("no")
    approved = _squash("deferral_approved").fill_null("no")
    deferred = initiated != approved

    by_date = pl.lit(0, dtype=pl.Int16)
    for rank, name in enumerate(LADDER, start=1):
        by_date = pl.when(pl.col(f"on_{name}").is_not_null()).then(pl.lit(rank, dtype=pl.Int16)).otherwise(by_date)
    status = _squash("application_status")
    by_status = pl.lit(0, dtype=pl.Int16)
    for name, rank in STATUS_FLOOR.items():
        by_status = pl.when(status == name).then(pl.lit(rank, dtype=pl.Int16)).otherwise(by_status)
    by_deposit = pl.when(deposit | partial | pl.col("at_pd").is_not_null()).then(pl.lit(2, dtype=pl.Int16)).otherwise(pl.lit(0, dtype=pl.Int16))

    def assigned(col: str) -> pl.Expr:
        return pl.coalesce(clean(pl.col(col)), pl.lit(UNASSIGNED)).alias(col)

    out = out.with_columns([
        pl.max_horizontal(by_date, by_status, by_deposit).cast(pl.Int16).alias("stage"),
        deposit.alias("deposit"),
        pl.col("at_deposit").alias("on_deposit"),
        pl.col("at_pd").alias("on_pd"),
        pl.col("at_deferral_initiated").alias("on_deferral_initiated"),
        pl.col("at_deferral_approved").alias("on_deferral_approved"),
        initiated.eq("yes").alias("deferral_initiated"),
        approved.eq("yes").alias("deferral_approved"),
        clean(pl.col("application_id")).alias("application_id"),
        clean(pl.col("student_ref")).alias("student_ref"),
        assigned("business_area"), assigned("business_region"), assigned("business_team"),
        clean(pl.col("course_level")).alias("course_level"),
        pl.when(_squash("course_level").is_in(ACADEMIC)).then(pl.lit("Academic"))
          .when(_squash("course_level").is_in(LANGUAGE)).then(pl.lit("Language"))
          .otherwise(pl.lit("Other")).alias("level_group"),
        clean(pl.col("application_status")).alias("application_status"),
        clean(pl.col("deposit_paid_status")).alias("deposit_paid_status"),
        pl.when(deposit & deferred).then(pl.lit("DAA"))
          .when(deposit).then(pl.lit("Active"))
          .when(partial).then(pl.lit("PD"))
          .alias("deposit_state"),
        _squash("closed_lost_raw").eq("yes").fill_null(False).alias("closed_lost"),
    ])

    content = pl.concat_str([
        pl.col(c).cast(pl.Utf8).fill_null("\x00") for c in
        ("student_ref", "application_status", "intake_year", "intake_month", "on_applied", "on_offered")
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
        "app_uid", "application_id", "student_key",
        "business_area", "business_region", "business_team",
        "application_status", "deposit_paid_status", "closed_lost", "course_level", "level_group",
        "intake_year", "intake_month", "stage",
        *[f"on_{name}" for name in LADDER],
        "deposit", "on_deposit", "deposit_state", "on_pd",
        "deferral_initiated", "on_deferral_initiated", "deferral_approved", "on_deferral_approved",
    )


def stats(dataset: str, raw: pl.DataFrame, final: pl.DataFrame) -> dict:
    """Counts worth keeping on the load: rows the page cannot place."""
    return {
        "input_rows": raw.height,
        "no_student_ref": int(final.select(pl.col("student_key").str.starts_with("app:").sum()).item()),
        "no_intake": int(final.select((pl.col("intake_year").is_null() | pl.col("intake_month").is_null()).sum()).item()),
        "no_stage": int(final.select((pl.col("stage") == 0).sum()).item()),
    }
