from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from . import PROJECT_ROOT
from ._fake_frappe import FakeFrappe, run_script

SCRIPT = PROJECT_ROOT / "roles/web-app-erpnext/files/python/apply/rbac_roles.py"
GRANTS = {
    "administrator": ["System Manager"],
    "manager": ["Sales User", "Purchase User"],
    "customer": ["Customer"],
}
BOT = "erpnext-api-bot@infinito.example"
PLATFORM_ADMIN = "platformadmin@infinito.example"
PROTECTED = ["Administrator", "Guest", BOT, PLATFORM_ADMIN]
NO_MEMBERS = {"administrator": [], "manager": [], "customer": []}


def _env(members):
    return {
        "SITE_NAME": "next.erp.infinito.example",
        "ROLE_GRANTS_JSON": json.dumps(GRANTS),
        "ROLE_MEMBERS_JSON": json.dumps(members),
        "PROTECTED_USERS_JSON": json.dumps(PROTECTED),
    }


def _roles(*names):
    return [SimpleNamespace(role=name) for name in names]


def _member(username, email):
    return {"username": username, "email": email, "name": username}


class TestRbacRoles(unittest.TestCase):
    def setUp(self) -> None:
        self.frappe = FakeFrappe()
        self.frappe.seed(
            "User", "Administrator", enabled=1, roles=_roles("System Manager")
        )
        self.frappe.seed("User", "Guest", enabled=1, roles=_roles("Guest"))
        self.frappe.seed(
            "User", BOT, email=BOT, enabled=1, roles=_roles("System Manager")
        )

    def _run(self, members=None):
        printed = run_script(SCRIPT, self.frappe, _env({**NO_MEMBERS, **(members or {})}))
        return printed.splitlines()

    def _user(self, name):
        return self.frappe.records["User"][name]

    def _role_names(self, name):
        return sorted(row.role for row in self._user(name)["roles"])

    def test_creates_a_member_with_the_roles_of_its_group(self) -> None:
        output = self._run({"manager": [_member("alice", "Alice@infinito.example")]})

        self.assertEqual(
            output,
            [
                "CHANGED alice@infinito.example created",
                "CHANGED alice@infinito.example granted Purchase User",
                "CHANGED alice@infinito.example granted Sales User",
            ],
        )
        self.assertEqual(self._user("alice@infinito.example")["enabled"], 1)
        self.assertEqual(
            self._role_names("alice@infinito.example"), ["Purchase User", "Sales User"]
        )

    def test_reenables_a_disabled_member(self) -> None:
        self.frappe.seed(
            "User", "alice@infinito.example", email="alice@infinito.example", enabled=0
        )

        output = self._run(
            {"administrator": [_member("alice", "alice@infinito.example")]}
        )

        self.assertEqual(
            output,
            [
                "CHANGED alice@infinito.example enabled",
                "CHANGED alice@infinito.example granted System Manager",
            ],
        )
        self.assertEqual(self._user("alice@infinito.example")["enabled"], 1)
        self.assertEqual(self._role_names("alice@infinito.example"), ["System Manager"])

    def test_withdraws_the_roles_of_a_group_the_member_left(self) -> None:
        self.frappe.seed(
            "User",
            "alice@infinito.example",
            email="alice@infinito.example",
            enabled=1,
            roles=_roles("System Manager", "Sales User", "Purchase User", "Blogger"),
        )

        output = self._run({"manager": [_member("alice", "alice@infinito.example")]})

        self.assertEqual(output, ["CHANGED alice@infinito.example revoked System Manager"])
        self.assertEqual(
            self._role_names("alice@infinito.example"),
            ["Blogger", "Purchase User", "Sales User"],
        )

    def test_disables_an_account_outside_every_group_without_a_managed_role(
        self,
    ) -> None:
        self.frappe.seed(
            "User",
            "biber@infinito.example",
            email="biber@infinito.example",
            enabled=1,
            roles=_roles("Website User"),
        )

        output = self._run()

        self.assertEqual(output, ["CHANGED biber@infinito.example disabled"])
        self.assertEqual(self._user("biber@infinito.example")["enabled"], 0)

    def test_demotes_and_disables_a_former_member(self) -> None:
        self.frappe.seed(
            "User",
            "biber@infinito.example",
            email="biber@infinito.example",
            enabled=1,
            roles=_roles("Sales User"),
        )

        output = self._run()

        self.assertEqual(
            output,
            [
                "CHANGED biber@infinito.example revoked Sales User",
                "CHANGED biber@infinito.example disabled",
            ],
        )
        self.assertEqual(self._role_names("biber@infinito.example"), [])

    def test_strips_managed_roles_from_a_disabled_outsider_without_touching_its_state(
        self,
    ) -> None:
        self.frappe.seed(
            "User",
            "biber@infinito.example",
            email="biber@infinito.example",
            enabled=0,
            roles=_roles("Customer"),
        )

        output = self._run()

        self.assertEqual(output, ["CHANGED biber@infinito.example revoked Customer"])
        self.assertEqual(self._user("biber@infinito.example")["enabled"], 0)

    def test_never_demotes_or_disables_a_protected_account(self) -> None:
        self.frappe.seed(
            "User",
            PLATFORM_ADMIN,
            email=PLATFORM_ADMIN,
            enabled=1,
            roles=_roles("System Manager"),
        )

        output = self._run()

        self.assertEqual(output, ["UNCHANGED"])
        for name in ("Administrator", "Guest", BOT, PLATFORM_ADMIN):
            self.assertEqual(self._user(name)["enabled"], 1)
        self.assertEqual(self._role_names(BOT), ["System Manager"])
        self.assertEqual(self._role_names(PLATFORM_ADMIN), ["System Manager"])

    def test_a_protected_member_gains_roles_but_keeps_its_other_managed_roles(
        self,
    ) -> None:
        self.frappe.seed(
            "User",
            PLATFORM_ADMIN,
            email=PLATFORM_ADMIN,
            enabled=1,
            roles=_roles("System Manager"),
        )

        output = self._run({"customer": [_member("platformadmin", PLATFORM_ADMIN)]})

        self.assertEqual(output, [f"CHANGED {PLATFORM_ADMIN} granted Customer"])
        self.assertEqual(self._role_names(PLATFORM_ADMIN), ["Customer", "System Manager"])

    def test_a_second_run_changes_nothing(self) -> None:
        self.frappe.seed(
            "User", "biber@infinito.example", email="biber@infinito.example", enabled=1
        )
        members = {"customer": [_member("carol", "carol@infinito.example")]}
        self._run(members)

        self.assertEqual(self._run(members), ["UNCHANGED"])

    def test_the_site_is_committed_and_released(self) -> None:
        self._run()

        self.assertTrue(self.frappe.db.committed)
        self.assertEqual(
            self.frappe.calls,
            [
                ("init", "next.erp.infinito.example", "/home/frappe/frappe-bench/sites"),
                ("connect",),
                ("destroy",),
            ],
        )

    def test_missing_protected_users_fails_before_touching_the_site(self) -> None:
        env = _env(NO_MEMBERS)
        del env["PROTECTED_USERS_JSON"]

        with self.assertRaises(KeyError):
            run_script(SCRIPT, self.frappe, env)

        self.assertEqual(self.frappe.calls, [])


if __name__ == "__main__":
    unittest.main()
