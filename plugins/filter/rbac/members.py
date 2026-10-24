"""Filters that resolve who holds one RBAC role on one application.

    {{ lookup('users') | rbac_members('web-app-gitlab', 'administrator') }}
    {{ ldap_search_result.results | rbac_ldap_members('uid', 'mail', 'cn') }}
    -> [{"username": "alice", "email": "alice@example.org", "name": "Alice Liddell"}]

A deploy-time reconciler needs the members of a role group to promote and
demote accounts in an application that cannot read the groups claim itself.
The directory is the live source once OpenLDAP is deployed, because Keycloak
writes group memberships changed in its admin console back to it; the
inventory grants are the fallback for a deployment without a directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plugins.filter.ldap.full_name import ldap_full_name
from utils.roles.rbac.scoped import members_with_role

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def _single(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return "" if value is None else str(value)


def rbac_members(
    users: Mapping[str, Any] | None, application_id: str, role: str
) -> list[dict[str, str]]:
    """Return the inventory users granted ``role`` on ``application_id``.

    Args:
        users: the merged users mapping.
        application_id: the application whose grants are resolved.
        role: the role name.
    """
    by_username = {
        str((cfg or {}).get("username", key)): (key, cfg or {})
        for key, cfg in (users or {}).items()
    }
    members = []
    for username in members_with_role(users, application_id, role):
        key, cfg = by_username.get(username, (username, {}))
        members.append(
            {
                "username": username,
                "email": str(cfg.get("email") or ""),
                "name": ldap_full_name(cfg, key),
            }
        )
    return members


def rbac_ldap_members(
    entries: Iterable[Mapping[str, Any]] | None,
    id_attribute: str,
    mail_attribute: str,
    name_attribute: str,
) -> list[dict[str, str]]:
    """Return the members found by an LDAP search, sorted by username.

    Args:
        entries: the ``results`` list of ``community.general.ldap_search``.
        id_attribute: the login attribute, ``LDAP.USER.ATTRIBUTES.ID``.
        mail_attribute: the mail attribute, ``LDAP.USER.ATTRIBUTES.MAIL``.
        name_attribute: the full name attribute, ``LDAP.USER.ATTRIBUTES.FULLNAME``.
    """
    members = [
        {
            "username": _single(entry.get(id_attribute)),
            "email": _single(entry.get(mail_attribute)),
            "name": _single(entry.get(name_attribute)),
        }
        for entry in entries or []
    ]
    return sorted(
        (member for member in members if member["username"]),
        key=lambda member: member["username"],
    )


class FilterModule:
    def filters(self):
        return {
            "rbac_members": rbac_members,
            "rbac_ldap_members": rbac_ldap_members,
        }
