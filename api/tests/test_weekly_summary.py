"""This week's summary, on exports small enough to count by hand.

The rules worth pinning are the ones a reader would argue about: where the
Saturday-to-Friday week starts, which deposits are active, and who counts as
resurrected or missed out.
"""
import io
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime

sys.path.insert(0, "/srv/api")

from app.reports.weekly_summary import Periods, Writer, build, read_export  # noqa: E402
from app.reports.xlsx import Chart, Formula, Workbook, col_letter  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
WHEN = datetime(2026, 10, 6, 9, 0)
TODAY = date(2026, 10, 6)         # a Tuesday: this week is Sat 3 Oct - Fri 9 Oct


def csv(*rows: str) -> bytes:
    return "\n".join(rows).encode() + b"\n"


INTRODUCERS = csv(
    "Partner Name,Country,Partner Managed By Team(SRM),Partner Managed By User(SRM),Became Customer Date,_id,BusinessTeam,BusinessRegion",
    "Alpha,India,South Desk,Asha,2026-10-03 00:00:00,a1,South B2B,Asia",      # this week (the Saturday)
    "Beta,Nigeria,West Desk,Bola,2026-10-02 00:00:00,b1,West B2B,Africa",      # last week (the Friday)
    "Gamma,India,South Desk,Asha,2025-03-01 00:00:00,c1,South B2B,Asia",      # same period last year
    "Delta,Kenya,East Desk,Dan,2023-05-01 00:00:00,d1,East B2B,Africa",
    "Eta,Ghana,West Desk,Bola,,e1,West B2B,Africa",                            # no Became Customer Date
)
LOGS = csv(
    "Introducers Name,Log Type,Log Time,Managed By Team,Created By,_id",
    "Alpha,F2FVisits,Sat Oct 03 2026 10:00:00 GMT+0000 (Coordinated Universal Time),South Desk,Asha,l1",
    "Alpha,Call,Fri Oct 02 2026 23:30:00 GMT+0000 (Coordinated Universal Time),South Desk,Asha,l2",
    # 01:00 on the 3rd in India is still the 2nd in UTC: last week
    "Beta,Email,Sat Oct 03 2026 01:00:00 GMT+0530 (India Standard Time),West Desk,Bola,l3",
    "Beta,Email,Sat Oct 03 2026 01:00:00 GMT+0530 (India Standard Time),West Desk,Bola,l3",   # same log twice
)
APPLICATIONS = csv(
    "Application Introducer Name,Application Introducer Id,Deposit Paid Status,Application Closed Lost,"
    "Deferred Initiated (No/Yes/All),Deferred Approved (No/Yes/All),Application Course Level,Actual Intake Year,"
    "Actual Intake Month,Introducer SRM User Name,CurrentlyAssignedToBusinessTeam,Introducer AMT User Name,Institution Name,"
    "StudentAssignedToBusinessArea,Application Ref No,Timestamp of ‚Äò Deposit Fully Paid‚Äô status,StudentAssignedToBusinessRegion,Application Destination Country,Student Nationality,Application Status,Application Sub-Status",
    "Delta,d1,FullyPaid,No,No,No,Postgraduate,2026,September,Dan,East,Amy,Uni A,B2B,A-01,2026-09-28 00:00:00,Africa,Canada,Kenya,Visa,Granted",         # Delta: 2026 only -> resurrected
    "Delta,d1,FullyPaid,No,Yes,Yes,Undergraduate,2026,January,Dan,East,Amy,Uni B,B2B,A-02,2026-10-03 00:00:00,Africa,United Kingdom,Kenya,Enrolled,Letter Received",        # deferred and approved: active
    "Gamma,c1,FullyPaid,No,No,No,Postgraduate,2025,September,Asha,South,Amy,Uni A,B2B,A-03,,Asia,United Kingdom,India,Enrolled,",       # Gamma: 2025 only -> missed out
    "Gamma,c1,FullyPaid,No,Yes,No,Postgraduate,2026,September,Asha,South,Amy,Uni A,B2B,A-04,2026-10-02 00:00:00,Asia,United Kingdom,India,Applied,",      # deferral pending: DAA
    "Gamma,c1,FullyPaid,Yes,No,No,Postgraduate,2026,September,Asha,South,Amy,Uni A,B2B,A-05,2026-09-30 00:00:00,Asia,United Kingdom,India,Visa,Deferral In Progress",      # closed lost: nothing
    "Gamma,c1,FullyPaid,No,No,No,Language,2026,September,Asha,South,Amy,Uni A,B2B,A-06,2026-09-29 00:00:00,Asia,United Kingdom,India,Applied,",           # not Academic
    "Delta,d1,FullyPaid,No,No,No,PresessionalEnglish,2026,September,Dan,East,Amy,Uni A,B2B,A-07,,Africa,United Kingdom,India,Applied,",  # not Academic
    "Delta,d1,FullyPaid,No,No,No,,2026,September,Dan,East,Amy,Uni A,B2B,A-08,,Africa,United Kingdom,India,Applied,",                     # no course level: out
    "Delta,d1,FullyPaid,No,No,No,September,2026,September,Dan,East,Amy,Uni A,B2B,A-09,,Africa,United Kingdom,India,Applied,",            # a stray value: out
    "Zeta,,FullyPaid,No,No,No,GCSEgradesAC,2026,May,Zed,North,Amy,Uni C,B2B,A-10,,Asia,United Kingdom,India,Offered,Conditional Offer",                 # a listed level: in
    "Alpha,a1,FullyPaid,No,No,No,Postgraduate,2026,September,Asha,South,Amy,Uni C,B2B,A-11,2026-09-20 00:00:00,Asia,United Kingdom,India,Visa,Applied",       # onboarded 2026: not resurrected
    "Alpha,a1,fullyPaidWaitingForApproval,No,No,No,Postgraduate,2026,January,Asha,South,Amy,Uni C,B2B,A-12,,Asia,United Kingdom,India,CoE Received,",  # paid in full: active
    "Beta,b1,FullyPaid,No,No,Yes,Postgraduate,2026,January,Bola,West,Amy,Uni C,B2B,A-13,,Africa,United Kingdom,India,Applied,",          # columns differ: DAA
    "Beta,b1,PartiallyPaid,No,No,No,Postgraduate,2025,September,Bola,West,Amy,Uni C,B2B,A-14,,Africa,United Kingdom,India,Applied,",     # PD
    "Beta,b1,PartiallyPaid,Yes,No,No,Postgraduate,2025,September,Bola,West,Amy,Uni C,B2B,A-15,,Africa,United Kingdom,India,Applied,",    # closed lost: not PD
    ",d1,PartiallyPaid,No,Yes,Yes,Postgraduate,2026,September,Dan,East,Amy,Uni A,B2B,A-16,,Africa,United Kingdom,India,Applied,",        # no name, Delta's id: PD
    ",,PartiallyPaid,No,No,No,Postgraduate,2026,September,Dan,East,Amy,Uni A,B2B,A-17,,Africa,United Kingdom,India,Applied,",            # no introducer at all: out
    "Beta,b1,NotPaid,No,No,No,Postgraduate,2026,September,Bola,West,Amy,Uni C,B2B,A-18,2026-09-21 00:00:00,Africa,United Kingdom,India,Applied,",           # nothing, though paid in the week before once
    "Zeta,,FullyPaid,No,No,No,Postgraduate,2026,May,Zed,North,Amy,Uni C,B2B,A-19,,Asia,United Kingdom,India,Offered,Unconditional Offer",                 # no id, not in master
    " eta ,,FullyPaid,No,No,No,Postgraduate,2025,May,Bola,West,Amy,Uni C,B2B,A-22,,Africa,United Kingdom,India,Visa,Granted",              # no id: Eta's by name
    "Alpha,a1,FullyPaid,No,No,No,Postgraduate,2026,September,Asha,South,Amy,Uni C,B2C,A-20,2026-09-22 00:00:00,Asia,United Kingdom,China,Enrolled,",   # not B2B: out
    "Alpha,a1,FullyPaid,No,No,No,Postgraduate,2026,September,Asha,South,Amy,Uni C,,A-21,,Asia,United Kingdom,India,Applied,",      # no business area: out
    "Alpha,a1,FullyPaid,No,No,No,Postgraduate,2027,January,Asha,South,Amy,Uni C,B2B,A-23,,Asia,Ireland,India,Applied,",     # next year's intake: its own sheet
)

