"""MCP-only desktop input and independent evidence for four native Windows apps."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import re
import zipfile

from PIL import Image, ImageDraw, ImageFont

GUEST_ROOT = r"C:\OSLabWall"
NATIVE = {
    "29": {
        "title": "Notepad",
        "kicker": "WINDOWS NATIVE · RELEASE HANDOFF",
        "scenario": "Approve a staged release in a text manifest. Save and reopen the result.",
        "steps": ["Open the release record", "Change the handoff gate", "Save and reopen"],
    },
    "30": {
        "title": "File Explorer",
        "kicker": "WINDOWS NATIVE · EVIDENCE RECOVERY",
        "scenario": "Restore an evidence bundle through the compressed-folder UI and check both exported files.",
        "steps": ["Open the zipped evidence", "Copy to recovery workspace", "Verify both SHA-256 hashes"],
    },
    "31": {
        "title": "Paint",
        "kicker": "WINDOWS NATIVE · ARTWORK REVIEW",
        "scenario": "Fill the approval tile in a PNG and check that the surrounding artwork stays unchanged.",
        "steps": ["Open the approval artwork", "Fill the review tile", "Save and inspect the PNG"],
    },
    "32": {
        "title": "Calculator",
        "kicker": "WINDOWS NATIVE · ORDER VALIDATION",
        "scenario": "Multiply a carton order, deduct the reserve, and get the exact number of pallet loads.",
        "steps": ["Calculate 375 × 24", "Deduct 240 reserve units", "Divide by 120 units per pallet"],
    },
}


def check(name, expected, observed):
    return {"name": name, "expected": expected, "observed": observed, "passed": expected == observed}


async def ps_json(desktop, script):
    output = await desktop.ps(
        "$text=(& {\n" + script + "\n} | Out-String); "
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($text))"
    )
    return json.loads(base64.b64decode(output.stdout.strip(), validate=True))


async def keys(desktop, characters):
    for key in characters:
        await desktop.key("Space" if key == " " else key)


async def snap(desktop, name, settle=.5):
    await asyncio.sleep(settle)
    return await desktop.screenshot(name)


async def inspect_controls(desktop, process_names, control_pattern):
    """Read the interactive user's UI Automation tree. Send input only via MCP."""
    request = rf"{GUEST_ROOT}\native-controls.json"
    await desktop.ps(rf"if (Test-Path -LiteralPath '{request}') {{ Remove-Item -LiteralPath '{request}' }}")
    scanner = r"""
        $ErrorActionPreference = 'Stop'
        try {
            Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
            $Automation = [System.Windows.Automation.AutomationElement]
            $scope = [System.Windows.Automation.TreeScope]
            $trueCondition = [System.Windows.Automation.Condition]::TrueCondition
            $pids = @(Get-Process | Where-Object { $_.ProcessName -match '__PROCESS__' } | ForEach-Object Id)
            $results = @(foreach ($window in $Automation::RootElement.FindAll($scope::Children, $trueCondition)) {
                if ($window.Current.ProcessId -notin $pids) { continue }
                foreach ($control in (@($window) + @($window.FindAll($scope::Descendants, $trueCondition)))) {
                    try {
                        $property = $control.Current
                        $box = $property.BoundingRectangle
                        if ($property.IsOffscreen -or $box.IsEmpty -or $box.Width -le 0 -or $box.Height -le 0) { continue }
                        if ($property.AutomationId -notmatch '__CONTROL__' -and $property.Name -notmatch '__CONTROL__') { continue }
                        [pscustomobject]@{name=$property.Name; id=$property.AutomationId; class=$property.ClassName;
                            kind=$property.ControlType.ProgrammaticName; x=[int]($box.Left+$box.Width/2);
                            y=[int]($box.Top+$box.Height/2); width=[int]$box.Width; height=[int]$box.Height}
                    } catch [System.Windows.Automation.ElementNotAvailableException] { continue }
                }
            })
            $value = ConvertTo-Json -InputObject @($results) -Depth 4 -Compress
        } catch {
            $value = ConvertTo-Json -InputObject @{error=$_.Exception.Message} -Compress
        }
        [IO.File]::WriteAllText('__REQUEST__', $value, [Text.UTF8Encoding]::new($false))
    """
    script = (scanner.replace("__PROCESS__", process_names)
              .replace("__CONTROL__", control_pattern).replace("__REQUEST__", request))
    await desktop.task("OSLabNativeInspect", script)
    await desktop.wait(rf"Test-Path -LiteralPath '{request}'", seconds=20)
    result = await ps_json(desktop, rf"Get-Content -LiteralPath '{request}' -Encoding UTF8 -Raw")
    if isinstance(result, dict):
        raise RuntimeError(f"Windows UI Automation observation failed: {result.get('error', result)}")
    return result


