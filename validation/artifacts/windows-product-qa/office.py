"""LibreOffice release QA fixtures and capture-driven Windows tests."""

from __future__ import annotations

import asyncio
import base64
import io
import re
import xml.etree.ElementTree as xml
import zipfile
from html import escape
from uuid import uuid4

ROOT = r"C:\OSLabWall"
NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "presentation": "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0",
    "of": "urn:oasis:names:tc:opendocument:xmlns:of:1.2",
}
DECLARATIONS = " ".join(f'xmlns:{key}="{uri}"' for key, uri in NS.items())
CASES = {
    "02": {
        "title": "LibreOffice Calc",
        "kicker": "RELEASE QA / FORMULA RECALCULATION",
        "scenario": "Repair a missing artifact subtotal and verify the release gate recalculates.",
        "steps": ["Inspect failed artifact gate", "Correct the Win-x64 count", "Save and verify computed cells"],
        "package": "libreoffice",
    },
    "12": {
        "title": "LibreOffice Writer",
        "kicker": "RELEASE QA / REPORT PAGINATION",
        "scenario": "Add an approval receipt to the QA handoff and render the two-page report to PDF.",
        "steps": ["Review release handoff", "Sign the decision page", "Verify two-page PDF"],
        "package": "libreoffice",
    },
    "13": {
        "title": "LibreOffice Impress",
        "kicker": "RELEASE QA / VISUAL REGRESSION",
        "scenario": "Play both incident brief slides and verify their sequence and 16:9 PDF geometry.",
        "steps": ["Play the release brief", "Advance to the decision", "Verify the exported deck"],
        "package": "libreoffice",
    },
    "14": {
        "title": "LibreOffice Draw",
        "kicker": "RELEASE QA / VECTOR LAYOUT",
        "scenario": "Adjust a registration mark and verify its vector geometry and released PDF bounds.",
        "steps": ["Locate the registration mark", "Move the mark away from the trim", "Save and verify print geometry"],
        "package": "libreoffice",
    },
}


def element(prefix, name):
    return "{" + NS[prefix] + "}" + name


def check(name, expected, observed):
    return {"name": name, "expected": expected, "observed": observed, "passed": expected == observed}


def document(kind, body, styles="", automatic="", masters=""):
    """Build an ODF ZIP with editable, macro-free content and no external references."""
    extension = "graphics" if kind == "drawing" else kind
    media = f"application/vnd.oasis.opendocument.{extension}"
    header = '<?xml version="1.0" encoding="UTF-8"?>'
    content = (
        f'{header}<office:document-content {DECLARATIONS} office:version="1.3">'
        f'<office:automatic-styles>{automatic}</office:automatic-styles>'
        f'<office:body><office:{kind}>{body}</office:{kind}></office:body></office:document-content>'
    )
    formatting = (
        f'{header}<office:document-styles {DECLARATIONS} office:version="1.3">'
        f'{styles}{masters}</office:document-styles>'
    )
    manifest_ns = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
    manifest = (
        f'{header}<manifest:manifest xmlns:manifest="{manifest_ns}" manifest:version="1.3">'
        f'<manifest:file-entry manifest:full-path="/" manifest:media-type="{media}"/>'
        '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
        '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
        '</manifest:manifest>'
    )
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("mimetype", media, compress_type=zipfile.ZIP_STORED)
        package.writestr("content.xml", content)
        package.writestr("styles.xml", formatting)
        package.writestr("META-INF/manifest.xml", manifest)
    return data.getvalue()


def calc_cell(value, appearance="Value", formula=None):
    numeric = isinstance(value, int)
    attrs = f'table:style-name="{appearance}" office:value-type="{"float" if numeric else "string"}"'
    if numeric:
        attrs += f' office:value="{value}"'
    if formula:
        attrs += f' table:formula="{escape(formula, quote=True)}"'
    return f"<table:table-cell {attrs}><text:p>{escape(str(value))}</text:p></table:table-cell>"