# When each stage was reached, by Application Ref No: Applied, Offer, COE Received,
# Visa| Applied, Visa| Granted, Enrolled, then when it was marked closed. As
# exported: with mangled quotes, among look-alikes (Ready to Apply, the bare
# VISA) that are not stages here. Deposits are dated by the paid-in-full column.
STAGE_HEADS = ["Timestamp of ‚ÄòReady to Apply‚Äô status", "Timestamp of ‚ÄòVisa| Applied‚Äô status",
               "Timestamp of ‚ÄòApplied‚Äô status", "Timestamp of ‚ÄòOffer‚Äô status",
               "Timestamp of ‚ÄòCOE Received‚Äô status", "Timestamp of ‚ÄòVISA‚Äô status",
               "Timestamp of ‚ÄòVisa| Granted‚Äô status", "Timestamp of ‚ÄòEnrolled‚Äô status",
               "Timestamp of Application marked as Closed", "Application Closure Reason"]
STAGE_TIMES = {   # applied, offer, coe, visa applied, visa granted, enrolled, closed
    "A-01": ("2026-05-01", "2026-06-01", "2026-09-30", "2026-10-01", "2026-10-05", "", ""),
    "A-02": ("2025-09-01", "2025-10-01", "2025-11-01", "2025-11-15", "2025-12-01", "2026-01-20", ""),
    "A-05": ("", "", "", "", "", "", "2026-10-01"),                          # paid, then closed
    "A-10": ("2026-03-01", "2026-04-01", "", "", "", "", ""),               # no deposit timestamp
    "A-11": ("2026-08-01", "2026-09-01", "2026-09-25", "2026-10-02", "", "", ""),
    "A-12": ("", "", "2026-09-01", "", "", "", ""),                         # CoE implies the stages before it
    "A-13": ("2026-09-15", "", "", "", "", "", "2026-08-01"),               # closed once, reopened: open
    "A-20": ("2026-07-01", "2026-08-01", "", "", "", "2026-10-07", ""),     # enrolled after the date
    "A-03": ("2024-11-01", "2025-01-10", "2025-05-01", "2025-06-01", "2025-07-01", "2025-09-15", ""),
    "A-14": ("2025-04-01", "2025-05-01", "", "", "", "", ""),
    "A-15": ("2025-02-01", "", "", "", "", "", "2025-11-01"),               # closed after the date: open then
    "A-22": ("2025-03-01", "2025-09-01", "2025-10-20", "2025-11-01", "2025-12-01", "2026-05-01", ""),  # CoE after the date
}
CLOSURE_REASONS = {"A-05": "Plan Dropped", "A-15": "Withdrawn by Student"}


