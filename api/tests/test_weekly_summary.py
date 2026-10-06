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

from app.reports.weekly_summary import Periods, build, read_export  # noqa: E402
from app.reports.xlsx import Formula, Workbook, col_letter  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
WHEN = datetime(2026, 10, 6, 9, 0)
TODAY = date(2026, 10, 6)         # a Tuesday: this week is Sat 3 Oct - Fri 9 Oct


def csv(*rows: str) -> bytes:
    return "\n".join(rows).encode() + b"\n"


INTRODUCERS = csv(
    "Partner Name,Country,Partner Managed By Team(SRM),Partner Managed By User(SRM),Became Customer Date,_id",
    "Alpha,India,South,Asha,2026-10-03 00:00:00,a1",      # this week (the Saturday)
    "Beta,Nigeria,West,Bola,2026-10-02 00:00:00,b1",      # last week (the Friday)
    "Gamma,India,South,Asha,2025-03-01 00:00:00,c1",      # same period last year
    "Delta,Kenya,East,Dan,2023-05-01 00:00:00,d1",
    "Eta,Ghana,West,Bola,,e1",                            # no Became Customer Date
)
LOGS = csv(
    "Introducers Name,Log Type,Log Time,Managed By Team,Created By,_id",
    "Alpha,F2FVisits,Sat Oct 03 2026 10:00:00 GMT+0000 (Coordinated Universal Time),South,Asha,l1",
    "Alpha,Call,Fri Oct 02 2026 23:30:00 GMT+0000 (Coordinated Universal Time),South,Asha,l2",
    # 01:00 on the 3rd in India is still the 2nd in UTC: last week
    "Beta,Email,Sat Oct 03 2026 01:00:00 GMT+0530 (India Standard Time),West,Bola,l3",
    "Beta,Email,Sat Oct 03 2026 01:00:00 GMT+0530 (India Standard Time),West,Bola,l3",   # same log twice
)
APPLICATIONS = csv(
    "Application Introducer Name,Application Introducer Id,Deposit Paid Status,Application Closed Lost,"
    "Deferred Initiated (No/Yes/All),Deferred Approved (No/Yes/All),Application Course Level,Actual Intake Year,"
    "Actual Intake Month,Introducer SRM User Name,Introducer SRM Team Name,Introducer AMT User Name,Institution Name,"
    "StudentAssignedToBusinessArea,Application Ref No,Timestamp of ‚Äò Deposit Fully Paid‚Äô status",
    "Delta,d1,FullyPaid,No,No,No,Postgraduate,2026,September,Dan,East,Amy,Uni A,B2B,A-01,2026-09-28 00:00:00",         # Delta: 2026 only -> resurrected
    "Delta,d1,FullyPaid,No,Yes,Yes,Undergraduate,2026,January,Dan,East,Amy,Uni B,B2B,A-02,2026-10-03 00:00:00",        # deferred and approved: active
    "Gamma,c1,FullyPaid,No,No,No,Postgraduate,2025,September,Asha,South,Amy,Uni A,B2B,A-03,",       # Gamma: 2025 only -> missed out
    "Gamma,c1,FullyPaid,No,Yes,No,Postgraduate,2026,September,Asha,South,Amy,Uni A,B2B,A-04,2026-10-02 00:00:00",      # deferral pending: DAA
    "Gamma,c1,FullyPaid,Yes,No,No,Postgraduate,2026,September,Asha,South,Amy,Uni A,B2B,A-05,2026-09-30 00:00:00",      # closed lost: nothing
    "Gamma,c1,FullyPaid,No,No,No,Language,2026,September,Asha,South,Amy,Uni A,B2B,A-06,2026-09-29 00:00:00",           # not Academic
    "Delta,d1,FullyPaid,No,No,No,PresessionalEnglish,2026,September,Dan,East,Amy,Uni A,B2B,A-07,",  # not Academic
    "Delta,d1,FullyPaid,No,No,No,,2026,September,Dan,East,Amy,Uni A,B2B,A-08,",                     # no course level: out
    "Delta,d1,FullyPaid,No,No,No,September,2026,September,Dan,East,Amy,Uni A,B2B,A-09,",            # a stray value: out
    "Zeta,,FullyPaid,No,No,No,GCSEgradesAC,2026,May,Zed,North,Amy,Uni C,B2B,A-10,",                 # a listed level: in
    "Alpha,a1,FullyPaid,No,No,No,Postgraduate,2026,September,Asha,South,Amy,Uni C,B2B,A-11,2026-09-20 00:00:00",       # onboarded 2026: not resurrected
    "Alpha,a1,fullyPaidWaitingForApproval,No,No,No,Postgraduate,2026,January,Asha,South,Amy,Uni C,B2B,A-12,",  # paid in full: active
    "Beta,b1,FullyPaid,No,No,Yes,Postgraduate,2026,January,Bola,West,Amy,Uni C,B2B,A-13,",          # columns differ: DAA
    "Beta,b1,PartiallyPaid,No,No,No,Postgraduate,2025,September,Bola,West,Amy,Uni C,B2B,A-14,",     # PD
    "Beta,b1,PartiallyPaid,Yes,No,No,Postgraduate,2025,September,Bola,West,Amy,Uni C,B2B,A-15,",    # closed lost: not PD
    ",d1,PartiallyPaid,No,Yes,Yes,Postgraduate,2026,September,Dan,East,Amy,Uni A,B2B,A-16,",        # no name, Delta's id: PD
    ",,PartiallyPaid,No,No,No,Postgraduate,2026,September,Dan,East,Amy,Uni A,B2B,A-17,",            # no introducer at all: out
    "Beta,b1,NotPaid,No,No,No,Postgraduate,2026,September,Bola,West,Amy,Uni C,B2B,A-18,2026-09-21 00:00:00",           # nothing, though paid in the week before once
    "Zeta,,FullyPaid,No,No,No,Postgraduate,2026,May,Zed,North,Amy,Uni C,B2B,A-19,",                 # no id, not in master
    " eta ,,FullyPaid,No,No,No,Postgraduate,2025,May,Bola,West,Amy,Uni C,B2B,A-22,",              # no id: Eta's by name
    "Alpha,a1,FullyPaid,No,No,No,Postgraduate,2026,September,Asha,South,Amy,Uni C,B2C,A-20,2026-09-22 00:00:00",   # not B2B: out
    "Alpha,a1,FullyPaid,No,No,No,Postgraduate,2026,September,Asha,South,Amy,Uni C,,A-21,",      # no business area: out
)


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
            t = c.find("m:is/m:t", NS)
            v = c.find("m:v", NS)
            cells[c.get("r")] = t.text if t is not None else (float(v.text) if v is not None and v.text and c.get("t") != "str" else (v.text if v is not None else None))
        out[name] = cells
    return out