async def click_control(desktop, frame, controls, *, preferred=()):
    usable = [row for row in controls if 0 <= row["x"] < frame["width"] and 0 <= row["y"] < frame["height"]]
    if not usable:
        return False
    match = min(usable, key=lambda row: (row["kind"] not in preferred, row["width"] * row["height"]))
    await desktop.click(frame, match["x"], match["y"])
    return True


async def notepad(desktop):
    path = rf"{GUEST_ROOT}\handoff-record.txt"
    original = "SHIPMENT HANDOFF\r\nRelease: OSLAB-113\r\nDestination: West dock\r\nManifest: 7 records\r\ngate=hold"
    updated = original.removesuffix("hold") + "ready"
    await desktop.upload("handoff-record.txt", original.encode())
    launch = rf"Start-Process notepad.exe -ArgumentList '{path}'"
    await desktop.task("OSLabNativeNotepad", launch)
    await snap(desktop, "app-launch", 2)
    await desktop.key("Win", "Up")
    await snap(desktop, "stage-0")
    await desktop.key("Ctrl", "End")
    await desktop.key("Shift", "Home")
    await snap(desktop, "stage-1")
    await keys(desktop, "gate=ready")
    await snap(desktop, "stage-2")
    await desktop.key("Ctrl", "s")
    await desktop.wait(rf"(Get-Content -LiteralPath '{path}' -Tail 1) -ceq 'gate=ready'", seconds=16)
    await desktop.key("Alt", "F4")
    await asyncio.sleep(.6)
    await desktop.task("OSLabNativeReopen", launch)
    await snap(desktop, "stage-3", 1.4)
    actual = await ps_json(desktop, rf"""
        $text=[IO.File]::ReadAllText('{path}')
        @{{gate=($text.TrimEnd() -split '\r?\n')[-1]; lines=($text.TrimEnd() -split '\r?\n').Count;
           hash=(Get-FileHash -LiteralPath '{path}' -Algorithm SHA256).Hash.ToLowerInvariant()}} | ConvertTo-Json -Compress
    """)
    return [
        check("The edited release gate was saved to disk", "gate=ready", actual["gate"]),
        check("Unchanged manifest lines and text encoding match exactly", hashlib.sha256(updated.encode()).hexdigest(), actual["hash"]),
        check("The reopened handoff record still has five lines", 5, actual["lines"]),
    ]


