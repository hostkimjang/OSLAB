"""Command line interface for oslab."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from oslab import __version__
from oslab.analysis import analyze_inventory
from oslab.assertions import AssertionResult, evaluate_assertions
from oslab.config import load_config
from oslab.console import Console, redact_value
from oslab.env_file import load_env_file
from oslab.errors import OslabError, ProviderError
from oslab.guests.base import GuestCommandResult
from oslab.guests.qemu_agent import QemuAgentChannel
from oslab.models.scenario import load_scenario
from oslab.plugins import normalize_output
from oslab.providers.base import VmRef
from oslab.providers.proxmox import ProxmoxClient, proxmox_config_from_oslab
from oslab.providers.proxmox_checks import ProxmoxResourceCheck, check_proxmox_resources
from oslab.runners.proxmox_artifact_smoke import ArtifactSmokeResult, ProgressEvent, run_proxmox_artifact_smoke
from oslab.runners.proxmox_boot_smoke import run_proxmox_boot_smoke
from oslab.runners.proxmox_clone_smoke import run_proxmox_clone_smoke
from oslab.runners.proxmox_fixture_smoke import FixtureSmokeResult, run_proxmox_fixture_smoke
from oslab.runners.proxmox_guest_preflight import GuestPreflightResult, run_proxmox_guest_preflight
from oslab.runners.scenario_runner import run_artifact_validation, run_skeleton


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oslab", description="OS integration test platform for disposable VMs.")
    parser.add_argument("--version", action="version", version=f"oslab {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-scenario", help="Validate a scenario YAML file.")
    validate.add_argument("--scenario", required=True, type=Path)
    validate.set_defaults(func=cmd_validate_scenario)

    preflight = subparsers.add_parser("preflight", help="Validate scenario/config without creating a VM yet.")
    preflight.add_argument("--scenario", required=True, type=Path)
    preflight.add_argument("--config", type=Path)
    preflight.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    preflight.add_argument(
        "--provider-config-check",
        action="store_true",
        help="Resolve provider config and env secrets without making network calls.",
    )
    preflight.add_argument(
        "--provider-connectivity-check",
        action="store_true",
        help="Call the provider API to verify remote connectivity.",
    )
    preflight.add_argument(
        "--provider-resource-check",
        action="store_true",
        help="Read provider node/template/VMID range state without mutating infrastructure.",
    )
    preflight.set_defaults(func=cmd_preflight)

    run = subparsers.add_parser("run", help="Run a scenario using the full run output layout.")
    run.add_argument("--scenario", required=True, type=Path)
    run.add_argument("--config", type=Path)
    run.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    run.add_argument("--run-id")
    run.add_argument("--artifact-path", type=Path)
    run.add_argument("--vm-id", type=int, help="Use a specific VMID instead of allocating from vmIdRange.")
    run.add_argument("--keep-vm", action="store_true", help="Keep the clone running after the run.")
    run.add_argument("--full-clone", action="store_true", help="Request a full clone instead of linked clone.")
    run.add_argument("--boot-timeout-seconds", type=int, default=300)
    run.add_argument("--guest-timeout-seconds", type=int, default=300)
    run.add_argument("--command-timeout-seconds", type=int, default=120)
    run.add_argument("--poll-interval-seconds", type=float, default=5.0)
    run.set_defaults(func=cmd_run)

    clone_smoke = subparsers.add_parser(
        "clone-smoke",
        help="Create a Proxmox clone from the scenario template and destroy it by default.",
    )
    clone_smoke.add_argument("--scenario", required=True, type=Path)
    clone_smoke.add_argument("--config", required=True, type=Path)
    clone_smoke.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    clone_smoke.add_argument("--vm-id", type=int, help="Use a specific VMID instead of allocating from vmIdRange.")
    clone_smoke.add_argument("--keep-vm", action="store_true", help="Keep the clone after the smoke test.")
    clone_smoke.add_argument("--full-clone", action="store_true", help="Request a full clone instead of linked clone.")
    clone_smoke.set_defaults(func=cmd_clone_smoke)

    boot_smoke = subparsers.add_parser(
        "boot-smoke",
        help="Create/start a Proxmox clone, wait for QEMU Guest Agent, and destroy it by default.",
    )
    boot_smoke.add_argument("--scenario", required=True, type=Path)
    boot_smoke.add_argument("--config", required=True, type=Path)
    boot_smoke.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    boot_smoke.add_argument("--vm-id", type=int, help="Use a specific VMID instead of allocating from vmIdRange.")
    boot_smoke.add_argument("--keep-vm", action="store_true", help="Keep the clone running after the smoke test.")
    boot_smoke.add_argument("--full-clone", action="store_true", help="Request a full clone instead of linked clone.")
    boot_smoke.add_argument("--boot-timeout-seconds", type=int, default=300)
    boot_smoke.add_argument("--guest-timeout-seconds", type=int, default=300)
    boot_smoke.add_argument("--poll-interval-seconds", type=float, default=5.0)
    boot_smoke.set_defaults(func=cmd_boot_smoke)

    guest_preflight = subparsers.add_parser(
        "guest-preflight",
        help="Create/start a Proxmox clone and run Windows guest readiness checks.",
    )
    guest_preflight.add_argument("--scenario", required=True, type=Path)
    guest_preflight.add_argument("--config", required=True, type=Path)
    guest_preflight.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    guest_preflight.add_argument("--vm-id", type=int, help="Use a specific VMID instead of allocating from vmIdRange.")
    guest_preflight.add_argument("--keep-vm", action="store_true", help="Keep the clone running after preflight.")
    guest_preflight.add_argument("--full-clone", action="store_true", help="Request a full clone instead of linked clone.")
    guest_preflight.add_argument("--boot-timeout-seconds", type=int, default=300)
    guest_preflight.add_argument("--guest-timeout-seconds", type=int, default=300)
    guest_preflight.add_argument("--command-timeout-seconds", type=int, default=60)
    guest_preflight.add_argument("--poll-interval-seconds", type=float, default=5.0)
    guest_preflight.set_defaults(func=cmd_guest_preflight)

    fixture_smoke = subparsers.add_parser(
        "fixture-smoke",
        help="Create/start a Proxmox clone, run scenario fixtures, collect expected outputs, and cleanup.",
    )
    fixture_smoke.add_argument("--scenario", required=True, type=Path)
    fixture_smoke.add_argument("--config", required=True, type=Path)
    fixture_smoke.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    fixture_smoke.add_argument("--vm-id", type=int, help="Use a specific VMID instead of allocating from vmIdRange.")
    fixture_smoke.add_argument("--keep-vm", action="store_true", help="Keep the clone running after fixture smoke.")
    fixture_smoke.add_argument("--full-clone", action="store_true", help="Request a full clone instead of linked clone.")
    fixture_smoke.add_argument("--boot-timeout-seconds", type=int, default=300)
    fixture_smoke.add_argument("--guest-timeout-seconds", type=int, default=300)
    fixture_smoke.add_argument("--command-timeout-seconds", type=int, default=60)
    fixture_smoke.add_argument("--poll-interval-seconds", type=float, default=5.0)
    fixture_smoke.set_defaults(func=cmd_fixture_smoke)

    artifact_smoke = subparsers.add_parser(
        "artifact-smoke",
        help="Create/start a Proxmox clone, upload a folder or installer artifact, execute it, collect output, and cleanup.",
    )
    artifact_smoke.add_argument("--scenario", required=True, type=Path)
    artifact_smoke.add_argument("--config", required=True, type=Path)
    artifact_smoke.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    artifact_smoke.add_argument("--artifact-path", required=True, type=Path)
    artifact_smoke.add_argument("--vm-id", type=int, help="Use a specific VMID instead of allocating from vmIdRange.")
    artifact_smoke.add_argument("--keep-vm", action="store_true", help="Keep the clone running after artifact smoke.")
    artifact_smoke.add_argument("--full-clone", action="store_true", help="Request a full clone instead of linked clone.")
    artifact_smoke.add_argument("--boot-timeout-seconds", type=int, default=300)
    artifact_smoke.add_argument("--guest-timeout-seconds", type=int, default=300)
    artifact_smoke.add_argument("--command-timeout-seconds", type=int, default=120)
    artifact_smoke.add_argument("--poll-interval-seconds", type=float, default=5.0)
    artifact_smoke.set_defaults(func=cmd_artifact_smoke)

    assert_result = subparsers.add_parser(
        "assert-result",
        help="Evaluate scenario assertions against a collected JSON result without creating a VM.",
    )
    assert_result.add_argument("--scenario", required=True, type=Path)
    assert_result.add_argument("--actual-json", required=True, type=Path)
    assert_result.set_defaults(func=cmd_assert_result)

    normalize = subparsers.add_parser(
        "normalize-output",
        help="Normalize a raw product JSON file through an output adapter.",
    )
    normalize.add_argument("--adapter", help="Adapter name such as supplyscan.inventory. Defaults to scenario output adapter.")
    normalize.add_argument("--scenario", type=Path, help="Scenario used to infer adapter and context.")
    normalize.add_argument("--input-json", required=True, type=Path)
    normalize.add_argument("--output-json", required=True, type=Path)
    normalize.set_defaults(func=cmd_normalize_output)

    analyze = subparsers.add_parser(
        "analyze-inventory",
        help="Analyze a canonical inventory JSON file without creating a VM.",
    )
    analyze.add_argument("--inventory-json", required=True, type=Path)
    analyze.add_argument("--output-json", type=Path, help="Optional path for inventory.analysis.json.")
    analyze.set_defaults(func=cmd_analyze_inventory)

    qga_exec = subparsers.add_parser(
        "qga-exec",
        help="Execute a command in an existing VM through Proxmox QEMU Guest Agent.",
    )
    qga_exec.add_argument("--config", required=True, type=Path)
    qga_exec.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    qga_exec.add_argument("--vm-id", required=True, type=int)
    qga_exec.add_argument("--timeout-seconds", type=int, default=60)
    qga_exec.add_argument("--poll-interval-seconds", type=float, default=1.0)
    qga_exec.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to execute after `--`, for example: -- powershell.exe -NoProfile -Command whoami",
    )
    qga_exec.set_defaults(func=cmd_qga_exec)

    qga_upload = subparsers.add_parser(
        "qga-upload",
        help="Upload a small local file into an existing VM through Proxmox QEMU Guest Agent.",
    )
    qga_upload.add_argument("--config", required=True, type=Path)
    qga_upload.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    qga_upload.add_argument("--vm-id", required=True, type=int)
    qga_upload.add_argument("--local-path", required=True, type=Path)
    qga_upload.add_argument("--guest-path", required=True)
    qga_upload.set_defaults(func=cmd_qga_upload)

    qga_download = subparsers.add_parser(
        "qga-download",
        help="Download a text file from an existing VM through Proxmox QEMU Guest Agent.",
    )
    qga_download.add_argument("--config", required=True, type=Path)
    qga_download.add_argument("--env-file", type=Path, help="Load ignored KEY=VALUE secrets before resolving config.")
    qga_download.add_argument("--vm-id", required=True, type=int)
    qga_download.add_argument("--guest-path", required=True)
    qga_download.add_argument("--local-path", required=True, type=Path)
    qga_download.set_defaults(func=cmd_qga_download)

    inspect = subparsers.add_parser("inspect-result", help="Inspect a completed run directory.")
    inspect.add_argument("--run-dir", required=True, type=Path)
    inspect.add_argument("--json", action="store_true", help="Print raw run.json instead of a human summary.")
    inspect.set_defaults(func=cmd_inspect_result)

    return parser


def cmd_validate_scenario(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    print(f"valid scenario: {scenario.scenario_id}")
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab preflight")

    if args.env_file:
        env_result = load_env_file(args.env_file)
        console.ok("Env file loaded")
        console.detail("file", args.env_file)
        console.detail("loadedKeys", ", ".join(env_result.loaded) if env_result.loaded else "<none>")
        console.detail(
            "skippedExistingKeys",
            ", ".join(env_result.skipped_existing) if env_result.skipped_existing else "<none>",
        )

    scenario = load_scenario(args.scenario)
    console.ok("Scenario loaded")
    console.detail("id", scenario.scenario_id)
    console.detail("name", scenario.name)
    console.detail("file", args.scenario)
    console.detail("os", scenario.os_family)
    console.detail("provider", scenario.provider_type)

    config = load_config(args.config)
    console.ok("Config loaded")
    console.detail("file", args.config or "<defaults>")
    console.detail("outputRoot", config.output_root)
    console.detail("timeoutMinutes", config.timeout_minutes)
    console.detail("keepVmOnFailure", config.keep_vm_on_failure)

    if args.provider_config_check or args.provider_connectivity_check or args.provider_resource_check:
        if scenario.provider_type == "proxmox":
            proxmox = proxmox_config_from_oslab(config)
            console.ok("Provider config resolved")
            console.detail("provider", "proxmox")
            console.detail("apiUrl", proxmox.api_url)
            console.detail("node", proxmox.node)
            console.detail("verifyTls", str(proxmox.verify_tls).lower())
            console.detail("timeoutSeconds", proxmox.timeout_seconds)
            console.detail("tokenId", redact_value(proxmox.token_id))
            console.detail("tokenSecret", "<redacted>")
            proxmox_client = ProxmoxClient(proxmox)
            if args.provider_connectivity_check or args.provider_resource_check:
                console.step("Proxmox API connectivity")
                console.detail("endpoint", "GET /version")
                started = time.perf_counter()
                version = proxmox_client.get_version()
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                version_text = version.get("version") or "unknown"
                release_text = version.get("release") or "unknown"
                console.ok("Proxmox API connectivity")
                console.detail("version", version_text)
                console.detail("release", release_text)
                console.detail("elapsedMs", elapsed_ms)
            if args.provider_resource_check:
                console.step("Proxmox resource preflight")
                console.detail("endpoints", "GET /nodes, GET /cluster/resources?type=vm, GET /nodes/<node>/qemu/<vmid>/config")
                resource_check = check_proxmox_resources(proxmox_client, scenario, proxmox)
                _print_proxmox_resource_check(console, resource_check)
                if not resource_check.passed:
                    raise ProviderError(
                        "Proxmox resource preflight failed",
                        details={"issues": resource_check.issues, "warnings": resource_check.warnings},
                    )
        else:
            raise OslabError(f"Provider config check is not implemented for provider: {scenario.provider_type}")
    console.warn("Preflight completed without creating a VM")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if args.artifact_path is None:
        scenario = load_scenario(args.scenario)
        config = load_config(args.config)

        result = run_skeleton(scenario, config, run_id=args.run_id)
        print(f"skeleton run complete: {result.run_id}")
        print(f"status: {result.status}")
        return 0

    console = Console()
    console.section("oslab run")

    if args.env_file:
        _print_env_load(console, args.env_file)

    scenario = load_scenario(args.scenario)
    config = load_config(args.config)

    if not args.artifact_path.exists():
        raise OslabError(f"Artifact path does not exist: {args.artifact_path}", details={"path": str(args.artifact_path)})

    if scenario.provider_type != "proxmox":
        raise OslabError(f"`oslab run` artifact execution is not implemented for provider: {scenario.provider_type}")

    proxmox = proxmox_config_from_oslab(config)
    console.ok("Scenario and provider config loaded")
    console.detail("scenario", scenario.scenario_id)
    console.detail("templateVmId", scenario.template_vm_id)
    console.detail("template", scenario.template_name or "<not set>")
    console.detail("artifactPath", args.artifact_path)
    console.detail("apiUrl", proxmox.api_url)
    console.detail("node", proxmox.node)
    console.detail("tokenId", redact_value(proxmox.token_id))
    console.detail("tokenSecret", "<redacted>")

    console.step("Run scenario with full output layout")
    console.detail("runId", args.run_id or "<auto>")
    console.detail("vmId", args.vm_id if args.vm_id is not None else "<auto>")
    console.detail("keepVm", str(args.keep_vm).lower())
    console.detail("fullClone", str(args.full_clone).lower())
    console.detail("bootTimeoutSeconds", args.boot_timeout_seconds)
    console.detail("guestTimeoutSeconds", args.guest_timeout_seconds)
    console.detail("commandTimeoutSeconds", args.command_timeout_seconds)
    console.detail("pollIntervalSeconds", args.poll_interval_seconds)

    result = run_artifact_validation(
        scenario,
        config,
        proxmox_config=proxmox,
        artifact_path=args.artifact_path,
        run_id=args.run_id,
        vm_id=args.vm_id,
        keep_vm=args.keep_vm,
        full_clone=args.full_clone,
        boot_timeout_seconds=args.boot_timeout_seconds,
        guest_timeout_seconds=args.guest_timeout_seconds,
        command_timeout_seconds=args.command_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        progress=lambda event: _print_progress_event(console, event),
    )
    _print_run_result(console, result)
    return 0 if result.status == "passed" else 1


def cmd_clone_smoke(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab clone smoke")

    if args.env_file:
        env_result = load_env_file(args.env_file)
        console.ok("Env file loaded")
        console.detail("file", args.env_file)
        console.detail("loadedKeys", ", ".join(env_result.loaded) if env_result.loaded else "<none>")
        console.detail(
            "skippedExistingKeys",
            ", ".join(env_result.skipped_existing) if env_result.skipped_existing else "<none>",
        )

    scenario = load_scenario(args.scenario)
    config = load_config(args.config)
    proxmox = proxmox_config_from_oslab(config)

    console.ok("Scenario and provider config loaded")
    console.detail("scenario", scenario.scenario_id)
    console.detail("templateVmId", scenario.template_vm_id)
    console.detail("template", scenario.template_name or "<not set>")
    console.detail("apiUrl", proxmox.api_url)
    console.detail("node", proxmox.node)
    console.detail("tokenId", redact_value(proxmox.token_id))
    console.detail("tokenSecret", "<redacted>")

    console.step("Create clone and cleanup")
    console.detail("vmId", args.vm_id if args.vm_id is not None else "<auto>")
    console.detail("keepVm", str(args.keep_vm).lower())
    console.detail("fullClone", str(args.full_clone).lower())
    result = run_proxmox_clone_smoke(
        scenario=scenario,
        oslab_config=config,
        proxmox_config=proxmox,
        vm_id=args.vm_id,
        keep_vm=args.keep_vm,
        full_clone=args.full_clone,
    )
    console.ok("Clone smoke completed")
    console.detail("cloneVmId", result.vm.vm_id)
    console.detail("cloneName", result.clone_name)
    console.detail("cloneStatus", result.status.status if result.status else "<unknown>")
    console.detail("destroyed", str(result.destroyed).lower())
    console.detail("kept", str(result.kept).lower())
    return 0


def cmd_boot_smoke(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab boot smoke")

    if args.env_file:
        env_result = load_env_file(args.env_file)
        console.ok("Env file loaded")
        console.detail("file", args.env_file)
        console.detail("loadedKeys", ", ".join(env_result.loaded) if env_result.loaded else "<none>")
        console.detail(
            "skippedExistingKeys",
            ", ".join(env_result.skipped_existing) if env_result.skipped_existing else "<none>",
        )

    scenario = load_scenario(args.scenario)
    config = load_config(args.config)
    proxmox = proxmox_config_from_oslab(config)

    console.ok("Scenario and provider config loaded")
    console.detail("scenario", scenario.scenario_id)
    console.detail("templateVmId", scenario.template_vm_id)
    console.detail("template", scenario.template_name or "<not set>")
    console.detail("apiUrl", proxmox.api_url)
    console.detail("node", proxmox.node)
    console.detail("tokenId", redact_value(proxmox.token_id))
    console.detail("tokenSecret", "<redacted>")

    console.step("Create clone, boot, wait for guest agent, cleanup")
    console.detail("vmId", args.vm_id if args.vm_id is not None else "<auto>")
    console.detail("keepVm", str(args.keep_vm).lower())
    console.detail("fullClone", str(args.full_clone).lower())
    console.detail("bootTimeoutSeconds", args.boot_timeout_seconds)
    console.detail("guestTimeoutSeconds", args.guest_timeout_seconds)
    console.detail("pollIntervalSeconds", args.poll_interval_seconds)
    result = run_proxmox_boot_smoke(
        scenario=scenario,
        oslab_config=config,
        proxmox_config=proxmox,
        vm_id=args.vm_id,
        keep_vm=args.keep_vm,
        full_clone=args.full_clone,
        boot_timeout_seconds=args.boot_timeout_seconds,
        guest_timeout_seconds=args.guest_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    console.ok("Boot smoke completed")
    console.detail("cloneVmId", result.vm.vm_id)
    console.detail("cloneName", result.clone_name)
    console.detail("cloneStatus", result.status.status)
    console.detail("guestInfo", "available" if result.guest_info else "<missing>")
    console.detail("started", str(result.started).lower())
    console.detail("destroyed", str(result.destroyed).lower())
    console.detail("kept", str(result.kept).lower())
    return 0


def cmd_guest_preflight(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab guest preflight")

    if args.env_file:
        _print_env_load(console, args.env_file)

    scenario = load_scenario(args.scenario)
    config = load_config(args.config)
    proxmox = proxmox_config_from_oslab(config)

    console.ok("Scenario and provider config loaded")
    console.detail("scenario", scenario.scenario_id)
    console.detail("templateVmId", scenario.template_vm_id)
    console.detail("template", scenario.template_name or "<not set>")
    console.detail("apiUrl", proxmox.api_url)
    console.detail("node", proxmox.node)
    console.detail("tokenId", redact_value(proxmox.token_id))
    console.detail("tokenSecret", "<redacted>")

    console.step("Create clone, boot, run guest preflight, cleanup")
    console.detail("vmId", args.vm_id if args.vm_id is not None else "<auto>")
    console.detail("keepVm", str(args.keep_vm).lower())
    console.detail("fullClone", str(args.full_clone).lower())
    console.detail("bootTimeoutSeconds", args.boot_timeout_seconds)
    console.detail("guestTimeoutSeconds", args.guest_timeout_seconds)
    console.detail("commandTimeoutSeconds", args.command_timeout_seconds)
    console.detail("pollIntervalSeconds", args.poll_interval_seconds)

    result = run_proxmox_guest_preflight(
        scenario=scenario,
        oslab_config=config,
        proxmox_config=proxmox,
        vm_id=args.vm_id,
        keep_vm=args.keep_vm,
        full_clone=args.full_clone,
        boot_timeout_seconds=args.boot_timeout_seconds,
        guest_timeout_seconds=args.guest_timeout_seconds,
        command_timeout_seconds=args.command_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    _print_guest_preflight_result(console, result)
    return 0 if result.passed else 1


def cmd_fixture_smoke(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab fixture smoke")

    if args.env_file:
        _print_env_load(console, args.env_file)

    scenario = load_scenario(args.scenario)
    config = load_config(args.config)
    proxmox = proxmox_config_from_oslab(config)

    console.ok("Scenario and provider config loaded")
    console.detail("scenario", scenario.scenario_id)
    console.detail("templateVmId", scenario.template_vm_id)
    console.detail("template", scenario.template_name or "<not set>")
    console.detail("apiUrl", proxmox.api_url)
    console.detail("node", proxmox.node)
    console.detail("tokenId", redact_value(proxmox.token_id))
    console.detail("tokenSecret", "<redacted>")

    console.step("Create clone, boot, run fixtures, collect expected outputs, cleanup")
    console.detail("vmId", args.vm_id if args.vm_id is not None else "<auto>")
    console.detail("keepVm", str(args.keep_vm).lower())
    console.detail("fullClone", str(args.full_clone).lower())
    console.detail("bootTimeoutSeconds", args.boot_timeout_seconds)
    console.detail("guestTimeoutSeconds", args.guest_timeout_seconds)
    console.detail("commandTimeoutSeconds", args.command_timeout_seconds)
    console.detail("pollIntervalSeconds", args.poll_interval_seconds)

    result = run_proxmox_fixture_smoke(
        scenario=scenario,
        oslab_config=config,
        proxmox_config=proxmox,
        vm_id=args.vm_id,
        keep_vm=args.keep_vm,
        full_clone=args.full_clone,
        boot_timeout_seconds=args.boot_timeout_seconds,
        guest_timeout_seconds=args.guest_timeout_seconds,
        command_timeout_seconds=args.command_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    _print_fixture_smoke_result(console, result)
    return 0 if result.passed else 1


def cmd_artifact_smoke(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab artifact smoke")

    if args.env_file:
        _print_env_load(console, args.env_file)

    scenario = load_scenario(args.scenario)
    config = load_config(args.config)
    proxmox = proxmox_config_from_oslab(config)

    console.ok("Scenario and provider config loaded")
    console.detail("scenario", scenario.scenario_id)
    console.detail("templateVmId", scenario.template_vm_id)
    console.detail("template", scenario.template_name or "<not set>")
    console.detail("artifactPath", args.artifact_path)
    console.detail("apiUrl", proxmox.api_url)
    console.detail("node", proxmox.node)
    console.detail("tokenId", redact_value(proxmox.token_id))
    console.detail("tokenSecret", "<redacted>")

    console.step("Create clone, boot, upload artifact, execute command, collect output, cleanup")
    console.detail("vmId", args.vm_id if args.vm_id is not None else "<auto>")
    console.detail("keepVm", str(args.keep_vm).lower())
    console.detail("fullClone", str(args.full_clone).lower())
    console.detail("bootTimeoutSeconds", args.boot_timeout_seconds)
    console.detail("guestTimeoutSeconds", args.guest_timeout_seconds)
    console.detail("commandTimeoutSeconds", args.command_timeout_seconds)
    console.detail("pollIntervalSeconds", args.poll_interval_seconds)

    result = run_proxmox_artifact_smoke(
        scenario=scenario,
        oslab_config=config,
        proxmox_config=proxmox,
        artifact_path=args.artifact_path,
        vm_id=args.vm_id,
        keep_vm=args.keep_vm,
        full_clone=args.full_clone,
        boot_timeout_seconds=args.boot_timeout_seconds,
        guest_timeout_seconds=args.guest_timeout_seconds,
        command_timeout_seconds=args.command_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        progress=lambda event: _print_progress_event(console, event),
    )
    _print_artifact_smoke_result(console, result)
    return 0 if result.passed else 1


def cmd_assert_result(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab assert result")

    scenario = load_scenario(args.scenario)
    if not args.actual_json.exists():
        raise OslabError(f"Actual JSON file does not exist: {args.actual_json}", details={"path": str(args.actual_json)})

    actual = json.loads(args.actual_json.read_text(encoding="utf-8-sig"))
    normalization = normalize_output(
        scenario.output_adapter,
        actual,
        context={"scenarioId": scenario.scenario_id, "actualJson": str(args.actual_json)},
    )
    summary = evaluate_assertions(scenario.assertions, normalization.canonical)

    if summary.passed:
        console.ok("Assertions passed")
    else:
        console.fail("Assertions failed")
    console.detail("scenario", scenario.scenario_id)
    console.detail("actualJson", args.actual_json)
    console.detail("adapter", normalization.adapter)
    console.detail("records", len(normalization.canonical.get("records", [])))
    console.detail("total", len(summary.results))
    console.detail("failed", summary.failed_count)
    _print_assertion_results(console, summary.results)
    return 0 if summary.passed else 1


def cmd_normalize_output(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab normalize output")

    scenario_id = None
    adapter = args.adapter
    if args.scenario is not None:
        scenario = load_scenario(args.scenario)
        scenario_id = scenario.scenario_id
        adapter = adapter or scenario.output_adapter
    if not adapter:
        raise OslabError("Output adapter is required when --scenario is not supplied")
    if not args.input_json.exists():
        raise OslabError(f"Input JSON file does not exist: {args.input_json}", details={"path": str(args.input_json)})

    raw = json.loads(args.input_json.read_text(encoding="utf-8-sig"))
    normalization = normalize_output(
        adapter,
        raw,
        context={"scenarioId": scenario_id, "inputJson": str(args.input_json)},
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(normalization.canonical, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    console.ok("Output normalized")
    if scenario_id:
        console.detail("scenario", scenario_id)
    console.detail("adapter", normalization.adapter)
    console.detail("inputJson", args.input_json)
    console.detail("outputJson", args.output_json)
    console.detail("records", len(normalization.canonical.get("records", [])))
    return 0


def cmd_analyze_inventory(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab analyze inventory")

    if not args.inventory_json.exists():
        raise OslabError(
            f"Inventory JSON file does not exist: {args.inventory_json}",
            details={"path": str(args.inventory_json)},
        )
    try:
        inventory = json.loads(args.inventory_json.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise OslabError(
            "Inventory JSON file could not be parsed",
            details={"path": str(args.inventory_json), "error": str(exc)},
        ) from exc

    analysis = analyze_inventory(inventory)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    console.ok("Inventory analyzed")
    _print_inventory_analysis(console, analysis)
    console.detail("inventoryJson", args.inventory_json)
    if args.output_json is not None:
        console.detail("outputJson", args.output_json)
    return 0


def cmd_qga_exec(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab qga exec")

    if args.env_file:
        env_result = load_env_file(args.env_file)
        console.ok("Env file loaded")
        console.detail("file", args.env_file)
        console.detail("loadedKeys", ", ".join(env_result.loaded) if env_result.loaded else "<none>")
        console.detail(
            "skippedExistingKeys",
            ", ".join(env_result.skipped_existing) if env_result.skipped_existing else "<none>",
        )

    command = _normalize_remainder_command(args.command)
    if not command:
        raise OslabError(
            "Guest command is required after `--`",
            details={"example": "oslab qga-exec --config config/oslab.local.yaml --vm-id 9101 -- whoami"},
        )

    config = load_config(args.config)
    proxmox = proxmox_config_from_oslab(config)

    console.ok("Provider config loaded")
    console.detail("apiUrl", proxmox.api_url)
    console.detail("node", proxmox.node)
    console.detail("tokenId", redact_value(proxmox.token_id))
    console.detail("tokenSecret", "<redacted>")

    console.step("Execute command through QEMU Guest Agent")
    console.detail("vmId", args.vm_id)
    console.detail("timeoutSeconds", args.timeout_seconds)
    console.detail("pollIntervalSeconds", args.poll_interval_seconds)
    console.detail("command", _format_command(command))

    channel = QemuAgentChannel(ProxmoxClient(proxmox))
    result = channel.execute(
        VmRef(vm_id=args.vm_id, node=proxmox.node),
        command,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    _print_guest_command_result(console, result)
    return 0 if result.passed else (result.exit_code or 1)


def cmd_qga_upload(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab qga upload")

    if args.env_file:
        _print_env_load(console, args.env_file)

    if not args.local_path.exists():
        raise OslabError(f"Local upload file does not exist: {args.local_path}", details={"path": str(args.local_path)})
    if not args.local_path.is_file():
        raise OslabError(f"Local upload path is not a file: {args.local_path}", details={"path": str(args.local_path)})

    config = load_config(args.config)
    proxmox = proxmox_config_from_oslab(config)
    _print_provider_config(console, proxmox)

    content = args.local_path.read_bytes()
    console.step("Upload file through QEMU Guest Agent")
    console.detail("vmId", args.vm_id)
    console.detail("localPath", args.local_path)
    console.detail("guestPath", args.guest_path)
    console.detail("bytes", len(content))

    channel = QemuAgentChannel(ProxmoxClient(proxmox))
    result = channel.upload_bytes(VmRef(vm_id=args.vm_id, node=proxmox.node), args.guest_path, content)
    console.ok("QEMU Guest Agent file upload completed")
    console.detail("guestPath", result.guest_path)
    console.detail("bytesWritten", result.bytes_written)
    return 0


def cmd_qga_download(args: argparse.Namespace) -> int:
    console = Console()
    console.section("oslab qga download")

    if args.env_file:
        _print_env_load(console, args.env_file)

    config = load_config(args.config)
    proxmox = proxmox_config_from_oslab(config)
    _print_provider_config(console, proxmox)

    console.step("Download text file through QEMU Guest Agent")
    console.detail("vmId", args.vm_id)
    console.detail("guestPath", args.guest_path)
    console.detail("localPath", args.local_path)

    channel = QemuAgentChannel(ProxmoxClient(proxmox))
    result = channel.download_text(VmRef(vm_id=args.vm_id, node=proxmox.node), args.guest_path)
    args.local_path.parent.mkdir(parents=True, exist_ok=True)
    args.local_path.write_bytes(result.content.encode("utf-8"))
    console.ok("QEMU Guest Agent file download completed")
    console.detail("guestPath", result.guest_path)
    console.detail("localPath", args.local_path)
    console.detail("bytesRead", result.bytes_read)
    return 0


def cmd_inspect_result(args: argparse.Namespace) -> int:
    run_json = args.run_dir / "run.json"
    if not run_json.exists():
        raise OslabError(f"Missing run.json: {run_json}", details={"runDir": str(args.run_dir)})
    payload = json.loads(run_json.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    console = Console()
    console.section("oslab inspect result")
    console.detail("runId", payload.get("runId") or "<unknown>")
    console.detail("scenario", payload.get("scenarioId") or "<unknown>")
    status = str(payload.get("status") or "unknown")
    if status == "passed":
        console.ok("Run passed")
    elif status == "failed":
        console.fail("Run failed")
    else:
        console.warn(f"Run status: {status}")
    console.detail("failureClass", payload.get("failureClass") or "<none>")
    console.detail("guestChannel", payload.get("selectedGuestChannel") or "<none>")

    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    console.detail("runDir", details.get("runDir") or str(args.run_dir))
    vm = details.get("vm") if isinstance(details.get("vm"), dict) else {}
    if vm:
        console.detail("vmId", vm.get("id") or "<unknown>")
        console.detail("vmDestroyed", vm.get("destroyed"))
        console.detail("vmKept", vm.get("kept"))

    assertions = details.get("assertions") if isinstance(details.get("assertions"), dict) else {}
    if assertions:
        console.detail("assertions", f"{assertions.get('total', 0)} total, {assertions.get('failed', 0)} failed")

    outputs = details.get("outputs") if isinstance(details.get("outputs"), dict) else {}
    if outputs:
        console.detail("rawOutput", outputs.get("raw") or "<none>")
        console.detail("normalizedOutput", outputs.get("normalized") or "<none>")
        if outputs.get("productSteps"):
            console.detail("productSteps", outputs.get("productSteps"))
        console.detail("collectedBytes", outputs.get("collectedBytes") if outputs.get("collectedBytes") is not None else "<none>")

    preflight = details.get("preflight") if isinstance(details.get("preflight"), dict) else {}
    if preflight and preflight.get("total", 0):
        console.detail("preflight", f"{preflight.get('total', 0)} total, {preflight.get('failed', 0)} failed")

    fixtures = details.get("fixtures") if isinstance(details.get("fixtures"), dict) else {}
    if fixtures and fixtures.get("total", 0):
        console.detail("fixtures", f"{fixtures.get('total', 0)} total, {fixtures.get('failed', 0)} failed")
        for fixture in fixtures.get("items", []):
            if not isinstance(fixture, dict) or fixture.get("passed", True):
                continue
            console.fail(f"fixture:{fixture.get('id') or '<unknown>'}")
            console.detail("message", fixture.get("message") or "<none>")
            console.detail("exitCode", fixture.get("exitCode") if fixture.get("exitCode") is not None else "<none>")
            if fixture.get("stdout"):
                console.detail("stdout", _preview_text(fixture.get("stdout")))
            if fixture.get("stderr"):
                console.detail("stderr", _preview_text(fixture.get("stderr")))

    scan = details.get("scan") if isinstance(details.get("scan"), dict) else {}
    if scan:
        console.ok("Scan summary" if scan.get("ok") is not False else "Scan reported failure")
        console.detail("scan.ok", scan.get("ok") if "ok" in scan else "<missing>")
        console.detail("scan.outputWritten", scan.get("outputWritten") if "outputWritten" in scan else "<missing>")
        console.detail("scan.bytesWritten", scan.get("bytesWritten") if scan.get("bytesWritten") is not None else "<none>")
        console.detail("scan.scanId", scan.get("scanId") or "<none>")
        console.detail("scan.uploadRequested", scan.get("uploadRequested") if "uploadRequested" in scan else "<missing>")
        console.detail("scan.uploadSuccess", scan.get("uploadSuccess") if "uploadSuccess" in scan else "<missing>")

    _print_inspect_inventory_analysis(console, args.run_dir)
    _print_inspect_command_result(console, args.run_dir)
    _print_inspect_product_steps(console, args.run_dir)

    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else {}
    for name, path in sorted(reports.items()):
        console.detail(f"report:{name}", path)

    logs = details.get("logs") if isinstance(details.get("logs"), dict) else {}
    for name, path in sorted(logs.items()):
        console.detail(f"log:{name}", path)
    return 0


def _print_inspect_inventory_analysis(console: Console, run_dir: Path) -> None:
    inventory_path = run_dir / "normalized" / "inventory.json"
    if not inventory_path.exists():
        return
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
        analysis = analyze_inventory(inventory)
    except Exception as exc:
        console.warn("Inventory analysis could not be produced")
        console.detail("path", inventory_path)
        console.detail("error", str(exc))
        return
    console.ok("Inventory analysis")
    _print_inventory_analysis(console, analysis)


def _print_inspect_command_result(console: Console, run_dir: Path) -> None:
    command_path = run_dir / "normalized" / "command-result.json"
    if not command_path.exists():
        return
    try:
        payload = json.loads(command_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        console.warn("Command result JSON could not be parsed")
        console.detail("path", command_path)
        console.detail("error", str(exc))
        return
    if not isinstance(payload, dict) or payload.get("kind") != "commandResult":
        return

    exit_code = payload.get("exitCode")
    if exit_code == 0:
        console.ok("Command result")
    else:
        console.fail("Command result")
    console.detail("command", payload.get("command") or "<none>")
    console.detail("exitCode", exit_code if exit_code is not None else "<none>")
    console.detail("stdout", _preview_text(payload.get("stdout")))
    console.detail("stderr", _preview_text(payload.get("stderr")))


def _preview_text(value, *, limit: int = 500) -> str:
    text = "" if value is None else str(value)
    text = text.strip()
    if not text:
        return "<empty>"
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def _print_inventory_analysis(console: Console, analysis: dict) -> None:
    quality = analysis.get("quality") if isinstance(analysis.get("quality"), dict) else {}
    console.detail("records", analysis.get("recordCount", 0))
    console.detail("sources", _format_count_mapping(analysis.get("sourceCounts")))
    console.detail("publishers", _format_count_mapping(analysis.get("publisherCounts")))
    console.detail("confidence", _format_count_mapping(analysis.get("confidenceCounts")))
    console.detail("missingVersion", quality.get("missingVersion", 0))
    console.detail("missingPublisher", quality.get("missingPublisher", 0))
    console.detail("missingEvidencePath", quality.get("missingEvidencePath", 0))
    warnings = analysis.get("warnings") if isinstance(analysis.get("warnings"), list) else []
    console.detail("analysisWarnings", ", ".join(str(warning) for warning in warnings) if warnings else "<none>")


def _format_count_mapping(value) -> str:
    if not isinstance(value, dict) or not value:
        return "<none>"
    return ", ".join(f"{key}={value[key]}" for key in sorted(value))


def _print_inspect_product_steps(console: Console, run_dir: Path) -> None:
    steps_path = run_dir / "raw" / "product-steps.json"
    if not steps_path.exists():
        return
    try:
        steps = json.loads(steps_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        console.warn("Product steps JSON could not be parsed")
        console.detail("path", steps_path)
        console.detail("error", str(exc))
        return
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or "<unknown>")
        if bool(step.get("passed")):
            console.ok(f"step:{step_id}")
        else:
            console.fail(f"step:{step_id}")
        console.detail("exitCode", step.get("exitCode") if step.get("exitCode") is not None else "<none>")
        console.detail("message", step.get("message") or "<none>")
        stdout_json = step.get("stdoutJson")
        if isinstance(stdout_json, dict):
            console.detail("stdoutJson.ok", stdout_json.get("ok") if "ok" in stdout_json else "<missing>")
            if stdout_json.get("errorCode"):
                console.detail("stdoutJson.errorCode", stdout_json.get("errorCode"))
            if step_id == "scan":
                if "outputWritten" in stdout_json:
                    console.detail("stdoutJson.outputWritten", stdout_json.get("outputWritten"))
                if stdout_json.get("bytesWritten") is not None:
                    console.detail("stdoutJson.bytesWritten", stdout_json.get("bytesWritten"))
                if stdout_json.get("scanId"):
                    console.detail("stdoutJson.scanId", stdout_json.get("scanId"))
                if "uploadRequested" in stdout_json:
                    console.detail("stdoutJson.uploadRequested", stdout_json.get("uploadRequested"))
                if "uploadSuccess" in stdout_json:
                    console.detail("stdoutJson.uploadSuccess", stdout_json.get("uploadSuccess"))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except OslabError as exc:
        console = Console(stream=sys.stderr)
        console.fail(exc.message)
        if exc.details:
            console.detail("details", exc.details)
        return exc.exit_code


def _print_proxmox_resource_check(console: Console, check: ProxmoxResourceCheck) -> None:
    if check.node_exists:
        console.ok("Configured Proxmox node exists")
    else:
        console.fail("Configured Proxmox node was not found")
    console.detail("configuredNode", check.node)
    console.detail("availableNodes", _format_list(check.nodes))
    console.detail("vmResourceCount", check.vm_resource_count)

    if check.template.found:
        console.ok("Template VMID exists")
    else:
        console.fail("Template VMID was not found")
    console.detail("templateVmId", check.template.vm_id if check.template.vm_id is not None else "<missing>")
    console.detail("templateName", check.template.name or "<unknown>")
    console.detail("templateNode", check.template.node or "<unknown>")
    console.detail("templateStatus", check.template.status or "<unknown>")
    if check.template.is_template is True:
        console.ok("Template flag confirmed")
    elif check.template.is_template is False:
        console.fail("Template flag is not set")
    else:
        console.warn("Template flag could not be confirmed")

    if check.vmid_range.start is None or check.vmid_range.end is None:
        console.warn("VMID range is not configured")
    else:
        console.ok("VMID range inspected")
        console.detail("range", f"{check.vmid_range.start}-{check.vmid_range.end}")
        console.detail("usedInRange", _format_list([str(vm_id) for vm_id in check.vmid_range.used_in_range]))
        console.detail("recommendedVmId", check.vmid_range.recommended_vmid or "<none>")

    for warning in check.warnings:
        console.warn(warning)


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "<none>"


def _print_env_load(console: Console, env_file: Path) -> None:
    env_result = load_env_file(env_file)
    console.ok("Env file loaded")
    console.detail("file", env_file)
    console.detail("loadedKeys", ", ".join(env_result.loaded) if env_result.loaded else "<none>")
    console.detail(
        "skippedExistingKeys",
        ", ".join(env_result.skipped_existing) if env_result.skipped_existing else "<none>",
    )


def _print_provider_config(console: Console, proxmox) -> None:
    console.ok("Provider config loaded")
    console.detail("apiUrl", proxmox.api_url)
    console.detail("node", proxmox.node)
    console.detail("tokenId", redact_value(proxmox.token_id))
    console.detail("tokenSecret", "<redacted>")


def _normalize_remainder_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def _format_command(command: list[str]) -> str:
    return " ".join(command)


def _print_guest_command_result(console: Console, result: GuestCommandResult) -> None:
    if result.passed:
        console.ok("QEMU Guest Agent command completed")
    else:
        console.fail("QEMU Guest Agent command failed")
    console.detail("exitCode", result.exit_code if result.exit_code is not None else "<missing>")
    console.detail("stdoutBytes", len(result.stdout.encode("utf-8")))
    console.detail("stderrBytes", len(result.stderr.encode("utf-8")))
    if result.stdout:
        console.section("stdout")
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", file=console.output)
    if result.stderr:
        console.section("stderr")
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=console.output)


def _print_progress_event(console: Console, event: ProgressEvent) -> None:
    if event.phase.endswith(".failed"):
        console.fail(event.message)
    elif event.phase.endswith(".done"):
        console.ok(event.message)
    elif event.phase.endswith(".skipped"):
        console.warn(event.message)
    else:
        console.step(event.message)
    for key, value in event.details.items():
        console.detail(key, value)


def _print_run_result(console: Console, result) -> None:
    if result.status == "passed":
        console.ok("Run completed")
    else:
        console.fail("Run failed")
    console.detail("runId", result.run_id)
    console.detail("scenario", result.scenario_id)
    console.detail("status", result.status)
    console.detail("failureClass", result.failure_class or "<none>")
    for name, path in sorted(result.reports.items()):
        console.detail(f"report:{name}", path)


def _print_guest_preflight_result(console: Console, result: GuestPreflightResult) -> None:
    if result.passed:
        console.ok("Guest preflight completed")
    else:
        console.fail("Guest preflight failed")
    console.detail("cloneVmId", result.vm.vm_id)
    console.detail("cloneName", result.clone_name)
    console.detail("cloneStatus", result.status.status)
    console.detail("guestInfo", "available" if result.guest_info else "<missing>")
    console.detail("started", str(result.started).lower())
    console.detail("destroyed", str(result.destroyed).lower())
    console.detail("kept", str(result.kept).lower())
    for check in result.checks:
        if check.passed:
            console.ok(f"check:{check.id}")
        else:
            console.fail(f"check:{check.id}")
        console.detail("message", check.message)
        if check.details:
            console.detail("details", check.details)


def _print_fixture_smoke_result(console: Console, result: FixtureSmokeResult) -> None:
    if result.passed:
        console.ok("Fixture smoke completed")
    else:
        console.fail("Fixture smoke failed")
    console.detail("cloneVmId", result.vm.vm_id)
    console.detail("cloneName", result.clone_name)
    console.detail("cloneStatus", result.status.status)
    console.detail("guestInfo", "available" if result.guest_info else "<missing>")
    console.detail("started", str(result.started).lower())
    console.detail("destroyed", str(result.destroyed).lower())
    console.detail("kept", str(result.kept).lower())
    for fixture in result.fixtures:
        if fixture.passed:
            console.ok(f"fixture:{fixture.id}")
        else:
            console.fail(f"fixture:{fixture.id}")
        console.detail("message", fixture.message)
        console.detail("source", fixture.source)
        console.detail("guestPath", fixture.guest_path)
        console.detail("uploadedBytes", fixture.uploaded_bytes)
        console.detail("exitCode", fixture.exit_code if fixture.exit_code is not None else "<missing>")
        console.detail("stdout", fixture.stdout.strip() or "<empty>")
        console.detail("stderr", fixture.stderr.strip() or "<empty>")
        if fixture.expected_output:
            console.detail("expectedOutput", fixture.expected_output)
        if fixture.collected_bytes is not None:
            console.detail("collectedBytes", fixture.collected_bytes)
        if fixture.local_output_path is not None:
            console.detail("localOutputPath", fixture.local_output_path)


def _print_artifact_smoke_result(console: Console, result: ArtifactSmokeResult) -> None:
    if result.passed:
        console.ok("Artifact smoke completed")
    else:
        console.fail("Artifact smoke failed")
    console.detail("message", result.message)
    console.detail("cloneVmId", result.vm.vm_id)
    console.detail("cloneName", result.clone_name)
    console.detail("cloneStatus", result.status.status)
    console.detail("guestInfo", "available" if result.guest_info else "<missing>")
    console.detail("started", str(result.started).lower())
    console.detail("destroyed", str(result.destroyed).lower())
    console.detail("kept", str(result.kept).lower())
    console.detail("artifactPath", result.artifact_path)
    console.detail("artifactDestination", result.artifact_destination)
    console.detail("uploadedFiles", len(result.uploaded_files))
    console.detail("uploadedBytes", sum(file.bytes_written for file in result.uploaded_files))
    if result.install_command is not None:
        console.detail("installCommand", result.install_command.safe_rendered)
        console.detail("installExitCode", result.install_exit_code if result.install_exit_code is not None else "<missing>")
        console.detail("installStdout", result.install_stdout.strip() or "<empty>")
        console.detail("installStderr", result.install_stderr.strip() or "<empty>")
    for step in result.product_steps:
        if step.passed:
            console.ok(f"productStep:{step.id}")
        else:
            console.fail(f"productStep:{step.id}")
        console.detail("message", step.message)
        console.detail("command", step.command.safe_rendered)
        console.detail("exitCode", step.exit_code if step.exit_code is not None else "<missing>")
        console.detail("stdoutBytes", len(step.stdout.encode("utf-8")))
        console.detail("stderrBytes", len(step.stderr.encode("utf-8")))
        console.detail("stdoutJson", "available" if step.stdout_json is not None else "<none>")
    if result.local_product_steps_path is not None:
        console.detail("localProductStepsPath", result.local_product_steps_path)
    console.detail("command", result.command.safe_rendered)
    console.detail("exitCode", result.exit_code if result.exit_code is not None else "<missing>")
    console.detail("stdout", result.stdout.strip() or "<empty>")
    console.detail("stderr", result.stderr.strip() or "<empty>")
    console.detail("outputPath", result.output_path)
    console.detail("outputAdapter", result.output_adapter)
    if result.collected_bytes is not None:
        console.detail("collectedBytes", result.collected_bytes)
    if result.local_output_path is not None:
        console.detail("localOutputPath", result.local_output_path)
    if result.local_normalized_path is not None:
        console.detail("localNormalizedPath", result.local_normalized_path)
    for log_name, log_path in sorted(result.local_log_paths.items()):
        console.detail(f"localLog:{log_name}", log_path)
    for report_format, report_path in sorted(result.local_report_paths.items()):
        console.detail(f"localReport:{report_format}", report_path)
    _print_assertion_results(console, result.assertions)


def _print_assertion_results(console: Console, assertions: list[AssertionResult]) -> None:
    for assertion in assertions:
        if assertion.passed:
            console.ok(f"assertion:{assertion.id}")
        else:
            console.fail(f"assertion:{assertion.id}")
        console.detail("type", assertion.type)
        console.detail("message", assertion.message)
        if assertion.failure_class:
            console.detail("failureClass", assertion.failure_class)
        if assertion.details:
            console.detail("details", assertion.details)


if __name__ == "__main__":
    raise SystemExit(main())