def calc_fixture():
    styles = (
        '<style:style style:name="Wide" style:family="table-column">'
        '<style:table-column-properties style:column-width="7.6cm"/></style:style>'
        '<style:style style:name="Narrow" style:family="table-column">'
        '<style:table-column-properties style:column-width="3.6cm"/></style:style>'
        '<style:style style:name="Tall" style:family="table-row">'
        '<style:table-row-properties style:row-height="1.09cm"/></style:style>'
    )
    for name, fill, ink, weight in (
        ("Header", "#17354b", "#ffffff", "bold"),
        ("Value", "#edf5f6", "#17354b", "normal"),
        ("Gate", "#d5efe5", "#145040", "bold"),
    ):
        styles += (
            f'<style:style style:name="{name}" style:family="table-cell">'
            f'<style:table-cell-properties fo:background-color="{fill}" '
            'fo:border="0.03cm solid #d6e0e7" style:vertical-align="middle" fo:padding-left="0.28cm"/>'
            f'<style:text-properties fo:font-size="15pt" fo:font-weight="{weight}" fo:color="{ink}"/>'
            '</style:style>'
        )
    rows = (
        tuple(calc_cell(value, "Header") for value in ("RELEASE-42 / Artifact Gate", "Observed", "Expected", "Missing")),
        (calc_cell("Windows x64 / signed packages"), calc_cell(17), calc_cell(22),
         calc_cell(5, formula="of:=[.C2]-[.B2]")),
        (calc_cell("Windows ARM64 / signed packages"), calc_cell(12), calc_cell(12),
         calc_cell(0, formula="of:=[.C3]-[.B3]")),
        (calc_cell("Cross-platform documentation"), calc_cell(8), calc_cell(8),
         calc_cell(0, formula="of:=[.C4]-[.B4]")),
        (calc_cell("TOTAL ARTIFACTS", "Gate"), calc_cell(37, "Gate", "of:=SUM([.B2:.B4])"),
         calc_cell(42, "Gate", "of:=SUM([.C2:.C4])"), calc_cell(5, "Gate", "of:=SUM([.D2:.D4])")),
        (calc_cell("RELEASE DECISION", "Gate"),
         calc_cell("BLOCKED", "Gate", 'of:=IF([.D5]=0;"PASS";"BLOCKED")')),
    )
    grid = (
        '<table:table table:name="Release_42">'
        '<table:table-column table:style-name="Wide"/>'
        '<table:table-column table:style-name="Narrow" table:number-columns-repeated="3"/>'
        + "".join('<table:table-row table:style-name="Tall">' + "".join(row) + "</table:table-row>" for row in rows)
        + "</table:table>"
    )
    return document("spreadsheet", grid, automatic=styles)


def page_styles(width, height):
    orientation = "landscape" if width > height else "portrait"
    return (
        '<office:automatic-styles><style:page-layout style:name="ReleasePage">'
        f'<style:page-layout-properties fo:page-width="{width}cm" fo:page-height="{height}cm" '
        f'fo:margin="1.1cm" style:print-orientation="{orientation}"/>'
        '</style:page-layout></office:automatic-styles>'
        '<office:master-styles><style:master-page style:name="Standard" '
        'style:page-layout-name="ReleasePage"/></office:master-styles>'
    )


def paragraph(text, style):
    return f'<text:p text:style-name="{style}">{escape(text)}</text:p>'


def writer_fixture():
    styles = (
        '<office:styles>'
        '<style:style style:name="Heading" style:family="paragraph">'
        '<style:paragraph-properties fo:margin-top="1.2cm" fo:margin-bottom="0.48cm"/>'
        '<style:text-properties fo:font-size="31pt" fo:font-weight="bold" fo:color="#12334e"/>'
        '</style:style>'
        '<style:style style:name="Label" style:family="paragraph">'
        '<style:paragraph-properties fo:margin-top="0.66cm" fo:margin-bottom="0.26cm"/>'
        '<style:text-properties fo:font-size="14pt" fo:font-weight="bold" fo:color="#167e72"/>'
        '</style:style>'
        '<style:style style:name="Summary" style:family="paragraph">'
        '<style:paragraph-properties fo:margin-top="0.22cm" fo:margin-bottom="0.24cm"/>'
        '<style:text-properties fo:font-size="13pt" fo:color="#34465d"/>'
        '</style:style>'
        '<style:style style:name="NewPage" style:family="paragraph" style:parent-style-name="Heading">'
        '<style:paragraph-properties fo:break-before="page" fo:margin-top="1.2cm"/>'
        '</style:style></office:styles>'
    )
    body = "".join(paragraph(value, appearance) for value, appearance in (
        ("RELEASE QA  /  WINDOWS 11", "Label"),
        ("Artifact acceptance report", "Heading"),
        ("BR-042 / Zero external dependencies", "Summary"),
        ("CLEAN VM COVERAGE", "Label"),
        ("01    MSI install and detection rules", "Summary"),
        ("02    Upgrade from the supported baseline", "Summary"),
        ("03    Export, SHA-256 and artifact retention", "Summary"),
        ("HANDOFF", "Label"),
        ("Reproducible artifacts and a paginated release decision.", "Summary"),
        ("Release decision", "NewPage"),
        ("OFFLINE SIGN-OFF / BR-042", "Label"),
        ("Results independently verified against the approved artifact list.", "Summary"),
        ("QA owner receipt", "Label"),
    ))
    return document("text", body, styles=styles, masters=page_styles(21, 29.7))


