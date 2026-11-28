"""Idempotent ``.env`` loader for Python CLI entry-points."""

from __future__ import annotations

import os
from pathlib import Path

from utils.env.parser import parse_static_env

_LOADED_FLAG = "INFINITO_ENV_LOADED"  # nocheck: env-loader-internal-guard
_CALLER_KEYS = "INFINITO_ENV_CALLER_KEYS"  # nocheck: env-loader-internal-guard
_LOADED_FILE = "INFINITO_ENV_LOADED_FILE"  # nocheck: env-loader-internal-guard
_DOTENV_NAME = ".env"


def loaded_caller_keys(dotenv: Path) -> set[str] | None:
    """
    Args:
        dotenv: a checkout's `.env`.

    Returns:
        The keys ``scripts/meta/env/load.sh`` recorded as caller-set when it
        sourced *dotenv* into this process env; None when it did not source
        *dotenv*, when *dotenv* is missing, or when the loader predates the
        record.
    """
    callers = os.environ.get(_CALLER_KEYS)
    loaded = os.environ.get(_LOADED_FILE, "")
    if callers is None or not loaded or not dotenv.is_file():
        return None
    if Path(loaded).resolve() != dotenv.resolve():
        return None
    return set(callers.split())


def loaded_only_values(previous: Path, dotenv: Path) -> dict[str, str]:
    """
    Args:
        previous: the `.env` content load.sh sourced, or a copy of it taken
            before a regeneration.
        dotenv: the checkout's `.env`, the file load.sh names as loaded.

    Returns:
        Every key of *previous* the process env holds only because load.sh
        sourced it: not recorded as caller-set and still equal to
        *previous*. Empty when :func:`loaded_caller_keys` returns None.
    """
    kept = loaded_caller_keys(dotenv)
    if kept is None:
        return {}
    return {
        key: value
        for key, value in parse_static_env(previous).items()
        if key not in kept and os.environ.get(key) == value
    }


def refresh_from_dotenv(previous: Path, dotenv: Path) -> None:
    """
    Args:
        previous: a copy of the `.env` load.sh sourced, taken before the
            regeneration.
        dotenv: the regenerated `.env`; every key of
            :func:`loaded_only_values` takes its value from it, or leaves the
            process env when *dotenv* no longer holds it.
    """
    fresh = parse_static_env(dotenv)
    for key in loaded_only_values(previous, dotenv):
        if key in fresh:
            os.environ[key] = fresh[key]
        else:
            del os.environ[key]


def _find_dotenv(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        path = candidate / _DOTENV_NAME
        if path.is_file():
            return path
    return None


def load_dotenv_once(start: Path | None = None) -> Path | None:
    """Source ``.env`` into ``os.environ`` exactly once per process.

    Mirrors the bash ``scripts/meta/env/load.sh`` semantics:

    * Honours ``INFINITO_ENV_LOADED=1`` and returns immediately when set.
    * Caller-set values win over ``.env`` defaults (``setdefault``).
    * Walks up from ``start`` (default: current working directory) until a
      ``.env`` is found; returns ``None`` if none exists in any parent.
    """
    if os.environ.get(_LOADED_FLAG) == "1":
        return None

    dotenv = _find_dotenv((start or Path.cwd()).resolve())
    if dotenv is None:
        return None

    for key, value in parse_static_env(dotenv).items():
        os.environ.setdefault(key, value)

    os.environ[_LOADED_FLAG] = "1"
    return dotenv
