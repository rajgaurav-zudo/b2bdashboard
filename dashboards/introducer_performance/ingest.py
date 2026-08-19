"""Introducer performance: how the two exports map onto this dashboard's tables.

Everything here is specific to this dashboard. Nothing imports it except the
registry, and no other dashboard is affected by changes to it.
See context.md for the definitions these columns exist to serve.
"""
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, "/srv/api")
from app.ingest.reader import Col, clean, normalize_header  # noqa: E402

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y",
                "%d %b %Y", "%b %d, %Y", "%d-%b-%Y")

COLUMNS = {
    "introducers": [
        Col("partner_name", "partner name", ("partner", "name"), required=True),
        Col("lifecycle_stage", "lifecycle stage", ("lifecycle",), required=True),
        Col("latest_contract_status", "latest contract status", ("contract", "status")),
        Col("country", "country", ("country",)),
        Col("srm_team", "partner managed by team(srm)", ("managed", "team")),
        Col("srm_owner", "partner managed by user(srm)", ("managed", "user")),
        Col("became_customer_date", "became customer date", ("became", "customer")),
        Col("source_created_at", "created at", ("created",)),
        Col("org_commission", "org commission", ("org", "commission")),
        Col("contract_commission_type", "contract commission type", ("commission", "type")),
    ],
    "applications": [
        Col("application_id", "application id", ("application", "id")),
        Col("introducer_name", "application introducer name", ("introducer", "name"), required=True),
        Col("deposit_paid_status", "deposit paid status", ("deposit", "paid"), required=True),
        Col("closed_lost_raw", "application closed lost", ("closed", "lost")),
        Col("intake_month", "actual intake month", ("intake", "month")),
        Col("intake_year_raw", "actual intake year", ("intake", "year")),
        # sub-status first so it cannot be stolen by the looser 'status' match
        Col("application_sub_status", "application sub-status", ("sub", "status")),
        Col("application_status", "application status", ()),
        Col("visa_granted_raw", "timestamp of 'visa| granted' status", ("timestamp", "visa", "granted")),
        Col("enrolled_raw", "timestamp of 'enrolled' status", ("timestamp", "enrolled")),
    ],
}


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
    expr = pl.lit(None, dtype=pl.Date)
    src = clean(pl.col(col)).str.slice(0, 30)
    for fmt in DATE_FORMATS:
        expr = pl.coalesce(expr, src.str.to_date(fmt, strict=False))
    return expr


def _year_of(col: str) -> pl.Expr:
    """Year from the parsed date, else the first 19xx/20xx found in the text."""
    return pl.coalesce(
        _parse_date(col).dt.year(),
        clean(pl.col(col)).str.extract(r"((?:19|20)\d{2})", 1).cast(pl.Int32, strict=False),
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
              ("lifecycle_stage", "latest_contract_status", "country", "srm_team",
               "srm_owner", "org_commission", "contract_commission_type")],
            _parse_date("became_customer_date").alias("became_customer_date"),
            _year_of("became_customer_date").alias("became_customer_year"),
            _parse_date("source_created_at").alias("source_created_at"),
            _year_of("source_created_at").alias("source_created_year"),
        ])
        # Partner Name is the join key: blank rows are unusable, duplicates keep the first.
        out = out.filter(pl.col("partner_name").is_not_null()).unique(subset=["partner_name"], keep="first")
        return out.select(
            "partner_name", "lifecycle_stage", "latest_contract_status", "country",
            "srm_team", "srm_owner", "became_customer_date", "became_customer_year",
            "source_created_at", "source_created_year", "org_commission", "contract_commission_type",
        )

    if dataset == "applications":
        month = _month_number()
        year = clean(pl.col("intake_year_raw")).str.extract(r"((?:19|20)\d{2})", 1).cast(pl.Int32, strict=False)
        # Nov & Dec roll into the FOLLOWING year's January intake
        cycle_year = (
            pl.when(month.is_in([11, 12])).then(year + 1)
            .when(year.is_not_null()).then(year)
            .otherwise(None)
        )
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
            cycle_year.cast(pl.Int32).alias("cycle_year"),
            cycle_index.alias("cycle_index"),
            clean(pl.col("deposit_paid_status")).str.to_lowercase().str.replace_all(r"\s+", "")
                .eq("fullypaid").fill_null(False).alias("deposit_fully_paid"),
            clean(pl.col("closed_lost_raw")).str.to_lowercase().eq("yes").fill_null(False).alias("closed_lost"),
            clean(pl.col("visa_granted_raw")).is_not_null().alias("visa_granted"),
            clean(pl.col("enrolled_raw")).is_not_null().alias("enrolled"),
            _timestamp("visa_granted_raw").alias("visa_granted_at"),
            _timestamp("enrolled_raw").alias("enrolled_at"),
        ])

        # A stable natural key. Real application ids are used when present; otherwise a
        # content hash plus its occurrence index, which stays stable across re-uploads
        # as long as the same row appears the same number of times.
        content = pl.concat_str([
            pl.col(c).cast(pl.Utf8).fill_null("\x00") for c in
            ("introducer_name", "deposit_paid_status", "closed_lost", "intake_month",
             "intake_year", "application_status", "application_sub_status")
        ], separator="\x1f").hash().cast(pl.Utf8)
        out = out.with_columns(content.alias("_c"))
        out = out.with_columns(
            pl.coalesce(
                pl.col("application_id"),
                pl.col("_c") + pl.lit("#") + pl.col("_c").cum_count().over("_c").cast(pl.Utf8),
            ).alias("app_uid")
        )
        return out.select(
            "app_uid", "application_id", "introducer_name", "deposit_paid_status",
            "deposit_fully_paid", "closed_lost", "intake_month", "intake_year",
            "cycle_year", "cycle_index", "application_status", "application_sub_status",
            "visa_granted", "visa_granted_at", "enrolled", "enrolled_at",
        )

    raise KeyError(f"unknown dataset '{dataset}'")


def _timestamp(col: str) -> pl.Expr:
    src = clean(pl.col(col))
    expr = pl.lit(None, dtype=pl.Datetime(time_unit="us"))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
        expr = pl.coalesce(expr, src.str.to_datetime(fmt, strict=False))
    return expr.dt.replace_time_zone("UTC")
