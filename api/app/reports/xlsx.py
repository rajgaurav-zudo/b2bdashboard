"""A small .xlsx writer on the standard library.

Only what the reports use: text, numbers, dates and formulas, a handful of
cell styles, column widths, row heights, merged cells, a frozen header and
bar / column charts drawn from cells on their own sheet.
A workbook is a zip of XML parts, and writing those directly is less code
than a dependency the API image would carry for one download.

Formulas are written with the value they evaluate to as their cached result,
so a previewer that never recalculates (Quick Look, a mail client, pandas)
still shows numbers. The workbook also asks Excel to recalculate on open,
so the formulas stay the source of truth once someone edits a cell.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import date
from xml.sax.saxutils import escape

_EPOCH = date(1899, 12, 30)       # Excel's day zero, past its 1900 leap-year bug


@dataclass(frozen=True)
class Style:
    bold: bool = False
    italic: bool = False
    size: float = 10
    color: str = "000000"         # RGB hex
    fill: str | None = None       # RGB hex of a solid fill
    border: bool = False          # thin light-grey box
    num_fmt: str | None = None    # Excel number format code
    wrap: bool = False
    halign: str | None = None     # left / center / right
    valign: str | None = None     # top / center / bottom


@dataclass(frozen=True)
class Formula:
    """A formula without its leading '=', and the value it evaluates to."""
    text: str
    value: float | int | str | None = None


@dataclass
class Chart:
    """A clustered bar or column chart over a block of cells on its sheet.

    `cats` is the (first row, last row, column) of the category labels; each
    series is (name, column) over the same rows, and its name is a plain
    label. The values are cached in the chart too, so a previewer that does
    not read the cells still draws it. `at` is the (row, col) of the top-left
    cell and `size` (rows, cols) how many it spans.
    """
    title: str
    cats: tuple[int, int, int]
    series: list[tuple[str, int]]
    at: tuple[int, int]
    size: tuple[int, int] = (18, 7)
    horizontal: bool = False
    colors: tuple[str, ...] = ("1F3864", "8EA9DB", "C00000", "FFC000")


def col_letter(col: int) -> str:
    """1 -> A, 27 -> AA."""
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def ref(row: int, col: int) -> str:
    return f"{col_letter(col)}{row}"


class Sheet:
    def __init__(self, name: str):
        self.name = name
        self.cells: dict[tuple[int, int], tuple[object, Style | None]] = {}
        self.widths: dict[int, float] = {}
        self.heights: dict[int, float] = {}
        self.merges: list[str] = []
        self.freeze: str | None = None    # top-left cell of the scrolling area, e.g. "A4"
        self.charts: list[Chart] = []

    def set(self, row: int, col: int, value: object, style: Style | None = None) -> None:
        self.cells[(row, col)] = (value, style)


class Workbook:
    def __init__(self, font: str = "Arial"):
        self.font = font
        self.sheets: list[Sheet] = []
        self._styles: list[Style] = [Style()]       # xf 0 is the default
        self._fmts: dict[str, int] = {}

    def add_sheet(self, name: str) -> Sheet:
        sheet = Sheet(name)
        self.sheets.append(sheet)
        return sheet

    def _xf(self, style: Style | None) -> int:
        style = style or Style()
        if style not in self._styles:
            self._styles.append(style)
        return self._styles.index(style)

    def _cell(self, row: int, col: int, value: object, style: Style | None) -> str:
        r = ref(row, col)
        s = f' s="{self._xf(style)}"' if style else ""
        if value is None or value == "":
            return f'<c r="{r}"{s}/>' if style else ""
        if isinstance(value, Formula):
            f = f"<f>{escape(value.text)}</f>"
            if value.value is None:
                return f'<c r="{r}"{s}>{f}</c>'
            if isinstance(value.value, str):
                return f'<c r="{r}"{s} t="str">{f}<v>{escape(value.value)}</v></c>'
            return f'<c r="{r}"{s}>{f}<v>{_num(value.value)}</v></c>'
        if isinstance(value, bool):
            return f'<c r="{r}"{s} t="b"><v>{int(value)}</v></c>'
        if isinstance(value, (int, float)):
            return f'<c r="{r}"{s}><v>{_num(value)}</v></c>'
        if isinstance(value, date):
            return f'<c r="{r}"{s}><v>{(value - _EPOCH).days}</v></c>'
        text = escape(str(value))
        return f'<c r="{r}"{s} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'

    def _sheet_xml(self, sheet: Sheet) -> str:
        rows: dict[int, list[tuple[int, object, Style | None]]] = {}
        for (r, c), (v, st) in sheet.cells.items():
            rows.setdefault(r, []).append((c, v, st))
        body = []
        for r in sorted(rows):
            cells = "".join(self._cell(r, c, v, st) for c, v, st in sorted(rows[r], key=lambda x: x[0]))
            ht = f' ht="{sheet.heights[r]}" customHeight="1"' if r in sheet.heights else ""
            body.append(f'<row r="{r}"{ht}>{cells}</row>')
        for r in sorted(set(sheet.heights) - set(rows)):
            body.append(f'<row r="{r}" ht="{sheet.heights[r]}" customHeight="1"/>')
        body.sort(key=lambda x: int(x.split('"')[1]))

        pane = ""
        if sheet.freeze:
            col, row = _split(sheet.freeze)
            xs, ys = col - 1, row - 1
            which = "bottomRight" if xs and ys else ("bottomLeft" if ys else "topRight")
            split = (f' xSplit="{xs}"' if xs else "") + (f' ySplit="{ys}"' if ys else "")
            pane = (f'<pane{split} topLeftCell="{sheet.freeze}" activePane="{which}" state="frozen"/>'
                    f'<selection pane="{which}"/>')
        cols = "".join(f'<col min="{c}" max="{c}" width="{w}" customWidth="1"/>'
                       for c, w in sorted(sheet.widths.items()))
        merges = "".join(f'<mergeCell ref="{m}"/>' for m in sheet.merges)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheetViews><sheetView workbookViewId="0" showGridLines="0">{pane}</sheetView></sheetViews>'
            '<sheetFormatPr defaultRowHeight="13"/>'
            + (f"<cols>{cols}</cols>" if cols else "")
            + f'<sheetData>{"".join(body)}</sheetData>'
            + (f'<mergeCells count="{len(sheet.merges)}">{merges}</mergeCells>' if merges else "")
            + ('<drawing r:id="rId1"/>' if sheet.charts else "")
            + "</worksheet>"
        )

    def _styles_xml(self) -> str:
        # Custom number formats start at 164; lower ids are Excel's built-ins.
        fmts = {}
        for st in self._styles:
            if st.num_fmt and st.num_fmt not in fmts:
                fmts[st.num_fmt] = 164 + len(fmts)
        fonts, fills, xfs = [], ['<fill><patternFill patternType="none"/></fill>',
                                 '<fill><patternFill patternType="gray125"/></fill>'], []
        for st in self._styles:
            font = (("<b/>" if st.bold else "") + ("<i/>" if st.italic else "")
                    + f'<sz val="{st.size}"/><color rgb="FF{st.color}"/><name val="{escape(self.font)}"/>')
            fonts.append(f"<font>{font}</font>")
            fill_id = 0
            if st.fill:
                fills.append(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{st.fill}"/>'
                             '<bgColor indexed="64"/></patternFill></fill>')
                fill_id = len(fills) - 1
            align = ""
            if st.wrap or st.halign or st.valign:
                align = ("<alignment" + (f' horizontal="{st.halign}"' if st.halign else "")
                         + (f' vertical="{st.valign}"' if st.valign else "")
                         + (' wrapText="1"' if st.wrap else "") + "/>")
            fmt_id = fmts.get(st.num_fmt, 0) if st.num_fmt else 0
            xfs.append(
                f'<xf numFmtId="{fmt_id}" fontId="{len(fonts) - 1}" fillId="{fill_id}" '
                f'borderId="{1 if st.border else 0}" xfId="0"'
                + (' applyNumberFormat="1"' if fmt_id else "")
                + (' applyFill="1"' if fill_id else "")
                + (' applyBorder="1"' if st.border else "")
                + (f' applyAlignment="1">{align}</xf>' if align else "/>")
            )
        line = '<{0} style="thin"><color rgb="FFBFBFBF"/></{0}>'
        box = "".join(line.format(side) for side in ("left", "right", "top", "bottom"))
        numfmts = "".join(f'<numFmt numFmtId="{i}" formatCode="{escape(f, {chr(34): "&quot;"})}"/>'
                          for f, i in fmts.items())
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + (f'<numFmts count="{len(fmts)}">{numfmts}</numFmts>' if fmts else "")
            + f'<fonts count="{len(fonts)}">{"".join(fonts)}</fonts>'
            + f'<fills count="{len(fills)}">{"".join(fills)}</fills>'
            + f'<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
              f"<border>{box}<diagonal/></border></borders>"
            + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            + f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
            + '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            + "</styleSheet>"
        )

    def save(self) -> bytes:
        # Sheets first: rendering them is what registers the styles they use.
        sheets = [self._sheet_xml(s) for s in self.sheets]
        styles = self._styles_xml()
        n = len(self.sheets)
        # One drawing per sheet with charts; charts numbered across the workbook.
        drawings: list[tuple[int, str, str]] = []      # (sheet index, drawing xml, its rels)
        charts: list[str] = []
        for i, sheet in enumerate(self.sheets, 1):
            if not sheet.charts:
                continue
            anchors, rels = [], []
            for k, chart in enumerate(sheet.charts, 1):
                charts.append(_chart_xml(sheet, chart))
                anchors.append(_anchor(chart, k))
                rels.append(f'<Relationship Id="rId{k}" Type="{_REL}/chart" Target="../charts/chart{len(charts)}.xml"/>')
            drawings.append((i, _DRAWING.format("".join(anchors)), _RELS.format("".join(rels))))
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                      for i in range(1, n + 1))
            + "".join(f'<Override PartName="/xl/drawings/drawing{d}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
                      for d in range(1, len(drawings) + 1))
            + "".join(f'<Override PartName="/xl/charts/chart{c}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>'
                      for c in range(1, len(charts) + 1))
            + "</Types>"
        )
        root_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        )
        workbook = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(f'<sheet name="{escape(s.name, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                      for i, s in enumerate(self.sheets, 1))
            + '</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'
        )
        wb_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                      for i in range(1, n + 1))
            + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", root_rels)
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
            z.writestr("xl/styles.xml", styles)
            for i, xml in enumerate(sheets, 1):
                z.writestr(f"xl/worksheets/sheet{i}.xml", xml)
            for d, (i, xml, rels) in enumerate(drawings, 1):
                z.writestr(f"xl/worksheets/_rels/sheet{i}.xml.rels",
                           _RELS.format(f'<Relationship Id="rId1" Type="{_REL}/drawing" Target="../drawings/drawing{d}.xml"/>'))
                z.writestr(f"xl/drawings/drawing{d}.xml", xml)
                z.writestr(f"xl/drawings/_rels/drawing{d}.xml.rels", rels)
            for c, xml in enumerate(charts, 1):
                z.writestr(f"xl/charts/chart{c}.xml", xml)
        return buf.getvalue()


# ------------------------------------------------------------------ charts

_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{}</Relationships>')
_DRAWING = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{}</xdr:wsDr>')


def _anchor(chart: Chart, k: int) -> str:
    (r, c), (h, w) = chart.at, chart.size

    def mark(tag: str, row: int, col: int) -> str:
        return (f"<xdr:{tag}><xdr:col>{col - 1}</xdr:col><xdr:colOff>0</xdr:colOff>"
                f"<xdr:row>{row - 1}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:{tag}>")

    return (
        '<xdr:twoCellAnchor editAs="oneCell">' + mark("from", r, c) + mark("to", r + h, c + w)
        + f'<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="{k + 1}" name="Chart {k}"/>'
        '<xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr>'
        '<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
        f'<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="{_REL}" r:id="rId{k}"/>'
        "</a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>"
    )


def _cached(sheet: Sheet, row: int, col: int) -> object:
    v = sheet.cells.get((row, col), (None, None))[0]
    return v.value if isinstance(v, Formula) else v


def _text(text: str, size: int, bold: bool = False) -> str:
    b = ' b="1"' if bold else ' b="0"'
    return (f'<c:rich><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="{size}"{b}/></a:pPr>'
            f'<a:r><a:rPr lang="en-GB" sz="{size}"{b}><a:latin typeface="Arial"/></a:rPr>'
            f"<a:t>{escape(text)}</a:t></a:r></a:p></c:rich>")


def _chart_xml(sheet: Sheet, chart: Chart) -> str:
    first, last, cat_col = chart.cats
    rows = range(first, last + 1)
    quoted = "'" + sheet.name.replace("'", "''") + "'"

    def rng(col: int) -> str:
        return f"{quoted}!${col_letter(col)}${first}:${col_letter(col)}${last}"

    cats = "".join(f'<c:pt idx="{i}"><c:v>{escape(str(_cached(sheet, r, cat_col) or ""))}</c:v></c:pt>'
                   for i, r in enumerate(rows))
    ser = []
    for k, (name, col) in enumerate(chart.series):
        vals = "".join(f'<c:pt idx="{i}"><c:v>{_num(v)}</c:v></c:pt>' for i, r in enumerate(rows)
                       if isinstance(v := _cached(sheet, r, col), (int, float)) and not isinstance(v, bool))
        ser.append(
            f'<c:ser><c:idx val="{k}"/><c:order val="{k}"/>'
            f"<c:tx><c:v>{escape(name)}</c:v></c:tx>"
            f'<c:spPr><a:solidFill><a:srgbClr val="{chart.colors[k % len(chart.colors)]}"/></a:solidFill></c:spPr>'
            '<c:invertIfNegative val="0"/>'
            '<c:dLbls><c:numFmt formatCode="#,##0" sourceLinked="0"/><c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>'
            '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="800"/></a:pPr><a:endParaRPr lang="en-GB"/></a:p></c:txPr>'
            '<c:dLblPos val="outEnd"/><c:showLegendKey val="0"/><c:showVal val="1"/><c:showCatName val="0"/>'
            '<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>'
            f'<c:cat><c:strRef><c:f>{rng(cat_col)}</c:f><c:strCache><c:ptCount val="{len(rows)}"/>{cats}'
            "</c:strCache></c:strRef></c:cat>"
            f'<c:val><c:numRef><c:f>{rng(col)}</c:f><c:numCache><c:formatCode>General</c:formatCode>'
            f'<c:ptCount val="{len(rows)}"/>{vals}</c:numCache></c:numRef></c:val></c:ser>'
        )
    # A horizontal bar chart reads top to bottom in the cells' order; the value
    # axis is left off, since every bar carries its own label.
    hz = chart.horizontal
    no_line = '<c:spPr><a:ln><a:noFill/></a:ln></c:spPr>'
    grid = '<c:majorGridlines><c:spPr><a:ln w="6350"><a:solidFill><a:srgbClr val="E7E6E6"/></a:solidFill></a:ln></c:spPr></c:majorGridlines>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
        f'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{_REL}">'
        '<c:roundedCorners val="0"/><c:chart>'
        f'<c:title><c:tx>{_text(chart.title, 1100, bold=True)}</c:tx><c:overlay val="0"/></c:title>'
        '<c:autoTitleDeleted val="0"/><c:plotArea><c:layout/>'
        f'<c:barChart><c:barDir val="{"bar" if hz else "col"}"/><c:grouping val="clustered"/><c:varyColors val="0"/>'
        + "".join(ser)
        + '<c:gapWidth val="60"/><c:axId val="10"/><c:axId val="20"/></c:barChart>'
        '<c:catAx><c:axId val="10"/>'
        f'<c:scaling><c:orientation val="{"maxMin" if hz else "minMax"}"/></c:scaling><c:delete val="0"/>'
        f'<c:axPos val="{"l" if hz else "b"}"/><c:numFmt formatCode="General" sourceLinked="0"/>'
        '<c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/>'
        + no_line +
        '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="800"/></a:pPr><a:endParaRPr lang="en-GB"/></a:p></c:txPr>'
        '<c:crossAx val="20"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/>'
        '<c:lblOffset val="100"/><c:noMultiLvlLbl val="0"/></c:catAx>'
        f'<c:valAx><c:axId val="20"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="{1 if hz else 0}"/>'
        f'<c:axPos val="{"b" if hz else "l"}"/>' + ("" if hz else grid)
        + '<c:numFmt formatCode="#,##0" sourceLinked="0"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/>'
        '<c:tickLblPos val="nextTo"/>' + no_line +
        '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="800"/></a:pPr><a:endParaRPr lang="en-GB"/></a:p></c:txPr>'
        '<c:crossAx val="10"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>'
        '</c:plotArea>'
        + ('<c:legend><c:legendPos val="t"/><c:overlay val="0"/></c:legend>' if len(chart.series) > 1 else "")
        + '<c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart>'
        '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="900"><a:latin typeface="Arial"/></a:defRPr></a:pPr>'
        '<a:endParaRPr lang="en-GB"/></a:p></c:txPr>'
        "</c:chartSpace>"
    )


def _num(value: float | int) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _split(cell: str) -> tuple[int, int]:
    """'B4' -> (2, 4)."""
    letters = "".join(ch for ch in cell if ch.isalpha())
    col = 0
    for ch in letters.upper():
        col = col * 26 + ord(ch) - 64
    return col, int(cell[len(letters):])
