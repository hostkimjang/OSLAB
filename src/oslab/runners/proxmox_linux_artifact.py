"""Linux artifact runner over Proxmox QEMU Guest Agent.

`run_proxmox_artifact_smoke` clones and boots the VM, then hands Linux scenarios to
`run_linux_artifact`. Guest commands run through `sh` or `bash` with POSIX paths, while
results, logs, reports and progress phases follow the Windows flow.
"""

from __future__ import annotations

import io
import json
import shlex
import tarfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from oslab.assertions import evaluate_assertions
from oslab.commands import TOKEN_PATTERN, CommandSpec, render_command_template
from oslab.config import OslabConfig
from oslab.errors import OslabError
from oslab.guests.base import GuestCommandResult, GuestFileReadResult
from oslab.guests.qemu_agent import LinuxQemuAgentChannel
from oslab.models.scenario import Scenario
from oslab.plugins import normalize_output
from oslab.providers.base import GuestInfo, VmRef, VmStatus
from oslab.runners.proxmox_artifact_smoke import (
    ArtifactSmokeResult,
    ProductStepResult,
    ProgressCallback,
    UploadedArtifactFile,
    _artifact_exclude_patterns,
    _artifact_transfer_mode,
    _early_artifact_result,
    _emit_progress,
    _emit_transfer_progress,
    _folder_artifact_files,
    _is_product_failure_artifact,
    _redact_text_secrets,
    _run_product_step,
    _scenario_artifact,
    _scenario_artifact_command,
    _scenario_fixture_specs,
    _scenario_install_command,
    _scenario_product_secret_values,
    _scenario_product_steps,
    _write_artifact_logs,
    _write_artifact_output,
    _write_normalized_output,
    _write_product_steps_output,
)
from oslab.runners.proxmox_fixture_smoke import (
    FixtureSmokeItem,
    _repo_root_from_path,
    _resolve_repo_path,
    _write_fixture_output,
)
from oslab.runners.proxmox_guest_preflight import GuestPreflightCheck, _run_command_check, _run_file_roundtrip_check

LINUX_WORK_ROOT = "/opt/oslab"
LINUX_FIXTURE_ROOT = f"{LINUX_WORK_ROOT}/fixtures"
LINUX_DEFAULT_OUTPUT_PATH = f"{LINUX_WORK_ROOT}/result.json"
LINUX_SHELLS = {"sh", "bash"}

@dataclass(frozen=True)
class _LinuxCommandSpec(CommandSpec):
    arguments: tuple[str, ...] = field(default=(), repr=False)


def _render_linux_command(
    command: Mapping[str, object], tokens: Mapping[str, str], *, secret_tokens: Mapping[str, str] | None = None
) -> CommandSpec:
    # Use the shared renderer to validate placeholders and generate the display text.
    # Values reach sh as positional arguments, where quotes, newlines and shell metacharacters remain data.
    secrets = secret_tokens or {}
    display = render_command_template(command, tokens, secret_tokens=dict.fromkeys(secrets, "<redacted>"))
    values = {**tokens, **secrets}
    argument_numbers: dict[str, int] = {}
    script = []
    quote = ""
    index = 0
    template = display.template
    while index < len(template):
        token = TOKEN_PATTERN.match(template, index)
        char = template[index]
        if token:
            name = token.group(1)
            number = argument_numbers.setdefault(name, len(argument_numbers) + 1)
            variable = f"${{{number}}}"
            if quote == '"':
                script.append(variable)
            elif quote == "'":
                script.append(f"'\"{variable}\"'")
            else:
                script.append(f'"{variable}"')
            index = token.end()
        elif char == "\\" and quote != "'":
            script.append(template[index : index + 2])
            index += 2
        else:
            if char in {"'", '"'}:
                quote = "" if quote == char else quote or char
            script.append(char)
            index += 1

    return _LinuxCommandSpec(
        shell=display.shell,
        template=template,
        rendered="".join(script),
        redacted=display.safe_rendered,
        arguments=tuple(values[name] for name in argument_numbers),
    )

# Prompt in the style of bash's default "\u@\h:\w\$ " for the user, host and
# working directory the guest agent actually runs commands with.
_CONSOLE_PROMPT = r"""
mark='$'
[ "$(id -u)" = 0 ] && mark='#'
prompt="$(id -un)@$(hostname):$(pwd)$mark "
"""

# Prepares the first text console (tty1) once per run. The tty1 login prompt is
# stopped so it cannot redraw over the commands, then the screen gets a large
# Terminus font when the guest ships one and the console can show it, a clear
# screen, and a prompt.
CONSOLE_SETUP_SCRIPT = (
    r"""
console=/dev/tty1
[ -w "$console" ] || exit 0
systemctl stop getty@tty1.service >/dev/null 2>&1
if command -v setfont >/dev/null 2>&1; then
  for font in /usr/share/consolefonts/Uni2-TerminusBold32x16.psf.gz /usr/share/consolefonts/*Terminus*32x16*; do
    [ -f "$font" ] && setfont -C "$console" "$font" && break
  done
fi
"""
    + _CONSOLE_PROMPT
    + r"""
printf '\033[H\033[2J\033[3J%s' "$prompt" >"$console"
"""
)