def shape(name, x, y, w, h, appearance, value=""):
    geometry = f'svg:x="{x}cm" svg:y="{y}cm" svg:width="{w}cm" svg:height="{h}cm"'
    return (f'<draw:rect draw:name="{name}" draw:style-name="{appearance}" {geometry}>'
            f'<text:p>{escape(value)}</text:p></draw:rect>')


def graphics_styles(colors):
    return "".join(
        f'<style:style style:name="{name}" style:family="graphic">'
        f'<style:graphic-properties draw:fill="solid" draw:fill-color="{fill}" draw:stroke="none" '
        'draw:textarea-horizontal-align="left" draw:textarea-vertical-align="middle" fo:padding-left="0.45cm"/>'
        f'<style:text-properties fo:font-size="{size}pt" fo:font-weight="bold" fo:color="{fg}"/>'
        '</style:style>'
        for name, fill, fg, size in colors
    )


def page(name, shapes):
    return f'<draw:page draw:name="{name}" draw:master-page-name="Standard">' + "".join(shapes) + '</draw:page>'


def impress_fixture():
    first = page("Candidate metrics", (
        shape("Canvas", 0, 0, 32, 18, "Midnight"),
        shape("Title", 1.4, 1.05, 28.8, 2.7, "Midnight", "Release 42 / Packaging"),
        shape("Scope", 1.4, 4.4, 28.8, 1.15, "Midnight", "WINDOWS BUILD VALIDATION  /  CANDIDATE"),
        shape("msi", 1.4, 7, 8.9, 5.6, "Steel", "42 signed artifacts"),
        shape("suite", 11.5, 7, 8.9, 5.6, "Ocean", "4 platform checks"),
        shape("hash", 21.6, 7, 8.9, 5.6, "Accent", "1 hash ledger"),
        shape("Footer", 1.4, 14.6, 28.8, 1.15, "Midnight", "01  /  READY FOR TEST"),
    ))
    second = page("Decision", (
        shape("Canvas", 0, 0, 32, 18, "Ocean"),
        shape("Title", 1.4, 1.05, 28.8, 2.7, "Ocean", "Release 42 / Decision"),
        shape("Scope", 1.4, 4.4, 28.8, 1.15, "Ocean", "WINDOWS BUILD VALIDATION  /  DECISION"),
        shape("msi", 1.4, 7, 8.9, 5.6, "Midnight", "Clean install"),
        shape("suite", 11.5, 7, 8.9, 5.6, "Steel", "Upgrade retains state"),
        shape("hash", 21.6, 7, 8.9, 5.6, "Accent", "Hashes match"),
        shape("Footer", 1.4, 14.6, 28.8, 1.15, "Ocean", "02  /  APPROVED"),
    ))
    style = graphics_styles((
        ("Midnight", "#172a41", "#e9f6fd", 29), ("Steel", "#345885", "#ffffff", 21),
        ("Ocean", "#185e62", "#effcf9", 25), ("Accent", "#b3edc5", "#174343", 21),
    ))
    return document("presentation", first + second, automatic=style, masters=page_styles(32, 18))


def draw_fixture():
    shapes = (
        shape("Proof header", 1.7, 1.4, 17.6, 2.2, "Navy", "Release package / alignment proof"),
        shape("Image reference", 2.0, 5.1, 8.3, 7.0, "Slate", "REFERENCE PANEL"),
        shape("Trim panel", 11.3, 5.1, 7.5, 7.0, "Pale", "TRIM PANEL"),
        shape("Reference anchor", 4, 10.6, .9, .7, "Navy"),
        shape("Move anchor", 11.55, 9.1, 2.3, 1.1, "Orange", "MARK"),
        shape("Footer", 1.7, 15.1, 17.6, 1.5, "Navy", "RC-42  /  QA PRINT PROOF"),
    )
    style = graphics_styles((
        ("Navy", "#12324b", "#f2f9fd", 25), ("Slate", "#41618b", "#ffffff", 18),
        ("Pale", "#e3eff6", "#183753", 18), ("Orange", "#ff6d42", "#ffffff", 13),
    ))
    return document("drawing", page("Alignment proof", shapes), automatic=style, masters=page_styles(21, 29.7))


