"""Reconcile the ERPNext roles of the deployment's RBAC groups.

Required env:
  SITE_NAME           the Frappe site
  ROLE_GRANTS_JSON    {role: [ERPNext role, ...]} of every declared RBAC role
  ROLE_MEMBERS_JSON   {role: [{username, email}, ...]} members of every declared RBAC role
  PROTECTED_USERS_JSON  User names this script never demotes or disables
Prints one JSON line: {"granted": [...], "revoked": [...], "created": [...], "disabled": [...], "enabled": [...]}.
"""

import json
import os

import frappe

SITE_NAME = os.environ["SITE_NAME"]
ROLE_GRANTS = json.loads(os.environ["ROLE_GRANTS_JSON"])
ROLE_MEMBERS = json.loads(os.environ["ROLE_MEMBERS_JSON"])
PROTECTED_USERS = {
    name.lower() for name in json.loads(os.environ["PROTECTED_USERS_JSON"])
}


def wanted_roles():
    wanted = {}
    for role, members in ROLE_MEMBERS.items():
        for member in members:
            email = (member.get("email") or "").strip().lower()
            if email:
                wanted.setdefault(
                    email, {"username": member["username"], "roles": set()}
                )
                wanted[email]["roles"].update(ROLE_GRANTS[role])
    return wanted


def provision(email, username, report):
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
    report["created"].append(email)
    return user


def reconcile():
    report = {
        "granted": [],
        "revoked": [],
        "created": [],
        "disabled": [],
        "enabled": [],
    }
    managed = {erpnext_role for roles in ROLE_GRANTS.values() for erpnext_role in roles}
    wanted = wanted_roles()

    for email, entry in sorted(wanted.items()):
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = provision(email, entry["username"], report)
        if not user.enabled:
            user.enabled = 1
            user.flags.ignore_permissions = True
            user.save()
            report["enabled"].append(email)
        current = {row.role for row in user.get("roles")}
        missing = entry["roles"] - current
        surplus = (
            set() if email in PROTECTED_USERS else (current & managed) - entry["roles"]
        )
        if missing:
            user.add_roles(*sorted(missing))
            report["granted"].extend(f"{email}:{role}" for role in sorted(missing))
        if surplus:
            user.remove_roles(*sorted(surplus))
            report["revoked"].extend(f"{email}:{role}" for role in sorted(surplus))

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
        if lowered in PROTECTED_USERS or lowered in wanted:
            continue
        user = frappe.get_doc("User", name)
        surplus = {row.role for row in user.get("roles")} & managed
        if surplus:
            user.remove_roles(*sorted(surplus))
            report["revoked"].extend(f"{name}:{role}" for role in sorted(surplus))
        if user.enabled:
            user.enabled = 0
            user.flags.ignore_permissions = True
            user.save()
            report["disabled"].append(name)
    return report


frappe.init(site=SITE_NAME, sites_path="/home/frappe/frappe-bench/sites")
frappe.connect()
try:
    result = reconcile()
    frappe.db.commit()
finally:
    frappe.destroy()

print(json.dumps(result))
