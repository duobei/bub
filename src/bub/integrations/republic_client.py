"""Republic integration helpers."""

from __future__ import annotations

from pathlib import Path

from republic import LLM
from republic.core.errors import ErrorKind

from bub.config.settings import Settings
from bub.tape.context import default_tape_context
from bub.tape.store import FileTapeStore

AGENTS_FILE = "AGENTS.md"


def _minimax_error_classifier(exc: Exception) -> ErrorKind | None:
    """Custom error classifier for MiniMax provider.

    MiniMax has tool calling format incompatibilities - mark these as
    INVALID_INPUT to skip retries and continue execution.
    """
    error_msg = str(exc).lower()
    # MiniMax tool call format errors - don't retry, just skip
    if "invalid function arguments json string" in error_msg:
        return ErrorKind.UNKNOWN  # Will fail fast without retries
    if "tool_call_id" in error_msg and "invalid params" in error_msg:
        return ErrorKind.UNKNOWN
    return None


def build_tape_store(settings: Settings, workspace: Path) -> FileTapeStore:
    """Build persistent tape store for one workspace."""

    return FileTapeStore(settings.resolve_home(), workspace)


def build_llm(settings: Settings, store: FileTapeStore) -> LLM:
    """Build Republic LLM client configured for Bub runtime."""

    client_args = None
    if "azure" in settings.model:
        client_args = {"api_version": "2025-01-01-preview"}

    # Use custom error classifier for MiniMax to handle tool call format errors
    error_classifier = _minimax_error_classifier if "minimax" in settings.model.lower() else None

    return LLM(
        settings.model,
        api_key=settings.resolved_api_key,
        api_base=settings.api_base,
        tape_store=store,
        context=default_tape_context(),
        client_args=client_args,
        max_retries=3,  # Enable retries for temporary errors
        error_classifier=error_classifier,
    )


def read_workspace_agents_prompt(workspace: Path) -> str:
    """Read workspace AGENTS.md if present."""

    prompt_file = workspace / AGENTS_FILE
    if not prompt_file.is_file():
        return ""
    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