# Runs command "$2" with shell "$1" and shows it on tty1 as if typed at the
# prompt: the display line "$3", then the command's stdout and stderr, then a
# fresh prompt. QEMU Guest Agent still captures stdout, stderr and the exit
# code. "$4" is 0 when the scenario has secret values. Remaining arguments
# are data for the guest shell. Without tty1, the command runs without the copy.
CONSOLE_COMMAND_SCRIPT = (
    r"""
console=/dev/tty1
shell=$1
script=$2
display=$3
show_output=$4
shift 4
if [ ! -w "$console" ]; then exec "$shell" -c "$script" oslab "$@"; fi
"""
    + _CONSOLE_PROMPT
    + r"""
printf '\r%s%s\n' "$prompt" "$display" >"$console"
status_file=$(mktemp) || exit 1
trap 'rm -f -- "$status_file"' EXIT
if [ "$show_output" = 1 ]; then
  { { "$shell" -c "$script" oslab "$@"; echo "$?" >"$status_file"; } 2>&1 1>&3 3>&- | tee -a "$console" >&2; } 3>&1 | tee -a "$console"
else
  "$shell" -c "$script" oslab "$@"
  echo "$?" >"$status_file"
  echo "(output hidden because the scenario uses secret tokens)" >"$console"
fi
status=$(cat "$status_file")
[ "$status" = 0 ] || printf '[exit %s]\n' "$status" >"$console"
printf '%s' "$prompt" >"$console"
exit "$status"
"""
)


def linux_shell_argv(command: CommandSpec, *, show_on_console: bool = False, secrets: tuple[str, ...] = ()) -> list[str]:
    """Build the guest argv for a rendered `sh` or `bash` command."""

    if command.shell not in LINUX_SHELLS:
        raise OslabError(
            f"Unsupported Linux command shell: {command.shell}",
            details={"shell": command.shell, "expected": sorted(LINUX_SHELLS)},
        )
    arguments = command.arguments if isinstance(command, _LinuxCommandSpec) else ()
    if not show_on_console:
        return [command.shell, "-c", command.rendered, "oslab", *arguments]
    return [
        "sh",
        "-c",
        CONSOLE_COMMAND_SCRIPT,
        "oslab-console",
        command.shell,
        command.rendered,
        _redact_text_secrets(command.safe_rendered, secrets),
        "0" if secrets else "1",
        *arguments,
    ]


def _execute_linux_command(
    command: CommandSpec,
    *,
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    timeout_seconds: int,
    show_on_console: bool,
    secrets: tuple[str, ...],
) -> GuestCommandResult:
    argv = linux_shell_argv(command, show_on_console=show_on_console, secrets=secrets)
    if secrets:
        return channel.execute_with_diagnostics(
            vm,
            argv,
            diagnostic_command=(command.shell, "-c", _redact_text_secrets(command.safe_rendered, secrets)),
            timeout_seconds=timeout_seconds,
        )
    return channel.execute(vm, argv, timeout_seconds=timeout_seconds)


