"""Introducer 360: how the two exports map onto this dashboard's tables.

Everything here is specific to this dashboard. Nothing imports it except the
registry, and no other dashboard is affected by changes to it.

The reason this dashboard has its own ingest rather than reading the introducer
performance dashboard's tables is the block of `at_*` columns: the applications
export carries a timestamp for every status an application has passed through,
and nothing was reading them. They are what a pipeline with a date range on it
needs -- see context.md.

Value rules that belong to the CRM rather than to this dashboard (deposit states,
course categories, the intake period columns) follow sources/context.md, and are
implemented the same way here as they are next door. Two dashboards disagreeing
about what `FullyPaid` means would be a bug, not a preference.
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

# The nine stage timestamps, in funnel order. `target` is the column they land
# in; the tokens are what actually finds them, because the header arrives as
# `Timestamp of 'Draft' status` in one export and as mojibake around the same
# words in another. The quotes are normalised away either way, so a token match
# on the two words that matter is the only stable test.
#
# Order matters: resolution walks this list and a column already taken cannot be
# taken again, so `visa applied` and `visa granted` are claimed before the looser
# `applied` -- which would otherwise be free to wander onto them.
STAGE_COLUMNS = [
    ("at_draft_raw", "timestamp of 'draft' status", ("timestamp", "draft")),
    ("at_ready_raw", "timestamp of 'ready to apply' status", ("timestamp", "ready")),
    ("at_offer_raw", "timestamp of 'offer' status", ("timestamp", "offer")),
    ("at_coe_raw", "timestamp of 'coe received' status", ("timestamp", "coe")),
    ("at_visa_applied_raw", "timestamp of 'visa| applied' status", ("timestamp", "visa", "applied")),
    ("at_visa_granted_raw", "timestamp of 'visa| granted' status", ("timestamp", "visa", "granted")),
    ("at_enrolled_raw", "timestamp of 'enrolled' status", ("timestamp", "enrolled")),
    ("at_deposit_raw", "timestamp of 'deposit fully paid' status", ("timestamp", "deposit")),
    # last, so the three above have already claimed their columns
    ("at_applied_raw", "timestamp of 'applied' status", ("timestamp", "applied")),
]

COLUMNS = {
    "introducers": [
        Col("partner_name", "partner name", ("partner", "name"), required=True),
        Col("lifecycle_stage", "lifecycle stage", ("lifecycle",), required=True),
        Col("latest_contract_status", "latest contract status", ("contract", "status")),
        Col("country", "country", ("country",)),
        Col("srm_team", "partner managed by team(srm)", ("managed", "team")),
        Col("srm_owner", "partner managed by user(srm)", ("managed", "user")),
        Col("became_customer_date", "became customer date", ("became", "customer")),
    ],
    "applications": [
        Col("application_id", "application ref no", ("application", "ref")),
        Col("introducer_name", "application introducer name", ("introducer", "name"), required=True),
        # sub-status first so it cannot be stolen by the looser 'status' match
        Col("application_sub_status", "application sub-status", ("sub", "status")),
        Col("application_status", "application status", (), required=True),
        Col("deposit_paid_status", "deposit paid status", ("deposit", "paid")),
        Col("deferral_initiated_raw", "deferred initiated (no/yes/all)", ("deferred", "initiated")),
        Col("deferral_approved_raw", "deferred approved (no/yes/all)", ("deferred", "approved")),
        Col("course_level", "application course level", ("course", "level")),
        Col("closed_lost_raw", "application closed lost", ("closed", "lost")),
        Col("intake_month", "actual intake month", ("intake", "month")),
        Col("intake_year_raw", "actual intake year", ("intake", "year")),
        *[Col(target, exact, tokens) for target, exact, tokens in STAGE_COLUMNS],
    ],
}

# target -> the stored date column, for the loop below
STAGE_DATES = [(target, target[: -len("_raw")]) for target, _, _ in STAGE_COLUMNS]


def wrong_file_hint(dataset: str, headers: list[str]) -> str:
    normalized = [normalize_header(h) for h in headers]
    has_apps = any("introducer name" in h for h in normalized)
    has_master = any("lifecycle" in h for h in normalized)
    if dataset == "introducers" and has_apps:
        return "This looks like the applications export."
    if dataset == "applications" and has_master:
        return "This looks like the introducers master."
    return ""


def _parse_date(col: str) -> pl.Expr:
    """A date from whatever the export wrote. Every stage timestamp in the file
    is midnight, so the time of day is not information being thrown away."""
    expr = pl.lit(None, dtype=pl.Date)
    src = clean(pl.col(col)).str.slice(0, 30)
    for fmt in DATE_FORMATS:
        parsed = src.str.to_datetime(fmt, strict=False) if "%H" in fmt else src.str.to_date(fmt, strict=False)
        expr = pl.coalesce(expr, parsed.cast(pl.Date))
    return expr


def _year_of(col: str) -> pl.Expr:
    return pl.coalesce(
        _parse_date(col).dt.year(),
        clean(pl.col(col)).str.extract(r"((?:19|20)\d{2})", 1).cast(pl.Int32, strict=False),
    )


def _deposit_status() -> pl.Expr:
    """Normalised once. `FullyPaid`, `fullyPaidWaitingForApproval` and
    `PartiallyPaid` are distinct values and must stay distinct."""
    return clean(pl.col("deposit_paid_status")).str.to_lowercase().str.replace_all(r"\s+", "")


COURSE_LANGUAGE = "Language"
COURSE_PRESESSIONAL = "Pre-sessional English"
COURSE_ACADEMIC = "Academic"


def _course_category(has_levels: bool) -> pl.Expr:
    """The three categories of sources/context.md, Academic as the residue.

    Same rule, same reasons, as the introducer performance dashboard: a course
    level the CRM adds tomorrow reports as Academic rather than falling out of
    every figure in silence, and a file that carries no course levels at all is
    Academic rather than wholly Unspecified.
    """
    if not has_levels:
        return pl.lit(COURSE_ACADEMIC)
    level = clean(pl.col("course_level")).str.to_lowercase().str.replace_all(r"[^a-z]", "")
    return (
        pl.when(level.is_null()).then(pl.lit("Unspecified"))
        .when(level == "language").then(pl.lit(COURSE_LANGUAGE))
        .when(level.str.starts_with("presessional")).then(pl.lit(COURSE_PRESESSIONAL))
        .otherwise(pl.lit(COURSE_ACADEMIC))
    )


def _month_number() -> pl.Expr:
    text = clean(pl.col("intake_month")).str.to_lowercase().str.slice(0, 3)
    numeric = clean(pl.col("intake_month")).str.extract(r"^(\d{1,2})$", 1).cast(pl.Int32, strict=False)
    mapped = pl.lit(None, dtype=pl.Int32)
    for name, number in MONTHS.items():
        mapped = pl.when(text == name).then(pl.lit(number, dtype=pl.Int32)).otherwise(mapped)
    return pl.coalesce(numeric, mapped)


def finalize(dataset: str, frame: pl.DataFrame) -> pl.DataFrame:
    if dataset == "introducers":
        out = frame.with_columns([
            clean(pl.col("partner_name")).alias("partner_name"),
            *[clean(pl.col(c)).alias(c) for c in
              ("lifecycle_stage", "latest_contract_status", "country", "srm_team", "srm_owner")],
            _parse_date("became_customer_date").alias("became_customer_date"),
            _year_of("became_customer_date").alias("became_customer_year"),
        ])
        out = out.filter(pl.col("partner_name").is_not_null()).unique(subset=["partner_name"], keep="first")
        return out.select(
            "partner_name", "lifecycle_stage", "latest_contract_status", "country",
            "srm_team", "srm_owner", "became_customer_date", "became_customer_year",
        )

    if dataset == "applications":
        has_levels = bool(frame.select(clean(pl.col("course_level")).is_not_null().any()).item())
        month = _month_number()
        year = clean(pl.col("intake_year_raw")).str.extract(r"((?:19|20)\d{2})", 1).cast(pl.Int32, strict=False)
        cycle_index = (
            pl.when(month.is_null()).then(None)
            .when(month.is_in([11, 12, 1, 2, 3])).then(0)
            .when(month.is_in([4, 5, 6, 7])).then(1)
            .when(month.is_in([8, 9, 10])).then(2)
            .otherwise(None)
        ).cast(pl.Int16)

        out = frame.with_columns([
            clean(pl.col("introducer_name")).alias("introducer_name"),
            clean(pl.col("application_id")).alias("application_id"),
            clean(pl.col("deposit_paid_status")).alias("deposit_paid_status"),
            clean(pl.col("intake_month")).alias("intake_month"),
            clean(pl.col("application_status")).alias("application_status"),
            clean(pl.col("application_sub_status")).alias("application_sub_status"),
            year.alias("intake_year"),
            cycle_index.alias("cycle_index"),
            _deposit_status().eq("fullypaid").fill_null(False).alias("deposit_fully_paid"),
            _deposit_status().eq("partiallypaid").fill_null(False).alias("deposit_partial"),
            clean(pl.col("deferral_initiated_raw")).str.to_lowercase()
                .eq("yes").fill_null(False).alias("deferral_initiated"),
            clean(pl.col("deferral_approved_raw")).str.to_lowercase()
                .eq("yes").fill_null(False).alias("deferral_approved"),
            clean(pl.col("course_level")).alias("course_level"),
            _course_category(has_levels).alias("course_category"),
            clean(pl.col("closed_lost_raw")).str.to_lowercase().eq("yes").fill_null(False).alias("closed_lost"),
            *[_parse_date(raw).alias(target) for raw, target in STAGE_DATES],
        ])

        # When this application entered the pipeline at all. The two stages that
        # are states rather than events -- a partial deposit, an initiated
        # deferral -- have no timestamp of their own, so this is what the date
        # range filters them on. Least of the stage dates rather than at_draft,
        # because a third of the export has an Applied date and no Draft one.
        out = out.with_columns(
            pl.min_horizontal([pl.col(target) for _, target in STAGE_DATES]).alias("at_entered")
        )

        content = pl.concat_str([
            pl.col(c).cast(pl.Utf8).fill_null("\x00") for c in
            ("introducer_name", "deposit_paid_status", "closed_lost", "intake_month",
             "intake_year", "application_status", "application_sub_status")
        ], separator="\x1f").hash().cast(pl.Utf8)
        out = out.with_columns(pl.coalesce(pl.col("application_id"), content).alias("_k"))
        out = out.with_columns(
            pl.when(pl.len().over("_k") == 1).then(pl.col("_k"))
            .otherwise(pl.col("_k") + pl.lit("#") + pl.col("_k").cum_count().over("_k").cast(pl.Utf8))
            .alias("app_uid")
        )
        return out.select(
            "app_uid", "application_id", "introducer_name",
            *[target for _, target in STAGE_DATES], "at_entered",
            "deposit_paid_status", "deposit_fully_paid", "deposit_partial",
            "deferral_initiated", "deferral_approved", "closed_lost",
            "course_level", "course_category", "intake_month", "intake_year",
            "cycle_index", "application_status", "application_sub_status",
        )

    raise KeyError(f"unknown dataset '{dataset}'")


def stats(dataset: str, raw: pl.DataFrame, final: pl.DataFrame) -> dict:
    """Counts that cannot be recovered from the loaded rows.

    `no_stage_dates` is the one worth watching: an export from before the
    timestamp columns existed loads cleanly and shows an empty pipeline, so the
    number of rows carrying no stage date at all is recorded on the load rather
    than left to be inferred from a page of zeroes.
    """
    if dataset == "introducers":
        named = raw.filter(clean(pl.col("partner_name")).is_not_null()).height
        return {"input_rows": raw.height, "blank_name_rows": raw.height - named,
                "duplicate_names": named - final.height}
    return {
        "input_rows": raw.height,
        "no_stage_dates": int(final.select(pl.col("at_entered").is_null().sum()).item()),
        "no_introducer": int(final.select(pl.col("introducer_name").is_null().sum()).item()),
    }
