#!/usr/bin/env python3
"""Demo Agent for Linux, a stand-in endpoint inventory agent for OSLab demos.

demo-agent.ps1 in the same folder is the Windows edition. Both editions read the
package version from VERSION and provide the same commands:

  version                                      build, OS, installed version and registration
  install                                      install or upgrade, migrating 2.3 config and state
  register --server-url URL --asset-name NAME  create the local asset registration
  status                                       version, registration, config and migration state
  scan --output PATH                           write an inventory of installed packages

With --json, stdout carries exactly one JSON object and the human-readable
progress goes to stderr. DEMO_AGENT_ROOT points every write at a sandbox
directory instead of the filesystem root, which is useful for local testing.
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PRODUCT = "Demo Agent"
PUBLISHER = "OSLab demo"
BUILD = "20261120.1"
STATE_SCHEMA = 2
DEFAULT_SCAN_INTERVAL_MINUTES = 360

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("DEMO_AGENT_ROOT") or "/")
PROGRAM_DIR = ROOT / "opt" / "demo-agent"
COMMAND_PATH = ROOT / "usr" / "local" / "bin" / "demo-agent"
CONFIG_PATH = ROOT / "etc" / "demo-agent" / "agent.json"
LEGACY_CONFIG_PATH = ROOT / "etc" / "demo-agent" / "agent.conf"
DATA_DIR = ROOT / "var" / "lib" / "demo-agent"
STATE_PATH = DATA_DIR / "state.json"
BACKUP_ROOT = DATA_DIR / "backup"
LOG_PATH = ROOT / "var" / "log" / "demo-agent" / "agent.log"
PACKAGE_FILES = ("demo-agent.py", "VERSION")
LEGACY_SETTINGS = (("server", "url"), ("scan", "interval_hours"), ("scan", "exclude"))
DPKG_FORMAT = "${db:Status-Abbrev}\t${Package}\t${Version}\t${Architecture}\t${Maintainer}\n"


class AgentError(Exception):
    """A failure that the agent reports with a stable error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Console:
    """Human-readable progress for someone watching the VM screen."""

    COLUMN = 40
    COLORS = {"title": "1", "value": "36", "ok": "32", "fail": "31"}

    def __init__(self, stream) -> None:
        self.stream = stream
        self.interactive = stream.isatty()
        self.total = 0
        self.current = 0

    def paint(self, text: str, kind: str) -> str:
        if not self.interactive:
            return text
        return f"\033[{self.COLORS[kind]}m{text}\033[0m"

    def write(self, text: str) -> None:
        print(text, file=self.stream, flush=True)

    def title(self, text: str) -> None:
        self.write(self.paint(text, "title"))

    def row(self, label: str, value: str) -> None:
        dots = "." * max(3, self.COLUMN - len(label))
        self.write(f"  {label} {dots} {self.paint(value, 'value')}")

    def plan(self, total: int) -> None:
        self.total = total
        self.current = 0

    def step(self, label: str, value: str) -> None:
        self.current += 1
        self.row(f"[{self.current}/{self.total}] {label}", value)
        if self.interactive:
            time.sleep(0.3)

    def ok(self, text: str) -> None:
        self.write(f"  {self.paint('OK', 'ok')}  {text}")

    def note(self, text: str) -> None:
        self.write(f"  --  {text}")

    def fail(self, text: str) -> None:
        self.write(f"  {self.paint('FAIL', 'fail')}  {text}")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def short_id(asset_id: str | None) -> str:
    return (asset_id or "-")[:8]


def read_version(directory: Path) -> str | None:
    try:
        return (directory / "VERSION").read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


def package_version() -> str:
    version = read_version(PACKAGE_DIR)
    if version is None:
        raise AgentError("PACKAGE_INCOMPLETE", f"VERSION is missing next to {Path(__file__).name}")
    return version


