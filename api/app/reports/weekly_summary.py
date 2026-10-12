"""This week's summary: deposits, onboarding, activity and sales & retention in one workbook.

Read straight from the latest archived export of each source:

    introducers      Became Customer Date, SRM, BusinessTeam, BusinessRegion, country, the CRM `_id`
    introducer_logs  Log Time, Log Type, Created By, Managed By Team (read as a business team and region)
    applications     the active-deposit columns, the application's own
                     Introducer SRM / AMT, Institution, Application Introducer Id,
                     CurrentlyAssignedToBusinessTeam, StudentAssignedToBusinessArea / Region,
                     Application Destination Country, Student Nationality,
                     Application Status / Sub-Status and the timestamp of each status

"This week" is the Edvoy week, Saturday to Friday, that contains `today`, and
it is to date. "Last week" is the seven days before it. Year to date runs
from 1 January to `today`, against the same span of last year.

Sheets, in order: YTD - Year to Date Summary (deposits, PD and DAA by intake
year and quarter, in tables and charts), the same for next year's intake
against this year's (e.g. "2027 sales sheet"), Deposit funnel movement (active
deposits by the stage each stands at now, by year, quarter and business area),
Sametime Last Year (this intake year's applications created at and active in
each stage by today, against last year's on the same date a year ago), Onboarding, Activity, Sales & Retention, and Last week -- last week, whole, against the
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
the export carries every business area, and this is the introducer business.
The YTD sheet is the exception: it counts every business area (a blank one
aside), with or without an introducer. Every sheet opens with a note that
says so, and says which files it was read from.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, replace
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
        Col("destination", "application destination country", ("destination", "country")),
        Col("nationality", "student nationality", ("student", "nationality")),
        # "Timestamp of 'Deposit Fully Paid' status"; the export's quotes arrive garbled
        Col("paid_at", "", ("timestamp", "deposit", "fully", "paid")),
        Col("status", "application status", ()),
        Col("sub_status", "application sub-status", ()),
        # when each stage was reached: "Timestamp of 'Offer' status" and so on
        Col("applied_at", "timestamp of applied status", ("timestamp", "applied")),
        Col("offer_at", "timestamp of offer status", ("timestamp", "offer")),
        Col("coe_at", "timestamp of coe received status", ("timestamp", "coe")),
        Col("visa_applied_at", "timestamp of visa| applied status", ("timestamp", "visa", "applied")),
        Col("visa_granted_at", "timestamp of visa| granted status", ("timestamp", "visa", "granted")),
        Col("enrolled_at", "timestamp of enrolled status", ("timestamp", "enrolled")),
        Col("closed_at", "timestamp of application marked as closed", ("marked", "closed")),
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
HDR_ALT = replace(HDR, fill="2F5597")   # every other column group: a lighter shade of the same blue
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


UP, DOWN = "38761D", "C00000"      # subtle green, red


def _trend(nf: str, value, total: bool = False) -> Style:
    """A Change or % change cell: green for growth, red for decline. Coloured by
    the value at build time; the workbook is rebuilt for every download."""
    st = _st(nf, total=total)
    if isinstance(value, (int, float)) and value:
        st = replace(st, color=UP if value > 0 else DOWN)
    return st


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

    def header(self, cols: list[str], height: float | None = None, alt: set[int] = frozenset()) -> None:
        """`alt`: the columns in the lighter shade, setting one kind of data apart."""
        for c, h in enumerate(cols, 1):
            self.ws.set(self.r, c, h, HDR_ALT if c in alt else HDR)
        if height:
            self.ws.heights[self.r] = height
        self.r += 1

    def _groups(self, rows: list[tuple[tuple[str, ...], tuple[int, ...]]],
                nest: str | None) -> list[list[tuple[tuple[str, ...], tuple[int, ...]]]]:
        """`rows` one group each, or with `nest` the rows sharing a first label
        together, biggest group first, so that one summary row can stand above
        them."""
        if not nest:
            return [[x] for x in rows]
        by: dict[str, list] = {}
        for labels, vals in rows:
            by.setdefault(labels[0], []).append((labels, vals))
        return sorted(by.values(), key=lambda m: ([-sum(v[j] for _, v in m) for j in range(len(m[0][1]))],
                                                  str(m[0][0][0])))

    def _body(self, rows: list[tuple[tuple[str, ...], tuple[int, ...]]], nl: int, nest: str | None,
              put) -> bool:
        """Lays `rows` down from the current row: labels, then `put(row, labels,
        values, details)` for the rest. With `nest`, a first label shared by several rows
        becomes a summary row over them ("2 teams"), its `details` the (first,
        last) of the rows under it, which are grouped and start collapsed.
        Says whether any group was made."""
        ws, nested = self.ws, False
        for members in self._groups(rows, nest):
            if len(members) == 1:
                labels, vals = members[0]
                for k, lab in enumerate(labels, 1):
                    ws.set(self.r, k, lab, _st())
                put(self.r, labels, vals, None)
                self.r += 1
                continue
            nested, top, n = True, self.r, len(members)
            ws.set(top, 1, members[0][0][0], _st())
            ws.set(top, 2, f"{n} {nest}", _st())
            for k in range(3, nl + 1):
                ws.set(top, k, "", _st())
            put(top, members[0][0][:1], tuple(sum(v[j] for _, v in members) for j in range(len(members[0][1]))),
                (top + 1, top + n))
            ws.collapsed.add(top)
            for i, (labels, vals) in enumerate(members, 1):
                r = top + i
                ws.set(r, 1, "", _st())
                for k, lab in enumerate(labels[1:], 2):
                    ws.set(r, k, lab, replace(_st(), indent=1))
                put(r, labels, vals, None)
                ws.outline[r] = 1
            self.r = top + n + 1
        return nested

    @staticmethod
    def _sum(c: int, first: int, last: int, nested: bool) -> str:
        """A column's total. Under groups it is SUBTOTAL, which skips the summary
        rows' own SUBTOTALs, so nothing counts twice."""
        span = f"{L(c)}{first}:{L(c)}{max(first, last)}"
        return f"SUBTOTAL(9,{span})" if nested else f"SUM({span})"

    def compare(self, label_cols: list[str], rows: list[tuple[tuple[str, ...], int, int]],
                cur_h: str, prev_h: str, total: bool = True, nest: str | None = None,
                intros=None) -> None:
        """Labels, current, previous, Change and % change -- the last two as
        formulas. `nest` groups the rows by their first label (see _body).
        `intros(labels)` adds the introducers behind a row's counts, current and
        previous; it is given the first label alone for a summary row and none
        for the total, since an introducer in several rows counts once there."""
        ws, nl = self.ws, len(label_cols)
        cc, pc = nl + 1, nl + 2
        ic = pc + 3
        extra = [f"{cur_h} introducers", f"{prev_h} introducers"] if intros else []
        self.header(label_cols + [cur_h, prev_h, "Change", "% change"] + extra, height=30, alt={ic, ic + 1})
        first = self.r

        def tail(r: int, cv: int, pv: int, tot: bool) -> None:
            C, P = ref(r, cc), ref(r, pc)
            ws.set(r, pc + 1, Formula(f"{C}-{P}", cv - pv), _trend(DLT, cv - pv, tot))
            ws.set(r, pc + 2, Formula(f'IF({P}=0,"",({C}-{P})/{P})', _pct(cv, pv)), _trend(PCT, _pct(cv, pv), tot))

        def who(r: int, labels: tuple[str, ...], tot: bool = False) -> None:
            if intros:
                for c, v in zip((ic, ic + 1), intros(labels)):
                    ws.set(r, c, v, _st(INT, total=tot))

        def put(r: int, labels: tuple[str, ...], vals: tuple[int, ...], details: tuple[int, int] | None) -> None:
            for c, v in ((cc, vals[0]), (pc, vals[1])):
                ws.set(r, c, Formula(self._sum(c, *details, True), v) if details else v, _st(INT))
            tail(r, vals[0], vals[1], False)
            who(r, labels)

        nested = self._body([(labels, (cv, pv)) for labels, cv, pv in rows], nl, nest, put)
        if total:
            sc, sp = sum(x[1] for x in rows), sum(x[2] for x in rows)
            ws.set(self.r, 1, "Total", _st(total=True))
            for k in range(2, nl + 1):
                ws.set(self.r, k, "", _st(total=True))
            for c, v in ((cc, sc), (pc, sp)):
                ws.set(self.r, c, Formula(self._sum(c, first, self.r - 1, nested), v), _st(INT, total=True))
            tail(self.r, sc, sp, True)
            who(self.r, (), True)
            self.r += 1
        self.r += 1

    def share(self, label_cols: list[str], rows: list[tuple[tuple[str, ...], int]], value_h: str,
              nest: str | None = None, intros=None) -> None:
        """Counts with each row's share of the total. `nest` groups the rows by
        their first label (see _body); `intros(labels)` adds the introducers
        behind a row's count, as in compare."""
        ws, nl = self.ws, len(label_cols)
        vc = nl + 1
        self.header(label_cols + [value_h, "Share"] + (["Introducers"] if intros else []), height=30,
                    alt={vc + 2})
        groups = self._groups([(labels, (v,)) for labels, v in rows], nest)
        first = self.r
        last = first + sum(len(m) + (len(m) > 1) for m in groups) - 1
        tot = sum(v for _, v in rows)

        def put(r: int, labels: tuple[str, ...], vals: tuple[int, ...], details: tuple[int, int] | None) -> None:
            if intros:
                ws.set(r, vc + 2, intros(labels), _st(INT))
            v = vals[0]
            ws.set(r, vc, Formula(self._sum(vc, *details, True), v) if details else v, _st(INT))
            ws.set(r, vc + 1, Formula(f"IF({L(vc)}${last + 1}=0,0,{L(vc)}{r}/{L(vc)}${last + 1})",
                                      v / tot if tot else 0), _st(SHARE))

        nested = self._body([(labels, (v,)) for labels, v in rows], nl, nest, put)
        ws.set(self.r, 1, "Total", _st(total=True))
        for k in range(2, nl + 1):
            ws.set(self.r, k, "", _st(total=True))
        ws.set(self.r, vc, Formula(self._sum(vc, first, last, nested), tot), _st(INT, total=True))
        ws.set(self.r, vc + 1, Formula(f"IF({L(vc)}{self.r}=0,0,1)", 1 if tot else 0), _st(SHARE, total=True))
        if intros:
            ws.set(self.r, vc + 2, intros(()), _st(INT, total=True))
        self.r += 2

    def grid(self, label_cols: list[str], rows: list[tuple[tuple[str, ...], list[int]]], value_h: list[str],
             given: dict[int, int] | None = None) -> None:
        """Several counts per row, each column summed in a total row -- except
        the columns in `given` (by index into `value_h`), whose total is the
        value there, shown in the lighter header shade."""
        ws, nl = self.ws, len(label_cols)
        given = given or {}
        self.header(label_cols + value_h, height=30, alt={nl + 1 + j for j in given})
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
            if j in given:
                ws.set(self.r, c, given[j], _st(INT, total=True))
                continue
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


