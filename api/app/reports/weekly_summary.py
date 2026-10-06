"""This week's summary: deposits, onboarding, activity and sales & retention in one workbook.

Read straight from the latest archived export of each source:

    introducers      Became Customer Date, SRM, BusinessTeam, BusinessRegion, country, the CRM `_id`
    introducer_logs  Log Time, Log Type, Created By, Managed By Team (read as a business team and region)
    applications     the active-deposit columns, the application's own
                     Introducer SRM / AMT, Institution, Application Introducer Id,
                     CurrentlyAssignedToBusinessTeam, StudentAssignedToBusinessRegion

"This week" is the Edvoy week, Saturday to Friday, that contains `today`, and
it is to date. "Last week" is the seven days before it. Year to date runs
from 1 January to `today`, against the same span of last year.

Sheets, in order: Deposits overview (the active deposits in charts), Onboarding,
Activity, Sales & Retention, and Last week -- last week, whole, against the
week before it: introducers onboarded, activity logs, and deposits by the date
they were paid in full. The applications export is a snapshot with no history,
so a deposit paid last week counts only if it is still paid in full today.

Deposits fall into three states, not Closed Lost in each. Paid in full
(FullyPaid or fullyPaidWaitingForApproval) is an active deposit when the
two deferral columns agree -- both No or both Yes -- and DAA when they do not.
PartiallyPaid is PD. This report counts fullyPaidWaitingForApproval as paid;
the dashboards (sources/context.md) count FullyPaid alone. Only the eight
Academic course levels in ACADEMIC count; anything else, a blank included, is
left out. Only applications whose StudentAssignedToBusinessArea is B2B count:
the export carries every business area, and this is the introducer business. Every sheet opens with a note that
says so, and says which files it was read from.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import polars as pl

from ..ingest.reader import Col, IngestError, clean, normalize_header, read_table, resolve_index
from ..storage import storage
from .xlsx import Chart, Formula, Sheet, Style, Workbook, col_letter as L, ref

SOURCES = ("introducers", "introducer_logs", "applications")

COLUMNS = {
    "introducers": [
        Col("id", "_id", ()),
        Col("name", "partner name", ("partner", "name"), required=True),
        Col("country", "country", ("country",)),
        Col("team", "businessteam", ("business", "team")),
        Col("srm_team", "partner managed by team(srm)", ("managed", "team")),
        Col("region", "businessregion", ("business", "region")),
        Col("srm", "partner managed by user(srm)", ("managed", "user")),
        Col("became_customer", "became customer date", ("became", "customer"), required=True),
    ],
    "introducer_logs": [
        Col("id", "_id", ()),
        Col("log_type", "log type", ("log", "type"), required=True),
        Col("log_time", "log time", ("log", "time"), required=True),
        Col("team", "managed by team", ("managed", "team")),
        Col("srm", "created by", ("created", "by")),
    ],
    "applications": [
        Col("introducer_name", "application introducer name", ("introducer", "name"), required=True),
        Col("introducer_id", "application introducer id", ("introducer", "id")),
        Col("deposit_paid_status", "deposit paid status", ("deposit", "paid"), required=True),
        Col("closed_lost", "application closed lost", ("closed", "lost")),
        Col("deferral_initiated", "deferred initiated (no/yes/all)", ("deferred", "initiated")),
        Col("deferral_approved", "deferred approved (no/yes/all)", ("deferred", "approved")),
        Col("course_level", "application course level", ("course", "level")),
        Col("intake_year", "actual intake year", ("actual", "intake", "year"), required=True),
        Col("intake_month", "actual intake month", ("actual", "intake", "month")),
        Col("srm", "introducer srm user name", ("srm", "user")),
        Col("team", "currentlyassignedtobusinessteam", ("currently", "business", "team")),
        Col("amt", "introducer amt user name", ("amt", "user")),
        Col("institution", "institution name", ("institution",)),
        Col("business_area", "studentassignedtobusinessarea", ("student", "business", "area"), required=True),
        Col("region", "studentassignedtobusinessregion", ("student", "business", "region")),
        # "Timestamp of 'Deposit Fully Paid' status"; the export's quotes arrive garbled
        Col("paid_at", "", ("timestamp", "deposit", "fully", "paid")),
    ],
}

LOG_TYPES = {"F2FVisits": "Face to face", "Call": "Call", "Meeting": "Meeting", "Email": "Email"}
TYPES = list(LOG_TYPES.values())
JS_DATE_FORMAT = "%a %b %d %Y %H:%M:%S GMT%z"
BLANK = "(blank)"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
PAID_IN_FULL = ["fullypaid", "fullypaidwaitingforapproval"]
ACADEMIC = ["ALevel", "ASLevel", "Doctorate", "Foundation", "GCSEgradesAC", "Postgraduate", "PreMasters",
            "Undergraduate"]


@dataclass
class Export:
    """One archived file: where it came from and what was read out of it."""
    source: str
    filename: str
    uploaded_at: datetime
    frame: pl.DataFrame


def read_export(source: str, filename: str, content: bytes, uploaded_at: datetime) -> Export:
    """Only the columns the report uses, resolved the way ingest resolves them.

    The workbook reader parses the whole sheet whatever it is asked for -- even
    a header-only read of the ~230k-row applications export costs most of a
    full one -- so the file is read once and the columns picked afterwards.
    """
    spec = COLUMNS[source]
    frame = read_table(filename, content)
    head = frame.columns
    names = {head[i]: target for target, i in _resolve(head, spec, source).items()}
    frame = frame.select(list(names)).rename(names)
    for col in spec:                         # optional columns absent from this export
        if col.target not in frame.columns:
            frame = frame.with_columns(pl.lit(None, dtype=pl.Utf8).alias(col.target))
    return Export(source, filename, uploaded_at, frame)


def _resolve(headers: list[str], spec: list[Col], source: str) -> dict[str, int]:
    normalized = [normalize_header(h) for h in headers]
    found: dict[str, int] = {}
    missing = []
    for col in spec:
        idx = resolve_index(normalized, col)
        if idx is not None and idx not in found.values():
            found[col.target] = idx
        elif col.required:
            missing.append(col.exact or col.target)
    if missing:
        raise IngestError(f"the latest {source} export has no column for: {', '.join(missing)}")
    return found


# ------------------------------------------------------------------ columns

def _label(col: str) -> pl.Expr:
    return clean(pl.col(col)).fill_null(BLANK).alias(col)


def _team(col: str) -> pl.Expr:
    """A team name without the CRM's SRM / SRMs / AMT words: "West Africa B2B
    SRMs 1" reads "West Africa B2B 1"."""
    t = clean(pl.col(col)).str.replace_all(r"(?i)\b(?:SRMs?|AMT)\b", "") \
        .str.replace_all(r"\s+", " ").str.strip_chars()
    return pl.when(t == "").then(None).otherwise(t).fill_null(BLANK).alias(col)


