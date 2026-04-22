"""Shared errors for oslab."""

from __future__ import annotations


class OslabError(Exception):
    """Base class for user-facing oslab failures."""

    exit_code = 1
    failure_class = "oslab_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ScenarioValidationError(OslabError):
    """Raised when a scenario YAML file is invalid."""

    exit_code = 10
    failure_class = "scenario_validation_failure"


class ConfigError(OslabError):
    """Raised when local config cannot be read or resolved."""

    exit_code = 11
    failure_class = "config_failure"


class RunDirectoryError(OslabError):
    """Raised when oslab cannot prepare a run directory."""

    exit_code = 12
    failure_class = "run_directory_failure"


class ProviderError(OslabError):
    """Raised when a provider cannot complete an infrastructure operation."""

    exit_code = 20
    failure_class = "provider_failure"


class PluginError(OslabError):
    """Raised when a product plugin cannot normalize or validate output."""

    exit_code = 40
    failure_class = "plugin_failure"


class AnalysisError(OslabError):
    """Raised when oslab cannot analyze a normalized output artifact."""

    exit_code = 60
    failure_class = "analysis_failure"


class VmCloneError(ProviderError):
    """Raised when a VM clone cannot be created."""

    exit_code = 21
    failure_class = "vm_clone_failure"


class CleanupError(ProviderError):
    """Raised when provider cleanup fails."""

    exit_code = 50
    failure_class = "cleanup_failure"