def _introducers(df: pl.DataFrame, keys: list[str]):
    """How many introducers (`key`) have a row in `df` matching the labels
    given for the first of `keys`: all of them, a prefix, or none (every row)."""
    def count(labels: tuple[str, ...]) -> int:
        f = df
        for k, v in zip(keys, labels):
            f = f.filter(pl.col(k) == v)
        return f["key"].n_unique()
    return count


def _counts(df: pl.DataFrame, keys: list[str]) -> list[tuple[tuple[str, ...], int]]:
    g = df.group_by(keys).len("n").sort(["n", *keys], descending=[True] + [False] * len(keys))
    return [(tuple(r[k] for k in keys), r["n"]) for r in g.iter_rows(named=True)]


def _source_note(e: Export) -> str:
    return f"{e.filename}, uploaded {e.uploaded_at:%d %b %Y %H:%M} UTC ({e.frame.height:,} rows)"


# ------------------------------------------------------------------ sheets

def build(introducers: Export, logs: Export, applications: Export, p: Periods) -> bytes:
    wb = Workbook()
    d = _deposits(applications, introducers, p)
    _ytd(wb.add_sheet(YTD_SHEET), applications, p)
    nxt = Periods(date(p.cy + 1, 1, 1))
    _ytd(wb.add_sheet(f"{nxt.cy} sales sheet"), applications, nxt, f"{nxt.cy} sales")
    _funnel(wb.add_sheet(FUNNEL_SHEET), applications, p)
    _same_time(wb.add_sheet(SAME_TIME_SHEET), applications, p)
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
    w.compare(["SRM", "Business team"], _grouped(on["ytd"], on["lytd"], ["srm", "team"]), yh, lyh, nest="teams")
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
    w.compare(["SRM", "Business team"], _grouped(on["wk"], on["pwk"], ["srm", "team"]), wh, pwh, nest="teams")
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
        for j in range(1, len(metrics), 2):
            for c in range(2 + 3 * j, 5 + 3 * j):
                ws.set(w.r - 1, c, cols[c - 1], HDR_ALT)
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
                ws.set(w.r, c + 2, Formula(f"{ref(w.r, c)}-{ref(w.r, c + 1)}", cv - pv), _trend(DLT, cv - pv))
                c += 3
            w.r += 1
        ws.set(w.r, 1, "Total", _st(total=True))
        for j in range(len(metrics)):
            c = 2 + 3 * j
            for off in (0, 1):
                ws.set(w.r, c + off, Formula(f"SUM({L(c + off)}{first}:{L(c + off)}{max(first, w.r - 1)})",
                                             sums[2 * j + off]), _st(INT, total=True))
            ws.set(w.r, c + 2, Formula(f"{ref(w.r, c)}-{ref(w.r, c + 1)}", sums[2 * j] - sums[2 * j + 1]),
                   _trend(DLT, sums[2 * j] - sums[2 * j + 1], total=True))
        w.r += 2

    w.section("B. SRM-wise")
    wide("srm", "SRM (Created By)")
    w.section("C. Business region-wise")
    wide("region", "Business region")
    w.section("D. Business team-wise")
    wide("team", "Business team")
    ws.widths.update({1: 34, **{c: 11 for c in range(2, 17)}})
    ws.freeze = "B4"