async def explorer(desktop):
    inputs = {
        "checksums.txt": b"OSLab artifact ledger\r\nrecorded=2\r\n",
        "shipment-manifest.csv": b"shipment,destination\r\nOS-17,West Dock\r\nOS-29,North Yard\r\n",
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in inputs.items():
            bundle.writestr(name, data)
    await desktop.upload("release-evidence.zip", archive.getvalue())
    source = rf"{GUEST_ROOT}\release-evidence.zip"
    target = rf"{GUEST_ROOT}\Recovered Evidence"
    await desktop.ps(rf"New-Item -Path '{target}' -ItemType Directory -Force | Out-Null")
    await desktop.task("OSLabNativeArchive", rf"""Start-Process explorer.exe -ArgumentList '"{source}"'""")
    await snap(desktop, "archive-launch", 1.7)
    await desktop.key("Win", "Up")
    frame, _ = await snap(desktop, "stage-0")
    rows = await inspect_controls(desktop, "^explorer$", "checksums|shipment-manifest")
    frame, _ = await desktop.screenshot("archive-entries")
    if not await click_control(desktop, frame, rows, preferred=("ControlType.ListItem", "ControlType.DataItem")):
        raise RuntimeError("File Explorer did not expose the archive entries")
    await desktop.key("Ctrl", "a")
    await desktop.key("Ctrl", "c")
    await snap(desktop, "stage-1")
    await desktop.task("OSLabNativeRecovery", rf"""Start-Process explorer.exe -ArgumentList '"{target}"'""")
    await snap(desktop, "stage-2", 1.3)
    await desktop.key("Ctrl", "v")
    await desktop.wait(rf"Test-Path -LiteralPath '{target}\shipment-manifest.csv'", seconds=20)
    await snap(desktop, "stage-3")
    results = await ps_json(desktop, rf"""
        $files=@(Get-ChildItem -LiteralPath '{target}' -File)
        $hashes=@{{}}
        foreach ($file in $files) {{
            $hashes[$file.Name]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }}
        @{{count=$files.Count; hashes=$hashes}} | ConvertTo-Json -Depth 4 -Compress
    """)
    return [check("Explorer recovered exactly two files", 2, results["count"])] + [
        check(f"Recovered {name} SHA-256 matches the archive entry", hashlib.sha256(data).hexdigest(), results["hashes"].get(name))
        for name, data in inputs.items()
    ]


PAINT_TARGET = (242, 186, 230)
PAINT_BACKGROUND = (19, 47, 67)
PAINT_SIZE = (720, 428)
PAINT_PATCH = (398, 161, 661, 312)


def paint_fixture():
    image = Image.new("RGB", PAINT_SIZE, PAINT_BACKGROUND)
    draw = ImageDraw.Draw(image)
    try:
        title = ImageFont.truetype("segoeuib.ttf", 33)
        subtitle = ImageFont.truetype("segoeuib.ttf", 16)
    except OSError:
        title = subtitle = ImageFont.load_default()
    draw.text((36, 31), "FULFILLMENT QA", font=subtitle, fill="#87dfbd")
    draw.text((36, 58), "Pallet artwork proof", font=title, fill="#f7f6ee")
    draw.rounded_rectangle((39, 143, 356, 339), radius=16, fill="#244d5b")
    draw.polygon([(60, 236), (164, 185), (262, 223), (163, 278)], fill="#e2a95f")
    draw.polygon([(60, 236), (163, 278), (163, 305), (60, 273)], fill="#b2694b")
    draw.polygon([(163, 278), (262, 223), (262, 258), (163, 305)], fill="#ce864f")
    draw.text((60, 314), "REFERENCE ART · KEEP UNCHANGED", font=subtitle, fill="#e6efe9")
    draw.rounded_rectangle((375, 143, 685, 365), radius=16, fill="#2e455b")
    draw.rectangle(PAINT_PATCH, fill=PAINT_TARGET)
    draw.text((399, 324), "APPROVAL TILE · FILL BLACK", font=subtitle, fill="#f9eff0")
    draw.text((36, 389), "EXPORT FORMAT   PNG  /  TARGET SIZE   720 × 428", font=subtitle, fill="#bcd6e6")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def find_target(image):
    pixels = image.load()
    width, height = image.size
    matches = [(x, y) for y in range(142, height) for x in range(width) if pixels[x, y] == PAINT_TARGET]
    if len(matches) < 300:
        raise RuntimeError("Visible Paint approval tile not found")
    return ((min(x for x, _ in matches) + max(x for x, _ in matches)) // 2,
            (min(y for _, y in matches) + max(y for _, y in matches)) // 2)


async def open_paint(desktop, path):
    report = rf"{GUEST_ROOT}\paint-inventory.json"
    await desktop.ps(rf"if (Test-Path -LiteralPath '{report}') {{ Remove-Item -LiteralPath '{report}' }}")
    await desktop.task("OSLabNativePaint", rf"""
        $names = @('Microsoft.Paint','Microsoft.MSPaint')
        $package = Get-AppxPackage | Where-Object {{ $_.Name -in $names }} |
            Sort-Object Version -Descending | Select-Object -First 1
        if (!$package) {{
            $staged = Get-AppxPackage -AllUsers | Where-Object {{ $_.Name -in $names }} |
                Sort-Object Version -Descending | Select-Object -First 1
            if ($staged.InstallLocation) {{
                $manifestPath = Join-Path $staged.InstallLocation 'AppxManifest.xml'
                try {{
                    Add-AppxPackage -Register $manifestPath -DisableDevelopmentMode -ErrorAction Stop
                    $package = Get-AppxPackage -Name $staged.Name | Select-Object -First 1
                }} catch {{ $registrationError = $_.Exception.Message }}
            }}
        }}
        $appId = Get-StartApps | Where-Object {{ $_.AppId -match '^Microsoft\.(Paint|MSPaint)_' }} |
            Select-Object -First 1 -ExpandProperty AppId
        if (!$appId -and $package) {{
            $manifest = Get-AppxPackageManifest -Package $package.PackageFullName -ErrorAction SilentlyContinue
            $manifestApp = $manifest.Package.Applications.Application | Select-Object -First 1
            if ($manifestApp.Id) {{ $appId = $package.PackageFamilyName + '!' + $manifestApp.Id }}
        }}
        $command = Get-Command mspaint.exe -ErrorAction SilentlyContinue
        $record = @{{appId=[string]$appId; package=[string]$package.Name;
            command=[string]$command.Source; registrationError=[string]$registrationError}}
        [IO.File]::WriteAllText('{report}', (ConvertTo-Json -InputObject $record -Compress), [Text.UTF8Encoding]::new($false))
        if ($appId) {{
            Start-Process explorer.exe -ArgumentList "shell:AppsFolder\$appId"
        }} elseif ($command) {{
            Start-Process -FilePath $command.Source -ArgumentList '"{path}"'
        }}
    """)
    await desktop.wait(rf"Test-Path -LiteralPath '{report}'", seconds=35)
    inventory = await ps_json(desktop, rf"Get-Content -LiteralPath '{report}' -Encoding UTF8 -Raw")
    if not inventory["command"] and not inventory["appId"]:
        raise RuntimeError("This guest has no working Paint app registration or local executable")
    _, image = await snap(desktop, "painting-launch", 4)
    try:
        find_target(image)
    except RuntimeError:
        visible = await inspect_controls(desktop, "^(mspaint|PaintApp|ApplicationFrameHost)$", r"그림판|(^| )Paint$")
        if not visible:
            raise RuntimeError("Paint is registered but did not open in the interactive desktop")
        await desktop.task("OSLabNativePaintPath", f"Set-Clipboard -Value '{path}'")
        await desktop.wait("(Get-ScheduledTask -TaskName 'OSLabNativePaintPath').State -eq 'Ready'", seconds=12)
        await desktop.key("Ctrl", "o")
        await snap(desktop, "paint-open-file", 1.65)
        await desktop.key("Alt", "n")
        await desktop.key("Ctrl", "a")
        await desktop.key("Ctrl", "v")
        await snap(desktop, "paint-file-path", .4)
        await desktop.key("Enter")
        await asyncio.sleep(1.65)

    await desktop.key("Win", "Up")
    _, image = await snap(desktop, "stage-0", 1.5)
    try:
        return find_target(image)
    except RuntimeError as error:
        raise RuntimeError("Paint opened but could not display the artwork fixture") from error


async def paint(desktop):
    path = rf"{GUEST_ROOT}\pallet-proof.png"
    await desktop.upload("pallet-proof.png", paint_fixture())
    target = await open_paint(desktop, path)
    fill = await inspect_controls(desktop, "^(mspaint|PaintApp|ApplicationFrameHost)$",
                                  "채우기|Fill with color|Color fill|Fill color|FillTool|ToolFill|Bucket")
    frame, _ = await desktop.screenshot("painting-tools")
    if not await click_control(desktop, frame, fill, preferred=("ControlType.RadioButton", "ControlType.Button")):
        raise RuntimeError("Paint did not expose a Fill tool in the visible tool ribbon")
    frame, _ = await snap(desktop, "stage-1")
    await desktop.click(frame, *target)
    await snap(desktop, "stage-2")
    await desktop.key("Ctrl", "s")
    await snap(desktop, "stage-3")
    actual = await ps_json(desktop, rf"""
        Add-Type -AssemblyName System.Drawing
        $image=[Drawing.Bitmap]::new('{path}')
        try {{
            function Get-Rgb($x,$y) {{
                $p=$image.GetPixel($x,$y)
                [int[]]@($p.R,$p.G,$p.B)
            }}
            @{{kind=$image.RawFormat.Guid -eq [Drawing.Imaging.ImageFormat]::Png.Guid;
               size=@($image.Width,$image.Height); approved=@(Get-Rgb 529 236); control=@(Get-Rgb 25 25)}} |
                ConvertTo-Json -Depth 4 -Compress
        }} finally {{ $image.Dispose() }}
    """)
    return [
        check("Paint saved a PNG", True, actual["kind"]),
        check("PNG dimensions survived the edit", list(PAINT_SIZE), actual["size"]),
        check("The center of the filled approval tile is black", [0, 0, 0], actual["approved"]),
        check("The untouched control pixel kept its RGB values", list(PAINT_BACKGROUND), actual["control"]),
    ]


async def calculator_value(desktop):
    results = await inspect_controls(desktop, "^(CalculatorApp|Calculator|ApplicationFrameHost|calc)$", "^CalculatorResults$")
    for row in results:
        if row["id"] == "CalculatorResults":
            digits = re.sub(r"[^0-9]", "", row["name"])
            if digits:
                return int(digits)
    raise RuntimeError("The Calculator display was not visible in UI Automation")


async def calculator(desktop):
    await desktop.task("OSLabNativeCalculator", "Start-Process calc.exe")
    await snap(desktop, "calculator-launch", 1.8)
    await desktop.key("Win", "Up")
    await desktop.key("Escape")
    frame, _ = await snap(desktop, "calculator-ready")
    controls = await inspect_controls(desktop, "^(CalculatorApp|Calculator|ApplicationFrameHost|calc)$",
                                      "History.*(Clear|Delete)|(Clear|Delete).*History|기록 지우기")
    frame, _ = await desktop.screenshot("calculator-history")
    await click_control(desktop, frame, controls, preferred=("ControlType.Button",))
    await desktop.key("Escape")
    await snap(desktop, "stage-0")
    observed = []
    for i, (operator, digits) in enumerate((("*", "24"), ("-", "240"), ("/", "120")), start=1):
        if i == 1:
            await keys(desktop, "375")
        if operator == "*":
            controls = await inspect_controls(desktop, "^(CalculatorApp|Calculator|ApplicationFrameHost|calc)$",
                                              "^multiplyButton$|^Multiply$|^곱하기$")
            frame, _ = await desktop.screenshot("calculator-multiply")
            if not await click_control(desktop, frame, controls, preferred=("ControlType.Button",)):
                raise RuntimeError("Calculator's multiplication button is not visible")
        else:
            await desktop.key(operator)
        await keys(desktop, digits)
        await desktop.key("Enter")
        await snap(desktop, f"stage-{i}")
        observed.append(await calculator_value(desktop))
    return [
        check("Calculator displayed 375 cartons × 24 units", 9000, observed[0]),
        check("Removing 240 reserve units left exactly 8,760", 8760, observed[1]),
        check("Calculator displayed exactly 73 pallets", 73, observed[2]),
    ]


async def execute(case_id, desktop):
    cases = {"29": notepad, "30": explorer, "31": paint, "32": calculator}
    return {"checks": await cases[str(case_id)](desktop)}
