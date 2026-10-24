from __future__ import annotations

import re
from typing import Any

_SYSTEM_ADMIN = re.compile(r"(^|\s)system_admin(\s|$)")


def mattermost_rbac_plan(
    users: list[dict[str, Any]], members: list[dict[str, str]], keep: list[str]
) -> dict[str, list[str]]:
    """Split the Mattermost accounts into those to promote and those to demote.

    Args:
        users: ``mmctl user list --json`` output; a bot carries ``is_bot``.
        members: ``[{"username", "email"}]`` of the administrator role.
        keep: usernames that keep ``system_admin`` outside the role.

    Returns:
        ``{"promote": [...], "demote": [...]}`` as usernames. ``promote``
        lists the human accounts without ``system_admin`` that match a member
        by username or e-mail, ``demote`` the human holders of
        ``system_admin`` that match neither a member nor ``keep``.
    """
    keys = [member["username"].lower() for member in members] + [
        member["email"].lower() for member in members if member["email"]
    ]
    kept = [name.lower() for name in keep]
    promote: list[str] = []
    demote: list[str] = []
    for user in users:
        if "is_bot" in user:
            continue
        username = user["username"]
        admin = _SYSTEM_ADMIN.search(user["roles"]) is not None
        member = username in keys or user["email"] in keys
        if not admin and member and username not in promote:
            promote.append(username)
        if admin and not member and username not in kept:
            demote.append(username)
    return {"promote": promote, "demote": demote}


class FilterModule:
    def filters(self):
        return {"mattermost_rbac_plan": mattermost_rbac_plan}