def _state() -> pl.Expr:
    """Active, DAA or PD, as the module docstring defines them; null for any
    other application and for a Closed Lost one."""
    # an export without the deferral columns reads as never deferred
    di = clean(pl.col("deferral_initiated")).fill_null("No")
    da = clean(pl.col("deferral_approved")).fill_null("No")
    status = _letters("deposit_paid_status")
    live = clean(pl.col("closed_lost")).fill_null("No").eq("No")
    return (pl.when(~live).then(None)
            .when(status.is_in(PAID_IN_FULL) & di.eq(da)).then(pl.lit("Active"))
            .when(status.is_in(PAID_IN_FULL)).then(pl.lit("DAA"))
            .when(status == "partiallypaid").then(pl.lit("PD"))
            .alias("state"))


def _academic() -> pl.Expr:
    return _letters("course_level").is_in([c.lower() for c in ACADEMIC]).alias("academic")


def _year() -> pl.Expr:
    return clean(pl.col("intake_year")).str.extract(r"(\d{4})").cast(pl.Int32, strict=False).alias("year")


def _month() -> pl.Expr:
    month = clean(pl.col("intake_month")).str.to_titlecase()
    return pl.when(month.is_in(MONTHS)).then(month).otherwise(pl.lit(BLANK)).alias("month")


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

    def n(self, state: str, year: int, q: int | None = None) -> tuple[int, int]:
        """The applications in `state` for `year`'s intake, in quarter `q` (0: no
        intake month) or all, and the introducers behind them."""
        f = self.held.filter((pl.col("state") == state) & (pl.col("year") == year))
        if q is not None:
            f = f.filter(pl.col("q") == q)
        return f.height, f["key"].n_unique()


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
    a = a.with_columns(
        _academic(),
        clean(pl.col("business_area")).str.to_uppercase().eq("B2B").fill_null(False).alias("b2b"),
        _state(), _year(), _month(),
        _date("paid_at").alias("paid"),
    )
    held = a.filter(pl.col("state").is_not_null() & pl.col("year").is_in([cy, ly]))
    non_acad = {r["year"]: r["len"] for r in held.filter((pl.col("state") == "Active") & ~pl.col("academic"))
                .group_by("year").len().iter_rows(named=True)}
    held = held.filter(pl.col("academic"))
    non_b2b = {r["year"]: r["len"] for r in held.filter((pl.col("state") == "Active") & ~pl.col("b2b"))
               .group_by("year").len().iter_rows(named=True)}
    # The introducer is the CRM id where the application carries one, its name
    # where it does not; either way it is looked up on the master for its
    # country and Became Customer Date.
    held = held.filter(pl.col("b2b")).with_columns(
        pl.coalesce(clean(pl.col("introducer_id")), pl.lit("name:") + pl.col("introducer_name")).alias("key"),
        pl.col("month").replace_strict(QUARTER_OF, default=0, return_dtype=pl.Int8).alias("q"),
    )
    dep = held.filter(pl.col("state") == "Active")
    dep = dep.with_columns(
        _label("srm"), _team("team"), _label("region"), _label("amt"), _label("institution"),
        _label("destination"),
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


YTD_SHEET = "YTD - Year to Date Summary"
MEASURES = [("Deposits", "Active"), ("PD", "PD"), ("DAA", "DAA")]
QUARTERS = ["Q1 (Jan–Mar)", "Q2 (Apr–Jun)", "Q3 (Jul–Sep)", "Q4 (Oct–Dec)"]
QUARTER_OF = {m: i // 3 + 1 for i, m in enumerate(MONTHS)}
YTD_TOP = 20


def _ytd_frame(applications: Export, p: Periods) -> tuple[pl.DataFrame, dict[str, dict[int, int]]]:
    """Active, DAA and PD applications for this year's and last year's intake,
    in every business area and with or without an introducer, each with the
    quarter of its intake month (0 when the month is blank). Also what was
    left out, per reason and intake year."""
    a = applications.frame.with_columns(
        _state(), _year(), _month(), _academic(), clean(pl.col("business_area")).alias("area"),
    ).filter(pl.col("state").is_not_null() & pl.col("year").is_in([p.cy, p.ly]))

    def per_year(df: pl.DataFrame) -> dict[int, int]:
        return {r["year"]: r["len"] for r in df.group_by("year").len().iter_rows(named=True)}

    left_out = {"non_acad": per_year(a.filter(~pl.col("academic"))),
                "no_area": per_year(a.filter(pl.col("academic") & pl.col("area").is_null()))}
    a = a.filter(pl.col("academic") & pl.col("area").is_not_null()).with_columns(
        pl.col("month").replace_strict(QUARTER_OF, default=0, return_dtype=pl.Int8).alias("q"),
        _label("region"), _label("destination"), _label("nationality"),
    )
    return a, left_out


def _ytd_table(w: Writer, label: str, df: pl.DataFrame, key: str, p: Periods, title: str,
               top: int | None = None, totals: bool = True) -> None:
    """Deposits, PD and DAA per `key`, one block of rows each: the full intake
    year and each quarter, this year against last. Under it, a chart of the
    deposits per key. `top` keeps the biggest keys and folds the rest into one
    row, which the chart leaves out."""
    ws, cy, ly = w.ws, p.cy, p.ly
    cyh, lyh = f"{cy} intake", f"{ly} intake"
    order = df.group_by(key).agg(
        *[((pl.col("state") == s) & (pl.col("year") == y)).sum().alias(f"{s}{y}")
          for s in ("Active", "PD", "DAA") for y in (cy, ly)])
    order = order.sort([f"Active{cy}", f"Active{ly}", f"PD{cy}", f"DAA{cy}", key],
                       descending=[True, True, True, True, False])
    keys = order[key].to_list()
    if top is not None and len(keys) > top:
        other = f"All others ({len(keys) - top})"
        df = df.with_columns(pl.when(pl.col(key).is_in(keys[:top])).then(pl.col(key))
                             .otherwise(pl.lit(other)).alias(key))
        keys = keys[:top] + [other]
    n: dict[tuple, int] = {}
    for r in df.group_by(key, "state", "year").len().iter_rows():
        n[(r[0], r[1], r[2], 0)] = r[3]
    for r in df.filter(pl.col("q") > 0).group_by(key, "state", "year", "q").len().iter_rows():
        n[(r[0], r[1], r[2], r[3])] = r[4]

    # two header rows: the period over its columns, then the years
    h = w.r
    groups = [("Full year", 3, [cyh, lyh, "Change", "% change"])] + \
             [(q, 7 + 3 * j, [str(cy), str(ly), "% change"]) for j, q in enumerate(QUARTERS)]
    for c, name in ((1, "Measure"), (2, label)):
        ws.set(h, c, name, HDR)
        ws.set(h + 1, c, "", HDR)
        ws.merges.append(f"{L(c)}{h}:{L(c)}{h + 1}")
    for j, (name, start, subs) in enumerate(groups):
        st = HDR_ALT if j % 2 else HDR
        for k, sub in enumerate(subs):
            ws.set(h, start + k, name if k == 0 else "", st)
            ws.set(h + 1, start + k, sub, st)
        ws.merges.append(f"{L(start)}{h}:{L(start + len(subs) - 1)}{h}")
    ws.heights[h + 1] = 30
    w.r += 2

    pairs = [(3, 4, 0)] + [(7 + 3 * j, 8 + 3 * j, j + 1) for j in range(4)]   # (this year, last year, quarter)

    def tail(r: int, cc: int, pc: int, cv: int, pv: int, change: bool, tot: bool) -> None:
        C, P = ref(r, cc), ref(r, pc)
        if change:
            ws.set(r, pc + 1, Formula(f"{C}-{P}", cv - pv), _trend(DLT, cv - pv, tot))
        ws.set(r, pc + 1 + change, Formula(f'IF({P}=0,"",({C}-{P})/{P})', _pct(cv, pv)), _trend(PCT, _pct(cv, pv), tot))

    measure = Style(bold=True, border=True, wrap=True, valign="center")
    top_row, deposits = w.r, []    # the deposit block's key rows: the chart's bars
    for mname, state in MEASURES:
        # a row with nothing in it from end to end is left out, and so is a
        # measure with no rows left
        rows = [k for k in keys if n.get((k, state, cy, 0), 0) or n.get((k, state, ly, 0), 0)]
        if not rows:
            continue
        first = w.r
        for k in rows:
            ws.set(w.r, 2, k, _st())
            for cc, pc, q in pairs:
                cv, pv = n.get((k, state, cy, q), 0), n.get((k, state, ly, q), 0)
                ws.set(w.r, cc, cv, _st(INT))
                ws.set(w.r, pc, pv, _st(INT))
                tail(w.r, cc, pc, cv, pv, q == 0, False)
            if state == "Active" and (top is None or k != keys[-1] or len(keys) <= top):
                deposits.append(w.r)
            w.r += 1
        if totals:
            ws.set(w.r, 2, "Total", _st(total=True))
            for cc, pc, q in pairs:
                cv = sum(n.get((k, state, cy, q), 0) for k in rows)
                pv = sum(n.get((k, state, ly, q), 0) for k in rows)
                for c, v in ((cc, cv), (pc, pv)):
                    ws.set(w.r, c, Formula(f"SUM({L(c)}{first}:{L(c)}{w.r - 1})", v), _st(INT, total=True))
                tail(w.r, cc, pc, cv, pv, q == 0, True)
            w.r += 1
        ws.set(first, 1, mname, measure)
        for r in range(first + 1, w.r):
            ws.set(r, 1, "", measure)
        if w.r - 1 > first:
            ws.merges.append(f"A{first}:A{w.r - 1}")
    end = w.r

    w.r = end + 1
    # the headline charts its measures, one row each; the rest their deposits per key
    cats = (top_row, end - 1, 1) if not totals else (deposits[0], deposits[-1], 2) if deposits else None
    if end == top_row or cats is None:
        return
    shown = cats[1] - cats[0] + 1
    many = shown > 6
    height = max(15, round(1.4 * shown) + 6) if many else 15
    ws.charts.append(Chart(title, cats, [(cyh, 3), (lyh, 4)], at=(w.r, 2), size=(height, 10), horizontal=many))
    w.r += height + 2


def _ytd(ws: Sheet, applications: Export, p: Periods, title: str = "Year to date summary") -> None:
    """Deposits, PD and DAA by Actual Intake Year, `p`'s year against the one
    before, for the full year and each quarter: overall, by business area, by
    region within each area, by destination country and by student nationality.
    The next year's sales sheet is this with `p` a year on."""
    cy, ly = p.cy, p.ly
    df, left_out = _ytd_frame(applications, p)
    blank_month = {y: df.filter((pl.col("year") == y) & (pl.col("q") == 0)).height for y in (cy, ly)}

    def per_year(d: dict[int, int]) -> str:
        return f"{d.get(cy, 0):,} for {cy}, {d.get(ly, 0):,} for {ly}"

    ws.set(1, 1, f"{title} — deposits, PD and DAA, {cy} intake vs {ly} intake", H1)
    ws.set(2, 1, f"Source: applications, {_source_note(applications)}. Deposits = active deposits: Deposit Paid "
                 "Status FullyPaid or fullyPaidWaitingForApproval, with Deferred Initiated and Deferred Approved "
                 "both No or both Yes. DAA = paid in full with those two differing. PD = PartiallyPaid. None Closed "
                 "Lost; Academic course levels only. Unlike the other sheets, every business area counts, with or "
                 "without an introducer; a blank Business Area is left out "
                 f"({per_year(left_out['no_area'])}), as are non-Academic levels ({per_year(left_out['non_acad'])}). "
                 "Intake = Actual Intake Year; quarters by Actual Intake Month, and an application with no month "
                 f"counts in the full year but in no quarter ({per_year(blank_month)}). The {cy} intake year is "
                 "still in progress.", NOTE_WRAP)
    ws.merges.append("A2:R2")
    ws.heights[2] = 54
    w = Writer(ws)

    w.section("A. Headline — all business areas")
    _ytd_table(w, "Business areas", df.with_columns(pl.lit("All business areas").alias("all")), "all", p,
               f"Deposits, PD and DAA — {cy} vs {ly} intake", totals=False)

    w.section("B. By Business Area")
    _ytd_table(w, "Business area", df, "area", p, "Deposits by business area")

    areas = df.filter(pl.col("state") == "Active").group_by("area").len().sort(["len", "area"], descending=[True, False])
    areas = areas["area"].to_list() + sorted(set(df["area"].to_list()) - set(areas["area"].to_list()))
    for i, area in enumerate(areas, 1):
        w.section(f"C{i}. {area} — by Business Region")
        _ytd_table(w, "Business region", df.filter(pl.col("area") == area), "region", p,
                   f"{area} deposits by business region")

    w.section("D. By application destination country",
              f"The {YTD_TOP} with the most {cy} deposits; the chart shows them, the table folds any others into one row.")
    _ytd_table(w, "Application Destination Country", df, "destination", p,
               "Deposits by application destination country", top=YTD_TOP)

    w.section("E. By student nationality",
              f"The {YTD_TOP} with the most {cy} deposits; the chart shows them, the table folds any others into one row.")
    _ytd_table(w, "Student Nationality", df, "nationality", p, "Deposits by student nationality", top=YTD_TOP)

    ws.widths.update({1: 12, 2: 32, 3: 11, 4: 11, 5: 9, 6: 9})
    ws.widths.update({c: 8 for c in range(7, 19)})
    ws.freeze = "C4"


FUNNEL_SHEET = "Deposit funnel movement"
STAGES = ["Offered", "CoE Received", "Visa Applied", "Visa Granted", "Enrolled"]


def _stage() -> pl.Expr:
    """Where an application stands now, by its Application Status -- Visa split
    by its Sub-Status into applied and granted. Anything else is Other."""
    status = clean(pl.col("status")).str.to_lowercase()
    sub = clean(pl.col("sub_status")).str.to_lowercase()
    return (pl.when(status == "offered").then(pl.lit("Offered"))
            .when(status == "coe received").then(pl.lit("CoE Received"))
            .when((status == "visa") & (sub == "granted")).then(pl.lit("Visa Granted"))
            .when((status == "visa") & (sub == "applied")).then(pl.lit("Visa Applied"))
            .when(status == "enrolled").then(pl.lit("Enrolled"))
            .otherwise(pl.lit("Other")).alias("stage"))


def _funnel_rows(w: Writer, label: str, groups: list[tuple[str, pl.DataFrame]], p: Periods,
                 stages: list[str]) -> None:
    """Per group: this year's active deposits by stage, last year's, and the
    % change; the total the sum of its stages. The group's name spans its rows."""
    ws, cy, ly = w.ws, p.cy, p.ly
    tc, sc = 3, 4                       # the total, then the stages from here
    w.header([label, "Intake", "Active deposits"] + stages, height=30,
             alt={sc + j for j in range(0, len(stages), 2)})
    measure = Style(bold=True, border=True, wrap=True, valign="center")
    for name, df in groups:
        first = w.r
        n = {(r[0], r[1]): r[2] for r in df.group_by("year", "stage").len().iter_rows()}
        for y in (cy, ly):
            ws.set(w.r, 2, f"{y} intake", _st())
            vals = [n.get((y, st), 0) for st in stages]
            for j, v in enumerate(vals):
                ws.set(w.r, sc + j, v, _st(INT))
            ws.set(w.r, tc, Formula(f"SUM({L(sc)}{w.r}:{L(sc + len(stages) - 1)}{w.r})", sum(vals)), _st(INT, bold=True))
            w.r += 1
        ws.set(w.r, 2, "% change", _st(total=True))
        for c in range(tc, sc + len(stages)):
            st = stages[c - sc] if c >= sc else None
            cv = sum(n.get((cy, s_), 0) for s_ in stages) if st is None else n.get((cy, st), 0)
            pv = sum(n.get((ly, s_), 0) for s_ in stages) if st is None else n.get((ly, st), 0)
            C, P = ref(first, c), ref(first + 1, c)
            ws.set(w.r, c, Formula(f'IF({P}=0,"",({C}-{P})/{P})', _pct(cv, pv)), _trend(PCT, _pct(cv, pv), True))
        w.r += 1
        ws.set(first, 1, name, measure)
        for r in range(first + 1, w.r):
            ws.set(r, 1, "", measure)
        ws.merges.append(f"A{first}:A{w.r - 1}")
    w.r += 1


def _funnel(ws: Sheet, applications: Export, p: Periods) -> None:
    """Active deposits by the stage each stands at now -- Offered, CoE
    Received, Visa Applied, Visa Granted, Enrolled -- this intake year against
    last: for the full year, each quarter and each business area, on the YTD
    sheet's footing (every business area, Academic levels)."""
    cy, ly = p.cy, p.ly
    cyh, lyh = f"{cy} intake", f"{ly} intake"
    df, _ = _ytd_frame(applications, p)
    df = df.filter(pl.col("state") == "Active").with_columns(_stage())
    # Other appears only if some deposit stands somewhere else
    stages = STAGES + (["Other"] if df.filter(pl.col("stage") == "Other").height else [])

    ws.set(1, 1, f"Deposit funnel movement — active deposits by stage, {cy} intake vs {ly} intake", H1)
    ws.set(2, 1, f"Source: applications, {_source_note(applications)}. Active deposits as on the YTD sheet: Deposit "
                 "Paid Status FullyPaid or fullyPaidWaitingForApproval, Deferred Initiated and Deferred Approved both "
                 "No or both Yes, not Closed Lost, Academic course levels, every business area but a blank one. Each "
                 "deposit counts once, at the stage it stands at now by its Application Status; Visa splits by "
                 "Application Sub-Status into Visa Applied and Visa Granted"
                 + (", and Other is any other status" if "Other" in stages else "") +
                 ". The stages add up to the total. Intake = Actual Intake Year; quarters by Actual Intake Month, "
                 f"and a deposit with no month counts in the full year but in no quarter. The {cy} intake year is "
                 "still in progress, so its deposits sit earlier in the funnel.", NOTE_WRAP)
    ws.merges.append(f"A2:{L(3 + len(stages))}2")
    ws.heights[2] = 66
    w = Writer(ws)

    w.section("A. Funnel — full intake year, all business areas",
              "Share = the stage's part of that year's active deposits.")
    n = {(r[0], r[1]): r[2] for r in df.group_by("year", "stage").len().iter_rows()}
    w.header(["Stage", cyh, lyh, "Change", "% change", f"{cy} share", f"{ly} share"], height=30, alt={6, 7})
    first = w.r
    last = first + len(stages) - 1
    tot = {y: sum(n.get((y, st), 0) for st in stages) for y in (cy, ly)}
    for i, st in enumerate(stages + ["Total active deposits"]):
        r, tr = first + i, st == "Total active deposits"
        cv = tot[cy] if tr else n.get((cy, st), 0)
        pv = tot[ly] if tr else n.get((ly, st), 0)
        ws.set(r, 1, st, _st(total=tr))
        for c, v in ((2, cv), (3, pv)):
            ws.set(r, c, Formula(f"SUM({L(c)}{first}:{L(c)}{last})", v) if tr else v, _st(INT, total=tr))
        ws.set(r, 4, Formula(f"B{r}-C{r}", cv - pv), _trend(DLT, cv - pv, tr))
        ws.set(r, 5, Formula(f'IF(C{r}=0,"",(B{r}-C{r})/C{r})', _pct(cv, pv)), _trend(PCT, _pct(cv, pv), tr))
        for c, (src, v, t) in ((6, ("B", cv, tot[cy])), (7, ("C", pv, tot[ly]))):
            ws.set(r, c, Formula(f'IF({src}${last + 1}=0,"",{src}{r}/{src}${last + 1})', v / t if t else ""),
                   _st(SHARE, total=tr))
    w.r = last + 3
    ws.charts.append(Chart(f"Active deposits by stage — {cy} vs {ly} intake", (first, last, 1),
                           [(cyh, 2), (lyh, 3)], at=(w.r, 1), size=(16, 7)))
    w.r += 18

    w.section("B. By Actual Intake Quarter", "Quarters by Actual Intake Month; the full year leads.")
    groups = [("Full year", df)] + [(q, df.filter(pl.col("q") == i)) for i, q in enumerate(QUARTERS, 1)]
    _funnel_rows(w, "Period", groups, p, stages)

    w.section("C. By Business Area", "Full intake year.")
    areas = df.group_by("area").len().sort(["len", "area"], descending=[True, False])["area"].to_list()
    _funnel_rows(w, "Business area", [(a, df.filter(pl.col("area") == a)) for a in areas], p, stages)

    ws.widths.update({1: 26, 2: 14, 3: 14, **{c: 13 for c in range(4, 4 + len(stages))}})
    ws.freeze = "A3"


SAME_TIME_SHEET = "Sametime Last Year"
MILESTONES = [("Applied", "applied_at"), ("Offered", "offer_at"), ("Deposit", "paid_at"),
              ("CoE Received", "coe_at"), ("Visa Applied", "visa_applied_at"),
              ("Visa Granted", "visa_granted_at"), ("Enrolled", "enrolled_at")]
TOTAL = "Total on the date"


def _milestones(applications: Export, p: Periods, cuts: dict[int, date]) -> pl.DataFrame:
    """Every application for this year's and last year's intake (Academic
    levels, a business area), with whether it had reached each stage by its
    intake year's cut-off -- a stage with no timestamp counts as passed when a
    later one was reached by then -- the furthest it had reached (`at`, null if
    not yet applied) and whether it was closed by then."""
    a = applications.frame.with_columns(
        _year(), _month(), _academic(), clean(pl.col("business_area")).alias("area"),
    ).filter(pl.col("year").is_in([p.cy, p.ly]) & pl.col("academic") & pl.col("area").is_not_null())
    cut = pl.lit(None, dtype=pl.Date)
    for y, d in cuts.items():
        cut = pl.when(pl.col("year") == y).then(pl.lit(d)).otherwise(cut)
    on = [(_date(c) <= cut).fill_null(False) for _, c in MILESTONES]
    a = a.with_columns(
        pl.col("month").replace_strict(QUARTER_OF, default=0, return_dtype=pl.Int8).alias("q"),
        *[pl.any_horizontal(on[k:]).alias(name) for k, (name, _) in enumerate(MILESTONES)],
        # closed by then: Closed Lost now, marked closed on or before the date
        # (with no timestamp, all along). One reopened since counts as open.
        (clean(pl.col("closed_lost")).str.to_lowercase().eq("yes")
         & (_date("closed_at").is_null() | (_date("closed_at") <= cut))).fill_null(False).alias("closed"),
    )
    at = pl.lit(None, dtype=pl.Utf8)
    for name, _ in MILESTONES:
        at = pl.when(pl.col(name)).then(pl.lit(name)).otherwise(at)
    return a.with_columns(at.alias("at"))


def _same_time_counts(df: pl.DataFrame, years: tuple[int, int]) -> dict[tuple[str, int, str], int]:
    """("created" | "active" | "closed", year, stage) -> applications: created
    there by the date (closed or not), standing in it then and open, standing in
    it then and closed lost; ("active" | "closed", year, TOTAL) every stage together."""
    n: dict[tuple[str, int, str], int] = {}
    for y in years:
        d = df.filter(pl.col("year") == y)
        for kind, part in (("active", d.filter(~pl.col("closed"))), ("closed", d.filter(pl.col("closed")))):
            at = {r[0]: r[1] for r in part.group_by("at").len().iter_rows()}
            for name, _ in MILESTONES:
                n[(kind, y, name)] = at.get(name, 0)
            n[(kind, y, TOTAL)] = sum(at.get(name, 0) for name, _ in MILESTONES)
        for name, _ in MILESTONES:
            n[("created", y, name)] = int(d[name].sum())
    return n


def _rate(closed: int, created: int) -> float | str:
    return closed / created if created else ""


def _two_headers(w: Writer, lead: list[str], groups: list[tuple[str, list[str]]], height: float) -> None:
    """`lead` columns merged over both rows, then each group's name over its columns."""
    ws, h = w.ws, w.r
    for c, name in enumerate(lead, 1):
        ws.set(h, c, name, HDR)
        ws.set(h + 1, c, "", HDR)
        ws.merges.append(f"{L(c)}{h}:{L(c)}{h + 1}")
    c = len(lead) + 1
    for j, (name, subs) in enumerate(groups):
        st = HDR_ALT if j % 2 else HDR
        for k, sub in enumerate(subs):
            ws.set(h, c + k, name if k == 0 else "", st)
            ws.set(h + 1, c + k, sub, st)
        ws.merges.append(f"{L(c)}{h}:{L(c + len(subs) - 1)}{h}")
        c += len(subs)
    ws.heights[h + 1] = height
    w.r += 2


CREATED = "Created by the date (closed lost included)"
ACTIVE = "Active in the stage on the date"
LOST = "Closed lost in the stage by the date"
LOST_RATE = "Closed lost % of created"


def _same_time_rows(w: Writer, label: str, groups: list[tuple[str, pl.DataFrame]], p: Periods) -> None:
    """Per group: this year's applications created at each stage by the date,
    those standing in it then -- open, and closed lost -- and the closed lost
    share of those created there; last year's; and the change (% for counts,
    points for the closed lost share)."""
    ws, cy, ly = w.ws, p.cy, p.ly
    names = [m for m, _ in MILESTONES]
    _two_headers(w, [label, "Intake"], [(CREATED, names), (ACTIVE, names + ["Total open"]),
                                        (LOST, names + ["Total closed lost"]),
                                        (LOST_RATE, names + ["All applied"])], 30)
    cols = ([("created", m) for m in names] + [("active", m) for m in names + [TOTAL]]
            + [("closed", m) for m in names + [TOTAL]])
    c_created, c_closed, c_rate = 3, 3 + 15, 3 + 23      # first column of each block
    measure = Style(bold=True, border=True, wrap=True, valign="center")
    for name, df in groups:
        n = _same_time_counts(df, (cy, ly))
        first = w.r
        rates: dict[int, list[float | str]] = {}
        for y in (cy, ly):
            r = w.r
            ws.set(r, 2, f"{y} intake", _st())
            for j, (kind, st) in enumerate(cols):
                ws.set(r, 3 + j, n[(kind, y, st)], _st(INT, bold=st == TOTAL))
            # closed lost at the stage over created at it; overall, over everyone who applied
            rates[y] = []
            for j, st in enumerate(names + [TOTAL]):
                k = j if st != TOTAL else 0
                v = _rate(n[("closed", y, st)], n[("created", y, names[k])])
                K, X = ref(r, c_created + k), ref(r, c_closed + j)
                ws.set(r, c_rate + j, Formula(f'IF({K}=0,"",{X}/{K})', v), _st(SHARE, bold=st == TOTAL))
                rates[y].append(v)
            w.r += 1
        ws.set(w.r, 2, "Change", _st(total=True))
        for j, (kind, st) in enumerate(cols):
            cv, pv = n[(kind, cy, st)], n[(kind, ly, st)]
            C, P = ref(first, 3 + j), ref(first + 1, 3 + j)
            pct, sign = _pct(cv, pv), -1 if kind == "closed" else 1
            ws.set(w.r, 3 + j, Formula(f'IF({P}=0,"",({C}-{P})/{P})', pct),
                   _trend(PCT, sign * pct if pct != "" else pct, True))
        for j in range(len(names) + 1):
            cv, pv = rates[cy][j], rates[ly][j]
            d = cv - pv if "" not in (cv, pv) else ""
            C, P = ref(first, c_rate + j), ref(first + 1, c_rate + j)
            ws.set(w.r, c_rate + j, Formula(f'IF(OR({C}="",{P}=""),"",{C}-{P})', d), _trend(PCT, -(d or 0), True))   # more lost reads red
        w.r += 1
        ws.set(first, 1, name, measure)
        for r in range(first + 1, w.r):
            ws.set(r, 1, "", measure)
        ws.merges.append(f"A{first}:A{w.r - 1}")
    w.r += 1


def _same_time(ws: Sheet, applications: Export, p: Periods) -> None:
    """A time machine: the funnel for this intake year's applications as it
    stands today, against last year's on the same date a year ago. Per stage --
    applied, offered, deposit, CoE, visa applied, visa granted, enrolled -- how
    many had been created there by then, by the timestamp of each status, and
    how many stood in it then, not closed."""
    cy, ly = p.cy, p.ly
    cuts = {cy: p.today, ly: p.lytd[1]}
    cyh, lyh = f"{cy} intake\nby {cuts[cy]:%d %b %Y}", f"{ly} intake\nby {cuts[ly]:%d %b %Y}"
    df = _milestones(applications, p, cuts)
    names = [m for m, _ in MILESTONES]

    ws.set(1, 1, f"Sametime Last Year — the funnel on {cuts[cy]:%d %b %Y}, {cy} intake vs {ly} intake on "
                 f"{cuts[ly]:%d %b %Y}", H1)
    ws.set(2, 1, f"Source: applications, {_source_note(applications)}. A time machine: every {cy}-intake "
                 f"application as it stands today, against every {ly}-intake one as it stood on the same date a year "
                 "ago. Created = reached the stage by then: the export's \"Timestamp of ...\" for that status (Applied, "
                 "Offer, Deposit Fully Paid, COE Received, Visa| Applied, Visa| Granted, Enrolled) on or before the "
                 "date; a stage with no timestamp counts as passed when a later one was reached by then, so each stage "
                 "counts everyone who got that far. Active = standing in that stage on the date -- the furthest it had "
                 "reached -- and not closed by then: Closed Lost, marked closed (Timestamp of Application marked as "
                 "Closed) on or before the date -- with no timestamp, closed throughout; one reopened since counts as "
                 "open; the active stages add up to the applications open on the date. Closed lost in the stage = "
                 "closed by then while standing in it; closed lost % = that over those created at the stage (the "
                 "total, over everyone who applied); created counts the closed lost too. Deposits are by the date paid in full; later deferrals are not dated in the export, so "
                 "they do not move a deposit. Academic course levels, every business area but a blank one. Intake = "
                 "Actual Intake Year; quarters by Actual Intake Month.", NOTE_WRAP)
    ws.merges.append("A2:P2")
    ws.heights[2] = 104
    w = Writer(ws)

    n = _same_time_counts(df, (cy, ly))
    w.section("A. Funnel — full intake year, all business areas")
    blocks = [(CREATED, "created"), (ACTIVE, "active"), (LOST, "closed")]
    _two_headers(w, ["Stage"], [(g, [cyh, lyh, "Change", "% change"]) for g, _ in blocks]
                 + [(LOST_RATE, [cyh, lyh, "Change (pts)"])], 44)
    first = w.r
    for st in names + [TOTAL]:
        r, tr = w.r, st == TOTAL
        ws.set(r, 1, st, _st(total=tr))
        for b, (_, kind) in enumerate(blocks):
            c0 = 2 + 4 * b
            if tr and kind == "created":
                for c in range(c0, c0 + 4):
                    ws.set(r, c, "", _st(total=True))
                continue
            cv, pv = n[(kind, cy, st)], n[(kind, ly, st)]
            for c, v in ((c0, cv), (c0 + 1, pv)):
                ws.set(r, c, Formula(f"SUM({L(c)}{first}:{L(c)}{r - 1})", v) if tr else v, _st(INT, total=tr))
            C, P, pct, sign = ref(r, c0), ref(r, c0 + 1), _pct(cv, pv), -1 if kind == "closed" else 1
            ws.set(r, c0 + 2, Formula(f"{C}-{P}", cv - pv), _trend(DLT, sign * (cv - pv), tr))
            ws.set(r, c0 + 3, Formula(f'IF({P}=0,"",({C}-{P})/{P})', pct),
                   _trend(PCT, sign * pct if pct != "" else pct, tr))
        # closed lost at the stage over created at it; the total over everyone who applied
        kr, created = (first, names[0]) if tr else (r, st)
        v = {}
        for c, y, kc, xc in ((14, cy, 2, 10), (15, ly, 3, 11)):
            v[y] = _rate(n[("closed", y, st)], n[("created", y, created)])
            K, X = ref(kr, kc), ref(r, xc)
            ws.set(r, c, Formula(f'IF({K}=0,"",{X}/{K})', v[y]), _st(SHARE, total=tr))
        d = v[cy] - v[ly] if "" not in v.values() else ""
        ws.set(r, 16, Formula(f'IF(OR({ref(r, 14)}="",{ref(r, 15)}=""),"",{ref(r, 14)}-{ref(r, 15)})', d),
               _trend(PCT, -(d or 0), tr))
        w.r += 1
    last = w.r - 2
    w.r += 1
    for title, (c, l), at in ((f"Created by the date — {cy} vs {ly} intake", (2, 3), 1),
                              (f"Active in the stage on the date — {cy} vs {ly} intake", (6, 7), 6)):
        ws.charts.append(Chart(title, (first, last, 1), [(f"{cy} intake", c), (f"{ly} intake", l)],
                               at=(w.r, at), size=(18, 5 if at == 1 else 4)))
    w.r += 20

    w.section("B. By Actual Intake Quarter", "Quarters by Actual Intake Month; the full year leads.")
    groups = [("Full year", df)] + [(q, df.filter(pl.col("q") == k)) for k, q in enumerate(QUARTERS, 1)]
    _same_time_rows(w, "Period", groups, p)

    w.section("C. By Business Area", "Full intake year.")
    areas = df.group_by("area").len().sort(["len", "area"], descending=[True, False])["area"].to_list()
    _same_time_rows(w, "Business area", [(a, df.filter(pl.col("area") == a)) for a in areas], p)

    ws.widths.update({1: 24, 2: 14, **{c: 12 for c in range(3, 34)}})
    ws.freeze = "A3"


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
                 "the application has an introducer, an Academic course level and Business Area "
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
    w.section("D1. Deposits fully paid by Business Region")
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
                 f"{non_acad.get(cy, 0)}, {ly} {non_acad.get(ly, 0)}. Business Area B2B only; "
                 f"Academic active deposits on other business areas left out: {cy} {non_b2b.get(cy, 0)}, "
                 f"{ly} {non_b2b.get(ly, 0)}. Every table from A2 on counts active "
                 "deposits only. Introducers = the introducers with at least one of a row's deposits; one in "
                 "several rows counts in each, and once in the total, so a total can be less than its rows' sum. "
                 f"The {cy} intake year is still in progress.", NOTE_WRAP)
    ws.merges.append("A2:G2")
    ws.heights[2] = 120
    cyh, lyh = f"{cy} intake", f"{ly} intake"
    w = Writer(ws)

    w.section(f"A. Deposits by introducers: {cy} vs {ly}")
    states = (("Active", "Active deposits"), ("DAA", "DAA — deferral awaiting approval"),
              ("PD", "PD — partial deposits"))
    state_of = {label: st for st, label in states}
    w.compare(["Deposits"], [((label,), n(st, cy)[0], n(st, ly)[0]) for st, label in states], cyh, lyh,
              total=False, intros=lambda labels: (n(state_of[labels[0]], cy)[1], n(state_of[labels[0]], ly)[1]))
    w.section("A1. By Actual Intake Quarter", "Quarters by Actual Intake Month.")
    pairs = [(y, st) for y in (cy, ly) for st in ("Active", "DAA", "PD")]
    present = set(held["q"].to_list())
    w.grid(["Actual Intake Quarter"],
           [((QUARTERS[q - 1] if q else "No intake month",), [x for y, st in pairs for x in n(st, y, q)])
            for q in (1, 2, 3, 4, 0) if q in present],
           [h for y, st in pairs for h in (f"{y} {st}", f"{y} {st} introducers")],
           given={2 * j + 1: n(st, y)[1] for j, (y, st) in enumerate(pairs)})
    w.section("A2. Active deposits by the year the introducer was onboarded (Became Customer Date)")
    cohorts = [((o,), cur.filter(pl.col("cohort") == o).height, prev.filter(pl.col("cohort") == o).height)
               for o in _cohorts(p)]
    w.compare(["Introducer onboarded in"], [c for c in cohorts if c[1] or c[2]], cyh, lyh,
              intros=lambda labels: (_introducers(cur, ["cohort"])(labels), _introducers(prev, ["cohort"])(labels)))

    w.section(f"B. {cy} active deposits broken down",
              "SRM and AMT counsellor are the Introducer SRM / AMT columns on the application; business team "
              "is its CurrentlyAssignedToBusinessTeam and business region its Business Region. "
              "Country is the introducer's country on the master file; destination country is the "
              "application's Application Destination Country.")
    value_h = f"{cy} active deposits"
    for title, labels, keys in (("B1. By introducer country", ["Country"], ["country"]),
                                ("B2. By application destination country", ["Application Destination Country"],
                                 ["destination"]),
                                ("B3. By business region", ["Business region"], ["region"]),
                                ("B4. By SRM", ["SRM", "Business team"], ["srm", "team"]),
                                ("B5. By business team", ["Business team"], ["team"]),
                                ("B6. By AMT counsellor", ["AMT counsellor"], ["amt"]),
                                ("B7. By institution", ["Institution"], ["institution"])):
        w.section(title)
        w.share(labels, _counts(cur, keys), value_h, nest="teams" if keys == ["srm", "team"] else None,
                intros=_introducers(cur, keys))

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
    ws.widths.update(dict(enumerate([46, 28, 24, 26, 20, 16, 16, 14, 14, 14, 14, 14, 14], 1)))
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