PROFILE = b"""<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
 <item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>
 <item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="ShowTipOfTheDay" oor:op="fuse"><value>false</value></prop></item>
 <item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="ShowDonation" oor:op="fuse"><value>false</value></prop></item>
 <item oor:path="/org.openoffice.Setup/L10N"><prop oor:name="ooLocale" oor:op="fuse"><value>en-US</value></prop></item>
</oor:items>"""


async def open_fixture(d, app, filename, data):
    profile = f"qa-{filename.rsplit('.', 1)[0]}"
    profile_seed = f"{profile}.xcu"
    marker = rf"{ROOT}\{profile}-ready.txt"
    await d.screenshot("office-before-launch")
    await d.key("Shift")
    await d.upload(filename, data)
    await d.upload(profile_seed, PROFILE)
    await d.ps(rf"""
        $userProfile = '{ROOT}\{profile}\user'
        New-Item -Path $userProfile -ItemType Directory -Force | Out-Null
        Copy-Item -LiteralPath '{ROOT}\{profile_seed}' (Join-Path $userProfile 'registrymodifications.xcu')
    """)
    await d.launch(app, [f"-env:UserInstallation=file:///C:/OSLabWall/{profile}",
                         "--nologo", "--norestore", rf"{ROOT}\{filename}"])
    await d.task("OSLabOfficeReady", rf"""
        for ($attempt=0; $attempt -lt 70; $attempt++) {{
            $visible = @(Get-Process -Name 'soffice.bin' -ErrorAction SilentlyContinue |
                Where-Object {{ $_.MainWindowHandle -and $_.MainWindowTitle -like '*{filename}*' }})
            if ($visible.Count -gt 0) {{
                [IO.File]::WriteAllText('{marker}', 'ready')
                break
            }}
            Start-Sleep -Milliseconds 400
        }}
    """)
    await d.wait(f"Test-Path -LiteralPath '{marker}'", seconds=38)
    await d.screenshot(f"{app}-window")
    await d.key("Escape")
    await d.key("Alt", "Space")
    await asyncio.sleep(.3)
    await d.key("x")
    await d.key("Escape")
    await asyncio.sleep(.45)


async def snap(d, name, pause=.38):
    await asyncio.sleep(pause)
    return await d.screenshot(name)


async def read_bytes(d, path):
    script = f"(Get-Item -LiteralPath '{path}').Length"
    length = int((await d.ps(script)).stdout.strip())
    if not 0 < length <= 1_000_000:
        raise RuntimeError(f"Unexpected fixture artifact size: {length}")
    chunks = []
    for offset in range(0, length, 6000):
        count = min(6000, length - offset)
        result = await d.ps(f"""
            $share = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
            $file = [IO.File]::Open('{path}', [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
            try {{
                $file.Position = {offset}
                $buffer = [byte[]]::new({count})
                $total = 0
                while ($total -lt $buffer.Length) {{
                    $read = $file.Read($buffer, $total, $buffer.Length - $total)
                    if ($read -eq 0) {{ throw 'The LibreOffice artifact was truncated during reading' }}
                    $total += $read
                }}
                [Convert]::ToBase64String($buffer)
            }} finally {{ $file.Dispose() }}
        """)
        chunk = base64.b64decode(result.stdout.strip(), validate=True)
        if len(chunk) != count:
            raise RuntimeError("Truncated LibreOffice evidence")
        chunks.append(chunk)
    return b"".join(chunks)


def content(package):
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        return xml.fromstring(archive.read("content.xml"))


def sheet_rows(package):
    sheet = content(package).find(".//table:table", NS)
    rows = []
    for row in sheet.findall("table:table-row", NS)[:6]:
        cells = []
        for cell in row.findall("table:table-cell", NS):
            value = cell.get(element("office", "value"))
            if value is None:
                value = "".join(cell.itertext()).strip()
            else:
                value = int(float(value))
            attributes = cell.attrib
            cells.extend([(value, attributes)] * min(5, int(cell.get(element("table", "number-columns-repeated"), "1"))))
        rows.append(cells)
    return rows


