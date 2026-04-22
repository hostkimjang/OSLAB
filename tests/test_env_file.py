from pathlib import Path

import pytest

from oslab.env_file import load_env_file
from oslab.errors import ConfigError


def test_load_env_file_sets_missing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OSLAB_FILE_TOKEN", raising=False)
    path = tmp_path / "local.env"
    path.write_text(
        """
# local lab secrets
OSLAB_FILE_TOKEN="secret-value"
OSLAB_OTHER_TOKEN='other-value'
""",
        encoding="utf-8",
    )

    result = load_env_file(path)

    assert result.loaded == ["OSLAB_FILE_TOKEN", "OSLAB_OTHER_TOKEN"]
    assert result.skipped_existing == []
    assert result.loaded[0] == "OSLAB_FILE_TOKEN"


def test_load_env_file_does_not_override_existing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSLAB_FILE_TOKEN", "already-set")
    path = tmp_path / "local.env"
    path.write_text("OSLAB_FILE_TOKEN=from-file\n", encoding="utf-8")

    result = load_env_file(path)

    assert result.loaded == []
    assert result.skipped_existing == ["OSLAB_FILE_TOKEN"]


def test_load_env_file_rejects_invalid_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.env"
    path.write_text("not-valid\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid env file line") as exc:
        load_env_file(path)

    assert exc.value.details["expectedExample"] == "OSLAB_PROXMOX_TOKEN_ID=root@pam!oslab"
    assert "raw passwords" in exc.value.details["note"]


def test_load_env_file_accepts_utf8_bom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OSLAB_BOM_TOKEN", raising=False)
    path = tmp_path / "bom.env"
    path.write_bytes("OSLAB_BOM_TOKEN=ok\n".encode("utf-8-sig"))

    result = load_env_file(path)

    assert result.loaded == ["OSLAB_BOM_TOKEN"]
