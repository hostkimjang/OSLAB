"""Windows product QA for export bounds, release navigation, search and image diff."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import zipfile
from pathlib import PureWindowsPath
from uuid import uuid4

from PIL import Image, ImageChops, ImageDraw, ImageFont

WORK = PureWindowsPath(r"C:\OSLabWall")
CASES = {
    "17": {
        "title": "Inkscape",
        "kicker": "SVG EXPORT / CLIPPING",
        "scenario": "The vector source contains print bleed. A production raster must keep the page rectangle and exclude the off-page registration mark.",
        "steps": ["Inspect the SVG and print bleed", "Export the page", "Verify dimensions and interior pixels"],
        "package": "inkscape",
    },
    "18": {
        "title": "SumatraPDF",
        "kicker": "DOCUMENT REVIEW / PAGE NAVIGATION",
        "scenario": "Navigate a release packet to the rollback evidence and final sign-off. Check that the correct page renders at every stop.",
        "steps": ["Open the three-page packet", "Jump to rollback evidence", "Navigate to sign-off"],
        "package": "sumatra",
    },
    "19": {
        "title": "Everything",
        "kicker": "RELEASE INVENTORY / EXACT SEARCH",
        "scenario": "Search an actual release directory inventory, remove non-ZIP matches and check the exact set of release-candidate packages.",
        "steps": ["Open the generated file inventory", "Find release-candidate files", "Restrict to ZIPs and copy verified paths"],
        "package": "everything",
    },
    "20": {
        "title": "ImageMagick",
        "kicker": "VISUAL REGRESSION / PIXEL DIFF",
        "scenario": "Detect a changed release badge in a raster baseline comparison, produce a real diff, and confirm the corrected build leaves zero changed pixels.",
        "steps": ["Compare reference and candidate", "Inspect the generated diff", "Compare the corrected candidate"],
        "package": "imagemagick",
    },
}


def check(name, expected, observed):
    return {"name": name, "expected": expected, "observed": observed, "passed": expected == observed}


def path(name):
    return str(WORK / name)


async def snap(desktop, name, delay=.65):
    await asyncio.sleep(delay)
    return await desktop.screenshot(name)


async def read_bytes(desktop, filename):
    result = await desktop.ps(f"[Convert]::ToBase64String([IO.File]::ReadAllBytes('{filename}'))")
    return base64.b64decode(result.stdout.strip(), validate=True)


async def open_output(desktop, filename, *, preferred=""):
    activated = r"""
        $file='__FILE__'
        $viewer='__VIEWER__'
        if ($viewer) {
            $viewerPath=(Get-Command "$viewer.exe" -ErrorAction SilentlyContinue).Source
            if (!$viewerPath) {
                $search=@($env:ProgramFiles, 'C:\OSLabWall', 'C:\OSLabApps') | Where-Object { Test-Path -LiteralPath $_ }
                $viewerPath=(Get-ChildItem -LiteralPath $search -Filter "$viewer.exe" -Recurse -File -ErrorAction SilentlyContinue |
                    Select-Object -First 1).FullName
            }
        }
        if ($viewerPath) { Start-Process -FilePath $viewerPath -ArgumentList ('"' + $file + '"') }
        else { Invoke-Item -LiteralPath $file }
    """
    await desktop.task("OslabOpenVisualEvidence", activated.replace("__FILE__", filename).replace("__VIEWER__", preferred))
    await asyncio.sleep(1.5)


async def magick_on_console(desktop, arguments):
    # Copy the command into the real guest terminal and execute it through MCP.
    binary = await desktop.executable("imagemagick")
    command = f"& '{binary}' " + " ".join(f"'{argument}'" for argument in arguments)
    command += f"; if ($LASTEXITCODE -eq 0) {{ Get-Item -LiteralPath '{arguments[-1]}' | Select-Object Name,Length }}"
    await desktop.task(
        "OslabOpenImageComparison",
        "Start-Process powershell.exe -WindowStyle Normal -ArgumentList '-NoLogo -NoProfile -NoExit'",
    )
    await asyncio.sleep(1.6)
    frame, _ = await desktop.screenshot(PureWindowsPath(arguments[-1]).stem + "-console")
    controls = await desktop.inspect(r"^(conhost|powershell|WindowsTerminal)$", r"Windows PowerShell|Terminal")
    panel = next((control for control in controls if control["y"] > 50 and control.get("width", 0) > 120), None)
    if panel:
        await desktop.click(frame, panel["x"], panel["y"])
    await desktop.paste(command)
    await desktop.key("Enter")


async def show_image_difference(desktop, filename):
    # Launch the native viewer directly so Windows never prompts for a PNG association.
    await desktop.task("OslabDisplayImageDifference", rf"""
        $viewer=Join-Path $env:ProgramFiles 'Windows Photo Viewer\PhotoViewer.dll'
        if (!(Test-Path -LiteralPath $viewer)) {{ throw 'Windows Photo Viewer is unavailable' }}
        $arguments='"' + $viewer + '",ImageView_Fullscreen {filename}'
        Start-Process rundll32.exe -ArgumentList $arguments
    """)
    await asyncio.sleep(1.3)


def export_fixture():
    target = path("toolbar-proof.png")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="640" height="360" viewBox="0 0 640 360" inkscape:export-filename="{target}" inkscape:export-xdpi="96" inkscape:export-ydpi="96">
  <rect width="640" height="360" fill="#142844"/>
  <rect x="35" y="28" width="570" height="304" rx="25" fill="#203e64"/>
  <text x="63" y="77" fill="#b3dffe" font-size="15" font-family="Segoe UI" font-weight="bold">WINDOWS DESKTOP / RELEASE ASSET</text>
  <text x="63" y="122" fill="#f1f6ff" font-size="40" font-family="Segoe UI" font-weight="bold">Toolbar raster proof</text>
  <rect x="65" y="162" width="124" height="112" rx="12" fill="#15304b"/>
  <rect x="205" y="162" width="124" height="112" rx="12" fill="#15304b"/>
  <rect x="345" y="162" width="124" height="112" rx="12" fill="#15304b"/>
  <path d="M92 220l21 20 46-47" fill="none" stroke="#61e4c1" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M266 187l39 69h-78z" fill="#e2ac58"/>
  <circle cx="407" cy="219" r="35" fill="#ad99f2"/>
  <rect x="504" y="194" width="79" height="53" rx="9" fill="#57d6ac"/>
  <text x="521" y="228" fill="#102a3d" font-size="22" font-family="Segoe UI" font-weight="bold">1x</text>
  <text x="67" y="307" fill="#a9bfdb" font-size="17" font-family="Segoe UI">640 x 360 px / export the page rectangle</text>
  <rect x="657" y="146" width="68" height="68" fill="#f0455b"/>
  <path d="M665 154l52 52M717 154l-52 52" stroke="white" stroke-width="6"/>
</svg>'''.encode()


async def inkscape(desktop):
    source = path("toolbar-proof.svg")
    target = path("toolbar-proof.png")
    await desktop.upload("toolbar-proof.svg", export_fixture())
    await desktop.launch("inkscape", [source])
    await snap(desktop, "inkscape-open", 2.5)
    await desktop.key("Win", "Up")
    await desktop.key("4")
    await snap(desktop, "stage-0")
    await desktop.key("5")
    await desktop.key("Ctrl", "Shift", "e")
    await snap(desktop, "stage-1", 1.6)
    try:
        export_buttons = await desktop.inspect(r"^inkscape$", r"^Export$|^Export Image$")
    except TimeoutError:
        export_buttons = []
    if choice := next((row for row in export_buttons if row["x"] > 750 and row["y"] > 320), None):
        frame, _ = await desktop.screenshot("inkscape-export-target")
        await desktop.click(frame, choice["x"], choice["y"])
        try:
            await desktop.wait(f"Test-Path -LiteralPath '{target}'", seconds=4)
        except TimeoutError:
            pass
    existing = await desktop.ps(f"[int](Test-Path -LiteralPath '{target}')")
    if existing.stdout.strip() != "1":
        # The GTK release may not expose the export button to Win32 UI Automation.
        await desktop.launch("inkscape", [source, "--export-area-page", "--export-type=png", f"--export-filename={target}"])
    await desktop.wait(f"Test-Path -LiteralPath '{target}'", seconds=18)
    await desktop.key("Escape")
    await desktop.key("3")
    await snap(desktop, "stage-2")
    await open_output(desktop, target)
    await snap(desktop, "stage-3")
    with Image.open(io.BytesIO(await read_bytes(desktop, target))) as png:
        mode, size = png.format, list(png.size)
        rgb = png.convert("RGB")
        pad = list(rgb.getpixel((10, 10)))
        badge = list(rgb.getpixel((556, 212)))
        bleed = list(rgb.getdata()).count((240, 69, 91))
    return [
        check("Actual Inkscape output format", "PNG", mode),
        check("Page export has the expected size", [640, 360], size),
        check("Page corner stays opaque navy", [20, 40, 68], pad),
        check("Release badge retains its interior color", [87, 214, 172], badge),
        check("Off-page red registration mark is clipped", 0, bleed),
    ]


PAGES = (
    ("Candidate overview", (32, 82, 148),
     (("CANDIDATE RC-42", "Widget desktop release"), ("PLATFORM", "Windows 11 x64"), ("GATE", "Review rollback evidence"))),
    ("Rollback evidence", (112, 57, 146),
     (("VERSION PAIR", "2.4.0 to 2.3.8"), ("RECOVERY CASE", "Restore prior user configuration"), ("EXPECTED", "Both exports stay byte-identical"))),
    ("Release sign-off", (34, 104, 86),
     (("EVIDENCE TYPE", "Release engineering checklist"), ("SCOPE", "Artifact, migration, smoke test"), ("HANDOFF", "Package in release candidate folder"))),
)


def pdf_string(value):
    return "(" + value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def qa_pdf():
    """A synthetic vector PDF release packet with real page outlines."""
    def content(index, title, color, rows):
        red, green, blue = (channel / 255 for channel in color)
        operations = [
            ".934 .958 .98 rg 0 0 620 776 re f",
            f"{red:.5f} {green:.5f} {blue:.5f} rg 0 555 620 221 re f",
        ]

        def line(value, x, y, size, fill, font="F1"):
            operations.append(f"{fill} rg BT /{font} {size} Tf {x} {y} Td {pdf_string(value)} Tj ET")

        line("DESKTOP RELEASE / EVIDENCE PACKET", 42, 715, 15, "1 1 1", "F2")
        line(title, 42, 642, 45, "1 1 1", "F2")
        line(f"PAGE {index:02} OF {len(PAGES):02}", 44, 598, 17, "1 1 1", "F2")
        for row, (label, value) in enumerate(rows):
            y = 412 - 117 * row
            operations.append(f"1 1 1 rg 42 {y - 30} 535 93 re f")
            line(label, 64, y + 27, 12, ".31 .40 .54", "F2")
            line(value, 64, y - 4, 21, ".11 .17 .27")
        line("Synthetic test fixture / no production data", 44, 46, 11, ".31 .40 .54")
        return ("\n".join(operations) + "\n").encode("ascii")

    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R /Outlines 5 0 R /PageMode /UseOutlines >>",
        2: b"<< /Type /Pages /Kids [6 0 R 9 0 R 12 0 R] /Count 3 >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        5: b"<< /Type /Outlines /First 8 0 R /Last 14 0 R /Count 3 >>",
    }
    for i, (title, color, data) in enumerate(PAGES):
        page = 6 + i * 3
        stream = content(i + 1, title, color, data)
        objects[page] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 620 776] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {page + 1} 0 R >>"
        ).encode("ascii")
        objects[page + 1] = f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream"
        links = (f"/Prev {page - 1} 0 R " if i else "") + (f"/Next {page + 5} 0 R " if i < 2 else "")
        objects[page + 2] = (
            f"<< /Title {pdf_string(title)} /Parent 5 0 R /Dest [{page} 0 R /Fit] {links}>>"
        ).encode("ascii")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in sorted(objects.items()):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    out.extend("".join(f"{offset:010} 00000 n \n" for offset in offsets[1:]).encode())
    out.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(out)


def displayed_page(image):
    # The large, unique document header is present only when that page is rendered.
    thumbnail = image.convert("RGB")
    thumbnail.thumbnail((320, 200))
    hits = [0] * len(PAGES)
    for pixel in thumbnail.getdata():
        for i, (_, color, _) in enumerate(PAGES):
            hits[i] += all(abs(left - right) <= 4 for left, right in zip(pixel, color))
    page = max(range(len(PAGES)), key=hits.__getitem__)
    if hits[page] >= 200:
        return page + 1
    return None


async def sumatra(desktop):
    packet = qa_pdf()
    target = path("desktop-release-packet.pdf")
    await desktop.upload("desktop-release-packet.pdf", packet)
    await desktop.launch("sumatra", ["-page", "1", "-view", "single page", "-zoom", "fit page", target])
    await snap(desktop, "sumatra-open", 1.7)
    await desktop.key("Win", "Up")
    await desktop.key("Ctrl", "6")
    await desktop.key("Ctrl", "0")
    # A busy guest can show the window a few seconds before the first page is drawn.
    _, initial = await snap(desktop, "sumatra-render")
    for _ in range(10):
        if displayed_page(initial) == 1:
            break
        _, initial = await snap(desktop, "sumatra-render", 1.0)
    _, initial = await snap(desktop, "stage-0", .2)
    await desktop.key("Ctrl", "g")
    await desktop.key("Ctrl", "a")
    await desktop.key("2")
    await snap(desktop, "stage-1")
    await desktop.key("Enter")
    _, rollback = await snap(desktop, "stage-2")
    await desktop.key("n")
    _, signoff = await snap(desktop, "stage-3")
    result = await desktop.ps(f"(Get-FileHash -LiteralPath '{target}' -Algorithm SHA256).Hash.ToLowerInvariant()")
    return [
        check("Rendered first page is the candidate overview", 1, displayed_page(initial)),
        check("Go to page renders the rollback evidence", 2, displayed_page(rollback)),
        check("Next page renders the release sign-off", 3, displayed_page(signoff)),
        check("Reviewing in SumatraPDF preserves the source bytes", hashlib.sha256(packet).hexdigest(), result.stdout.strip()),
    ]


RELEASE_FILES = {
    "release-rc-x64.zip": "candidate 42 x64 payload",
    "release-rc-arm64.zip": "candidate 42 ARM64 payload",
    "release-rc-notes.txt": "review checklist for candidate 42",
    "release-stable-x64.zip": "previous x64 production payload",
    "symbols-x64.zip": "debugging symbols for build comparison",
}


async def everything(desktop):
    attempt = uuid4().hex[:6]
    directory = path(f"release-index-{attempt}")
    index = path(f"release-index-{attempt}.efu")
    clipboard = path(f"release-query-export-{attempt}.txt")
    create_fixtures = [f"New-Item -ItemType Directory -Path '{directory}' -Force | Out-Null"]
    for name, content in RELEASE_FILES.items():
        data = content.encode("ascii")
        if name.endswith(".zip"):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.txt", data)
            data = stream.getvalue()
        await desktop.upload(name, data)
        create_fixtures.append(f"Move-Item -LiteralPath '{path(name)}' -Destination '{directory}'")
    await desktop.ps("\n".join(create_fixtures))
    await desktop.launch("everything", ["-create-file-list", index, directory])
    await desktop.wait(f"Test-Path -LiteralPath '{index}'", seconds=20)
    await desktop.launch("everything", ["-filelist", index])
    await snap(desktop, "everything-open", 1.5)
    await desktop.key("Win", "Up")
    await snap(desktop, "stage-0")
    await desktop.key("Ctrl", "f")
    await desktop.key("Ctrl", "a")
    await desktop.paste("release-rc")
    await snap(desktop, "stage-1")
    await desktop.key("Ctrl", "f")
    await desktop.key("Ctrl", "a")
    await desktop.paste("release-rc ext:zip")
    frame, _ = await snap(desktop, "stage-2")
    results = await desktop.inspect(r"^Everything$", r"^release-rc-(x64|arm64)\.zip$")
    result = next((item for item in results if item["y"] >= 55 and item["x"] < frame["width"] // 2), None)
    if result is not None:
        await desktop.click(frame, result["x"], result["y"])
    else:
        await desktop.key("Down")
    await desktop.key("Ctrl", "a")
    await desktop.key("Ctrl", "Shift", "c")
    await snap(desktop, "stage-3")
    await desktop.task("OslabReadEverythingPaths", f"""
        $selection=Get-Clipboard -Raw -TextFormatType Text
        [IO.File]::WriteAllText('{clipboard}', [string]$selection, [Text.UTF8Encoding]::new($false))
    """)
    await desktop.wait(f"Test-Path -LiteralPath '{clipboard}'", seconds=8)
    copied = (await read_bytes(desktop, clipboard)).decode("utf-8").splitlines()
    observed = sorted(line.strip().strip('"').casefold() for line in copied if line.strip())
    expected = sorted(f"{directory}\\{name}".casefold() for name in ("release-rc-arm64.zip", "release-rc-x64.zip"))
    indexed = (await read_bytes(desktop, index)).decode("utf-8-sig")
    return [
        check("Everything indexed five controlled release files", 5, sum(name in indexed for name in RELEASE_FILES)),
        check("The UI result set contains only candidate ZIP files", expected, observed),
        check("Candidate notes and stable ZIP do not appear in exported results", [], [
            PureWindowsPath(item).name for item in observed if "notes" in item or "stable" in item
        ]),
    ]


WIDTH, HEIGHT = 640, 360
DIFF_RECT = (412, 157, 556, 218)


def raster_fixture(broken=False):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#151d32")
    draw = ImageDraw.Draw(image)
    try:
        title = ImageFont.truetype("segoeuib.ttf", 34)
        subtitle = ImageFont.truetype("segoeui.ttf", 17)
    except OSError:
        title = subtitle = ImageFont.load_default()
    draw.rectangle((24, 26, 616, 330), fill="#26334b")
    draw.text((52, 55), "Windows desktop / artifact review", fill="#89bbd0", font=subtitle)
    draw.text((52, 92), "Build status badge", fill="#edf6fb", font=title)
    for i, length in enumerate((218, 140, 191)):
        y = 164 + 38 * i
        draw.rounded_rectangle((56, y, 56 + length, y + 12), radius=4, fill="#647995")
    x1, y1, x2, y2 = DIFF_RECT
    draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill="#d7826b" if broken else "#64d9b1")
    draw.text((52, 277), "Snapshot QA / color contract", fill="#ccdaed", font=subtitle)
    memory = io.BytesIO()
    image.save(memory, "PNG")
    return memory.getvalue()


async def imagemagick(desktop):
    attempt = uuid4().hex[:6]
    baseline = path(f"baseline-badge-{attempt}.png")
    candidate = path(f"candidate-badge-{attempt}.png")
    repaired = path(f"fixed-badge-{attempt}.png")
    delta = path(f"badge-regression-diff-{attempt}.png")
    verified = path(f"badge-fixed-diff-{attempt}.png")
    for artifact, broken in ((baseline, False), (candidate, True), (repaired, False)):
        await desktop.upload(PureWindowsPath(artifact).name, raster_fixture(broken))
    await show_image_difference(desktop, candidate)
    await desktop.screenshot("candidate-viewer")
    await desktop.key("Win", "Up")
    _, broken = await snap(desktop, "stage-0")
    await magick_on_console(desktop, [baseline, candidate, "-compose", "difference", "-composite", delta])
    await desktop.wait(f"Test-Path -LiteralPath '{delta}'", seconds=15)
    await snap(desktop, "magick-produced-regression-diff", .3)
    await show_image_difference(desktop, delta)
    await snap(desktop, "stage-1")
    await magick_on_console(desktop, [baseline, repaired, "-compose", "difference", "-composite", verified])
    await desktop.wait(f"Test-Path -LiteralPath '{verified}'", seconds=15)
    await snap(desktop, "magick-produced-fixed-diff", .3)
    await show_image_difference(desktop, repaired)
    await snap(desktop, "stage-2")
    await show_image_difference(desktop, verified)
    _, fixed = await snap(desktop, "stage-3")

    def read_png(data):
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB")

    delta_image = read_png(await read_bytes(desktop, delta))
    fixed_image = read_png(await read_bytes(desktop, verified))
    reference = read_png(raster_fixture())
    change = read_png(raster_fixture(True))
    independent = ImageChops.difference(reference, change)
    failures = sum(color != (0, 0, 0) for color in delta_image.getdata())
    residual = sum(color != (0, 0, 0) for color in fixed_image.getdata())
    x1, y1, x2, y2 = DIFF_RECT
    return [
        check("ImageMagick identifies the precise changed bounding box", list(DIFF_RECT), list(delta_image.getbbox() or ())),
        check("Visual difference detects exactly the released badge pixels", (x2 - x1) * (y2 - y1), failures),
        check("ImageMagick diff agrees with independent pixel arithmetic", True,
              ImageChops.difference(delta_image, independent).getbbox() is None),
        check("Corrected raster yields zero changed pixels", 0, residual),
        check("The displayed comparison changes from candidate to repaired diff", True,
              broken.tobytes() != fixed.tobytes()),
    ]


async def execute(case_id, desktop):
    workflows = {"17": inkscape, "18": sumatra, "19": everything, "20": imagemagick}
    return await workflows[str(case_id)](desktop)