def run_linux_artifact(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    artifact_path: Path,
    command_timeout_seconds: int,
    progress: ProgressCallback | None = None,
    run_dir: Path | None = None,
) -> ArtifactSmokeResult:
    """Prepare a booted Linux guest, run the scenario's artifact commands, and evaluate the collected output."""

    artifact = _scenario_artifact(scenario)
    artifact_type = str(artifact.get("type"))
    destination = str(artifact["destination"])
    output_path = scenario.output_path or LINUX_DEFAULT_OUTPUT_PATH
    secrets = tuple(sorted(_scenario_product_secret_values(scenario), key=len, reverse=True))
    execute_command = partial(
        _execute_linux_command,
        channel=channel,
        vm=vm,
        timeout_seconds=command_timeout_seconds,
        show_on_console=scenario.show_commands,
        secrets=secrets,
    )
    command_tokens = {"ArtifactDir": destination, "OutputPath": output_path}
    guest_checks: list[GuestPreflightCheck] = []
    fixtures: list[FixtureSmokeItem] = []

    if scenario.show_commands:
        # A failed console setup only affects what the screen shows, so its exit code is ignored.
        channel.execute(vm, ["sh", "-c", CONSOLE_SETUP_SCRIPT], timeout_seconds=command_timeout_seconds)

    if run_dir is not None:
        guest_checks = _run_preflight(channel, vm, command_timeout_seconds=command_timeout_seconds, progress=progress)
        if any(not check.passed for check in guest_checks):
            return _early_artifact_result(
                vm,
                scenario=scenario,
                artifact_path=artifact_path,
                artifact_destination=destination,
                output_path=output_path,
                output_adapter=scenario.output_adapter,
                message="Guest preflight failed",
                guest_checks=guest_checks,
                fixtures=fixtures,
            )
        if _scenario_fixture_specs(scenario):
            fixtures = _apply_fixtures(
                channel,
                vm,
                scenario=scenario,
                oslab_config=oslab_config,
                command_timeout_seconds=command_timeout_seconds,
                run_dir=run_dir,
                progress=progress,
            )
            if any(not fixture.passed for fixture in fixtures):
                return _early_artifact_result(
                    vm,
                    scenario=scenario,
                    artifact_path=artifact_path,
                    artifact_destination=destination,
                    output_path=output_path,
                    output_adapter=scenario.output_adapter,
                    message="Fixture failed",
                    guest_checks=guest_checks,
                    fixtures=fixtures,
                )

    install_command: CommandSpec | None = None
    install_exit_code: int | None = None
    install_stdout = ""
    install_stderr = ""
    if artifact_type == "folder":
        uploaded_files = _upload_folder_artifact(
            channel,
            vm,
            artifact_path,
            destination,
            artifact=artifact,
            command_timeout_seconds=command_timeout_seconds,
            progress=progress,
        )
    elif artifact_type == "installer":
        uploaded_files = [
            _upload_installer_artifact(
                channel,
                vm,
                artifact_path,
                destination,
                command_timeout_seconds=command_timeout_seconds,
                progress=progress,
            )
        ]
        command_tokens = {
            "ArtifactDir": str(PurePosixPath(destination).parent),
            "InstallerPath": destination,
            "OutputPath": output_path,
        }
        install_command = _render_linux_command(_scenario_install_command(artifact), command_tokens)
        _emit_progress(progress, "artifact.install.start", "Run artifact installer", destination=destination)
        install = execute_command(install_command)
        install_exit_code = install.exit_code
        install_stdout = _redact_text_secrets(install.stdout, secrets)
        install_stderr = _redact_text_secrets(install.stderr, secrets)
        if not install.passed:
            _emit_progress(
                progress,
                "artifact.install.failed",
                "Artifact installer failed",
                exitCode=install_exit_code if install_exit_code is not None else "<missing>",
            )
            failed_install = _early_artifact_result(
                vm,
                scenario=scenario,
                artifact_path=artifact_path,
                artifact_destination=destination,
                output_path=output_path,
                output_adapter=scenario.output_adapter,
                message="Artifact install command failed",
                guest_checks=guest_checks,
                fixtures=fixtures,
            )
            return replace(
                failed_install,
                uploaded_files=uploaded_files,
                install_command=install_command,
                install_exit_code=install_exit_code,
                install_stdout=install_stdout,
                install_stderr=install_stderr,
                local_log_paths=_write_artifact_logs(
                    oslab_config.output_root,
                    scenario.scenario_id,
                    install_stdout=install_stdout,
                    install_stderr=install_stderr,
                    product_stdout="",
                    product_stderr="",
                    product_steps=[],
                    run_dir=run_dir,
                ),
            )
        _emit_progress(progress, "artifact.install.done", "Artifact installer completed", exitCode=install_exit_code)
    else:
        raise OslabError("Unsupported artifact type", details={"type": artifact_type})

    _run_guest_command(
        channel,
        vm,
        ["sh", "-c", 'test ! -e "$1" && test ! -L "$1"', "oslab", output_path],
        timeout_seconds=command_timeout_seconds,
        failure_message="Product output path already exists before the product command",
    )
    product_steps: list[ProductStepResult] = []
    local_product_steps_path: Path | None = None
    if _scenario_product_steps(scenario):
        product_steps = _run_product_steps(
            channel,
            vm,
            scenario=scenario,
            tokens=command_tokens,
            execute_command=execute_command,
            secrets=secrets,
            timeout_seconds=command_timeout_seconds,
            progress=progress,
        )
        local_product_steps_path = _write_product_steps_output(
            oslab_config.output_root,
            scenario.scenario_id,
            product_steps,
            run_dir=run_dir,
        )
        _emit_progress(progress, "product.steps.write.done", "Product step results written", path=local_product_steps_path)
        last_step = product_steps[-1]
        command = last_step.command
        exit_code = last_step.exit_code
        stdout = last_step.stdout
        stderr = last_step.stderr
        passed = last_step.passed
        message = "Artifact smoke passed" if passed else f"Product step failed: {last_step.id}"
    else:
        command = _render_linux_command(_scenario_artifact_command(artifact), command_tokens)
        _emit_progress(progress, "product.command.start", "Run product command")
        execution = execute_command(command)
        exit_code = execution.exit_code
        stdout = execution.stdout
        stderr = execution.stderr
        passed = execution.passed
        message = "Artifact smoke passed" if passed else "Artifact command failed"
        _emit_progress(
            progress,
            "product.command.done" if passed else "product.command.failed",
            "Product command completed" if passed else "Product command failed",
            exitCode=exit_code if exit_code is not None else "<missing>",
            stdoutBytes=len(stdout.encode("utf-8")),
            stderrBytes=len(stderr.encode("utf-8")),
        )

    result = ArtifactSmokeResult(
        vm=vm,
        clone_name=vm.name or f"vm-{vm.vm_id}",
        status=VmStatus(vm_id=vm.vm_id, status="unknown"),
        guest_info=GuestInfo(vm_id=vm.vm_id),
        artifact_path=artifact_path,
        artifact_destination=destination,
        uploaded_files=uploaded_files,
        install_command=install_command,
        install_exit_code=install_exit_code,
        install_stdout=install_stdout,
        install_stderr=install_stderr,
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        output_path=output_path,
        output_adapter=scenario.output_adapter,
        collected_bytes=None,
        collected_json=None,
        local_output_path=None,
        normalized_json=None,
        local_normalized_path=None,
        started=True,
        destroyed=False,
        kept=True,
        passed=passed,
        message=message,
        product_steps=product_steps,
        local_product_steps_path=local_product_steps_path,
        local_log_paths=_write_artifact_logs(
            oslab_config.output_root,
            scenario.scenario_id,
            install_stdout=install_stdout,
            install_stderr=install_stderr,
            product_stdout=stdout,
            product_stderr=stderr,
            product_steps=product_steps,
            run_dir=run_dir,
        ),
        guest_checks=guest_checks,
        fixtures=fixtures,
    )
    if not passed:
        return result
    return _collect_output(
        channel,
        vm,
        scenario=scenario,
        oslab_config=oslab_config,
        result=result,
        run_dir=run_dir,
        progress=progress,
        secrets=secrets,
        command_timeout_seconds=command_timeout_seconds,
    )


