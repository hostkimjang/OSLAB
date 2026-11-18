"""Archive, release configuration, migration, and merge checks in real desktop apps."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import sqlite3
import zipfile
from configparser import ConfigParser
from contextlib import closing


ROOT = r"C:\OSLabWall"
CASES = {
    "01": {
        "title": "7-Zip File Manager",
        "kicker": "PACKAGING QA",
        "scenario": "Restore a build delivery ZIP and compare every recovered file to its release manifest.",
        "steps": ["Inspect the release archive", "Set an extraction destination", "Verify six recovered files"],
        "package": "7zip",
    },
    "04": {
        "title": "Notepad++",
        "kicker": "RELEASE CONFIGURATION",
        "scenario": "Approve the release gate in the active INI stanza without altering its rollback template.",
        "steps": ["Review the configuration", "Select the active release gate", "Save and verify exact bytes"],
        "package": "notepadpp",
    },
    "08": {
        "title": "DB Browser for SQLite",
        "kicker": "DATABASE MIGRATION QA",
        "scenario": "Run and commit a backfill migration, then verify legacy rows and database integrity.",
        "steps": ["Open the pre-upgrade database", "Run the SQL migration", "Commit and verify the backfill"],
        "package": "sqlitebrowser",
    },
    "09": {
        "title": "WinMerge",
        "kicker": "CHANGE REVIEW QA",
        "scenario": "Merge the approved retry-policy hunk while keeping the candidate version and routing.",
        "steps": ["Open baseline and candidate", "Review both differences", "Merge one hunk and save"],
        "package": "winmerge",
    },
}

ARCHIVE_ENTRIES = {
    "build-manifest.json": b'{"release":"2.14.7","platform":"win-x64","channel":"staging"}\n',
    "smoke-report.xml": b'<testsuite name="desktop-release" tests="3" failures="0"/>\n',
    "deployment.ini": b"[Release]\r\nChannel=staging\r\nRetryLimit=3\r\n",
    "checks/api-contract.json": b'{"handshake":2,"offline":true,"timeout_ms":2500}\n',
    "checks/expected-commands.txt": b"register\nstatus\nexport\n",
    "notes/migration.md": b"# Release 2.14.7\nPreserve the shared cache from 2.14.x.\n",
}

APPROVAL_INI = (
    "; Release 2.14.7 / build 702\r\n"
    "[Build]\r\nrevision=702\r\nplatform=win-x64\r\n"
    "[RollbackTemplate]\r\ngate=hold\r\nkeep_state=true\r\n"
    "[Release]\r\nchannel=staging\r\ngate=hold"
)

SOURCE_POLICY = (
    "; App package rollout policy\r\n"
    "[RetryPolicy]\r\nretry_limit=3\r\nbackoff_ms=600\r\n"
    "\r\n; Preserve these unrelated application settings\r\n"
    "[Network]\r\nallow_offline=true\r\n"
    "transport=local-fixture\r\n"
    "\r\n[Release]\r\nversion=2.14.6\r\nchannel=staging\r\n"
)

DATABASE_ROWS = (
    (101, "installer", "P", 240),
    (102, "startup", "P", 145),
    (103, "import", "F", 810),
    (104, "rollback", "P", 390),
    (105, "first-launch", None, 0),
)

APPLICATION_PROCESS = {
    "7zip": "7zFM",
    "notepadpp": "notepad++",
    "sqlitebrowser": "DB Browser for SQLite",
    "winmerge": "WinMergeU",
}

MIGRATION = """-- Release 2.14.7: backfill result_state without altering legacy evidence.
ALTER TABLE release_evidence ADD COLUMN result_state TEXT NOT NULL DEFAULT 'pending';
UPDATE release_evidence
SET result_state = CASE legacy_code WHEN 'P' THEN 'passed' WHEN 'F' THEN 'failed' ELSE 'pending' END;
CREATE INDEX idx_release_result ON release_evidence(result_state);
PRAGMA user_version = 2;
SELECT id, suite, legacy_code, result_state, duration_ms FROM release_evidence ORDER BY id;
"""


def check(name, expected, observed):
    return {"name": name, "expected": expected, "observed": observed, "passed": expected == observed}


def sha256(content):
    return hashlib.sha256(content).hexdigest()


async def snap(desktop, name, delay=.5):
    await asyncio.sleep(delay)
    return await desktop.screenshot(name)


async def read_bytes(desktop, path):
    output = await desktop.ps(f"""
        $share = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
        $stream = [IO.File]::Open('{path}', [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
        $buffer = [IO.MemoryStream]::new()
        try {{
            $stream.CopyTo($buffer)
            [Convert]::ToBase64String($buffer.ToArray())
        }} finally {{
            $buffer.Dispose()
            $stream.Dispose()
        }}
    """)
    return base64.b64decode(output.stdout.strip(), validate=True)


async def read_hash(desktop, path):
    output = await desktop.ps(f"(Get-FileHash -LiteralPath '{path}' -Algorithm SHA256).Hash")
    return output.stdout.strip().lower()


def click_target(rows, frame, *, kinds=()):
    """Pick a specific on-screen control and reject hits outside the current frame."""
    usable = [
        row for row in rows
        if 0 <= row["x"] < frame["width"] and 0 <= row["y"] < frame["height"]
    ]
    if not usable:
        return None
    return min(usable, key=lambda row: (
        row.get("kind") not in kinds,
        row.get("width", 1) * row.get("height", 1),
    ))


async def open_maximized(desktop, package, arguments, capture):
    await desktop.launch(package, arguments)
    process = APPLICATION_PROCESS[package]
    await desktop.wait(f"@(Get-Process -Name '{process}' -ErrorAction SilentlyContinue).Count -gt 0", seconds=35)
    await snap(desktop, f"{capture}-window", 1.25)
    await desktop.key("Escape")
    await desktop.key("Win", "Up")
    return await snap(desktop, capture, .7)


async def archive(desktop):
    source = ROOT + r"\release-candidate-2.14.7.zip"
    target = ROOT + r"\verified-release"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as candidate:
        for name, content in ARCHIVE_ENTRIES.items():
            candidate.writestr(name, content)
    await desktop.upload("release-candidate-2.14.7.zip", payload.getvalue())
    await desktop.ps(f"New-Item -Path '{target}' -ItemType Directory -Force | Out-Null")
    await open_maximized(desktop, "7zip", [source], "stage-0")
    rows = await desktop.inspect(r"^7zFM$", r"build-manifest|smoke-report|deployment\.ini")
    frame, _ = await desktop.screenshot("archive-payload")
    entry = click_target(rows, frame, kinds=("ControlType.DataItem", "ControlType.ListItem"))
    if entry:
        point = (entry["x"], entry["y"])
    elif (frame["width"], frame["height"]) == (1280, 800):
        # Some 7-Zip builds do not expose the native list view's row children.
        point = (80, 192)
    else:
        raise RuntimeError("7-Zip did not expose the release archive file list")
    await desktop.click(frame, *point)
    await desktop.key("Ctrl", "a")
    await snap(desktop, "stage-1")
    await desktop.key("F5")
    await snap(desktop, "extract-dialog", .65)
    await desktop.key("Home")
    await desktop.key("Shift", "End")
    await desktop.paste(target + "\\")
    await snap(desktop, "stage-2")
    await desktop.key("Enter")
    marker = target + r"\build-manifest.json"
    await desktop.wait(f"Test-Path -LiteralPath '{marker}'", seconds=25)
    await desktop.key("Alt", "F4")
    await open_maximized(desktop, "7zip", [target + "\\"], "stage-3")

    result = await desktop.ps(f"""
        $output = '{target}'
        $files = @(Get-ChildItem -LiteralPath $output -File -Recurse)
        $hashes = @{{}}
        foreach ($item in $files) {{
            $relative = $item.FullName.Substring($output.Length + 1).Replace([char]92, [char]47)
            $hashes[$relative] = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }}
        $hashes | ConvertTo-Json -Compress
    """)
    observed = json.loads(result.stdout)
    return [check("Recovered release tree", sorted(ARCHIVE_ENTRIES), sorted(observed))] + [
        check(f"{name} SHA-256", sha256(content), observed.get(name))
        for name, content in ARCHIVE_ENTRIES.items()
    ]


async def notepad(desktop):
    file = ROOT + r"\release-gate.ini"
    expected = APPROVAL_INI.removesuffix("gate=hold") + "gate=ready"
    await desktop.upload("release-gate.ini", APPROVAL_INI.encode())
    await open_maximized(desktop, "notepadpp", ["-nosession", "-noPlugin", file], "stage-0")
    await desktop.key("Ctrl", "End")
    await desktop.key("Shift", "Home")
    await snap(desktop, "stage-1")
    await desktop.paste("gate=ready")
    await snap(desktop, "stage-2")
    await desktop.key("Ctrl", "s")
    await desktop.wait(f"(Get-Content -LiteralPath '{file}' -Tail 1) -ceq 'gate=ready'", seconds=15)
    await snap(desktop, "stage-3")

    saved = await read_bytes(desktop, file)
    content = ConfigParser()
    content.read_string(saved.decode("utf-8"))
    return [
        check("Active release gate", "ready", content["Release"]["gate"]),
        check("Rollback template gate", "hold", content["RollbackTemplate"]["gate"]),
        check("Unrelated build revision", "702", content["Build"]["revision"]),
        check("Exact approved INI bytes including CRLF", sha256(expected.encode()), sha256(saved)),
    ]


def fixture_database():
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("PRAGMA page_size = 1024")
        connection.execute("VACUUM")
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "CREATE TABLE release_evidence (id INTEGER PRIMARY KEY, suite TEXT NOT NULL, "
            "legacy_code TEXT, duration_ms INTEGER NOT NULL)"
        )
        connection.executemany("INSERT INTO release_evidence VALUES (?, ?, ?, ?)", DATABASE_ROWS)
        connection.commit()
        return connection.serialize()


def verify_migration(data):
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.deserialize(data)
        runs = "release_evidence"
        row_records = connection.execute(
            f"SELECT id, suite, legacy_code, duration_ms FROM {runs} ORDER BY id"
        ).fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        columns = connection.execute(f"PRAGMA table_info({runs})").fetchall()
        indexes = connection.execute(f"PRAGMA index_list({runs})").fetchall()
        states = connection.execute(f"SELECT result_state FROM {runs} ORDER BY id").fetchall()
    return [
        check("SQLite integrity check", "ok", integrity),
        check("Migrated database version", 2, version),
        check("Legacy rows unchanged", [list(entry) for entry in DATABASE_ROWS], [list(entry) for entry in row_records]),
        check("Backfilled states", ["passed", "passed", "failed", "passed", "pending"], [row[0] for row in states]),
        check("New result field is non-null", 1, next(row[3] for row in columns if row[1] == "result_state")),
        check("Filter index installed", True, any(row[1] == "idx_release_result" for row in indexes)),
    ]


async def sqlite_browser(desktop):
    name = "release-evidence-v1-migration.sqlite"
    database = ROOT + "\\" + name
    fixture = fixture_database()
    await desktop.upload(name, fixture)
    await open_maximized(desktop, "sqlitebrowser", [database], "stage-0")
    rows = await desktop.inspect(r"^(DB Browser for SQLite|sqlitebrowser)$", r"Execute SQL|E&xecute SQL|SQL 실행")
    frame, _ = await desktop.screenshot("database-tabs")
    button = click_target([row for row in rows if row.get("kind") == "ControlType.TabItem"], frame)
    if button:
        await desktop.click(frame, button["x"], button["y"])
    else:
        await desktop.key("Alt", "x")
    frame, _ = await snap(desktop, "migration-editor", .6)
    await desktop.click(frame, frame["width"] // 4, frame["height"] // 4)
    await desktop.key("Ctrl", "a")
    await desktop.paste(MIGRATION)
    await snap(desktop, "stage-1")
    await desktop.key("Ctrl", "Enter")
    await snap(desktop, "stage-2", 1)
    # SQLite Browser requests approval to commit the current transaction before the PRAGMA.
    await desktop.key("Enter")
    await snap(desktop, "migration-results", .9)
    await desktop.key("Ctrl", "s")
    await snap(desktop, "stage-3", .9)
    await desktop.key("Ctrl", "F4")
    await asyncio.sleep(.6)
    data = await read_bytes(desktop, database)
    return verify_migration(data)


async def winmerge(desktop):
    baseline = ROOT + r"\approved-policy.ini"
    candidate = ROOT + r"\release-candidate.ini"
    original = SOURCE_POLICY.replace("retry_limit=3", "retry_limit=18").replace("version=2.14.6", "version=2.14.7")
    expected = SOURCE_POLICY.replace("version=2.14.6", "version=2.14.7")
    await desktop.upload("approved-policy.ini", SOURCE_POLICY.encode())
    await desktop.upload("release-candidate.ini", original.encode())
    await desktop.launch("winmerge", [
        "/u", "/wl", "/fr", "/maximize", "/dl", "Approved baseline", "/dr", "2.14.7 candidate", baseline, candidate,
    ])
    await desktop.wait("@(Get-Process -Name 'WinMergeU' -ErrorAction SilentlyContinue).Count -gt 0", seconds=35)
    for attempt in range(3):
        _, image = await snap(desktop, f"compare-ready-{attempt + 1}", 1.35)
        # WinMerge handles Escape by closing the loaded comparison tab. Leave it open.
        sample_points = ((580, 150), (988, 150), (580, 294), (1160, 294))
        if image.size == (1280, 800):
            if all(image.getpixel(point)[:3] == (239, 203, 5) for point in sample_points):
                break
            continue
        rows = await desktop.inspect(r"^WinMergeU$", r"Approved baseline|2\.14\.7 candidate")
        labels = " ".join(row["name"] for row in rows)
        if "Approved baseline" in labels and "2.14.7 candidate" in labels:
            break
    else:
        raise RuntimeError("WinMerge did not open both files for comparison")
    await desktop.screenshot("stage-0")
    await desktop.key("Alt", "End")
    await snap(desktop, "stage-1")
    await desktop.key("Alt", "Home")
    await desktop.key("Alt", "Right")
    await snap(desktop, "stage-2")
    await desktop.key("Ctrl", "s")
    await desktop.wait(f"(Select-String -LiteralPath '{candidate}' -Pattern '^retry_limit=3$' -Quiet)", seconds=15)
    await desktop.key("Alt", "End")
    await snap(desktop, "stage-3")

    saved = await read_bytes(desktop, candidate)
    return [
        check("Baseline was never modified", sha256(SOURCE_POLICY.encode()), await read_hash(desktop, baseline)),
        check("Only the approved retry limit was ported", sha256(expected.encode()), sha256(saved)),
        check("Candidate retains its release version", True, b"version=2.14.7\r\n" in saved),
    ]


async def execute(case_id, desktop):
    cases = {"01": archive, "04": notepad, "08": sqlite_browser, "09": winmerge}
    return await cases[str(case_id)](desktop)
