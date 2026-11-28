from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SSO_ROOT = "sso"
RBAC_ROOT = "rbac"
IDENTITY_ROOTS = frozenset({SSO_ROOT, RBAC_ROOT})


def is_sso_source(source: Any) -> bool:
    """Whether a field's ``source`` names an ``OIDC.ATTRIBUTES`` key of the SSO sign-in.

    Args:
        source: the field's ``source``.
    """
    return isinstance(source, str) and source.split(".", 1)[0] == SSO_ROOT


def is_rbac_source(source: Any) -> bool:
    """Whether a field's ``source`` names an RBAC role whose group the RBAC sync converges.

    Args:
        source: the field's ``source``.
    """
    return isinstance(source, str) and source.split(".", 1)[0] == RBAC_ROOT


def is_identity_source(source: Any) -> bool:
    """Whether a field's ``source`` is an ``sso.<ATTRIBUTE>`` or ``rbac.<ROLE>`` the IdP owns.

    Args:
        source: the field's ``source``.
    """
    return isinstance(source, str) and source.split(".", 1)[0] in IDENTITY_ROOTS


def only_identity(block: Any) -> bool:
    """Whether every field of one form names an ``sso.<ATTRIBUTE>`` or ``rbac.<ROLE>`` source.

    Args:
        block: one form of ``meta/forms.yml``.
    """
    fields = block.get("fields") if isinstance(block, Mapping) else None
    return (
        isinstance(fields, Mapping)
        and bool(fields)
        and all(
            isinstance(spec, Mapping) and is_identity_source(spec.get("source"))
            for spec in fields.values()
        )
    )