async def calc(d):
    filename = f"release-checks-{uuid4().hex[:6]}.ods"
    path = rf"{ROOT}\{filename}"
    fixture = calc_fixture()
    await open_fixture(d, "calc", filename, fixture)
    await snap(d, "stage-0")
    original = sheet_rows(fixture)
    await d.key("Ctrl", "Home")
    await d.key("Down")
    await d.key("Right")
    await snap(d, "stage-1")
    await d.key("2")
    await d.key("2")
    await d.key("Enter")
    await d.key("Ctrl", "Shift", "F9")
    await snap(d, "stage-2")
    await d.key("Ctrl", "s")
    await d.key("Ctrl", "Home")
    await snap(d, "stage-3", .9)
    await d.key("Ctrl", "w")
    await asyncio.sleep(.8)
    sheet = sheet_rows(await read_bytes(d, path))
    return [
        check("The uploaded baseline contains the 37/42 blocked gate", [37, 42, 5, "BLOCKED"],
              [cell[0] for cell in original[4][1:4]] + [original[5][1][0]]),
        check("Saved repair changed only the Windows x64 input count", [22, 12, 8], [row[1][0] for row in sheet[1:4]]),
        check("Calc stored recalculated totals and deficit", [42, 42, 0], [cell[0] for cell in sheet[4][1:4]]),
        check("The persisted gate formula evaluates to PASS", "PASS", sheet[5][1][0]),
        check("The gate, deficit and totals remain formula cells", True,
              all(element("table", "formula") in attrs for _, attrs in [*sheet[4][1:4], sheet[5][1]])),
    ]


async def export_pdf(d, filename, app):
    basename = filename.rsplit(".", 1)[0]
    target = rf"{ROOT}\{basename}.pdf"
    await d.ps(f"if (Test-Path -LiteralPath '{target}') {{ Remove-Item -LiteralPath '{target}' }}")
    await d.key("Shift", "Escape")
    await asyncio.sleep(.4)
    await d.paste("Export Directly as PDF")
    await d.key("Enter")
    await asyncio.sleep(.7)
    await d.screenshot("pdf-command")
    try:
        controls = await d.inspect(
            r"^soffice(?:\.bin)?$",
            r"^Save As$|^Export$|^다른 이름으로 저장$|^내보내기$|^File name:?\s*$|^파일 이름:?\s*$|^1148$",
        )
        if not controls:
            raise TimeoutError("PDF save dialog was not visible")
        await d.key("Alt", "n")
        await d.key("Ctrl", "a")
        await d.paste(target)
        await d.key("Enter")
        await d.wait(f"Test-Path -LiteralPath '{target}'", seconds=8)
    except (TimeoutError, RuntimeError):
        await d.key("Escape")
        await d.key("Escape")
        # The command palette is localized on some Windows builds. Run the installed
        # LibreOffice converter with an isolated profile against the same saved file.
        await d.ps(rf"""
            $office = "$env:ProgramFiles\LibreOffice\program\soffice.exe"
            $args = '-env:UserInstallation=file:///C:/OSLabWall/qa-render --headless --convert-to pdf:{app}_pdf_Export --outdir {ROOT} {ROOT}\{filename}'
            $result = Start-Process -FilePath $office -ArgumentList $args -Wait -PassThru
            if ($result.ExitCode -ne 0) {{ throw "LibreOffice export failed: $($result.ExitCode)" }}
        """, timeout=55)
        await d.wait(f"Test-Path -LiteralPath '{target}'", seconds=15)
    return await read_bytes(d, target)


def pdf_pages(pdf):
    if not pdf.startswith(b"%PDF-") or not pdf.rstrip().endswith(b"%%EOF"):
        raise ValueError("LibreOffice did not create a complete PDF")
    return len(re.findall(rb"/Type\s*/Page\b", pdf))


def page_dimensions(pdf):
    match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", pdf)
    if not match:
        raise ValueError("PDF has no page media box")
    return tuple(float(n) for n in match.groups())