def _date(col: str) -> pl.Expr:
    """'2026-10-02 00:00:00' as the workbook reader returns it, or a csv's own spelling."""
    src = clean(pl.col(col))
    out = src.str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"):
        out = pl.coalesce(out, src.str.to_date(fmt, strict=False))
    return out


def _log_day(col: str) -> pl.Expr:
    """The UTC day of a log, as the Logs dashboard dates it.

    The export writes JavaScript's Date.toString(); the "(...)" zone name is a
    localised label, so it is dropped and the GMT offset is honoured.
    """
    raw = clean(pl.col(col))
    js = (raw.str.replace(r"\s*\(.*\)\s*$", "")
          .str.to_datetime(JS_DATE_FORMAT, strict=False)
          .dt.convert_time_zone("UTC").dt.date())
    return pl.coalesce(js, raw.str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False))


def _letters(col: str) -> pl.Expr:
    return clean(pl.col(col)).fill_null("").str.to_lowercase().str.replace_all(r"[^a-z]", "")


# ------------------------------------------------------------------ periods

@dataclass(frozen=True)
class Periods:
    """The dates a summary covers. `today` is the day it is as of; `closed` marks
    last week's summary, whose `today` is the Friday that ended its week."""
    today: date
    closed: bool = False

    @classmethod
    def last_week_of(cls, today: date) -> "Periods":
        return cls(cls(today).week[0] - timedelta(1), closed=True)

    @property
    def cur(self) -> str:
        return "Last week" if self.closed else "This week"

    @property
    def prev(self) -> str:
        return "Week before" if self.closed else "Last week"

    @property
    def cy(self) -> int:
        return self.today.year

    @property
    def ly(self) -> int:
        return self.today.year - 1

    @property
    def ytd(self) -> tuple[date, date]:
        return date(self.cy, 1, 1), self.today

    @property
    def lytd(self) -> tuple[date, date]:
        # 29 Feb has no twin last year; the 28th stands in for it
        end = self.today.replace(year=self.ly, day=min(self.today.day, 28)) \
            if (self.today.month, self.today.day) == (2, 29) else self.today.replace(year=self.ly)
        return date(self.ly, 1, 1), end

    @property
    def week(self) -> tuple[date, date]:
        """The Saturday-to-Friday week containing today. weekday(): Monday = 0, Saturday = 5."""
        start = self.today - timedelta((self.today.weekday() - 5) % 7)
        return start, start + timedelta(6)

    @property
    def last_week(self) -> tuple[date, date]:
        start = self.week[0] - timedelta(7)
        return start, start + timedelta(6)


def _between(col: str, span: tuple[date, date]) -> pl.Expr:
    return pl.col(col).is_between(pl.lit(span[0]), pl.lit(span[1]))


# ------------------------------------------------------------------ styles

H1 = Style(bold=True, size=14)
H2 = Style(bold=True, size=11, color="1F3864")
NOTE = Style(italic=True, size=9, color="595959")
NOTE_WRAP = Style(italic=True, size=9, color="595959", wrap=True, valign="top")
HDR = Style(bold=True, color="FFFFFF", fill="1F3864", border=True, wrap=True, halign="center", valign="center")
INT = '#,##0;-#,##0;"-"'
DLT = '+#,##0;-#,##0;"-"'
PCT = '+0.0%;-0.0%;"-"'
SHARE = '0.0%;-0.0%;"-"'
DAY = "dd mmm yyyy"
TFILL = "D9E1F2"


def _st(nf: str | None = None, bold: bool = False, total: bool = False) -> Style:
    return Style(bold=bold or total, border=True, num_fmt=nf, fill=TFILL if total else None)


def _fmt(d: date | None) -> str:
    return d.strftime("%a %d %b %Y") if d else "none"


def _span(span: tuple[date, date]) -> str:
    return f"{span[0]:%d %b} – {span[1]:%d %b}"


def _pct(cur: float, prev: float) -> float | str:
    return "" if prev == 0 else (cur - prev) / prev


