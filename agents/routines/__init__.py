"""Agent routines: one LangGraph graph per routine.

A routine module in this package exposes:

- ``STEPS``: the ordered steps as a list of one-line strings, for an
  interactive agent to follow by hand.
- ``MERMAID``: a Mermaid ``flowchart`` of the same steps, as a string.
- ``build()``: returns the compiled LangGraph graph. Imported lazily, so
  ``show`` never needs LangGraph installed, only ``run`` does.

A routine's deterministic steps call the repository's own logic in ``cli/``
and ``utils/`` through a make target or ``python -m``; the logic stays there.
A routine never imports a skill or a role.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

__all__ = ["discover", "load"]

HELPERS = {"contract"}


def discover() -> list[str]:
    """Return the names of every routine module in this package.

    Helper modules (the routine contract) and private modules are not
    routines and are left out.
    """
    return sorted(
        info.name
        for info in pkgutil.iter_modules(__path__)
        if not info.name.startswith("_") and info.name not in HELPERS
    )


def load(name: str) -> ModuleType:
    """Import and return the routine module ``name``.

    Args:
        name: the routine module name, as ``discover`` lists it.
    """
    if name not in discover():
        raise KeyError(name)
    return importlib.import_module(f"{__name__}.{name}")