def run_linux_guest_checks(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    *,
    command_timeout_seconds: int,
) -> list[GuestPreflightCheck]:
    """Check that the guest runs `sh` and that the OSLab work directory accepts a file round trip."""

    test_file = f"{LINUX_WORK_ROOT}/oslab-preflight.txt"
    return [
        _run_command_check(
            channel,
            vm,
            check_id="linux.shell",
            command=["sh", "-c", "uname -s"],
            timeout_seconds=command_timeout_seconds,
            expected_stdout="Linux",
        ),
        _run_command_check(
            channel,
            vm,
            check_id="oslab.directory",
            command=["sh", "-c", 'mkdir -p "$1" && test -w "$1"', "sh", LINUX_WORK_ROOT],
            timeout_seconds=command_timeout_seconds,
        ),
        _run_file_roundtrip_check(channel, vm, guest_path=test_file),
        _run_command_check(
            channel,
            vm,
            check_id="oslab.cleanup_test_file",
            command=["rm", "-f", test_file],
            timeout_seconds=command_timeout_seconds,
        ),
    ]


def run_linux_fixtures(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    command_timeout_seconds: int,
    run_dir: Path | None = None,
) -> list[FixtureSmokeItem]:
    """Upload and run every `shell` fixture, collecting each optional `expectedOutput` JSON file."""

    _run_guest_command(
        channel,
        vm,
        ["mkdir", "-p", LINUX_FIXTURE_ROOT],
        timeout_seconds=command_timeout_seconds,
        failure_message="Failed to create guest fixture directory",
    )
    return [
        _run_fixture(
            channel,
            vm,
            fixture=fixture,
            scenario=scenario,
            oslab_config=oslab_config,
            command_timeout_seconds=command_timeout_seconds,
            run_dir=run_dir,
        )
        for fixture in _scenario_fixture_specs(scenario)
    ]


def _run_preflight(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    *,
    command_timeout_seconds: int,
    progress: ProgressCallback | None,
) -> list[GuestPreflightCheck]:
    _emit_progress(progress, "preflight.start", "Run guest preflight checks")
    checks = run_linux_guest_checks(channel, vm, command_timeout_seconds=command_timeout_seconds)
    for check in checks:
        _emit_progress(
            progress,
            "preflight.check.done" if check.passed else "preflight.check.failed",
            "Guest preflight check passed" if check.passed else "Guest preflight check failed",
            checkId=check.id,
            checkMessage=check.message,
        )
    failed = sum(1 for check in checks if not check.passed)
    if failed:
        _emit_progress(progress, "preflight.failed", "Guest preflight failed", checks=len(checks), failed=failed)
    else:
        _emit_progress(progress, "preflight.done", "Guest preflight passed", checks=len(checks))
    return checks