class Writer:
    """Lays tables down a sheet, top to bottom, one blank row between them."""

    def __init__(self, sheet: Sheet, row: int = 4):
        self.ws = sheet
        self.r = row

    def section(self, title: str, note: str | None = None) -> None:
        self.ws.set(self.r, 1, title, H2)
        self.r += 1
        if note:
            self.ws.set(self.r, 1, note, NOTE)
            self.r += 1

    def header(self, cols: list[str], height: float | None = None) -> None:
        for c, h in enumerate(cols, 1):
            self.ws.set(self.r, c, h, HDR)
        if height:
            self.ws.heights[self.r] = height
        self.r += 1

    def compare(self, label_cols: list[str], rows: list[tuple[tuple[str, ...], int, int]],
                cur_h: str, prev_h: str, total: bool = True) -> None:
        """Labels, current, previous, Change and % change -- the last two as formulas."""
        ws, nl = self.ws, len(label_cols)
        cc, pc = nl + 1, nl + 2
        self.header(label_cols + [cur_h, prev_h, "Change", "% change"], height=30)
        first = self.r

        def tail(r: int, cv: int, pv: int, tot: bool) -> None:
            C, P = ref(r, cc), ref(r, pc)
            ws.set(r, pc + 1, Formula(f"{C}-{P}", cv - pv), _st(DLT, total=tot))
            ws.set(r, pc + 2, Formula(f'IF({P}=0,"",({C}-{P})/{P})', _pct(cv, pv)), _st(PCT, total=tot))

        for labels, cv, pv in rows:
            for k, lab in enumerate(labels, 1):
                ws.set(self.r, k, lab, _st())
            ws.set(self.r, cc, cv, _st(INT))
            ws.set(self.r, pc, pv, _st(INT))
            tail(self.r, cv, pv, False)
            self.r += 1
        if total:
            sc, sp = sum(x[1] for x in rows), sum(x[2] for x in rows)
            ws.set(self.r, 1, "Total", _st(total=True))
            for k in range(2, nl + 1):
                ws.set(self.r, k, "", _st(total=True))
            for c, v in ((cc, sc), (pc, sp)):
                ws.set(self.r, c, Formula(f"SUM({L(c)}{first}:{L(c)}{max(first, self.r - 1)})", v), _st(INT, total=True))
            tail(self.r, sc, sp, True)
            self.r += 1
        self.r += 1

    def share(self, label_cols: list[str], rows: list[tuple[tuple[str, ...], int]], value_h: str) -> None:
        """Counts with each row's share of the total."""
        ws, nl = self.ws, len(label_cols)
        vc = nl + 1
        self.header(label_cols + [value_h, "Share"], height=30)
        first, last = self.r, self.r + len(rows) - 1
        tot = sum(v for _, v in rows)
        for labels, v in rows:
            for k, lab in enumerate(labels, 1):
                ws.set(self.r, k, lab, _st())
            ws.set(self.r, vc, v, _st(INT))
            ws.set(self.r, vc + 1, Formula(f"IF({L(vc)}${last + 1}=0,0,{L(vc)}{self.r}/{L(vc)}${last + 1})",
                                           v / tot if tot else 0), _st(SHARE))
            self.r += 1
        ws.set(self.r, 1, "Total", _st(total=True))
        for k in range(2, nl + 1):
            ws.set(self.r, k, "", _st(total=True))
        ws.set(self.r, vc, Formula(f"SUM({L(vc)}{first}:{L(vc)}{max(first, last)})", tot), _st(INT, total=True))
        ws.set(self.r, vc + 1, Formula(f"IF({L(vc)}{self.r}=0,0,1)", 1 if tot else 0), _st(SHARE, total=True))
        self.r += 2

    def grid(self, label_cols: list[str], rows: list[tuple[tuple[str, ...], list[int]]], value_h: list[str]) -> None:
        """Several counts per row, each column summed in a total row."""
        ws, nl = self.ws, len(label_cols)
        self.header(label_cols + value_h, height=30)
        first = self.r
        for labels, values in rows:
            for k, lab in enumerate(labels, 1):
                ws.set(self.r, k, lab, _st())
            for k, v in enumerate(values, nl + 1):
                ws.set(self.r, k, v, _st(INT))
            self.r += 1
        ws.set(self.r, 1, "Total", _st(total=True))
        for k in range(2, nl + 1):
            ws.set(self.r, k, "", _st(total=True))
        for j in range(len(value_h)):
            c = nl + 1 + j
            ws.set(self.r, c, Formula(f"SUM({L(c)}{first}:{L(c)}{max(first, self.r - 1)})",
                                      sum(v[j] for _, v in rows)), _st(INT, total=True))
        self.r += 2


def _grouped(cur: pl.DataFrame, prev: pl.DataFrame, keys: list[str]) -> list[tuple[tuple[str, ...], int, int]]:
    """Counts per key in both periods, biggest this period first."""
    c = cur.group_by(keys).len("c")
    p = prev.group_by(keys).len("p")
    df = c.join(p, on=keys, how="full", coalesce=True).with_columns(pl.col("c", "p").fill_null(0))
    df = df.sort(["c", "p", *keys], descending=[True, True] + [False] * len(keys))
    return [(tuple(r[k] for k in keys), r["c"], r["p"]) for r in df.iter_rows(named=True)]


def _counts(df: pl.DataFrame, keys: list[str]) -> list[tuple[tuple[str, ...], int]]:
    g = df.group_by(keys).len("n").sort(["n", *keys], descending=[True] + [False] * len(keys))
    return [(tuple(r[k] for k in keys), r["n"]) for r in g.iter_rows(named=True)]


def _source_note(e: Export) -> str:
    return f"{e.filename}, uploaded {e.uploaded_at:%d %b %Y %H:%M} UTC ({e.frame.height:,} rows)"


# ------------------------------------------------------------------ sheets

def build(introducers: Export, logs: Export, applications: Export, p: Periods) -> bytes:
    wb = Workbook()
    d = _deposits(applications, introducers, p)
    _overview(wb.add_sheet("Deposits overview"), d, applications, p)
    _onboarding(wb.add_sheet("Onboarding"), introducers, p)
    _activity(wb.add_sheet("Activity"), logs, introducers, p)
    _sales(wb.add_sheet("Sales & Retention"), d, applications, p)
    _last_week(wb.add_sheet("Last week"), d, introducers, logs, applications, Periods.last_week_of(p.today))
    return wb.save()


def _master(introducers: Export) -> pl.DataFrame:
    return introducers.frame.select(
        clean(pl.col("id")).alias("id"),
        _label("name"), _label("country"), _team("team"), _label("srm"), _label("srm_team"), _label("region"),
        _date("became_customer").alias("bc"),
    )


def _onboarding(ws: Sheet, introducers: Export, p: Periods) -> None:
    i = _master(introducers)
    on = {k: i.filter(_between("bc", span)) for k, span in
          (("ytd", p.ytd), ("lytd", p.lytd), ("wk", p.week), ("pwk", p.last_week))}
    bc_max = i["bc"].max()

    ws.set(1, 1, "Onboarding — introducers by Became Customer Date", H1)
    ws.set(2, 1, f"Source: introducers master, {_source_note(introducers)}. Latest Became Customer Date in "
                 f"the file: {_fmt(bc_max)}. SRM, business team (BusinessTeam), business region (BusinessRegion) and country are the introducer's current values "
                 "on the master.", NOTE)
    w = Writer(ws)
    yh = f"{p.cy} YTD\n(1 Jan – {p.today:%d %b})"
    lyh = f"{p.ly} same period\n(1 Jan – {p.lytd[1]:%d %b})"
    w.section(f"A. Year to date: {p.cy} vs the same period of {p.ly}")
    w.compare(["Introducers onboarded"], [(("All introducers",), on["ytd"].height, on["lytd"].height)],
              yh, lyh, total=False)
    w.section("A1. By business region")
    w.compare(["Business region"], _grouped(on["ytd"], on["lytd"], ["region"]), yh, lyh)
    w.section("A2. By business team")
    w.compare(["Business team"], _grouped(on["ytd"], on["lytd"], ["team"]), yh, lyh)
    w.section("A3. By SRM (with business team)")
    w.compare(["SRM", "Business team"], _grouped(on["ytd"], on["lytd"], ["srm", "team"]), yh, lyh)
    w.section("A4. By country")
    w.compare(["Country"], _grouped(on["ytd"], on["lytd"], ["country"]), yh, lyh)

    wh, pwh = f"{p.cur}\n{_span(p.week)}", f"{p.prev}\n{_span(p.last_week)}"
    w.r += 1
    w.section(f"B. {p.cur} vs {p.prev.lower()} (Edvoy week: Saturday – Friday)",
              f"{p.cur} is {_fmt(p.week[0])} – {_fmt(p.week[1])}"
              + (", the whole week" if p.closed else f", to date: the summary was built {_fmt(p.today)}")
              + f". The latest Became Customer Date in the file is {_fmt(bc_max)}. "
              f"{p.prev} is {_fmt(p.last_week[0])} – {_fmt(p.last_week[1])}.")
    w.compare(["Introducers onboarded"], [(("All introducers",), on["wk"].height, on["pwk"].height)],
              wh, pwh, total=False)
    w.section("B1. By business region")
    w.compare(["Business region"], _grouped(on["wk"], on["pwk"], ["region"]), wh, pwh)
    w.section("B2. By business team")
    w.compare(["Business team"], _grouped(on["wk"], on["pwk"], ["team"]), wh, pwh)
    w.section("B3. By SRM (with business team)")
    w.compare(["SRM", "Business team"], _grouped(on["wk"], on["pwk"], ["srm", "team"]), wh, pwh)
    w.section("B4. By country")
    w.compare(["Country"], _grouped(on["wk"], on["pwk"], ["country"]), wh, pwh)
    w.section(f"B5. Introducers onboarded {p.cur.lower()} ({on['wk'].height})")
    w.header(["Introducer", "Country", "Business team", "SRM", "Became Customer Date"])
    for x in on["wk"].sort(["bc", "name"]).iter_rows(named=True):
        for k, v in enumerate([x["name"], x["country"], x["team"], x["srm"]], 1):
            ws.set(w.r, k, v, _st())
        ws.set(w.r, 5, x["bc"], _st(DAY))
        w.r += 1
    ws.widths.update(dict(enumerate([42, 30, 24, 24, 20, 12], 1)))
    ws.freeze = "A4"