def read_json(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise AgentError("FILE_CORRUPT", f"{path} is not valid JSON: {error}") from error


def write_json(path: Path, payload: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
    return len(data)


def append_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"{utc_now()} INFO {message}\n")


def os_description() -> str:
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


def new_state(version: str) -> dict:
    return {
        "schemaVersion": STATE_SCHEMA,
        "kind": "demoAgentState",
        "agentVersion": version,
        "registration": None,
        "lastScan": None,
        "migration": None,
    }


def default_config() -> dict:
    return {
        "schemaVersion": 2,
        "server": {"url": None},
        "scan": {"intervalMinutes": DEFAULT_SCAN_INTERVAL_MINUTES, "excludePaths": []},
    }


def registration_of(state: dict | None) -> dict | None:
    """Return the asset registration from a 2.3 (schema 1) or 2.4 (schema 2) state."""
    if not state:
        return None
    if state.get("schemaVersion") == 1:
        if not state.get("registered"):
            return None
        return {
            "assetId": state.get("assetId"),
            "assetName": state.get("assetName"),
            "serverUrl": state.get("serverUrl"),
            "registeredAtUtc": state.get("registeredAtUtc"),
            "origin": "legacy",
        }
    return state.get("registration")


def describe_registration(registration: dict | None) -> str:
    if registration is None:
        return "none"
    return f"{short_id(registration.get('assetId'))} ({registration.get('assetName')})"


def same_registration(current: dict | None, previous: dict | None) -> bool:
    if current is None or previous is None:
        return False
    return (
        current.get("assetId") == previous.get("assetId")
        and current.get("registeredAtUtc") == previous.get("registeredAtUtc")
    )


def require_current_state(state: dict | None) -> None:
    if state is not None and state.get("schemaVersion") != STATE_SCHEMA:
        raise AgentError("MIGRATION_REQUIRED", "State from an earlier version was found. Run install to migrate it.")


def convert_legacy_config(path: Path) -> tuple[dict, int]:
    """Translate the 2.3 INI config into the 2.4 JSON config and count the migrated settings."""
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    interval_hours = parser.getint("scan", "interval_hours", fallback=DEFAULT_SCAN_INTERVAL_MINUTES // 60)
    exclude = parser.get("scan", "exclude", fallback="")
    config = {
        "schemaVersion": 2,
        "server": {"url": parser.get("server", "url", fallback=None)},
        "scan": {
            "intervalMinutes": interval_hours * 60,
            "excludePaths": [item.strip() for item in exclude.split(";") if item.strip()],
        },
    }
    migrated = sum(1 for section, option in LEGACY_SETTINGS if parser.has_option(section, option))
    return config, migrated


def migrate_state(legacy: dict, version: str) -> dict:
    """Convert the 2.3 state (schema 1) to schema 2 and keep its registration as is."""
    state = new_state(version)
    registration = registration_of(legacy)
    if registration is not None:
        registration["assetId"] = registration["assetId"] or str(uuid.uuid4())
        registration["origin"] = "migrated"
    state["registration"] = registration
    if legacy.get("lastScanUtc"):
        state["lastScan"] = {"atUtc": legacy["lastScanUtc"], "recordCount": legacy.get("lastScanRecords"), "scanId": None}
    return state


def new_backup_dir(from_version: str) -> Path:
    backup_dir = BACKUP_ROOT / from_version
    if backup_dir.exists():
        backup_dir = BACKUP_ROOT / f"{from_version}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    backup_dir.mkdir(parents=True)
    return backup_dir


def migrate_previous_data(
    ui: Console,
    version: str,
    from_version: str,
    state: dict | None,
    *,
    legacy_state: bool,
    legacy_config: bool,
) -> dict:
    """Back up the 2.3 data, then convert its INI config and schema 1 state."""
    backup_dir = new_backup_dir(from_version)
    for path in (LEGACY_CONFIG_PATH, STATE_PATH):
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)
    ui.step(f"Backup of {from_version} data", str(backup_dir))

    migration = {
        "status": "migrated",
        "from": from_version,
        "to": version,
        "atUtc": utc_now(),
        "backupDir": str(backup_dir),
        "configFormat": None,
        "stateSchema": None,
        "previousRegistration": None,
    }
    if legacy_config:
        config, migrated_settings = convert_legacy_config(LEGACY_CONFIG_PATH)
        write_json(CONFIG_PATH, config)
        LEGACY_CONFIG_PATH.unlink()
        migration["configFormat"] = "ini->json"
        ui.step(f"Config {LEGACY_CONFIG_PATH.name} -> {CONFIG_PATH.name}", f"{migrated_settings} settings migrated")
    if legacy_state:
        previous = registration_of(state)
        migrated = migrate_state(state, version)
        write_json(STATE_PATH, migrated)
        migration["stateSchema"] = "1->2"
        if previous is None:
            ui.step("State schema 1 -> 2", "no registration to keep")
        else:
            migration["previousRegistration"] = {
                "assetId": previous["assetId"],
                "registeredAtUtc": previous["registeredAtUtc"],
            }
            kept = same_registration(migrated["registration"], previous)
            ui.step("State schema 1 -> 2", f"registration {short_id(previous['assetId'])} {'kept' if kept else 'CHANGED'}")
    return migration


def install_program_files() -> None:
    """Replace the program directory with this package and expose the demo-agent command."""
    if PACKAGE_DIR == PROGRAM_DIR.resolve():
        return
    if PROGRAM_DIR.exists():
        shutil.rmtree(PROGRAM_DIR)
    PROGRAM_DIR.mkdir(parents=True)
    for name in PACKAGE_FILES:
        shutil.copy2(PACKAGE_DIR / name, PROGRAM_DIR / name)
    COMMAND_PATH.parent.mkdir(parents=True, exist_ok=True)
    if COMMAND_PATH.is_symlink() or COMMAND_PATH.exists():
        COMMAND_PATH.unlink()
    launcher = f'#!/bin/sh\nexec "{sys.executable}" "{PROGRAM_DIR / "demo-agent.py"}" "$@"\n'
    COMMAND_PATH.write_text(launcher, encoding="utf-8")
    COMMAND_PATH.chmod(0o755)


def migration_summary(state: dict | None) -> dict:
    """Describe whether 2.3 data still needs migration and whether the registration survived it."""
    current_schema = state is not None and state.get("schemaVersion") == STATE_SCHEMA
    record = (state.get("migration") if current_schema else None) or {}
    legacy_config = LEGACY_CONFIG_PATH.exists()
    if (state is not None and not current_schema) or legacy_config:
        status = "required"
    elif record:
        status = "migrated"
    else:
        status = "not-needed"
    previous = record.get("previousRegistration")
    backup_dir = record.get("backupDir")
    return {
        "status": status,
        "from": record.get("from"),
        "backupPresent": bool(backup_dir) and Path(backup_dir).is_dir(),
        "legacyConfigPresent": legacy_config,
        "registrationKept": same_registration(registration_of(state), previous) if previous else None,
    }


def read_dpkg_packages() -> list[dict]:
    """List installed Debian packages as inventory records."""
    if shutil.which("dpkg-query") is None:
        return []
    listing = subprocess.run(
        ["dpkg-query", "-W", f"-f={DPKG_FORMAT}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    records = []
    for line in listing.splitlines():
        status, name, version, architecture, maintainer = (line.split("\t") + [""] * 5)[:5]
        if not status.startswith("ii"):
            continue
        records.append(
            {
                "name": name,
                "version": version,
                "publisher": re.sub(r"\s*<[^>]*>", "", maintainer).strip(),
                "sources": ["dpkg"],
                "confidence": "high",
                "evidence": [{"type": "package", "source": "dpkg", "path": "/var/lib/dpkg/status"}],
                "metadata": {"architecture": architecture},
            }
        )
    return sorted(records, key=lambda record: record["name"])


def agent_record(version: str, state: dict, registration: dict) -> dict:
    evidence = [
        {"type": "state", "source": "DemoAgent", "path": str(STATE_PATH)},
        {"type": "config", "source": "DemoAgent", "path": str(CONFIG_PATH)},
    ]
    migration = state.get("migration") or {}
    if migration.get("backupDir"):
        evidence.append({"type": "migration", "source": "DemoAgent", "path": migration["backupDir"]})
    return {
        "name": PRODUCT,
        "version": version,
        "publisher": PUBLISHER,
        "sources": ["DemoAgent"],
        "confidence": "high",
        "evidence": evidence,
        "metadata": {
            "assetId": registration.get("assetId"),
            "assetName": registration.get("assetName"),
            "serverUrl": registration.get("serverUrl"),
            "registeredAtUtc": registration.get("registeredAtUtc"),
            "registrationOrigin": registration.get("origin"),
            "migratedFrom": migration.get("from"),
            "installed": read_version(PROGRAM_DIR) is not None,
        },
    }


def cmd_version(args: argparse.Namespace, ui: Console) -> dict:
    version = package_version()
    installed_version = read_version(PROGRAM_DIR)
    registration = registration_of(read_json(STATE_PATH))
    os_name = os_description()
    ui.title(f"{PRODUCT} {version} (build {BUILD})")
    ui.row("Platform", f"linux {platform.machine()}")
    ui.row("Operating system", os_name)
    ui.row("Installed version", installed_version or "none")
    ui.row("Registration", describe_registration(registration))
    return {
        "version": version,
        "build": BUILD,
        "platform": "linux",
        "os": os_name,
        "installed": {"present": installed_version is not None, "version": installed_version},
        "registered": registration is not None,
        "registration": registration,
    }


def cmd_install(args: argparse.Namespace, ui: Console) -> dict:
    version = package_version()
    ui.title(f"{PRODUCT} {version} | install")
    previous_version = read_version(PROGRAM_DIR)
    state = read_json(STATE_PATH)
    legacy_state = state is not None and state.get("schemaVersion") == 1
    legacy_config = LEGACY_CONFIG_PATH.exists()
    needs_migration = legacy_state or legacy_config
    needs_default_config = not CONFIG_PATH.exists() and not legacy_config
    if previous_version is None:
        mode = "fresh"
    elif previous_version == version:
        mode = "reinstall"
    else:
        mode = "upgrade"

    planned_steps = 2 + int(needs_default_config)
    if needs_migration:
        planned_steps += 1 + int(legacy_config) + int(legacy_state)
    ui.plan(planned_steps)
    ui.step("Installed version", previous_version or "none")

    migration = {"status": "not-needed"}
    if needs_migration:
        migration = migrate_previous_data(
            ui,
            version,
            previous_version or "unknown",
            state,
            legacy_state=legacy_state,
            legacy_config=legacy_config,
        )
    install_program_files()
    ui.step("Program files", str(PROGRAM_DIR))
    if needs_default_config:
        write_json(CONFIG_PATH, default_config())
        ui.step("Default config", str(CONFIG_PATH))

    state = read_json(STATE_PATH)
    if state is not None:
        state["agentVersion"] = version
        if needs_migration:
            state["migration"] = migration
        write_json(STATE_PATH, state)
    append_log(f"install mode={mode} version={version} previous={previous_version or '-'} migration={migration['status']}")

    if mode == "upgrade":
        summary = f"upgraded {previous_version} -> {version}"
        previous = migration.get("previousRegistration")
        if previous:
            summary += f", registration {short_id(previous['assetId'])} kept, no re-registration"
    else:
        summary = f"{'installed' if mode == 'fresh' else 'reinstalled'} {version}"
    ui.ok(summary)
    return {
        "mode": mode,
        "version": version,
        "previousVersion": previous_version,
        "migration": migration,
    }


def cmd_register(args: argparse.Namespace, ui: Console) -> dict:
    version = package_version()
    ui.title(f"{PRODUCT} {version} | register")
    state = read_json(STATE_PATH)
    require_current_state(state)
    existing = registration_of(state)
    if existing is not None:
        ui.plan(1)
        ui.step("Existing registration", describe_registration(existing))
        ui.ok(f"already registered as {existing.get('assetName')}, nothing changed")
        return {"registered": True, "alreadyRegistered": True, "registration": existing}

    ui.plan(3)
    ui.step("Existing registration", "none")
    registration = {
        "assetId": str(uuid.uuid4()),
        "assetName": args.asset_name,
        "serverUrl": args.server_url,
        "registeredAtUtc": utc_now(),
        "origin": "registered",
    }
    ui.step("Registration ID", registration["assetId"])
    state = state or new_state(version)
    state["registration"] = registration
    write_json(STATE_PATH, state)
    config = read_json(CONFIG_PATH) or default_config()
    config.setdefault("server", {})["url"] = args.server_url
    write_json(CONFIG_PATH, config)
    ui.step("Saved to", str(STATE_PATH))
    append_log(f"register asset={args.asset_name} id={registration['assetId']}")
    ui.ok(f"registered {args.asset_name} with {args.server_url}")
    return {"registered": True, "alreadyRegistered": False, "registration": registration}


def cmd_status(args: argparse.Namespace, ui: Console) -> dict:
    version = package_version()
    ui.title(f"{PRODUCT} {version} | status")
    installed_version = read_version(PROGRAM_DIR)
    state = read_json(STATE_PATH)
    config = read_json(CONFIG_PATH)
    registration = registration_of(state)
    migration = migration_summary(state)
    scan_config = (config or {}).get("scan") or {}
    last_scan = (state or {}).get("lastScan")

    if installed_version is None:
        ui.row("Version", f"{version}, not installed")
    elif migration["status"] == "migrated":
        ui.row("Version", f"{installed_version}, upgraded from {migration['from']}")
    else:
        ui.row("Version", installed_version)
    if registration is None:
        ui.row("Asset", "not registered")
    else:
        ui.row("Asset", str(registration.get("assetName")))
        ui.row("Registration ID", str(registration.get("assetId")))
        ui.row("Registered at", str(registration.get("registeredAtUtc")))
        if migration["registrationKept"] is True:
            ui.row("Registration source", f"kept from {migration['from']}, no re-registration")
        elif migration["registrationKept"] is False:
            ui.row("Registration source", f"CHANGED during upgrade from {migration['from']}")
        else:
            ui.row("Registration source", "new registration")
        ui.row("Server", str(registration.get("serverUrl")))
    if config is None:
        ui.row("Config", "missing")
    else:
        ui.row("Config", f"schema {config.get('schemaVersion')}, scan every {scan_config.get('intervalMinutes')} min")
    ui.row("State", f"schema {state.get('schemaVersion')}" if state else "missing")
    if last_scan:
        ui.row("Last scan", f"{last_scan.get('atUtc')}, {last_scan.get('recordCount')} records")
    else:
        ui.row("Last scan", "never")

    if migration["status"] == "required":
        ui.fail("data from an earlier version is waiting for install to migrate it")
    elif registration is None:
        ui.note("not registered yet")
    else:
        ui.ok(f"registered as {registration.get('assetName')}, ready to scan")
    return {
        "version": version,
        "installed": {"present": installed_version is not None, "version": installed_version},
        "registered": registration is not None,
        "registration": registration,
        "config": {
            "serverUrl": ((config or {}).get("server") or {}).get("url"),
            "scanIntervalMinutes": scan_config.get("intervalMinutes"),
            "excludePaths": scan_config.get("excludePaths"),
        },
        "state": {"schemaVersion": (state or {}).get("schemaVersion")},
        "migration": migration,
    }


def cmd_scan(args: argparse.Namespace, ui: Console) -> dict:
    version = package_version()
    ui.title(f"{PRODUCT} {version} | scan")
    state = read_json(STATE_PATH)
    require_current_state(state)
    registration = registration_of(state)
    if registration is None:
        raise AgentError("NOT_REGISTERED", "Register the agent before scanning.")

    scan_id = uuid.uuid4().hex
    ui.plan(4)
    ui.step("Registration", describe_registration(registration))
    packages = read_dpkg_packages()
    ui.step("Installed packages (dpkg)", f"{len(packages)} found")
    records = [agent_record(version, state, registration), *packages]
    ui.step("Agent record", f"{PRODUCT} {version}")

    output = Path(args.output)
    generated_at = utc_now()
    inventory = {
        "schemaVersion": 1,
        "kind": "inventory",
        "generatedAtUtc": generated_at,
        "scanId": scan_id,
        "agent": {"name": PRODUCT, "version": version, "platform": "linux"},
        "asset": {"id": registration.get("assetId"), "name": registration.get("assetName")},
        "records": records,
    }
    bytes_written = write_json(output, inventory)
    ui.step("Inventory", str(output))
    state["lastScan"] = {"atUtc": generated_at, "recordCount": len(records), "scanId": scan_id}
    write_json(STATE_PATH, state)
    append_log(f"scan id={scan_id} records={len(records)} output={output}")
    ui.ok(f"inventory {scan_id[:8]} written: {len(records)} records for {registration.get('assetName')}")
    return {
        "outputPath": str(output),
        "outputWritten": True,
        "bytesWritten": bytes_written,
        "scanId": scan_id,
        "recordCount": len(records),
        "sources": {"DemoAgent": 1, "dpkg": len(packages)},
        "asset": {
            "id": registration.get("assetId"),
            "name": registration.get("assetName"),
            "origin": registration.get("origin"),
        },
        "uploadRequested": False,
    }


COMMANDS = {
    "version": cmd_version,
    "install": cmd_install,
    "register": cmd_register,
    "status": cmd_status,
    "scan": cmd_scan,
}


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print one JSON object on stdout")
    parser = argparse.ArgumentParser(prog="demo-agent", description=f"{PRODUCT} for Linux")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", parents=[common], help="show the build, OS, installed version and registration")
    commands.add_parser("install", parents=[common], help="install or upgrade the agent")
    register = commands.add_parser("register", parents=[common], help="register this machine as an asset")
    register.add_argument("--server-url", required=True)
    register.add_argument("--asset-name", required=True)
    commands.add_parser("status", parents=[common], help="show version, registration, config and migration state")
    scan = commands.add_parser("scan", parents=[common], help="write an inventory of installed packages")
    scan.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ui = Console(sys.stderr if args.json else sys.stdout)
    try:
        payload = {"ok": True, "command": args.command, **COMMANDS[args.command](args, ui)}
    except AgentError as error:
        payload = {"ok": False, "command": args.command, "error": {"code": error.code, "message": error.message}}
    except (OSError, subprocess.CalledProcessError) as error:
        payload = {"ok": False, "command": args.command, "error": {"code": "INTERNAL_ERROR", "message": str(error)}}
    if not payload["ok"]:
        ui.fail(f"{payload['error']['code']}: {payload['error']['message']}")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), flush=True)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
