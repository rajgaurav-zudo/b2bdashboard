"""B2B Pulse: how the three platform exports map onto this dashboard's tables.

Everything here is specific to this dashboard. Nothing imports it except the
registry. Every row is kept: the page counts events by the day they happened,
and filtering belongs to the reader.

Area, region and team are stored already defaulted to 'Unassigned', so the page
can offer "Unassigned" as a choice like any other and no query has to treat a
null specially. Applications take the student's business area and region and
the currently assigned business team -- the same columns the weekly summary
reads. A log carries none; metrics.py takes its introducer's from the master.
"""
import sys

import polars as pl

sys.path.insert(0, "/srv/api")
from app.ingest.reader import Col, clean, normalize_header  # noqa: E402

UNASSIGNED = "Unassigned"
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y",
                "%Y/%m/%d", "%d-%m-%Y", "%d %b %Y", "%b %d, %Y", "%d-%b-%Y")
JS_DATE_FORMAT = "%a %b %d %Y %H:%M:%S GMT%z"

# Stage timestamps, stricter headers first: 'visa| granted' must be claimed
# before anything looser could take it, and 'applied' goes last because
# 'visa| applied' also contains the word.
STAGE_COLUMNS = [
    ("at_offer", "timestamp of offer status", ("timestamp", "offer")),
    ("at_coe", "timestamp of coe received status", ("timestamp", "coe")),
    ("at_visa", "timestamp of visa| granted status", ("timestamp", "visa", "granted")),
    ("at_enrolled", "timestamp of enrolled status", ("timestamp", "enrolled")),
    ("at_deposit", "timestamp of deposit fully paid status", ("timestamp", "deposit")),
    ("at_closed", "timestamp of application marked as closed", ("timestamp", "closed")),
    ("at_applied", "timestamp of applied status", ("timestamp", "applied")),
]

COLUMNS = {
    "introducers": [
        Col("partner_name", "partner name", ("partner", "name"), required=True),
        Col("introducer_id", "_id", ()),
        Col("introducer_status", "introducer status", ("introducer", "status")),
        Col("country", "country", ()),
        Col("srm_owner", "partner managed by user(srm)", ("managed", "user")),
        Col("srm_team", "partner managed by team(srm)", ("managed", "team")),
        Col("became_raw", "became customer date", ("became", "customer")),
        Col("area_raw", "businessarea", ()),
        Col("region_raw", "businessregion", ()),
        Col("team_raw", "businessteam", ()),
    ],
    "applications": [
        Col("application_id", "application ref no", ("application", "ref")),
        Col("student_ref", "student ref id", ("student", "ref", "id")),
        Col("student_name", "student name", ()),
        Col("student_country", "student country", ()),
        Col("introducer_name", "application introducer name", ("introducer", "name")),
        Col("institution", "institution name", ("institution",)),
        Col("course_name", "course name", ()),
        Col("course_level", "application course level", ("course", "level")),
        Col("recruitment_type", "recruitment type", ("recruitment", "type")),
        Col("application_status", "application status", (), required=True),
        Col("deposit_paid_status", "deposit paid status", ("deposit", "paid")),
        Col("intake_month_raw", "actual intake month", ("actual", "intake", "month")),
        Col("intake_year_raw", "actual intake year", ("actual", "intake", "year")),
        Col("area_raw", "studentassignedtobusinessarea", ()),
        Col("region_raw", "studentassignedtobusinessregion", ()),
        Col("team_raw", "currentlyassignedtobusinessteam", ()),
        *[Col(f"{target}_raw", exact, tokens) for target, exact, tokens in STAGE_COLUMNS],
    ],
    "logs": [
        Col("log_id", "_id", ()),
        Col("call_type", "call type", ("call", "type")),
        Col("log_type", "log type", ("log", "type"), required=True),
        Col("log_time", "log time", ("log", "time"), required=True),
        Col("introducer_name", "introducers name", ("introducer", "name"), required=True),
        Col("outcome", "outcome", ()),
        Col("managed_by_team", "managed by team", ("managed", "team")),
        Col("created_by", "created by", ("created", "by")),
        Col("note", "note", ()),
    ],
}

APP_DATES = ("at_applied", "at_offer", "at_deposit", "at_coe", "at_visa", "at_enrolled", "at_closed")


def wrong_file_hint(dataset: str, headers: list[str]) -> str:
    normalized = [normalize_header(h) for h in headers]
    if dataset != "introducers" and any("lifecycle" in h for h in normalized):
        return "This looks like the introducers master."
    if dataset != "applications" and any("application status" in h for h in normalized):
        return "This looks like the applications export."
    if dataset != "logs" and any("log type" in h for h in normalized):
        return "This looks like the introducer activity log."
    return ""


def _parse_date(col: str) -> pl.Expr:
    expr = pl.lit(None, dtype=pl.Date)
    src = clean(pl.col(col)).str.slice(0, 30)
    for fmt in DATE_FORMATS:
        parsed = src.str.to_datetime(fmt, strict=False) if "%H" in fmt else src.str.to_date(fmt, strict=False)
        expr = pl.coalesce(expr, parsed.cast(pl.Date))
    return expr