def _logs(logs: Export, introducers: Export) -> pl.DataFrame:
    lg = logs.frame
    # one row per CRM log id when the export has one, as the Logs dashboard keeps it
    if lg["id"].null_count() < lg.height:
        lg = pl.concat([lg.filter(pl.col("id").is_null()),
                        lg.filter(pl.col("id").is_not_null()).unique("id", keep="first", maintain_order=True)])
    return lg.select(
        _log_day("log_time").alias("day"),
        clean(pl.col("log_type")).replace_strict(LOG_TYPES, default="Other").alias("type"),
        _label("srm"), _label("team").alias("srm_team"), _team("team"),
    ).join(_business_teams(introducers), on="srm_team", how="left") \
        .with_columns(pl.coalesce("business_team", "team").alias("team"),
                      pl.col("region").fill_null(BLANK)).drop("srm_team", "business_team")


def _business_teams(introducers: Export) -> pl.DataFrame:
    """The log export names the SRM team (Managed By Team), not the business
    team or region. The master carries all three for each introducer; an SRM
    team reads as the business team and region its introducers are most often on."""
    return _master(introducers).filter((pl.col("srm_team") != BLANK) & (pl.col("team") != BLANK)) \
        .group_by("srm_team", "team", "region").len() \
        .sort(["len", "team", "region"], descending=[True, False, False]) \
        .unique("srm_team", keep="first", maintain_order=True) \
        .select("srm_team", pl.col("team").alias("business_team"), "region")


def _activity(ws: Sheet, logs: Export, introducers: Export, p: Periods) -> None:
    lg = _logs(logs, introducers)
    log_max = lg["day"].max()
    lc, lp = lg.filter(_between("day", p.week)), lg.filter(_between("day", p.last_week))

    ws.set(1, 1, f"Activity — introducer logs, {p.cur.lower()} vs {p.prev.lower()}", H1)
    ws.set(2, 1, f"Source: introducer logs, {_source_note(logs)}; latest log {_fmt(log_max)}. "
                 "Week = Saturday – Friday, dated by Log Time in UTC as the Logs dashboard does. "
                 f"{p.cur} {_span(p.week)} is {'the whole week' if p.closed else 'to date'}; "
                 f"{p.prev.lower()} is {_span(p.last_week)}. "
                 "SRM = the log's Created By; business team and region = the BusinessTeam and BusinessRegion "
                 "the introducer master pairs with its Managed By Team.", NOTE)
    wh, pwh = f"{p.cur}\n{_span(p.week)}", f"{p.prev}\n{_span(p.last_week)}"
    w = Writer(ws)
    w.section("A. Total logs and by log type")
    rows = [(("Total logs",), lc.height, lp.height)] + [
        ((t,), lc.filter(pl.col("type") == t).height, lp.filter(pl.col("type") == t).height) for t in TYPES]
    w.compare(["Log type"], rows, wh, pwh, total=False)
    other = lc.filter(pl.col("type") == "Other").height + lp.filter(pl.col("type") == "Other").height
    ws.set(w.r - 1, 1, "Face to face = F2FVisits and Meeting = Meeting in the CRM's Log Type."
                       + (f" {other} logs of other types are in the total only." if other else
                          " The four types add up to Total logs."), NOTE)
    w.r += 1

    def wide(key: str, label: str) -> None:
        metrics = ["Total logs", *TYPES]
        cols = [label]
        for m in metrics:
            cols += [f"{m}\n{p.cur.lower()}", f"{m}\n{p.prev.lower()}", f"{m}\nchange"]
        w.header(cols, height=42)
        both = pl.concat([lc.with_columns(pl.lit("c").alias("wk")), lp.with_columns(pl.lit("p").alias("wk"))])
        totals = both.group_by(key).agg((pl.col("wk") == "c").sum().alias("c"), (pl.col("wk") == "p").sum().alias("p"))
        keys = [r[key] for r in totals.sort(["c", "p", key], descending=[True, True, False]).iter_rows(named=True)]
        first = w.r
        sums = [0] * (2 * len(metrics))
        for k in keys:
            ws.set(w.r, 1, k, _st())
            sub = both.filter(pl.col(key) == k)
            c = 2
            for j, m in enumerate(metrics):
                part = sub if m == "Total logs" else sub.filter(pl.col("type") == m)
                cv, pv = part.filter(pl.col("wk") == "c").height, part.filter(pl.col("wk") == "p").height
                sums[2 * j] += cv
                sums[2 * j + 1] += pv
                ws.set(w.r, c, cv, _st(INT))
                ws.set(w.r, c + 1, pv, _st(INT))
                ws.set(w.r, c + 2, Formula(f"{ref(w.r, c)}-{ref(w.r, c + 1)}", cv - pv), _st(DLT))
                c += 3
            w.r += 1
        ws.set(w.r, 1, "Total", _st(total=True))
        for j in range(len(metrics)):
            c = 2 + 3 * j
            for off in (0, 1):
                ws.set(w.r, c + off, Formula(f"SUM({L(c + off)}{first}:{L(c + off)}{max(first, w.r - 1)})",
                                             sums[2 * j + off]), _st(INT, total=True))
            ws.set(w.r, c + 2, Formula(f"{ref(w.r, c)}-{ref(w.r, c + 1)}", sums[2 * j] - sums[2 * j + 1]),
                   _st(DLT, total=True))
        w.r += 2

    w.section("B. SRM-wise")
    wide("srm", "SRM (Created By)")
    w.section("C. Business region-wise")
    wide("region", "Business region")
    w.section("D. Business team-wise")
    wide("team", "Business team")
    ws.widths.update({1: 34, **{c: 11 for c in range(2, 17)}})
    ws.freeze = "B4"