def row_after(cells: dict[str, object], label: str, occurrence: int = 1) -> list[object]:
    """The values to the right of the n-th cell in column A reading `label`."""
    rows = sorted((int(k[1:]) for k, v in cells.items() if k.startswith("A") and k[1:].isdigit() and v == label))
    r = rows[occurrence - 1]
    return [cells.get(f"{col_letter(c)}{r}") for c in range(2, 8)]


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
    s = workbook()["Last week"]
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


def test_overview_comes_first_with_its_charts():
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
    assert names == ["Deposits overview", "Onboarding", "Activity", "Sales & Retention", "Last week"]
    charts = sorted(n for n in z.namelist() if n.startswith("xl/charts/"))
    assert len(charts) == 7                                        # six on the overview, one on Last week
    assert "xl/drawings/drawing1.xml" in z.namelist() and "xl/worksheets/_rels/sheet1.xml.rels" in z.namelist()
    assert "'Deposits overview'!$A$" in z.read("xl/charts/chart1.xml").decode()
    s = workbook()["Deposits overview"]
    assert row_after(s, "Active deposits")[:2] == [6, 2]
    assert row_after(s, "Introducers with active deposits")[:2] == [3, 2]     # Delta, Alpha, Zeta; Gamma, Eta
    assert row_after(s, "September")[:2] == [2, 1]


def test_onboarding_counts():
    s = workbook()["Onboarding"]
    assert row_after(s, "All introducers", 1)[:2] == [2, 1]        # YTD: Alpha, Beta; last year: Gamma
    assert row_after(s, "All introducers", 2)[:2] == [1, 1]        # this week Alpha; last week Beta


def test_activity_dates_in_utc_and_drops_repeated_ids():
    s = workbook()["Activity"]
    assert row_after(s, "Total logs")[:2] == [1, 2]
    assert row_after(s, "Face to face")[:2] == [1, 0]
    assert row_after(s, "Email")[:2] == [0, 1]


def test_active_daa_and_pd_deposits():
    s = workbook()["Sales & Retention"]
    assert row_after(s, "Active deposits")[:2] == [6, 2]           # Delta x2, Alpha x2, Zeta x2; Gamma, Eta
    assert row_after(s, "DAA — deferral awaiting approval")[:2] == [2, 0]   # Gamma Yes/No, Beta No/Yes
    assert row_after(s, "PD — partial deposits")[:2] == [1, 1]     # Delta by id alone; Beta 2025, not the closed-lost one
    # 2026 Active, DAA, PD, then 2025 Active, DAA, PD
    assert row_after(s, "January") == [2, 1, 0, 0, 0, 0]
    assert row_after(s, "September") == [2, 1, 1, 1, 0, 1]
    assert row_after(s, "May") == [2, 0, 0, 1, 0, 0]


def test_retention_counts_active_deposits_only():
    s = workbook()["Sales & Retention"]
    assert row_after(s, "Introducer not in master file")[:2] == [2, 0]   # Zeta x2
    assert row_after(s, "Introducers resurrected")[0] == 2         # Delta and Zeta, not Alpha
    assert row_after(s, "Their 2026 active deposits")[0] == 4
    assert row_after(s, "Introducers missed out")[0] == 2          # Gamma, and Eta matched by name
    assert row_after(s, "Their 2025 active deposits")[0] == 2
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


def test_team_names_drop_srm_and_amt():
    import polars as pl
    from app.reports.weekly_summary import _team
    names = ["West Africa B2B SRMs 1", "MENA B2B SRMs", "CIS B2B SRM", "AMT Team London", "SRMs", None]
    out = pl.DataFrame({"team": names}).select(_team("team"))["team"].to_list()
    assert out == ["West Africa B2B 1", "MENA B2B", "CIS B2B", "Team London", "(blank)", "(blank)"]
