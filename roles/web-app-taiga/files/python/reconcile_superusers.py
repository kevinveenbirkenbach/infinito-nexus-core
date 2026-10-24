"""Reconcile the Taiga superuser flag with the administrator role group.

Read on stdin by ``manage.py shell``, which execs it when stdin is not a tty.

Env (from the container):
    TAIGA_RBAC_ADMINISTRATORS  JSON list of ``{username, email}`` members of the
                               administrator role group
    TAIGA_RBAC_KEPT_SUPERUSERS JSON list of usernames that keep their flags even
                               outside the role group

Prints ``promoted=<username>`` or ``demoted=<username>`` per account it changed,
then ``CHANGED=1`` when it wrote anything and ``CHANGED=0`` otherwise.
"""

import json
import os

from django.contrib.auth import get_user_model


def _key(value):
    return str(value or "").strip().lower()


members = json.loads(os.environ["TAIGA_RBAC_ADMINISTRATORS"])
kept = {_key(name) for name in json.loads(os.environ["TAIGA_RBAC_KEPT_SUPERUSERS"])}
member_keys = {_key(member.get("username")) for member in members} | {
    _key(member.get("email")) for member in members
}
member_keys.discard("")

changed = False
for user in get_user_model().objects.order_by("id"):
    if getattr(user, "is_system", False):
        continue
    username = _key(user.username)
    is_member = username in member_keys or _key(user.email) in member_keys
    is_admin = bool(user.is_superuser and user.is_staff)
    if is_member and not is_admin:
        user.is_superuser = True
        user.is_staff = True
        user.save()
        print(f"promoted={user.username}")
        changed = True
    elif (
        not is_member and username not in kept and (user.is_superuser or user.is_staff)
    ):
        user.is_superuser = False
        user.is_staff = False
        user.save()
        print(f"demoted={user.username}")
        changed = True

print("CHANGED=1" if changed else "CHANGED=0")