@dataclass
class Deposits:
    """The applications as the deposit sheets count them.

    `a` is every application with an introducer, with its state, intake and
    the date it was fully paid; `held` the Active / DAA / PD ones for this
    year's and last year's intake that count (Academic, B2B); `dep` the active
    deposits among them, keyed to their introducer and looked up on the master.
    """
    a: pl.DataFrame
    held: pl.DataFrame
    dep: pl.DataFrame
    cur: pl.DataFrame
    prev: pl.DataFrame
    resurrected: pl.DataFrame
    missed: pl.DataFrame
    non_acad: dict[int, int]
    non_b2b: dict[int, int]

    def n(self, state: str, year: int, mon: str | None = None) -> int:
        f = self.held.filter((pl.col("state") == state) & (pl.col("year") == year))
        return f.height if mon is None else f.filter(pl.col("month") == mon).height


def _deposits(applications: Export, introducers: Export, p: Periods) -> Deposits:
    cy, ly = p.cy, p.ly
    master = _master(introducers).filter(pl.col("id").is_not_null()).unique("id", keep="first", maintain_order=True)
    # Some applications carry the introducer's CRM id but no name; the master
    # names them. Only an application with neither is not an introducer's.
    a = applications.frame.with_columns(clean(pl.col("introducer_id")).alias("_iid")) \
        .join(master.select(pl.col("id").alias("_iid"), pl.col("name").alias("_mname")), on="_iid", how="left") \
        .with_columns(pl.coalesce(clean(pl.col("introducer_name")), pl.col("_mname")).alias("introducer_name")) \
        .drop("_iid", "_mname") \
        .filter(pl.col("introducer_name").is_not_null())
    # Others carry the name but no id; the master gives the id when exactly one
    # introducer there has that name (compared ignoring case and spacing).
    norm = pl.col("introducer_name").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars()
    by_name = master.filter(pl.col("name") != BLANK).select(
        pl.col("name").str.to_lowercase().str.replace_all(r"\s+", " ").str.strip_chars().alias("_n"),
        pl.col("id").alias("_mid"),
    ).filter(pl.len().over("_n") == 1)
    a = a.with_columns(norm.alias("_n")).join(by_name, on="_n", how="left") \
        .with_columns(pl.coalesce(clean(pl.col("introducer_id")), pl.col("_mid")).alias("introducer_id")) \
        .drop("_n", "_mid")
    level = _letters("course_level")
    # an export without the deferral columns reads as never deferred
    di = clean(pl.col("deferral_initiated")).fill_null("No")
    da = clean(pl.col("deferral_approved")).fill_null("No")
    status = _letters("deposit_paid_status")
    live = clean(pl.col("closed_lost")).fill_null("No").eq("No")
    month = clean(pl.col("intake_month")).str.to_titlecase()
    a = a.with_columns(
        level.is_in([c.lower() for c in ACADEMIC]).alias("academic"),
        clean(pl.col("business_area")).str.to_uppercase().eq("B2B").fill_null(False).alias("b2b"),
        pl.when(~live).then(None)
        .when(status.is_in(PAID_IN_FULL) & di.eq(da)).then(pl.lit("Active"))
        .when(status.is_in(PAID_IN_FULL)).then(pl.lit("DAA"))
        .when(status == "partiallypaid").then(pl.lit("PD"))
        .alias("state"),
        clean(pl.col("intake_year")).str.extract(r"(\d{4})").cast(pl.Int32, strict=False).alias("year"),
        pl.when(month.is_in(MONTHS)).then(month).otherwise(pl.lit(BLANK)).alias("month"),
        _date("paid_at").alias("paid"),
    )
    held = a.filter(pl.col("state").is_not_null() & pl.col("year").is_in([cy, ly]))
    non_acad = {r["year"]: r["len"] for r in held.filter((pl.col("state") == "Active") & ~pl.col("academic"))
                .group_by("year").len().iter_rows(named=True)}
    held = held.filter(pl.col("academic"))
    non_b2b = {r["year"]: r["len"] for r in held.filter((pl.col("state") == "Active") & ~pl.col("b2b"))
               .group_by("year").len().iter_rows(named=True)}
    held = held.filter(pl.col("b2b"))
    dep = held.filter(pl.col("state") == "Active")

    # The introducer is the CRM id where the application carries one, its name
    # where it does not; either way it is looked up on the master for its
    # country and Became Customer Date.
    dep = dep.with_columns(
        pl.coalesce(clean(pl.col("introducer_id")), pl.lit("name:") + pl.col("introducer_name")).alias("key"),
        _label("srm"), _team("team"), _label("region"), _label("amt"), _label("institution"),
    ).join(master.select(pl.col("id").alias("key"), "country", "bc", pl.lit(True).alias("in_master")),
           on="key", how="left").with_columns(
        pl.col("country").fill_null("(not in introducer master)"),
        pl.col("in_master").fill_null(False),
    ).with_columns(
        pl.when(~pl.col("in_master")).then(pl.lit("Introducer not in master file"))
        # a master introducer with no Became Customer Date is an old one
        .when(pl.col("bc").is_null()).then(pl.lit("2023 & earlier"))
        .when(pl.col("bc").dt.year() >= 2024).then(pl.col("bc").dt.year().cast(pl.Utf8))
        .otherwise(pl.lit("2023 & earlier")).alias("cohort"),
    )
    cur, prev = dep.filter(pl.col("year") == cy), dep.filter(pl.col("year") == ly)

    # One row per introducer: its deposits in each year, and its details from
    # its most recent intake (the SRM on a 2026 application over a 2025 one).
    counts = dep.group_by("key").agg((pl.col("year") == cy).sum().alias("cy"), (pl.col("year") == ly).sum().alias("ly"))
    info = dep.sort("year", descending=True, maintain_order=True).unique("key", keep="first", maintain_order=True) \
        .select("key", "introducer_name", "country", "team", "srm", "bc")
    pi = counts.join(info, on="key")
    resurrected = pi.filter((pl.col("cy") > 0) & (pl.col("ly") == 0)
                            & (pl.col("bc").is_null() | (pl.col("bc").dt.year() != cy))) \
        .sort(["cy", "introducer_name"], descending=[True, False])
    missed = pi.filter((pl.col("ly") > 0) & (pl.col("cy") == 0)).sort(["ly", "introducer_name"], descending=[True, False])
    return Deposits(a, held, dep, cur, prev, resurrected, missed, non_acad, non_b2b)


