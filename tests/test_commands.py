import pytest

from oslab.commands import render_command_template
from oslab.errors import ScenarioValidationError


def test_render_command_template_replaces_known_tokens() -> None:
    command = {
        "shell": "powershell",
        "template": '& "{ArtifactDir}\\SupplyScan.exe" --output "{OutputPath}"',
    }

    rendered = render_command_template(
        command,
        {
            "ArtifactDir": "C:\\Oslab\\artifact",
            "OutputPath": "C:\\Oslab\\scan-result.json",
        },
    )

    assert rendered.shell == "powershell"
    assert rendered.rendered == '& "C:\\Oslab\\artifact\\SupplyScan.exe" --output "C:\\Oslab\\scan-result.json"'
    assert rendered.safe_rendered == rendered.rendered


def test_render_command_template_redacts_secret_tokens() -> None:
    command = {
        "shell": "powershell",
        "template": '& "{InstallDir}\\SupplyScanAgent.exe" cli_mode register --server-url "{ServerUrl}" --access-token "{AccessToken}" --json',
    }

    rendered = render_command_template(
        command,
        {
            "InstallDir": r"C:\Program Files\SupplyScan",
            "ServerUrl": "https://supplyscan.example.local",
        },
        secret_tokens={"AccessToken": "secret-token-value"},
    )

    assert "secret-token-value" in rendered.rendered
    assert "secret-token-value" not in rendered.safe_rendered
    assert '--access-token "<redacted>"' in rendered.safe_rendered


def test_render_command_template_rejects_token_secret_overlap() -> None:
    command = {"shell": "powershell", "template": "echo {Token}"}

    with pytest.raises(ScenarioValidationError, match="both public and secret"):
        render_command_template(command, {"Token": "public"}, secret_tokens={"Token": "secret"})


def test_render_command_template_rejects_unknown_tokens() -> None:
    command = {"shell": "sh", "template": "cat {MissingToken}"}

    with pytest.raises(ScenarioValidationError, match="Unknown command template token `MissingToken`"):
        render_command_template(command, {})