def _parse_log_day(col: str) -> pl.Expr:
    """Log Time is JavaScript's Date.toString() in the live export, honoured in
    UTC like the Logs dashboard; plain dates are the fallback."""
    raw = clean(pl.col(col))
    js = raw.str.replace(r"\s*\(.*\)\s*$", "").str.to_datetime(
        JS_DATE_FORMAT, strict=False
    ).dt.convert_time_zone("UTC").dt.date()
    return pl.coalesce(js, _parse_date(col))


def _month_number() -> pl.Expr:
    raw = clean(pl.col("intake_month_raw"))
    text = raw.str.to_lowercase().str.slice(0, 3)
    numeric = raw.str.extract(r"^(\d{1,2})$", 1).cast(pl.Int16, strict=False)
    mapped = pl.lit(None, dtype=pl.Int16)
    for name, number in MONTHS.items():
        mapped = pl.when(text == name).then(pl.lit(number, dtype=pl.Int16)).otherwise(mapped)
    month = pl.coalesce(numeric, mapped)
    return pl.when(month.is_between(1, 12)).then(month).otherwise(None)


def _scope() -> list[pl.Expr]:
    return [pl.coalesce(clean(pl.col(f"{d}_raw")), pl.lit(UNASSIGNED)).alias(d) for d in ("area", "region", "team")]


def _uid(out: pl.DataFrame, id_col: str, content_cols: tuple[str, ...], name: str) -> pl.DataFrame:
    """The CRM id where there is one, a content hash where not, and `#n` on
    duplicates so the key stays unique without dropping a row."""
    content = pl.concat_str([pl.col(c).cast(pl.Utf8).fill_null("\x00") for c in content_cols],
                            separator="\x1f").hash().cast(pl.Utf8)
    out = out.with_columns(pl.coalesce(pl.col(id_col), content).alias("_k"))
    return out.with_columns(
        pl.when(pl.len().over("_k") == 1).then(pl.col("_k"))
        .otherwise(pl.col("_k") + pl.lit("#") + pl.col("_k").cum_count().over("_k").cast(pl.Utf8))
        .alias(name)
    )


TEXT = {
    "introducers": ("partner_name", "introducer_id", "introducer_status", "country", "srm_owner", "srm_team"),
    "applications": ("application_id", "student_ref", "student_name", "student_country", "introducer_name",
                     "institution", "course_name", "course_level", "recruitment_type",
                     "application_status", "deposit_paid_status"),
    "logs": ("log_id", "call_type", "log_type", "introducer_name", "outcome", "managed_by_team",
             "created_by", "note"),
}


def finalize(dataset: str, frame: pl.DataFrame) -> pl.DataFrame:
    if dataset not in TEXT:
        raise KeyError(f"unknown dataset '{dataset}'")
    out = frame.with_columns([clean(pl.col(c)).alias(c) for c in TEXT[dataset]])

    if dataset == "introducers":
        out = out.with_columns([*_scope(), _parse_date("became_raw").alias("became_customer")])
        out = out.filter(pl.col("partner_name").is_not_null()).unique(subset=["partner_name"], keep="first",
                                                                       maintain_order=True)
        return out.select(*TEXT["introducers"], "area", "region", "team", "became_customer")

    if dataset == "applications":
        out = out.with_columns([
            *_scope(),
            *[_parse_date(f"{target}_raw").alias(target) for target, _, _ in STAGE_COLUMNS],
            _month_number().alias("intake_month"),
            clean(pl.col("intake_year_raw")).str.extract(r"((?:19|20)\d{2})", 1)
                .cast(pl.Int32, strict=False).alias("intake_year"),
        ])
        out = out.with_columns(
            pl.when(pl.col("intake_month").is_not_null() & pl.col("intake_year").is_not_null())
              .then(pl.col("intake_year") * 100 + pl.col("intake_month").cast(pl.Int32))
              .otherwise(None).alias("intake_ym")
        )
        out = _uid(out, "application_id",
                   ("student_ref", "course_name", "institution", "application_status", "intake_ym", "at_applied"),
                   "app_uid")
        return out.select("app_uid", *TEXT["applications"], "area", "region", "team", "intake_ym", *APP_DATES)

    out = out.with_columns(_parse_log_day("log_time").alias("logged_on"))
    out = _uid(out, "log_id", ("introducer_name", "log_type", "log_time", "created_by", "note"), "log_uid")
    return out.select("log_uid", *TEXT["logs"], "logged_on")


def stats(dataset: str, raw: pl.DataFrame, final: pl.DataFrame) -> dict:
    """Counts worth keeping on the load: rows the page cannot place on a day."""
    out = {"input_rows": raw.height, "rows": final.height}
    if dataset == "introducers":
        out["no_became_customer"] = int(final["became_customer"].null_count())
    elif dataset == "applications":
        out["no_intake"] = int(final["intake_ym"].null_count())
        out["no_applied"] = int(final["at_applied"].null_count())
    else:
        out["no_log_day"] = int(final["logged_on"].null_count())
    return out