def _cohorts(p: Periods) -> list[str]:
    """The onboarding-year rows, newest first."""
    order = [str(p.cy), str(p.ly), "2024", "2023 & earlier", "Introducer not in master file"]
    order = list(dict.fromkeys(order))     # in 2025, "last year" is 2024
    if p.cy - 2 > 2024:                    # years between 2024 and last year get their own rows
        order[2:2] = [str(y) for y in range(p.ly - 1, 2024, -1)]
    return order


def _definitions(applications: Export, p: Periods) -> str:
    return (f"Source: applications, {_source_note(applications)}. Active deposit = Deposit Paid Status FullyPaid "
            "or fullyPaidWaitingForApproval, with Deferred Initiated and Deferred Approved both No or both Yes, "
            "not Closed Lost, on an application with an introducer; Academic course levels and "
            "StudentAssignedToBusinessArea B2B only, as on Sales & Retention, which has the full definitions "
            f"and what is left out. Intake = Actual Intake Year. The {p.cy} intake year is still in progress.")


def _overview(ws: Sheet, d: Deposits, applications: Export, p: Periods) -> None:
    """The active deposits at a glance: a headline table, then each breakdown
    as a small table with its chart beside it."""
    cy, ly = p.cy, p.ly
    cyh, lyh = f"{cy} intake", f"{ly} intake"
    ws.set(1, 1, f"Deposits overview — active deposits, {cy} intake vs {ly} intake", H1)
    ws.set(2, 1, _definitions(applications, p), NOTE_WRAP)
    ws.merges.append("A2:N2")
    ws.heights[2] = 40
    w = Writer(ws)

    w.section("A. Headline")
    w.compare(["Deposits by introducers"], [
        (("Active deposits",), d.n("Active", cy), d.n("Active", ly)),
        (("DAA — deferral awaiting approval",), d.n("DAA", cy), d.n("DAA", ly)),
        (("PD — partial deposits",), d.n("PD", cy), d.n("PD", ly)),
        (("Introducers with active deposits",), d.cur["key"].n_unique(), d.prev["key"].n_unique()),
    ], cyh, lyh, total=False)
    for label, v in (("Introducers resurrected", d.resurrected.height), ("Introducers missed out", d.missed.height)):
        ws.set(w.r, 1, label, _st(bold=True))
        ws.set(w.r, 2, v, _st(INT, bold=True))
        w.r += 1
    ws.set(w.r, 1, f"Resurrected: not onboarded in {cy}, no active deposit for {ly}, some for {cy}. Missed out: "
                   f"active deposits for {ly}, none for {cy}. Both are listed on Sales & Retention.", NOTE)
    w.r += 2

    def block(title: str, label: str, rows: list[tuple[tuple[str, ...], int, int]],
              rest: tuple[str, int, int] | None = None, horizontal: bool = False) -> None:
        """A table of active deposits per `label`, with its chart to the right.
        `rest` is a row for everything outside the top rows; it is in the table
        and its total but not the chart."""
        w.section(title)
        top = w.r
        w.header([label, cyh, lyh], height=30)
        first = w.r
        for row in rows + ([((rest[0],), rest[1], rest[2])] if rest else []):
            ws.set(w.r, 1, row[0][0], _st())
            ws.set(w.r, 2, row[1], _st(INT))
            ws.set(w.r, 3, row[2], _st(INT))
            w.r += 1
        ws.set(w.r, 1, "Total", _st(total=True))
        for c in (2, 3):
            ws.set(w.r, c, Formula(f"SUM({L(c)}{first}:{L(c)}{max(first, w.r - 1)})",
                                   sum(r[c - 1] for r in rows) + (rest[c - 1] if rest else 0)), _st(INT, total=True))
        w.r += 1
        height = max(15, round(1.4 * len(rows)) + 6) if horizontal else 15
        if rows:
            ws.charts.append(Chart(title.split(". ", 1)[1], (first, first + len(rows) - 1, 1),
                                   [(cyh, 2), (lyh, 3)], at=(top, 7), size=(height, 10), horizontal=horizontal))
        w.r = max(w.r, top + height) + 2

    def top10(key: str, other: str) -> tuple[list[tuple[tuple[str, ...], int, int]], tuple[str, int, int] | None]:
        g = _grouped(d.cur, d.prev, [key])
        rest = g[10:]
        return g[:10], ((f"{other} ({len(rest)})", sum(r[1] for r in rest), sum(r[2] for r in rest))
                        if rest else None)

    months = set(d.dep["month"].to_list())
    block("B. By Actual Intake Month", "Actual Intake Month",
          [((m,), d.n("Active", cy, m), d.n("Active", ly, m)) for m in MONTHS + [BLANK] if m in months])
    block("C. By business region", "Business region", _grouped(d.cur, d.prev, ["region"]), horizontal=True)
    block("D. By business team", "Business team", _grouped(d.cur, d.prev, ["team"]), horizontal=True)
    rows, rest = top10("country", "All other countries")
    block(f"E. Top 10 introducer countries ({cy} intake)", "Country", rows, rest, horizontal=True)
    rows, rest = top10("institution", "All other institutions")
    block(f"F. Top 10 institutions ({cy} intake)", "Institution", rows, rest, horizontal=True)
    lv = [_label("course_level")]
    block("G. By course level", "Application Course Level",
          _grouped(d.cur.with_columns(lv), d.prev.with_columns(lv), ["course_level"]), horizontal=True)
    block("H. By the year the introducer was onboarded", "Introducer onboarded in",
          [((o,), d.cur.filter(pl.col("cohort") == o).height, d.prev.filter(pl.col("cohort") == o).height)
           for o in _cohorts(p)])
    ws.widths.update({1: 40, 2: 13, 3: 13, 4: 10, 5: 10, 6: 3})
    ws.freeze = "A4"