def _apply_fixtures(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    command_timeout_seconds: int,
    run_dir: Path,
    progress: ProgressCallback | None,
) -> list[FixtureSmokeItem]:
    _emit_progress(progress, "fixture.start", "Apply scenario fixtures", fixtures=len(_scenario_fixture_specs(scenario)))
    fixtures = run_linux_fixtures(
        channel,
        vm,
        scenario=scenario,
        oslab_config=oslab_config,
        command_timeout_seconds=command_timeout_seconds,
        run_dir=run_dir,
    )
    for fixture in fixtures:
        _emit_progress(
            progress,
            "fixture.done" if fixture.passed else "fixture.failed",
            "Fixture applied" if fixture.passed else "Fixture failed",
            fixtureId=fixture.id,
            exitCode=fixture.exit_code if fixture.exit_code is not None else "<missing>",
            collectedBytes=fixture.collected_bytes if fixture.collected_bytes is not None else "<none>",
        )
    if all(fixture.passed for fixture in fixtures):
        _emit_progress(progress, "fixture.all.done", "Scenario fixtures applied", fixtures=len(fixtures))
    return fixtures


def _run_fixture(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    *,
    fixture: dict,
    scenario: Scenario,
    oslab_config: OslabConfig,
    command_timeout_seconds: int,
    run_dir: Path | None,
) -> FixtureSmokeItem:
    fixture_id = str(fixture["id"])
    fixture_type = str(fixture["type"])
    source = _resolve_repo_path(_repo_root_from_path(scenario.path), str(fixture["source"]))
    if not source.is_file():
        raise OslabError(f"Fixture source does not exist: {source}", details={"fixtureId": fixture_id, "source": str(source)})
    if fixture_type != "shell":
        raise OslabError(f"Unsupported Linux fixture type: {fixture_type}", details={"fixtureId": fixture_id, "expected": "shell"})

    guest_path = f"{LINUX_FIXTURE_ROOT}/{source.name}"
    # Windows checkouts may turn LF into CRLF, which `sh` cannot run.
    upload = channel.upload_bytes(vm, guest_path, source.read_bytes().replace(b"\r\n", b"\n"))
    _run_guest_command(
        channel,
        vm,
        ["chmod", "+x", guest_path],
        timeout_seconds=command_timeout_seconds,
        failure_message="Failed to mark guest fixture executable",
    )
    # Running the path through `sh -c` honours a shebang line and falls back to sh without one.
    script = shlex.quote(guest_path)
    secrets = tuple(sorted(_scenario_product_secret_values(scenario), key=len, reverse=True))
    command = _execute_linux_command(
        CommandSpec(shell="sh", template=script, rendered=script),
        channel=channel,
        vm=vm,
        timeout_seconds=command_timeout_seconds,
        show_on_console=scenario.show_commands,
        secrets=secrets,
    )
    expected_output = fixture.get("expectedOutput")
    item = FixtureSmokeItem(
        id=fixture_id,
        fixture_type=fixture_type,
        source=source,
        guest_path=guest_path,
        expected_output=expected_output if isinstance(expected_output, str) else None,
        uploaded_bytes=upload.bytes_written,
        exit_code=command.exit_code,
        stdout=_redact_text_secrets(command.stdout, secrets),
        stderr=_redact_text_secrets(command.stderr, secrets),
        passed=command.passed,
        message="Fixture smoke passed" if command.passed else "Fixture command failed",
    )
    if not command.passed or not isinstance(expected_output, str) or not expected_output.strip():
        return item

    download = _download_scenario_output(channel, vm, expected_output, secrets)
    collected_json, content, parse_error = _prepare_collected_output(download.content, secrets)
    local_output_path = _write_fixture_output(
        oslab_config.output_root,
        scenario.scenario_id,
        fixture_id,
        content,
        run_dir=run_dir,
    )
    if parse_error is not None:
        return replace(
            item,
            collected_bytes=download.bytes_read,
            collected_json={"jsonError": parse_error},
            local_output_path=local_output_path,
            passed=False,
            message="Expected output was not valid JSON",
        )
    return replace(
        item,
        collected_bytes=download.bytes_read,
        collected_json=collected_json,
        local_output_path=local_output_path,
    )


