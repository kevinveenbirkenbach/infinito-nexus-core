"""Converge the ERPNext roles and accounts on the deployment's role groups.

Environment:
    SITE_NAME: the Frappe site.
    ROLE_GRANTS_JSON: JSON ``{role: [ERPNext role, ...]}`` of every declared role.
    ROLE_MEMBERS_JSON: JSON ``{role: [{username, email, name}]}`` of every declared role.
    PROTECTED_USERS_JSON: JSON list of user names the run never demotes or disables.

Output:
    One ``CHANGED <user> <change>`` line per change, else ``UNCHANGED``.
"""

import json
import os

import frappe

SITES_PATH = "/home/frappe/frappe-bench/sites"


def wanted_roles(grants, members):
    """Return ``{email: {"username", "roles"}}`` for every member with an e-mail.

    Args:
        grants: ``{role: [ERPNext role, ...]}``.
        members: ``{role: [members]}``.
    """
    wanted = {}
    for role, entries in members.items():
        for member in entries:
            email = member["email"].strip().lower()
            if email:
                wanted.setdefault(
                    email, {"username": member["username"], "roles": set()}
                )
                wanted[email]["roles"].update(grants[role])
    return wanted


def provision(email, username):
    """Create the enabled website account of a member and return it.

    Args:
        email: the member's e-mail, the account's name.
        username: the member's username.
    """
    user = frappe.new_doc("User")
    user.email = email
    user.username = username
    user.first_name = username
    user.enabled = 1
    user.send_welcome_email = 0
    user.user_type = "Website User"
    user.new_password = frappe.generate_hash()
    user.flags.ignore_permissions = True
    user.flags.no_welcome_mail = True
    user.insert()
    return user


def set_enabled(user, enabled):
    """Save the enabled state of an account.

    Args:
        user: the ``User`` document.
        enabled: 1 or 0.
    """
    user.enabled = enabled
    user.flags.ignore_permissions = True
    user.save()


def reconcile(grants, members, protected):
    """Converge every account and return one line per change.

    Args:
        grants: ``{role: [ERPNext role, ...]}``.
        members: ``{role: [members]}``.
        protected: lower-cased user names the run never demotes or disables.
    """
    lines = []
    managed = {erpnext_role for roles in grants.values() for erpnext_role in roles}
    wanted = wanted_roles(grants, members)

    for email, entry in sorted(wanted.items()):
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = provision(email, entry["username"])
            lines.append(f"CHANGED {email} created")
        if not user.enabled:
            set_enabled(user, 1)
            lines.append(f"CHANGED {email} enabled")
        current = {row.role for row in user.get("roles")}
        missing = entry["roles"] - current
        surplus = set() if email in protected else (current & managed) - entry["roles"]
        if missing:
            user.add_roles(*sorted(missing))
            lines.extend(f"CHANGED {email} granted {role}" for role in sorted(missing))
        if surplus:
            user.remove_roles(*sorted(surplus))
            lines.extend(f"CHANGED {email} revoked {role}" for role in sorted(surplus))

    enabled = set(frappe.get_all("User", filters={"enabled": 1}, pluck="name"))
    holders = set(
        frappe.get_all(
            "Has Role",
            filters={"role": ["in", sorted(managed)], "parenttype": "User"},
            pluck="parent",
        )
    )
    for name in sorted(enabled | holders):
        lowered = name.lower()
        if lowered in protected or lowered in wanted:
            continue
        user = frappe.get_doc("User", name)
        surplus = {row.role for row in user.get("roles")} & managed
        if surplus:
            user.remove_roles(*sorted(surplus))
            lines.extend(f"CHANGED {name} revoked {role}" for role in sorted(surplus))
        if user.enabled:
            set_enabled(user, 0)
            lines.append(f"CHANGED {name} disabled")
    return lines


def main(environ):
    """Converge the site and print the result.

    Args:
        environ: the process environment.
    """
    site = environ["SITE_NAME"]
    grants = json.loads(environ["ROLE_GRANTS_JSON"])
    members = json.loads(environ["ROLE_MEMBERS_JSON"])
    protected = {name.lower() for name in json.loads(environ["PROTECTED_USERS_JSON"])}

    frappe.init(site=site, sites_path=SITES_PATH)
    frappe.connect()
    try:
        lines = reconcile(grants, members, protected)
        frappe.db.commit()
    finally:
        frappe.destroy()
    print("\n".join(lines) if lines else "UNCHANGED")


if __name__ == "__main__":
    main(os.environ)
