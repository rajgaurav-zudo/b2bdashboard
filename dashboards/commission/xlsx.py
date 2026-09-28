"""A small xlsx reader: cell values, their types and the merged ranges.

The importer needs the merged-cell ranges to forward-fill a contract block the
way the sheet was drawn, rather than smearing every blank downwards. polars and
fastexcel return values only, so this reads the workbook's XML directly with the
standard library instead of adding a dependency.
"""
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

# built-in number formats that are dates (ECMA-376 18.8.30)
_DATE_IDS = set(range(14, 23)) | set(range(45, 48)) | {27, 30, 36, 50, 57}
_EPOCH = datetime(1899, 12, 30)


@dataclass
class Sheet:
    name: str
    cells: dict[tuple[int, int], object] = field(default_factory=dict)   # (row, col) 1-based
    merged: list[tuple[int, int, int, int]] = field(default_factory=list)  # r1, c1, r2, c2
    max_row: int = 0
    max_col: int = 0

    def value(self, row: int, col: int):
        return self.cells.get((row, col))

    def merged_origin(self, row: int, col: int) -> tuple[int, int] | None:
        """The top-left cell of the merged range covering (row, col), if any."""
        for r1, c1, r2, c2 in self.merged:
            if r1 <= row <= r2 and c1 <= col <= c2:
                return r1, c1
        return None


def col_letter(col: int) -> str:
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def _ref(ref: str) -> tuple[int, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref)
    letters, digits = m.group(1), m.group(2)
    col = 0
    for ch in letters:
        col = col * 26 + ord(ch) - 64
    return int(digits), col


def read(path_or_file) -> list[Sheet]:
    with zipfile.ZipFile(path_or_file) as z:
        names = set(z.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))

        date_styles: set[int] = set()
        if "xl/styles.xml" in names:
            root = ET.fromstring(z.read("xl/styles.xml"))
            custom = {}
            for fmt in root.findall("m:numFmts/m:numFmt", NS):
                code = fmt.get("formatCode", "").lower()
                code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", code)
                custom[int(fmt.get("numFmtId"))] = bool(re.search(r"[dy]|m{3,}", code))
            for i, xf in enumerate(root.findall("m:cellXfs/m:xf", NS)):
                fid = int(xf.get("numFmtId", 0))
                if fid in _DATE_IDS or custom.get(fid):
                    date_styles.add(i)

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels}
        sheets = []
        for s in wb.findall("m:sheets/m:sheet", NS):
            target = targets[s.get(REL)].lstrip("/")
            path = target if target.startswith("xl/") else f"xl/{target}"
            sheets.append(_sheet(s.get("name"), z.read(path), shared, date_styles))
        return sheets


def _sheet(name: str, xml: bytes, shared: list[str], date_styles: set[int]) -> Sheet:
    sheet = Sheet(name)
    root = ET.fromstring(xml)
    for c in root.iter(f"{{{NS['m']}}}c"):
        row, col = _ref(c.get("r"))
        kind = c.get("t")
        v = c.find("m:v", NS)
        if kind == "inlineStr":
            value = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
        elif v is None or v.text is None:
            continue
        elif kind == "s":
            value = shared[int(v.text)]
        elif kind in ("str", "e"):
            value = v.text
        elif kind == "b":
            value = v.text == "1"
        else:
            num = float(v.text)
            if int(c.get("s", 0)) in date_styles:
                value = _EPOCH + timedelta(days=num)
            else:
                value = int(num) if num.is_integer() and "." not in v.text and "E" not in v.text else num
        if isinstance(value, str) and not value.strip():
            continue
        sheet.cells[(row, col)] = value
        sheet.max_row = max(sheet.max_row, row)
        sheet.max_col = max(sheet.max_col, col)
    for mc in root.iter(f"{{{NS['m']}}}mergeCell"):
        a, _, b = mc.get("ref").partition(":")
        r1, c1 = _ref(a)
        r2, c2 = _ref(b or a)
        sheet.merged.append((r1, c1, r2, c2))
    return sheet