async def writer(d):
    filename = f"artifact-acceptance-{uuid4().hex[:6]}.odt"
    await open_fixture(d, "writer", filename, writer_fixture())
    await snap(d, "stage-0")
    await d.key("Ctrl", "End")
    await snap(d, "stage-1")
    await d.key("End")
    await d.key("Enter")
    receipt = "APPROVED / 42 artifacts verified / QA receipt BR-042"
    await d.paste(receipt)
    await d.key("Ctrl", "s")
    await snap(d, "stage-2", .8)
    pdf = await export_pdf(d, filename, "writer")
    await d.key("Ctrl", "Home")
    await snap(d, "stage-3")
    await d.key("Ctrl", "w")
    await asyncio.sleep(.8)
    saved = content(await read_bytes(d, rf"{ROOT}\{filename}"))
    paragraphs = ["".join(p.itertext()) for p in saved.findall(".//text:p", NS)]
    width, height = page_dimensions(pdf)
    return [
        check("The release receipt was persisted exactly once", 1, paragraphs.count(receipt)),
        check("The decision page retains its title and sign-off label", True,
              all(line in paragraphs for line in ("Release decision", "QA owner receipt"))),
        check("The acceptance report exports exactly two pages", 2, pdf_pages(pdf)),
        check("The exported page geometry remains A4 portrait", True, abs(width - 595.28) < 1 and abs(height - 841.89) < 1),
    ]


def pixel_count(image, rgb):
    return sum(count for count, color in image.getcolors(image.width * image.height) if color == rgb)


async def impress(d):
    filename = f"release-decision-{uuid4().hex[:6]}.odp"
    fixture = impress_fixture()
    await open_fixture(d, "impress", filename, fixture)
    await snap(d, "stage-0")
    await d.key("F5")
    _, first = await snap(d, "stage-1", 1.4)
    await d.key("Right")
    _, second = await snap(d, "stage-2", .85)
    await d.key("Escape")
    pdf = await export_pdf(d, filename, "impress")
    await snap(d, "stage-3")
    width, height = page_dimensions(pdf)
    return [
        check("Slide 1 filled the slideshow with the candidate navy background", True,
              pixel_count(first, (23, 42, 65)) > first.width * first.height // 4),
        check("Slide 2 used the approved decision teal background", True,
              pixel_count(second, (24, 94, 98)) > second.width * second.height // 4),
        check("The PDF contains both slides", 2, pdf_pages(pdf)),
        check("The released deck remains 16:9", True, abs(width / height - 16 / 9) < .005),
    ]


def mark_position(image):
    rgb = (255, 109, 66)
    pixels = image.load()
    positions = [(x, y) for y in range(150, image.height - 65) for x in range(100, image.width - 170)
                 if pixels[x, y] == rgb]
    if len(positions) < 50:
        raise RuntimeError("The orange registration mark is not visible in Draw")
    return (int(sum(x for x, _ in positions) / len(positions)),
            int(sum(y for _, y in positions) / len(positions)))


def shapes_by_name(package):
    return {shape.get(element("draw", "name")): shape
            for shape in content(package).findall(".//draw:rect", NS)}


def cm(value):
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(cm|mm|in)", value)
    if not match:
        raise ValueError(f"Unexpected geometry unit: {value}")
    return float(match[1]) * {"cm": 1, "mm": .1, "in": 2.54}[match[2]]


async def draw(d):
    filename = f"alignment-proof-{uuid4().hex[:6]}.odg"
    fixture = draw_fixture()
    await open_fixture(d, "draw", filename, fixture)
    frame, image = await snap(d, "stage-0")
    x, y = mark_position(image)
    await d.click(frame, x, y)
    await snap(d, "stage-1")
    for _ in range(4):
        await d.key("Right")
    await snap(d, "stage-2")
    await d.key("Ctrl", "s")
    await asyncio.sleep(.7)
    pdf = await export_pdf(d, filename, "draw")
    await d.key("Escape")
    await snap(d, "stage-3")
    await d.key("Ctrl", "w")
    await asyncio.sleep(.8)
    before = shapes_by_name(fixture)
    current = shapes_by_name(await read_bytes(d, rf"{ROOT}\{filename}"))
    x_attr = element("svg", "x")
    actual_x = cm(current["Move anchor"].get(x_attr))
    old_x = cm(before["Move anchor"].get(x_attr))
    width, height = page_dimensions(pdf)
    return [
        check("The printed registration mark moved right of the original trim", True, old_x + .25 <= actual_x <= old_x + 2),
        check("The adjacent reference anchor kept its exact x position", 4.0, cm(current["Reference anchor"].get(x_attr))),
        check("The release proof is a single PDF page", 1, pdf_pages(pdf)),
        check("The exported release proof retained its A4 bounds", True,
              abs(width - 595.28) < 1 and abs(height - 841.89) < 1),
    ]


async def execute(case_id, d):
    return await {"02": calc, "12": writer, "13": impress, "14": draw}[str(case_id)](d)
