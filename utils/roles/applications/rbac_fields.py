from __future__ import annotations

from collections.abc import Mapping

from utils.roles.applications.forms import SourceError, iter_fields
from utils.roles.applications.source_kinds import RBAC_ROOT, is_rbac_source
from utils.roles.rbac.catalogue import IMPLICIT_ADMINISTRATOR

RBAC_SOURCE_PARTS = 2


def flags(application: Mapping) -> frozenset[str]:
    """Return the RBAC roles an ``rbac.<ROLE>`` source may name.

    Args:
        application: the role's ``applications.<role>`` defaults; its
            ``rbac.roles`` is the role's ``meta/rbac.yml``.

    Returns:
        Every role key of ``rbac.roles`` and the implicit ``administrator``,
        the roles whose group ``RBAC.GROUP.NAME/<application_id>/<ROLE>``
        the ``RBAC.GROUP.CLAIM`` claim carries.
    """
    rbac = application.get("rbac") if isinstance(application, Mapping) else None
    roles = rbac.get("roles") if isinstance(rbac, Mapping) else None
    declared = {str(key) for key in roles} if isinstance(roles, Mapping) else set()
    return frozenset({IMPLICIT_ADMINISTRATOR, *declared})


def _rule(named: frozenset[str]) -> str:
    return (
        f"must be {RBAC_ROOT}.<ROLE> with a role of meta/rbac.yml or the implicit "
        f"{IMPLICIT_ADMINISTRATOR} {sorted(named)}"
    )


def role(source: str, named: frozenset[str]) -> str:
    """Return the RBAC role an ``rbac.<ROLE>`` source names.

    Args:
        source: the field's ``source``.
        named: what ``flags`` returns for the role.

    Raises:
        SourceError: when the source is no ``rbac.<ROLE>`` with a role of
            ``named``; the message lists the roles and never repeats the source.
    """
    parts = source.split(".") if isinstance(source, str) else []
    if (
        len(parts) != RBAC_SOURCE_PARTS
        or parts[0] != RBAC_ROOT
        or parts[1] not in named
    ):
        raise SourceError(f"the source {_rule(named)}")
    return parts[1]


def errors(role_name: str, forms: Mapping, application: Mapping) -> list[str]:
    """Return what keeps the ``rbac.<ROLE>`` fields of a role from the schema.

    Args:
        role_name: role name, used in the findings.
        forms: the parsed ``meta/forms.yml``.
        application: the role's ``applications.<role>`` defaults.

    Returns:
        One finding per ``rbac`` source that ``role`` refuses, per such field
        whose ``mode`` is not ``enforced``, per such field with a ``when`` and
        per such field whose form declares a ``record``; no finding repeats
        the source.
    """
    named = flags(application)
    found = []
    for form, field, spec in iter_fields(forms):
        source = spec.get("source")
        if not is_rbac_source(source):
            continue
        where = f"{role_name}: {form}.{field}"
        try:
            role(source, named)
        except SourceError:
            found.append(f"{where}.source {_rule(named)}")
        if spec.get("mode") != "enforced":
            found.append(
                f"{where}.mode must be enforced, since the RBAC sync writes it"
            )
        if "when" in spec:
            found.append(f"{where} takes no `when`; the selector's marker decides")
        if "record" in forms.get(form, {}):
            found.append(f"{where} takes no `record`; the selector's marker decides")
    return found


def selectors(forms: Mapping) -> dict[str, str]:
    """Return the selector of every ``rbac.<ROLE>`` field, keyed by field.

    Args:
        forms: ``applications.<role>.forms`` or the parsed ``meta/forms.yml``.
    """
    return {
        field: spec["selector"]
        for _, field, spec in iter_fields(forms)
        if is_rbac_source(spec.get("source")) and isinstance(spec.get("selector"), str)
    }