def _upload_folder_artifact(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    artifact_path: Path,
    destination: str,
    *,
    artifact: dict,
    command_timeout_seconds: int,
    progress: ProgressCallback | None,
) -> list[UploadedArtifactFile]:
    if not artifact_path.is_dir():
        raise OslabError(f"Folder artifact path is not a directory: {artifact_path}", details={"path": str(artifact_path)})
    files = _folder_artifact_files(artifact_path, _artifact_exclude_patterns(artifact))
    if not files:
        raise OslabError(f"Folder artifact does not contain any files: {artifact_path}", details={"path": str(artifact_path)})

    _emit_progress(progress, "artifact.prepare.start", "Prepare artifact directory", destination=destination)
    _run_guest_command(
        channel,
        vm,
        ["mkdir", "-p", destination],
        timeout_seconds=command_timeout_seconds,
        failure_message="Failed to create guest artifact directory",
    )
    _emit_progress(progress, "artifact.prepare.done", "Artifact directory is ready", destination=destination)

    transfer_mode = _artifact_transfer_mode(artifact)
    total_bytes = sum(path.stat().st_size for path in files)
    _emit_progress(
        progress,
        "artifact.upload.start",
        "Upload artifact folder",
        mode=transfer_mode,
        files=len(files),
        bytes=total_bytes,
    )
    if transfer_mode == "archive":
        uploaded = _upload_folder_archive(
            channel,
            vm,
            artifact_path,
            files,
            destination,
            command_timeout_seconds=command_timeout_seconds,
            progress=progress,
        )
    else:
        uploaded = _upload_folder_files(
            channel,
            vm,
            artifact_path,
            files,
            destination,
            total_bytes=total_bytes,
            command_timeout_seconds=command_timeout_seconds,
            progress=progress,
        )
    _emit_progress(
        progress,
        "artifact.upload.done",
        "Artifact folder uploaded",
        mode=transfer_mode,
        files=len(files),
        uploadedFiles=len(uploaded),
        bytes=sum(file.bytes_written for file in uploaded),
    )
    return uploaded


def _upload_folder_files(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    artifact_path: Path,
    files: list[Path],
    destination: str,
    *,
    total_bytes: int,
    command_timeout_seconds: int,
    progress: ProgressCallback | None,
) -> list[UploadedArtifactFile]:
    guest_paths = [str(PurePosixPath(destination) / path.relative_to(artifact_path).as_posix()) for path in files]
    _run_guest_command(
        channel,
        vm,
        ["mkdir", "-p", *sorted({str(PurePosixPath(guest_path).parent) for guest_path in guest_paths})],
        timeout_seconds=command_timeout_seconds,
        failure_message="Failed to create guest artifact directory",
    )

    uploaded: list[UploadedArtifactFile] = []
    uploaded_bytes = 0
    last_percent = -10
    for path, guest_path in zip(files, guest_paths):
        write = channel.upload_bytes(vm, guest_path, path.read_bytes())
        uploaded.append(UploadedArtifactFile(local_path=path, guest_path=guest_path, bytes_written=write.bytes_written))
        uploaded_bytes += write.bytes_written
        last_percent = _emit_transfer_progress(
            progress,
            "artifact.upload.progress",
            "Uploading artifact files",
            transferred=uploaded_bytes,
            total=total_bytes,
            last_percent=last_percent,
            filesUploaded=len(uploaded),
            totalFiles=len(files),
        )

    executables = [guest_path for path, guest_path in zip(files, guest_paths) if _is_executable(path)]
    if executables:
        _run_guest_command(
            channel,
            vm,
            ["chmod", "+x", *executables],
            timeout_seconds=command_timeout_seconds,
            failure_message="Failed to mark guest artifact files executable",
        )
    return uploaded


def _upload_folder_archive(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    artifact_path: Path,
    files: list[Path],
    destination: str,
    *,
    command_timeout_seconds: int,
    progress: ProgressCallback | None,
) -> list[UploadedArtifactFile]:
    staging = str(PurePosixPath(destination).parent / f".oslab-archive-{uuid4().hex}")
    archive_guest_path = f"{staging}/artifact.tar.gz"
    _emit_progress(progress, "artifact.archive.start", "Create artifact archive", files=len(files))
    archive_bytes = _tar_gz(artifact_path, files)
    _emit_progress(
        progress,
        "artifact.archive.done",
        "Artifact archive created",
        bytes=len(archive_bytes),
        guestPath=archive_guest_path,
    )
    last_percent = -10

    def on_upload_progress(bytes_written: int, total_bytes: int) -> None:
        nonlocal last_percent
        last_percent = _emit_transfer_progress(
            progress,
            "artifact.upload.progress",
            "Uploading artifact archive",
            transferred=bytes_written,
            total=total_bytes,
            last_percent=last_percent,
            guestPath=archive_guest_path,
        )

    _run_guest_command(
        channel,
        vm,
        ["mkdir", "-m", "700", "--", staging],
        timeout_seconds=command_timeout_seconds,
        failure_message="Failed to create archive staging directory",
    )
    active_error: BaseException | None = None
    try:
        write = channel.upload_bytes(vm, archive_guest_path, archive_bytes, progress=on_upload_progress)
        _emit_progress(
            progress,
            "artifact.archive.upload.done",
            "Artifact archive uploaded",
            guestPath=archive_guest_path,
            bytes=write.bytes_written,
        )
        _emit_progress(progress, "artifact.archive.expand.start", "Expand artifact archive in guest", destination=destination)
        _run_guest_command(
            channel,
            vm,
            [
                "sh",
                "-c",
                'mkdir -- "$1/content" && tar -xzf "$2" -C "$1/content" && cp -aT -- "$1/content" "$3"',
                "sh",
                staging,
                archive_guest_path,
                destination,
            ],
            timeout_seconds=command_timeout_seconds,
            failure_message="Failed to expand guest artifact archive",
        )
    except BaseException as exc:
        active_error = exc
        raise
    finally:
        try:
            _run_guest_command(
                channel,
                vm,
                ["rm", "-rf", "--", staging],
                timeout_seconds=command_timeout_seconds,
                failure_message="Failed to clean up archive staging directory",
            )
        except OslabError as exc:
            if active_error is None:
                raise
            active_error.add_note(f"Archive staging cleanup failed for {staging}: {exc}")
    _emit_progress(progress, "artifact.archive.expand.done", "Artifact archive expanded", destination=destination)
    return [UploadedArtifactFile(local_path=artifact_path, guest_path=archive_guest_path, bytes_written=write.bytes_written)]