def _last_week(ws: Sheet, d: Deposits, introducers: Export, logs: Export, applications: Export,
               p: Periods) -> None:
    """Last week, whole, against the week before: onboarding, logs and the
    deposits paid in full. `p` is as of last Friday."""
    wh, pwh = f"{p.cur}\n{_span(p.week)}", f"{p.prev}\n{_span(p.last_week)}"
    i = _master(introducers)
    on, pon = i.filter(_between("bc", p.week)), i.filter(_between("bc", p.last_week))
    lg = _logs(logs, introducers)
    lc, lp = lg.filter(_between("day", p.week)), lg.filter(_between("day", p.last_week))
    # Paid in full that week: dated by the export's "Timestamp of 'Deposit Fully
    # Paid' status", whatever the intake year. Those since closed lost, or no
    # longer paid in full, are left out and counted in the note.
    a = d.a.filter(pl.col("academic") & pl.col("b2b")).with_columns(
        _team("team"), _label("region"), _label("institution"),
        pl.when(pl.col("year").is_null()).then(pl.lit(BLANK))
        .otherwise(pl.col("month") + " " + pl.col("year").cast(pl.Utf8)).alias("intake"),
    )
    paid_in = {k: a.filter(_between("paid", span)) for k, span in (("c", p.week), ("p", p.last_week))}
    counted = pl.col("state").is_in(["Active", "DAA"])
    fc, fp = paid_in["c"].filter(counted), paid_in["p"].filter(counted)
    dropped = paid_in["c"].height - fc.height + paid_in["p"].height - fp.height

    ws.set(1, 1, f"Last week — {_fmt(p.week[0])} – {_fmt(p.week[1])} against the week before", H1)
    ws.set(2, 1, f"{p.cur} is the whole Edvoy week {_fmt(p.week[0])} – {_fmt(p.week[1])}; the week before is "
                 f"{_fmt(p.last_week[0])} – {_fmt(p.last_week[1])}. Introducers onboarded: Became Customer Date on "
                 f"the introducers master, {_source_note(introducers)}. Activity logs: Log Time in UTC, one row per "
                 f"log id, {_source_note(logs)}. Deposits fully paid: the application's \"Timestamp of 'Deposit "
                 f"Fully Paid' status\" in the week, any intake year, on {_source_note(applications)}; counted when "
                 "the application has an introducer, an Academic course level and StudentAssignedToBusinessArea "
                 "B2B, and is today an active deposit or DAA. The applications export keeps no history, so a "
                 "deposit since closed lost or no longer paid in full drops out"
                 + (f": {dropped} paid in these two weeks did." if dropped else "; none paid in these two weeks did."),
           NOTE_WRAP)
    ws.merges.append("A2:N2")
    ws.heights[2] = 66
    w = Writer(ws)

    w.section("A. At a glance")
    top = w.r
    w.compare(["Measure"], [(("Introducers onboarded",), on.height, pon.height),
                            (("Activity logs",), lc.height, lp.height),
                            (("Deposits fully paid",), fc.height, fp.height)], wh, pwh, total=False)
    ws.charts.append(Chart(f"{p.cur} vs {p.prev.lower()}", (top + 1, top + 3, 1),
                           [(p.cur, 2), (p.prev, 3)], at=(top - 1, 8), size=(14, 8)))
    w.r = max(w.r, top + 14)

    w.section("B. Activity logs by log type")
    w.compare(["Log type"], [((t,), lc.filter(pl.col("type") == t).height, lp.filter(pl.col("type") == t).height)
                             for t in TYPES + (["Other"] if lc.filter(pl.col("type") == "Other").height
                                               + lp.filter(pl.col("type") == "Other").height else [])], wh, pwh)
    w.section("B1. Activity logs by business region")
    w.compare(["Business region"], _grouped(lc, lp, ["region"]), wh, pwh)
    w.section("B2. Activity logs by business team")
    w.compare(["Business team"], _grouped(lc, lp, ["team"]), wh, pwh)

    w.section("C. Introducers onboarded by business region (BusinessRegion)")
    w.compare(["Business region"], _grouped(on, pon, ["region"]), wh, pwh)
    w.section("C1. Introducers onboarded by business team (BusinessTeam)")
    w.compare(["Business team"], _grouped(on, pon, ["team"]), wh, pwh)
    w.section("C2. Introducers onboarded by country")
    w.compare(["Country"], _grouped(on, pon, ["country"]), wh, pwh)
    w.section(f"C3. Introducers onboarded {p.cur.lower()} ({on.height})")
    w.header(["Introducer", "Country", "Business team", "SRM", "Became Customer Date"])
    for x in on.sort(["bc", "name"]).iter_rows(named=True):
        for k, v in enumerate([x["name"], x["country"], x["team"], x["srm"]], 1):
            ws.set(w.r, k, v, _st())
        ws.set(w.r, 5, x["bc"], _st(DAY))
        w.r += 1
    w.r += 1

    w.section("D. Deposits fully paid by state today")
    w.compare(["State"], [(("Active deposit",), fc.filter(pl.col("state") == "Active").height,
                           fp.filter(pl.col("state") == "Active").height),
                          (("DAA — deferral awaiting approval",), fc.filter(pl.col("state") == "DAA").height,
                           fp.filter(pl.col("state") == "DAA").height)], wh, pwh)
    w.section("D1. Deposits fully paid by business region (StudentAssignedToBusinessRegion)")
    w.compare(["Business region"], _grouped(fc, fp, ["region"]), wh, pwh)
    w.section("D2. Deposits fully paid by business team (CurrentlyAssignedToBusinessTeam)")
    w.compare(["Business team"], _grouped(fc, fp, ["team"]), wh, pwh)
    w.section("D3. Deposits fully paid by intake (Actual Intake Month and Year)")
    w.compare(["Intake"], _grouped(fc, fp, ["intake"]), wh, pwh)
    ws.widths.update(dict(enumerate([40, 34, 30, 18, 22, 10, 14], 1)))
    ws.freeze = "A4"


