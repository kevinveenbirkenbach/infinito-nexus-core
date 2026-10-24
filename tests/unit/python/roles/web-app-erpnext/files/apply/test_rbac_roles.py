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


def _env(members):
    return {
        "SITE_NAME": "next.erp.infinito.example",
        "ROLE_GRANTS_JSON": json.dumps(GRANTS),
        "ROLE_MEMBERS_JSON": json.dumps(members),
        "PROTECTED_USERS_JSON": json.dumps(PROTECTED),
    }


def _roles(*names):
    return [SimpleNamespace(role=name) for name in names]


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
        members = members or {"administrator": [], "manager": [], "customer": []}
        printed = run_script(SCRIPT, self.frappe, _env(members))
        return json.loads(printed.strip().splitlines()[-1])

    def _user(self, name):
        return self.frappe.records["User"][name]

    def _role_names(self, name):
        return sorted(row.role for row in self._user(name)["roles"])

    def test_creates_a_member_with_the_roles_of_its_group(self) -> None:
        report = self._run(
            {
                "administrator": [],
                "manager": [{"username": "alice", "email": "Alice@infinito.example"}],
                "customer": [],
            }
        )

        self.assertEqual(report["created"], ["alice@infinito.example"])
        self.assertEqual(self._user("alice@infinito.example")["enabled"], 1)
        self.assertEqual(
            self._role_names("alice@infinito.example"), ["Purchase User", "Sales User"]
        )

    def test_reenables_a_disabled_member(self) -> None:
        self.frappe.seed(
            "User", "alice@infinito.example", email="alice@infinito.example", enabled=0
        )

        report = self._run(
            {
                "administrator": [
                    {"username": "alice", "email": "alice@infinito.example"}
                ],
                "manager": [],
                "customer": [],
            }
        )

        self.assertEqual(report["enabled"], ["alice@infinito.example"])
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

        report = self._run(
            {
                "administrator": [],
                "manager": [{"username": "alice", "email": "alice@infinito.example"}],
                "customer": [],
            }
        )

        self.assertEqual(report["revoked"], ["alice@infinito.example:System Manager"])
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

        report = self._run()

        self.assertEqual(report["disabled"], ["biber@infinito.example"])
        self.assertEqual(report["revoked"], [])
        self.assertEqual(self._user("biber@infinito.example")["enabled"], 0)

    def test_demotes_and_disables_a_former_member(self) -> None:
        self.frappe.seed(
            "User",
            "biber@infinito.example",
            email="biber@infinito.example",
            enabled=1,
            roles=_roles("Sales User"),
        )

        report = self._run()

        self.assertEqual(report["revoked"], ["biber@infinito.example:Sales User"])
        self.assertEqual(report["disabled"], ["biber@infinito.example"])
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

        report = self._run()

        self.assertEqual(report["revoked"], ["biber@infinito.example:Customer"])
        self.assertEqual(report["disabled"], [])
        self.assertEqual(self._user("biber@infinito.example")["enabled"], 0)

    def test_never_demotes_or_disables_a_protected_account(self) -> None:
        self.frappe.seed(
            "User",
            PLATFORM_ADMIN,
            email=PLATFORM_ADMIN,
            enabled=1,
            roles=_roles("System Manager"),
        )

        report = self._run()

        self.assertEqual(report["disabled"], [])
        self.assertEqual(report["revoked"], [])
        for name in ("Administrator", "Guest", BOT, PLATFORM_ADMIN):
            self.assertEqual(self._user(name)["enabled"], 1)
        self.assertEqual(self._role_names(BOT), ["System Manager"])
        self.assertEqual(self._role_names(PLATFORM_ADMIN), ["System Manager"])

    def test_a_second_run_changes_nothing(self) -> None:
        self.frappe.seed(
            "User", "biber@infinito.example", email="biber@infinito.example", enabled=1
        )
        members = {
            "administrator": [],
            "manager": [],
            "customer": [{"username": "carol", "email": "carol@infinito.example"}],
        }
        self._run(members)

        report = self._run(members)

        self.assertEqual(
            report,
            {
                "granted": [],
                "revoked": [],
                "created": [],
                "disabled": [],
                "enabled": [],
            },
        )

    def test_missing_protected_users_fails_before_touching_the_site(self) -> None:
        env = _env({})
        del env["PROTECTED_USERS_JSON"]

        with self.assertRaises(KeyError):
            run_script(SCRIPT, self.frappe, env)

        self.assertEqual(self.frappe.calls, [])


if __name__ == "__main__":
    unittest.main()