def _tar_gz(artifact_path: Path, files: list[Path]) -> bytes:
    """Pack files as root-owned tar.gz entries; executables get mode 0755 and other files 0644."""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in files:
            info = archive.gettarinfo(str(path), arcname=path.relative_to(artifact_path).as_posix())
            info.mode = 0o755 if _is_executable(path) else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    return buffer.getvalue()


def _is_executable(path: Path) -> bool:
    """Recognize shebangs and ELF headers even on checkouts without POSIX mode bits."""

    with path.open("rb") as stream:
        header = stream.read(4)
    return header.startswith(b"#!") or header == b"\x7fELF" or bool(path.stat().st_mode & 0o111)


def _upload_installer_artifact(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    artifact_path: Path,
    destination: str,
    *,
    command_timeout_seconds: int,
    progress: ProgressCallback | None,
) -> UploadedArtifactFile:
    if not artifact_path.is_file():
        raise OslabError(f"Installer artifact path is not a file: {artifact_path}", details={"path": str(artifact_path)})
    _emit_progress(
        progress,
        "artifact.upload.start",
        "Upload installer artifact",
        destination=destination,
        bytes=artifact_path.stat().st_size,
    )
    _run_guest_command(
        channel,
        vm,
        ["mkdir", "-p", str(PurePosixPath(destination).parent)],
        timeout_seconds=command_timeout_seconds,
        failure_message="Failed to create guest installer directory",
    )
    write = channel.upload_bytes(vm, destination, artifact_path.read_bytes())
    _run_guest_command(
        channel,
        vm,
        ["chmod", "+x", destination],
        timeout_seconds=command_timeout_seconds,
        failure_message="Failed to mark guest installer executable",
    )
    _emit_progress(progress, "artifact.upload.done", "Installer artifact uploaded", destination=destination, bytes=write.bytes_written)
    return UploadedArtifactFile(local_path=artifact_path, guest_path=destination, bytes_written=write.bytes_written)


def _run_product_steps(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    tokens: dict[str, str],
    execute_command: Callable[[CommandSpec], GuestCommandResult],
    secrets: tuple[str, ...],
    timeout_seconds: int,
    progress: ProgressCallback | None,
) -> list[ProductStepResult]:
    """Run product steps in order and stop at the first failing step."""

    results: list[ProductStepResult] = []
    for step in _scenario_product_steps(scenario):
        _emit_progress(progress, "product.step.start", "Run product step", stepId=str(step.get("id", "<missing>")))
        step_result = _run_product_step(
            channel,
            vm,
            scenario=scenario,
            step=step,
            tokens=tokens,
            timeout_seconds=timeout_seconds,
            redaction_secrets=list(secrets),
            command_renderer=_render_linux_command,
            execute_command=execute_command,
        )
        results.append(step_result)
        _emit_progress(
            progress,
            "product.step.done" if step_result.passed else "product.step.failed",
            "Product step completed" if step_result.passed else "Product step failed",
            stepId=step_result.id,
            exitCode=step_result.exit_code if step_result.exit_code is not None else "<missing>",
        )
        if not step_result.passed:
            break
    return results


