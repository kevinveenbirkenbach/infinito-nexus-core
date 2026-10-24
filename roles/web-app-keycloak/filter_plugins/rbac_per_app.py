"""Per-application RBAC naming for Keycloak.

Single SPOT for the Keycloak component name `ldap-roles-<application_id>`
of a deployed application's per-app `group-ldap-mapper`. The name is
referenced from `vars/main.yml` (`KEYCLOAK_PER_APP_LDAP_ROLES_MAPPER`) and
from the host-side `upsert_app_mapper.sh` script. The mapper's LDAP filter
comes from `kc_app_ldap_scopes` in `build_realm_rbac_groups.py`.
"""

from __future__ import annotations

from utils.roles.validation.invokable import list_invokable_app_ids


def kc_per_app_mapper_name(application_id):
    """Return the canonical Keycloak component name for a deployed app's
    per-application `group-ldap-mapper`."""
    if not isinstance(application_id, str) or not application_id:
        raise ValueError(
            "kc_per_app_mapper_name: application_id must be a non-empty string"
        )
    return f"ldap-roles-{application_id}"


def rbac_app_ids(app_ids):
    if app_ids is None:
        app_ids = []
    if not isinstance(app_ids, (list, tuple)):
        raise TypeError(
            f"rbac_app_ids: app_ids must be a list/tuple, got {type(app_ids)}"
        )

    invokable = set(list_invokable_app_ids())
    return sorted({x for x in app_ids if isinstance(x, str) and x in invokable})


class FilterModule:
    def filters(self):
        return {
            "kc_per_app_mapper_name": kc_per_app_mapper_name,
            "rbac_app_ids": rbac_app_ids,
        }