def _sales(ws: Sheet, d: Deposits, applications: Export, p: Periods) -> None:
    cy, ly = p.cy, p.ly
    held, cur, prev, n = d.held, d.cur, d.prev, d.n
    non_acad, non_b2b, resurrected, missed = d.non_acad, d.non_b2b, d.resurrected, d.missed
    ws.set(1, 1, "Sales & Retention — active deposits by Actual Intake Year", H1)
    ws.set(2, 1, f"Source: applications, {_source_note(applications)}; applications with an Application "
                 "Introducer and not Closed Lost only. Active deposit = Deposit Paid Status FullyPaid or "
                 "fullyPaidWaitingForApproval, with Deferred Initiated and Deferred Approved both No or both Yes. "
                 "DAA = the same paid statuses where those two columns differ. PD = Deposit Paid Status "
                 f"PartiallyPaid. Intake = Actual Intake Year and Actual Intake Month. Application Course Level "
                 f"{', '.join(ACADEMIC)} only; active deposits on any other course level left out: {cy} "
                 f"{non_acad.get(cy, 0)}, {ly} {non_acad.get(ly, 0)}. StudentAssignedToBusinessArea B2B only; "
                 f"Academic active deposits on other business areas left out: {cy} {non_b2b.get(cy, 0)}, "
                 f"{ly} {non_b2b.get(ly, 0)}. Every table from A2 on counts active "
                 f"deposits only. The {cy} intake year is still in progress.", NOTE_WRAP)
    ws.merges.append("A2:G2")
    ws.heights[2] = 96
    cyh, lyh = f"{cy} intake", f"{ly} intake"
    w = Writer(ws)

    w.section(f"A. Deposits by introducers: {cy} vs {ly}")
    w.compare(["Deposits"], [((label,), n(st, cy), n(st, ly)) for st, label in
                             (("Active", "Active deposits"), ("DAA", "DAA — deferral awaiting approval"),
                              ("PD", "PD — partial deposits"))], cyh, lyh, total=False)
    w.section("A1. By Actual Intake Month")
    present = set(held["month"].to_list())
    w.grid(["Actual Intake Month"],
           [((m,), [n(st, y, m) for y in (cy, ly) for st in ("Active", "DAA", "PD")])
            for m in MONTHS + [BLANK] if m in present],
           [f"{y} {st}" for y in (cy, ly) for st in ("Active", "DAA", "PD")])
    w.section("A2. Active deposits by the year the introducer was onboarded (Became Customer Date)")
    w.compare(["Introducer onboarded in"],
              [((o,), cur.filter(pl.col("cohort") == o).height, prev.filter(pl.col("cohort") == o).height)
               for o in _cohorts(p)], cyh, lyh)

    w.section(f"B. {cy} active deposits broken down",
              "SRM and AMT counsellor are the Introducer SRM / AMT columns on the application; business team "
              "is its CurrentlyAssignedToBusinessTeam and business region its StudentAssignedToBusinessRegion. "
              "Country is the introducer's country on the master file.")
    value_h = f"{cy} active deposits"
    for title, labels, keys in (("B1. By introducer country", ["Country"], ["country"]),
                                ("B2. By business region", ["Business region"], ["region"]),
                                ("B3. By SRM", ["SRM", "Business team"], ["srm", "team"]),
                                ("B4. By business team", ["Business team"], ["team"]),
                                ("B5. By AMT counsellor", ["AMT counsellor"], ["amt"]),
                                ("B6. By institution", ["Institution"], ["institution"])):
        w.section(title)
        w.share(labels, _counts(cur, keys), value_h)

    def intro_list(df: pl.DataFrame, title: str, count_label: str, deposits_label: str, deposit_col: int) -> None:
        w.section(title)
        rc = w.r
        ws.set(rc, 1, count_label, Style(bold=True))
        ws.set(rc + 1, 1, deposits_label, Style(bold=True))
        w.r += 3
        w.header(["Introducer", "Country", "Business team", "SRM", "Became Customer Date", f"{cy} active deposits",
                  f"{ly} active deposits"], height=30)
        first = w.r
        for x in df.iter_rows(named=True):
            for k, v in enumerate([x["introducer_name"], x["country"], x["team"], x["srm"]], 1):
                ws.set(w.r, k, v, _st())
            ws.set(w.r, 5, x["bc"], _st(DAY))
            ws.set(w.r, 6, x["cy"], _st(INT))
            ws.set(w.r, 7, x["ly"], _st(INT))
            w.r += 1
        tot = w.r
        ws.set(tot, 1, "Total", _st(total=True))
        for k in range(2, 6):
            ws.set(tot, k, "", _st(total=True))
        sums = {6: int(df["cy"].sum()), 7: int(df["ly"].sum())}
        for c, v in sums.items():
            ws.set(tot, c, Formula(f"SUM({L(c)}{first}:{L(c)}{max(first, tot - 1)})", v), _st(INT, total=True))
        ws.set(rc, 2, Formula(f"COUNTA(A{first}:A{max(first, tot - 1)})" if df.height else "0", df.height),
               Style(bold=True, num_fmt=INT))
        ws.set(rc + 1, 2, Formula(f"{L(deposit_col)}{tot}", sums[deposit_col]), Style(bold=True, num_fmt=INT))
        w.r = tot + 2

    intro_list(resurrected,
               f"C. Resurrected — introducers not onboarded in {cy}, with no active deposit for the {ly} intake, "
               f"who have active deposits for the {cy} intake",
               "Introducers resurrected", f"Their {cy} active deposits", 6)
    intro_list(missed,
               f"D. Missed out — introducers with active deposits for the {ly} intake and none for the {cy} intake",
               "Introducers missed out", f"Their {ly} active deposits", 7)
    ws.widths.update(dict(enumerate([46, 28, 24, 26, 20, 16, 16], 1)))
    ws.freeze = "A4"


# ------------------------------------------------------------------ serving

def latest_uploads(conn) -> dict[str, dict]:
    """The newest successfully read upload of each source the report needs.

    The newest rather than the one a dashboard has current: the button promises
    the latest data, and every source here is read whole from its own file.
    """
    with conn.cursor() as cur:
        cur.execute(
            """select distinct on (s.slug) s.slug as source, s.display_name, u.id, u.filename,
                      u.stored_path, u.started_at
                 from core.uploads u join core.sources s on s.id = u.source_id
                where s.slug = any(%s) and u.status = 'ready' and u.stored_path is not null
                order by s.slug, u.started_at desc""",
            (list(SOURCES),),
        )
        return {r["source"]: r for r in cur.fetchall()}


_cache: dict[tuple, dict[str, Export]] = {}
_lock = threading.Lock()


def summary(uploads: dict[str, dict], p: Periods) -> bytes:
    """The workbook for these three uploads over the periods `p`.

    Reading the exports takes seconds and building from them a fraction of
    one, so the read is what is kept: until a new upload, both summaries build
    from it. Only the latest is kept; the lock stops two clicks reading twice.
    """
    key = tuple(uploads[s]["id"] for s in SOURCES)
    with _lock:
        if key not in _cache:
            ex = {s: read_export(s, uploads[s]["filename"], storage().get(uploads[s]["stored_path"]),
                                 uploads[s]["started_at"]) for s in SOURCES}
            _cache.clear()
            _cache[key] = ex
        ex = _cache[key]
    return build(ex["introducers"], ex["introducer_logs"], ex["applications"], p)