def _with_stages(content: bytes) -> bytes:
    head, *rows = content.decode().splitlines()
    out = [head + "," + ",".join(STAGE_HEADS)]
    for row in rows:
        no = row.split(",")[14]
        t = STAGE_TIMES.get(no, ("",) * 7)
        a, o, c, va, vg, e, cl = (f"{x} 00:00:00" if x else "" for x in t)
        out.append(row + "," + ",".join(["", va, a, o, c, "", vg, e, cl, CLOSURE_REASONS.get(no, "")]))
    return ("\n".join(out) + "\n").encode()


APPLICATIONS = _with_stages(APPLICATIONS)


def workbook(periods: Periods = Periods(TODAY)) -> dict[str, dict[str, object]]:
    content = build(
        read_export("introducers", "i.csv", INTRODUCERS, WHEN),
        read_export("introducer_logs", "l.csv", LOGS, WHEN),
        read_export("applications", "a.csv", APPLICATIONS, WHEN),
        periods,
    )
    z = zipfile.ZipFile(io.BytesIO(content))
    names = [s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{{{NS['m']}}}sheet")]
    out = {}
    for i, name in enumerate(names, 1):
        cells = {}
        for c in ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml")).iter(f"{{{NS['m']}}}c"):
            t = c.find("m:is", NS)        # plain, or rich text's runs read as one
            v = c.find("m:v", NS)
            cells[c.get("r")] = "".join(x.text or "" for x in t.iter(f"{{{NS['m']}}}t")) if t is not None else (float(v.text) if v is not None and v.text and c.get("t") != "str" else (v.text if v is not None else None))
        out[name] = cells
    return out


def row_after(cells: dict[str, object], label: str, occurrence: int = 1, width: int = 6) -> list[object]:
    """The `width` values to the right of the n-th cell in column A reading `label`."""
    rows = sorted((int(k[1:]) for k, v in cells.items() if k.startswith("A") and k[1:].isdigit() and v == label))
    r = rows[occurrence - 1]
    return [cells.get(f"{col_letter(c)}{r}") for c in range(2, 2 + width)]


def test_week_runs_saturday_to_friday():
    assert Periods(date(2026, 10, 6)).week == (date(2026, 10, 3), date(2026, 10, 9))
    assert Periods(date(2026, 10, 3)).week == (date(2026, 10, 3), date(2026, 10, 9))     # Saturday starts it
    assert Periods(date(2026, 10, 9)).week == (date(2026, 10, 3), date(2026, 10, 9))     # Friday ends it
    assert Periods(date(2026, 10, 6)).last_week == (date(2026, 9, 26), date(2026, 10, 2))
    assert Periods(date(2028, 2, 29)).lytd == (date(2027, 1, 1), date(2027, 2, 28))


def test_last_week_sheet_compares_last_week_with_the_week_before():
    p = Periods.last_week_of(date(2026, 10, 6))
    assert p.today == date(2026, 10, 2)
    assert p.week == (date(2026, 9, 26), date(2026, 10, 2))
    assert p.last_week == (date(2026, 9, 19), date(2026, 9, 25))
    assert Periods.last_week_of(date(2026, 10, 3)).today == date(2026, 10, 2)    # on a Saturday, too
    s = workbook()["B2B Summary Last Week"]
    assert row_after(s, "Introducers onboarded")[:2] == [1, 0]     # Beta; none
    assert row_after(s, "Activity logs")[:2] == [2, 0]             # Alpha's call, Beta's email
    # Delta's (active) and Gamma's (DAA) last week; Alpha's the week before. Not
    # Gamma's closed-lost one, Beta's no longer paid, the Language or B2C ones,
    # nor Delta's paid this week.
    assert row_after(s, "Deposits fully paid")[:2] == [2, 1]
    assert row_after(s, "Active deposit")[:2] == [1, 1]
    assert row_after(s, "DAA — deferral awaiting approval")[:2] == [1, 0]
    assert row_after(s, "September 2026")[:2] == [2, 1]
    assert "A-01" not in s.values()                                   # no list of the deposits
    assert not any(k.startswith("A") and v == "A-11" for k, v in s.items())    # the week before: not listed
    assert any(isinstance(v, str) and "2 paid in these two weeks did" in v for v in s.values())
    heads = [v for v in s.values() if isinstance(v, str)]
    assert "Last week\n26 Sep – 02 Oct" in heads and "Week before\n19 Sep – 25 Sep" in heads


def ytd_row(cells: dict[str, object], measure: str, label: str) -> list[object]:
    """On the YTD sheet: the full year (this year, last, change, % change), then
    each quarter (this year, last, % change), of `label`'s row in `measure`'s block."""
    rows = sorted(int(k[1:]) for k in cells if k[1:].isdigit())
    starts = [r for r in rows if cells.get(f"A{r}") == measure]
    r = next(r for r in rows if r >= starts[0] and cells.get(f"B{r}") == label)
    return [cells.get(f"{col_letter(c)}{r}") for c in range(3, 19)]


def test_ytd_comes_first_with_its_charts():
    content = build(
        read_export("introducers", "i.csv", INTRODUCERS, WHEN),
        read_export("introducer_logs", "l.csv", LOGS, WHEN),
        read_export("applications", "a.csv", APPLICATIONS, WHEN),
        Periods(TODAY),
    )
    z = zipfile.ZipFile(io.BytesIO(content))
    for name in z.namelist():
        ET.fromstring(z.read(name))                                # every part is well-formed XML
    names = [s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{{{NS['m']}}}sheet")]
    assert names == ["YTD - Academic", "YTD - Language", "2027 sales sheet", "Deposit funnel movement",
                     "Sametime Last Year", "Closed Lost Deposits", "B2B - Onboarding", "B2B - Activity Logs",
                     "B2B - Sales and Retention", "B2B Summary Last Week"]
    # the four B2B sheets, and only those, carry the group's tab colour
    tabs = [(el := ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml")).find("m:sheetPr/m:tabColor", NS))
            is not None and el.get("rgb") for i in range(1, len(names) + 1)]
    assert tabs == [False] * 6 + ["FF9B77D2"] * 4
    charts = sorted(n for n in z.namelist() if n.startswith("xl/charts/"))
    # on YTD: the headline, the areas, each area's regions (B2B, B2C),
    # destinations, nationalities; five on the Language sheet (B2B alone); the
    # same six on the 2027 sheet; the funnel's, Sametime Last Year's; then one on Last week
    assert len(charts) == 21
    assert "xl/drawings/drawing1.xml" in z.namelist() and "xl/worksheets/_rels/sheet1.xml.rels" in z.namelist()
    assert "'YTD - Academic'!$A$" in z.read("xl/charts/chart1.xml").decode()
    # nothing to the right of the quarters: the per-quarter side table is gone
    refs = [c.get("r") for c in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(f"{{{NS['m']}}}c")]
    assert not [r for r in refs if r.rstrip("0123456789") in ("T", "U", "V")]
    # growth in subtle green, decline in red
    styles = z.read("xl/styles.xml").decode()
    assert "38761D" in styles and "C00000" in styles
    assert "2F5597" in styles                                      # alternate column groups shade the header


def test_ytd_counts_every_business_area_by_quarter():
    s = workbook()["YTD - Academic"]
    # Every area, introducer or not: A-17 (no introducer) and A-20 (B2C) count;
    # A-21 (no area), the closed-lost and the non-Academic ones do not.
    # Deposits 2026: Jan A-02 A-12, May A-10 A-19, Sep A-01 A-11 A-20; 2025: May A-22, Sep A-03
    assert ytd_row(s, "Deposits", "All business areas") == [7, 2, 5, 2.5, 2, 0, None, 2, 1, 1, 3, 1, 2, 0, 0, None]
    assert ytd_row(s, "PD", "All business areas")[:4] == [2, 1, 1, 1]       # A-16, A-17; A-14
    assert ytd_row(s, "DAA", "All business areas")[:4] == [2, 0, 2, None]   # A-04, A-13
    assert ytd_row(s, "Deposits", "B2B")[:2] == [6, 2]
    assert ytd_row(s, "Deposits", "B2C")[:2] == [1, 0]
    assert ytd_row(s, "Deposits", "Total")[:2] == [7, 2]
    assert "(blank)" not in s.values()                              # A-21's blank area is no row
    # each area by StudentAssignedToBusinessRegion, B2B's first
    assert ytd_row(s, "Deposits", "Asia")[:2] == [4, 1]
    assert ytd_row(s, "Deposits", "Africa")[:2] == [2, 1]
    assert any(v == "C2. B2C — by Business Region" for v in s.values())
    # Delta's A-01 is Canada, the rest the UK; A-01 and A-02 are Kenyan, A-20 Chinese, the rest Indian
    assert ytd_row(s, "Deposits", "United Kingdom")[:2] == [6, 2]
    assert ytd_row(s, "Deposits", "Canada")[:2] == [1, 0]
    assert ytd_row(s, "Deposits", "India")[:2] == [4, 2]
    assert ytd_row(s, "Deposits", "Kenya")[:2] == [2, 0]
    assert ytd_row(s, "Deposits", "China")[:2] == [1, 0]
    # a row with nothing this year or last is left out, though other measures have it
    rows = {int(k[1:]) for k in s if k[1:].isdigit()}
    blank = [r for r in rows if isinstance(s.get(f"C{r}"), int) and not s.get(f"C{r}") and not s.get(f"D{r}")]
    assert blank == []


def test_language_sheet_counts_the_language_and_presessional_levels_alone():
    s = workbook()["YTD - Language"]
    assert s["A1"] == "Year to date summary, Language and Pre-sessional — deposits, PD and DAA, 2026 intake vs 2025 intake"
    # A-06 (Language, Asia) and A-07 (PresessionalEnglish, Africa), both September 2026
    assert ytd_row(s, "Deposits", "All business areas") == [2, 0, 2, None, 0, 0, None, 0, 0, None, 2, 0, None, 0, 0, None]
    assert ytd_row(s, "Deposits", "B2B")[:2] == [2, 0]
    assert ytd_row(s, "Deposits", "Asia")[:2] == [1, 0]
    assert ytd_row(s, "Deposits", "Africa")[:2] == [1, 0]
    assert "B2C" not in s.values()                                  # no Academic application here
    # each row opens onto its two course levels
    assert ytd_row(s, "Deposits", "Language")[:2] == [1, 0]
    assert ytd_row(s, "Deposits", "Pre-sessional")[:2] == [1, 0]
    assert "Language" not in workbook()["YTD - Academic"].values()


def test_next_years_sales_sheet_sets_its_intake_against_this_years():
    s = workbook()["2027 sales sheet"]
    assert s["A1"] == "2027 sales — deposits, PD and DAA, 2027 intake vs 2026 intake"
    # A-23 alone for 2027, in Q1; this year's seven deposits as the year before
    assert ytd_row(s, "Deposits", "All business areas")[:4] == [1, 7, -6, -6 / 7]
    assert ytd_row(s, "Deposits", "All business areas")[4:6] == [1, 2]
    assert ytd_row(s, "Deposits", "Ireland")[:2] == [1, 0]
    assert ytd_row(s, "PD", "All business areas")[:2] == [0, 2]
    # 2027 is out of every other sheet
    assert "Ireland" not in workbook()["YTD - Academic"].values()


def test_deposit_funnel_counts_each_active_deposit_at_its_stage_now():
    s = workbook()["Deposit funnel movement"]
    # 2026: A-10 A-19 offered, A-12 CoE, A-11 visa applied, A-01 granted, A-02 A-20 enrolled; 2025: A-22 granted, A-03 enrolled
    assert row_after(s, "Offered")[:2] == [2, 0]
    assert row_after(s, "CoE Received")[:2] == [1, 0]
    assert row_after(s, "Visa Applied")[:2] == [1, 0]
    assert row_after(s, "Visa Granted")[:2] == [1, 1]
    assert row_after(s, "Enrolled")[:6] == [2, 1, 1, 1.0, 2 / 7, 0.5]
    assert row_after(s, "Total active deposits")[:2] == [7, 2]
    assert "Other" not in s.values()                                # every deposit is at one of the five
    # by quarter and area: the year's row, total first, then the five stages
    def block(name: str) -> list[object]:
        r = next(int(k[1:]) for k, v in s.items() if k[:1] == "A" and v == name)
        return [s.get(f"{col_letter(c)}{r}") for c in range(2, 9)]
    assert block("Full year") == ["2026 intake", 7, 2, 1, 1, 1, 2]
    assert block("Q1 (Jan–Mar)") == ["2026 intake", 2, 0, 1, 0, 0, 1]   # A-12 CoE, A-02 enrolled
    assert block("Q2 (Apr–Jun)") == ["2026 intake", 2, 2, 0, 0, 0, 0]   # A-10, A-19 offered
    assert block("B2C") == ["2026 intake", 1, 0, 0, 0, 0, 1]            # A-20


def test_sametime_last_year_sets_the_funnel_today_against_the_same_date_last_year():
    s = workbook()["Sametime Last Year"]
    assert s["A1"] == "Sametime Last Year — the funnel on 06 Oct 2026, 2026 intake vs 2025 intake on 06 Oct 2025"
    assert {"2026 intake\nby 06 Oct 2026", "2025 intake\nby 06 Oct 2025"} <= set(s.values())
    # Every application, deposit or not. 2026 by 06 Oct 2026: A-01 at visa granted,
    # A-02 enrolled, A-10 offered, A-11 visa applied, A-12 CoE (so applied,
    # offered, paid too), A-13 applied (reopened: open), paid in full A-04, A-18,
    # A-20 (enrolled the day after) and A-05 (closed since); A-16, A-17, A-19
    # nowhere yet. 2025 by 06 Oct 2025: A-03 enrolled, A-14 and A-22 offered (A-22's
    # CoE came later), A-15 applied (closed only after the date).
    # Created then, change, %; active then, change, %
    assert row_after(s, "Applied", width=8) == [10, 4, 6, 1.5, 1, 1, 0, 0.0]
    assert row_after(s, "Offered", width=8) == [9, 3, 6, 2.0, 1, 2, -1, -0.5]
    assert row_after(s, "Deposit", width=6)[:5] == [8, 1, 7, 7.0, 3]
    assert row_after(s, "CoE Received", width=5)[:2] == [4, 1]
    assert row_after(s, "Visa Applied", width=5)[:2] == [3, 1]
    assert row_after(s, "Visa Granted", width=5)[:2] == [2, 1]
    assert row_after(s, "Enrolled", width=8) == [1, 1, 0, 0.0, 1, 1, 0, 0.0]
    assert row_after(s, "Total on the date", width=8)[4:] == [9, 4, 5, 1.25]
    # closed lost in the stage by the date, then its share of those created there:
    # A-05 paid, closed 01 Oct 2026; A-15 closed only after 06 Oct 2025, open then
    assert row_after(s, "Deposit", width=15)[8:] == [1, 0, 1, None, 0.125, 0.0, 0.125]
    assert row_after(s, "Applied", width=15)[8:11] == [0, 0, 0]
    assert row_after(s, "Total on the date", width=15)[8:] == [1, 0, 1, None, 0.1, 0.0, 0.1]  # over all applied
    # by quarter and area: created at each stage, then active in each, then open
    def block(name: str, nxt: int = 0) -> list[object]:
        r = next(int(k[1:]) for k, v in s.items() if k[:1] == "A" and v == name) + nxt
        return [s.get(f"{col_letter(c)}{r}") for c in range(2, 34)]
    assert block("Full year") == ["2026 intake", 10, 9, 8, 4, 3, 2, 1, 1, 1, 3, 1, 1, 1, 1, 9,
                                  0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0.125, 0, 0, 0, 0, 0.1]
    assert block("Full year", 1) == ["2025 intake", 4, 3, 1, 1, 1, 1, 1, 1, 2, 0, 0, 0, 0, 1, 4] + [0] * 16
    assert block("Q3 (Jul–Sep)", 1)[:16] == ["2025 intake", 3, 2, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 3]
    assert block("B2C")[:16] == ["2026 intake", 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]   # A-20


def test_closed_lost_sheet_counts_this_years_deposits_by_the_stage_they_were_closed_in():
    s = workbook()["Closed Lost Deposits"]
    assert s["A1"] == "Closed lost deposits — Deposits, PD and DAA closed lost, 2026 intake"
    # 2026 paid in full: A-01 A-02 A-10 A-11 A-12 A-19 A-20 active, A-05 closed lost;
    # created, active, closed lost, closed lost %
    assert ytd_row(s, "Deposits", "All business areas")[:4] == [8, 7, 1, 0.125]
    assert ytd_row(s, "DAA", "All business areas")[:4] == [2, 2, 0, 0]          # A-04, A-13
    assert ytd_row(s, "PD", "All business areas")[:4] == [2, 2, 0, 0]           # A-16, A-17
    # expanded, by stage: A-05's visa had a deferral in progress, never granted
    assert ytd_row(s, "Deposits", "Offered")[:4] == [2, 2, 0, 0]                # A-10, A-19
    assert ytd_row(s, "Deposits", "Visa Applied")[:4] == [2, 1, 1, 0.5]         # A-11; A-05
    assert ytd_row(s, "Deposits", "Enrolled")[:4] == [2, 2, 0, 0]               # A-02, A-20
    assert "2025 intake" not in s.values()                          # this intake year alone
    # by introducer and institution, the most closed lost first
    # the introducer's business team and SRM on a line under its name, in smaller grey type
    assert ytd_row(s, "Deposits", "Gamma\nSouth · Asha")[:4] == [1, 0, 1, 1.0]
    assert ytd_row(s, "Deposits", "Uni A")[:4] == [2, 1, 1, 0.5]                # A-01; A-05
    assert any(v == "G. By institution" for v in s.values())
    # then each quarter by Actual Intake Month: Q3 holds A-01, A-05, A-11, A-20
    assert ytd_row(s, "Deposits", "All business areas")[12:16] == [4, 3, 1, 0.25]
    assert ytd_row(s, "Deposits", "All business areas")[4:8] == [2, 2, 0, 0]   # Q1: A-02, A-12
    # by closure reason, the closed lost alone, and their share of the measure's
    assert ytd_row(s, "Deposits", "Plan Dropped")[:2] == [1, 1.0]
    assert "Withdrawn by Student" not in s.values()                 # A-15: last year's intake


def test_closed_lost_rates_read_green_amber_red():
    content = build(
        read_export("introducers", "i.csv", INTRODUCERS, WHEN),
        read_export("introducer_logs", "l.csv", LOGS, WHEN),
        read_export("applications", "a.csv", APPLICATIONS, WHEN),
        Periods(TODAY),
    )
    z = zipfile.ZipFile(io.BytesIO(content))
    names = [s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{{{NS['m']}}}sheet")]
    sheet = ET.fromstring(z.read(f"xl/worksheets/sheet{names.index('Closed Lost Deposits') + 1}.xml"))
    styles = ET.fromstring(z.read("xl/styles.xml"))
    fonts = list(styles.find("m:fonts", NS))
    xfs = list(styles.find("m:cellXfs", NS))
    cells = {c.get("r"): c for c in sheet.iter(f"{{{NS['m']}}}c")}

    def colour(r: str) -> str | None:
        font = fonts[int(xfs[int(cells[r].get("s"))].get("fontId"))]
        return font.find("m:color", NS).get("rgb")

    rows = {c.get("r")[1:] for c in cells.values() if c.get("r").startswith("B")
            and c.find("m:is", NS) is not None and "".join(c.find("m:is", NS).itertext()) == "All business areas"}
    first = min(rows, key=int)                       # the Deposits headline: 12.5%, 25% in Q3
    assert colour(f"F{first}") == "FF38761D" and colour(f"R{first}") == "FFBF8F00"
    gamma = next(c for c in cells.values() if c.find("m:is/m:r", NS) is not None)   # Gamma: 100% lost
    assert colour(f"F{gamma.get('r')[1:]}") == "FFC00000"
    reason = next(c.get("r")[1:] for c in cells.values() if c.get("r").startswith("B")
                  and "".join(c.itertext()) == "Plan Dropped")
    assert colour(f"D{reason}") == "FFC00000"                    # all of the Deposits' closed lost
    runs = gamma.findall("m:is/m:r", NS)
    assert [r.find("m:rPr/m:sz", NS).get("val") for r in runs] == ["10", "8"]


def test_onboarding_counts():
    s = workbook()["B2B - Onboarding"]
    assert row_after(s, "All introducers", 1)[:2] == [2, 1]        # YTD: Alpha, Beta; last year: Gamma
    assert row_after(s, "All introducers", 2)[:2] == [1, 1]        # this week Alpha; last week Beta


def test_activity_dates_in_utc_and_drops_repeated_ids():
    s = workbook()["B2B - Activity Logs"]
    assert row_after(s, "Total logs")[:2] == [1, 2]
    assert row_after(s, "Face to face")[:2] == [1, 0]
    assert row_after(s, "Email")[:2] == [0, 1]
    # Managed By Team "South Desk" reads as the business team the master pairs with it
    assert row_after(s, "South B2B")[:2] == [1, 1]
    assert row_after(s, "West B2B")[:2] == [0, 1]
    assert "South Desk" not in s.values()
    assert row_after(s, "Asia")[:2] == [1, 1]
    assert row_after(s, "Africa")[:2] == [0, 1]


def test_active_daa_and_pd_deposits():
    s = workbook()["B2B - Sales and Retention"]
    assert row_after(s, "Active deposits")[:2] == [6, 2]           # Delta x2, Alpha x2, Zeta x2; Gamma, Eta
    assert row_after(s, "DAA — deferral awaiting approval")[:2] == [2, 0]   # Gamma Yes/No, Beta No/Yes
    assert row_after(s, "PD — partial deposits")[:2] == [1, 1]     # Delta by id alone; Beta 2025, not the closed-lost one
    # the introducers behind them, this year and last: Delta, Alpha, Zeta; Gamma, Eta
    assert row_after(s, "Active deposits")[-2:] == [3, 2]
    # 2026 Active, DAA, PD, then 2025 Active, DAA, PD -- each deposits, then introducers
    assert row_after(s, "Q1 (Jan–Mar)", width=12) == [2, 2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    assert row_after(s, "Q2 (Apr–Jun)", width=12) == [2, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0]   # Zeta twice
    assert row_after(s, "Q3 (Jul–Sep)", width=12) == [2, 2, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1]
    assert "Q4 (Oct–Dec)" not in s.values()
    # Delta and Alpha deposit in Q1 and Q3: once each in the total, not twice
    total = row_after(s, "Total", width=12)
    assert total[:2] == [6, 3] and total[2:4] == [2, 2]
    # by StudentAssignedToBusinessRegion: Delta x2; Alpha x2, Zeta x2
    assert row_after(s, "Africa")[0] == 2 and row_after(s, "Asia")[0] == 4
    assert row_after(s, "Africa")[2] == 1 and row_after(s, "Asia")[2] == 2   # Delta; Alpha, Zeta
    assert row_after(s, "United Kingdom")[0] == 5 and row_after(s, "Canada")[0] == 1


def test_retention_counts_active_deposits_only():
    s = workbook()["B2B - Sales and Retention"]
    assert row_after(s, "Introducer not in master file")[:2] == [2, 0]   # Zeta x2
    assert "2024" not in s.values()                                  # no deposits either year: no row
    assert row_after(s, "Introducers resurrected")[0] == 2         # Delta and Zeta, not Alpha
    assert row_after(s, "Their 2026 active deposits")[0] == 4
    assert row_after(s, "Introducers missed out")[0] == 2          # Gamma, and Eta matched by name
    assert row_after(s, "Their 2025 active deposits")[0] == 2
    # by business team, each team's introducers in the rows under it (the last such label on the sheet)
    assert row_after(s, "East", 0) == ["1 introducer", None, None, None, 2, 0]
    assert row_after(s, "Delta", 0) == ["Kenya", "East", "Dan", 45047, 2, 0]
    assert row_after(s, "West", 0) == ["1 introducer", None, None, None, 0, 1]
    assert row_after(s, "eta", 0)[:3] == ["Ghana", "West", "Bola"]
    # Eta's deposit has no introducer id: the master's id for the name stands in,
    # and an introducer with no Became Customer Date counts as an old one.
    assert row_after(s, "2023 & earlier")[1] == 1
    assert "No Became Customer Date" not in s.values()


def test_writer_escapes_text_and_caches_formula_values():
    wb = Workbook()
    ws = wb.add_sheet("A & B")
    ws.set(1, 1, 'Tom & "Jerry" <3')
    ws.set(1, 2, 5)
    ws.set(1, 3, Formula('IF(B1=0,"",B1*2)', 10))
    ws.set(1, 4, date(2026, 10, 6))
    z = zipfile.ZipFile(io.BytesIO(wb.save()))
    for name in z.namelist():
        ET.fromstring(z.read(name))                                # every part is well-formed XML
    sheet = z.read("xl/worksheets/sheet1.xml").decode()
    assert "Tom &amp; &quot;Jerry&quot; &lt;3" in sheet or 'Tom &amp; "Jerry" &lt;3' in sheet
    assert "<f>IF(B1=0,&quot;&quot;,B1*2)</f><v>10</v>" in sheet or '<f>IF(B1=0,"",B1*2)</f><v>10</v>' in sheet
    assert '<c r="D1"><v>46301</v></c>' in sheet                   # Excel's serial for 6 Oct 2026
    assert col_letter(28) == "AB"


def test_an_srm_in_several_teams_is_one_row_over_its_teams():
    wb = Workbook()
    ws = wb.add_sheet("S")
    w = Writer(ws, row=1)
    w.compare(["SRM", "Business team"], [(("Bob", "West"), 4, 1), (("Ann", "East"), 3, 5), (("Ann", "West"), 3, 3)],
              "This", "Last", nest="teams")
    w.share(["SRM", "Business team"], [(("Bob", "West"), 4), (("Ann", "East"), 3), (("Ann", "West"), 3)],
            "Deposits", nest="teams")
    sheet = ET.fromstring(zipfile.ZipFile(io.BytesIO(wb.save())).read("xl/worksheets/sheet1.xml"))
    rows = {int(r.get("r")): r for r in sheet.iter(f"{{{NS['m']}}}row")}
    text = {c.get("r"): c.findtext("m:v", namespaces=NS) or "".join(c.itertext()) for c in sheet.iter(f"{{{NS['m']}}}c")}
    formula = {c.get("r"): c.findtext("m:f", namespaces=NS) for c in sheet.iter(f"{{{NS['m']}}}c")}
    # Ann's 6 beat Bob's 4: her total row first, collapsed over her two teams
    assert [text.get(f"A{r}") for r in range(2, 7)] == ["Ann", "", "", "Bob", "Total"]
    assert text["B2"] == "2 teams" and text["B3"] == "East" and text["B4"] == "West"
    assert formula["C2"] == "SUBTOTAL(9,C3:C4)" and text["C2"] == "6"
    assert rows[2].get("collapsed") == "1"
    assert [rows[r].get("outlineLevel") for r in (2, 3, 4, 5)] == [None, "1", "1", None]
    assert rows[3].get("hidden") == "1"
    # the total skips the summary row's own SUBTOTAL: 10 and 9, not 16 and 17
    assert formula["C6"] == "SUBTOTAL(9,C2:C5)" and text["C6"] == "10" and text["D6"] == "9"
    # the share table groups the same way, its total over the same rows
    assert formula["C9"] == "SUBTOTAL(9,C10:C11)" and formula["C13"] == "SUBTOTAL(9,C9:C12)"
    assert sheet.find("m:sheetPr/m:outlinePr", NS).get("summaryBelow") == "0"


def test_team_names_drop_srm_and_amt():
    import polars as pl
    from app.reports.weekly_summary import _team
    names = ["West Africa B2B SRMs 1", "MENA B2B SRMs", "CIS B2B SRM", "AMT Team London", "SRMs", None]
    out = pl.DataFrame({"team": names}).select(_team("team"))["team"].to_list()
    assert out == ["West Africa B2B 1", "MENA B2B", "CIS B2B", "Team London", "(blank)", "(blank)"]


def test_a_chart_with_a_wide_spread_draws_on_a_log_scale():
    """Small bars beside big ones would vanish on a linear axis."""
    def chart(values: list[int]) -> str:
        wb = Workbook()
        ws = wb.add_sheet("S")
        for i, v in enumerate(values, 1):
            ws.set(i, 1, f"k{i}")
            ws.set(i, 2, v)
        ws.charts.append(Chart("Deposits", (1, len(values), 1), [("cy", 2)], at=(1, 4)))
        return zipfile.ZipFile(io.BytesIO(wb.save())).read("xl/charts/chart1.xml").decode()

    wide = chart([1163, 270, 14, 0])
    assert '<c:logBase val="10"/>' in wide and "Deposits (log scale)" in wide
    narrow = chart([282, 235, 144])
    assert "logBase" not in narrow and "log scale" not in narrow
    tiny = chart([1, 1, 0])                      # whole-number steps, not 0.2 rounded to "0"
    assert "logBase" not in tiny and '<c:majorUnit val="1"/>' in tiny