def _collect_output(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    *,
    scenario: Scenario,
    oslab_config: OslabConfig,
    result: ArtifactSmokeResult,
    run_dir: Path | None,
    progress: ProgressCallback | None,
    secrets: tuple[str, ...],
    command_timeout_seconds: int,
) -> ArtifactSmokeResult:
    """Download the product output JSON, normalize it with the scenario adapter, and evaluate assertions."""

    _emit_progress(progress, "output.collect.start", "Collect product output", outputPath=result.output_path)
    exists = channel.execute(
        vm,
        ["sh", "-c", 'test -f "$1" && test ! -L "$1"', "oslab", result.output_path],
        timeout_seconds=command_timeout_seconds,
    )
    if not exists.passed:
        _emit_progress(progress, "output.collect.failed", "Product did not create the expected output file")
        return replace(result, passed=False, message="Product did not create the expected output file")
    download = _download_scenario_output(channel, vm, result.output_path, secrets)
    _emit_progress(progress, "output.collect.done", "Product output collected", bytesRead=download.bytes_read)
    result = replace(result, collected_bytes=download.bytes_read)
    _emit_progress(progress, "output.parse.start", "Parse product output JSON")
    collected_json, content, parse_error = _prepare_collected_output(download.content, secrets)
    if parse_error is not None:
        _emit_progress(progress, "output.parse.failed", "Product output JSON parse failed")
        result = replace(
            result,
            collected_json={"jsonError": parse_error},
            passed=False,
            message="Artifact output was not valid JSON",
        )
    else:
        _emit_progress(progress, "output.parse.done", "Product output JSON parsed")
        result = replace(result, collected_json=collected_json)
        if _is_product_failure_artifact(collected_json):
            _emit_progress(progress, "product.failure_artifact", "Product returned failure artifact")
            result = replace(result, passed=False, message="Product CLI returned failure artifact")
        else:
            result = _normalize_and_assert(scenario, oslab_config, result, run_dir=run_dir, progress=progress)

    local_output_path = _write_artifact_output(oslab_config.output_root, scenario.scenario_id, content, run_dir=run_dir)
    _emit_progress(progress, "output.write.done", "Raw product output written", path=local_output_path)
    return replace(result, local_output_path=local_output_path)


def _download_scenario_output(
    channel: LinuxQemuAgentChannel, vm: VmRef, guest_path: str, secrets: tuple[str, ...]
) -> GuestFileReadResult:
    try:
        return channel.download_text(vm, guest_path)
    except OslabError:
        if not secrets:
            raise
        # Provider failures may quote partial file contents or their base64 representation.
        raise OslabError("Failed to read guest scenario output", details={"guestPath": guest_path}) from None


def _redact_output_json(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {_redact_text_secrets(key, secrets): _redact_output_json(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_output_json(item, secrets) for item in value]
    if isinstance(value, str):
        return _redact_text_secrets(value, secrets)
    return value


def _prepare_collected_output(content: str, secrets: tuple[str, ...]) -> tuple[Any, str, str | None]:
    try:
        payload = json.loads(content.lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        safe_content = _redact_text_secrets(content, secrets)
        if secrets:
            # A malformed JSON file can contain incomplete or escaped secrets that cannot be safely redacted.
            safe_content = ""
        return None, safe_content, str(exc)
    if not secrets:
        return payload, content, None
    sanitized = _redact_output_json(payload, secrets)
    return sanitized, json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n", None


def _normalize_and_assert(
    scenario: Scenario,
    oslab_config: OslabConfig,
    result: ArtifactSmokeResult,
    *,
    run_dir: Path | None,
    progress: ProgressCallback | None,
) -> ArtifactSmokeResult:
    _emit_progress(progress, "output.normalize.start", "Normalize product output", adapter=result.output_adapter)
    normalization = normalize_output(
        result.output_adapter,
        result.collected_json,
        context={"scenarioId": scenario.scenario_id, "outputPath": result.output_path},
    )
    normalized_json = normalization.canonical
    local_normalized_path = _write_normalized_output(
        oslab_config.output_root,
        scenario.scenario_id,
        normalized_json,
        run_dir=run_dir,
    )
    _emit_progress(
        progress,
        "output.normalize.done",
        "Product output normalized",
        records=len(normalized_json.get("records", [])),
        path=local_normalized_path,
    )
    _emit_progress(progress, "assertions.start", "Evaluate assertions", assertions=len(scenario.assertions))
    summary = evaluate_assertions(scenario.assertions, normalized_json)
    if summary.passed:
        _emit_progress(progress, "assertions.done", "Assertions passed", total=len(summary.results))
    else:
        _emit_progress(progress, "assertions.failed", "Assertions failed", total=len(summary.results), failed=summary.failed_count)
    return replace(
        result,
        normalized_json=normalized_json,
        local_normalized_path=local_normalized_path,
        assertions=summary.results,
        passed=summary.passed,
        message="Artifact smoke passed" if summary.passed else "Artifact assertions failed",
    )


def _run_guest_command(
    channel: LinuxQemuAgentChannel,
    vm: VmRef,
    command: list[str],
    *,
    timeout_seconds: int,
    failure_message: str,
) -> None:
    result = channel.execute(vm, command, timeout_seconds=timeout_seconds)
    if not result.passed:
        raise OslabError(
            failure_message,
            details={"command": command, "exitCode": result.exit_code, "stdout": result.stdout, "stderr": result.stderr},
        )
