from __future__ import annotations

import copy
import unittest

from utils.roles.applications import forms, rbac_fields, source_kinds
from utils.roles.applications.converge import values

APPLICATION = {
    "design": {"label": "Infinito.Nexus"},
    "rbac": {"roles": {"collaborator": {"description": "moderates"}}},
}
USERS: dict = {}
FORMS = {
    "general": {
        "path": "/admin/settings",
        "fields": {
            "title": {
                "source": "design.label",
                "mode": "enforced",
                "selector": "#title",
                "type": "text",
            }
        },
    },
    "members": {
        "path": "/admin/users",
        "fields": {
            "administrator": {
                "source": "rbac.administrator",
                "mode": "enforced",
                "selector": "#members [data-rbac] .level",
            },
            "collaborator": {
                "source": "rbac.collaborator",
                "mode": "enforced",
                "selector": "#members [data-rbac] .level",
            },
        },
    },
}
REFUSED = (
    "rbac.superuser",
    "rbac.Administrator",
    "rbac.administrator.flag",
    "rbac",
    "rbac.roles",
)
RULE = "must be rbac.<ROLE> with a role of meta/rbac.yml or the implicit administrator"


def _members(**changes) -> dict:
    broken = copy.deepcopy(FORMS)
    broken["members"]["fields"]["administrator"].update(changes)
    return broken


class TestFlags(unittest.TestCase):
    def test_the_flags_are_the_declared_roles_and_the_implicit_administrator(self):
        self.assertEqual(
            frozenset({"administrator", "collaborator"}),
            rbac_fields.flags(APPLICATION),
        )

    def test_a_role_without_rbac_offers_the_implicit_administrator_only(self):
        self.assertEqual(frozenset({"administrator"}), rbac_fields.flags({}))

    def test_a_declared_role_resolves_to_its_name(self):
        self.assertEqual(
            "collaborator",
            rbac_fields.role("rbac.collaborator", rbac_fields.flags(APPLICATION)),
        )

    def test_an_unknown_or_malformed_flag_is_refused(self):
        named = rbac_fields.flags(APPLICATION)
        for source in REFUSED:
            with self.subTest(source=source):
                with self.assertRaises(forms.SourceError) as caught:
                    rbac_fields.role(source, named)
                self.assertIn(RULE, str(caught.exception))


class TestErrors(unittest.TestCase):
    def test_the_declared_flags_pass(self):
        self.assertEqual([], rbac_fields.errors("web-app-demo", FORMS, APPLICATION))

    def test_an_unknown_flag_fails(self):
        found = rbac_fields.errors(
            "web-app-demo", _members(source="rbac.superuser"), APPLICATION
        )

        self.assertEqual(1, len(found))
        self.assertIn(f"web-app-demo: members.administrator.source {RULE}", found[0])

    def test_a_flag_of_another_application_fails(self):
        found = rbac_fields.errors("web-app-demo", FORMS, {})

        self.assertEqual(
            ["web-app-demo: members.collaborator.source"],
            [message.split(" must")[0] for message in found],
        )

    def test_each_broken_rule_names_itself(self):
        cases = {
            "mode must be enforced, since the RBAC sync writes it": _members(
                mode="seeded"
            ),
            "takes no `when`; the selector's marker decides": _members(
                when="services.sso.enabled"
            ),
        }
        recorded = copy.deepcopy(FORMS)
        recorded["members"]["record"] = {"selector": "#id", "source": "ids.list"}
        cases["takes no `record`; the selector's marker decides"] = recorded
        for message, broken in cases.items():
            with self.subTest(message=message):
                self.assertIn(
                    message,
                    "\n".join(rbac_fields.errors("web-app-demo", broken, APPLICATION)),
                )

    def test_an_sso_or_inventory_field_is_left_to_its_own_check(self):
        mixed = copy.deepcopy(FORMS)
        mixed["members"]["fields"]["name"] = {
            "source": "sso.NAME",
            "mode": "seeded",
            "selector": "#name",
        }
        self.assertEqual([], rbac_fields.errors("web-app-demo", mixed, APPLICATION))


class TestTheFormsMachinery(unittest.TestCase):
    def test_an_rbac_source_has_no_deploy_time_value(self):
        with self.assertRaises(forms.SourceError) as caught:
            forms.resolve("rbac.administrator", APPLICATION, USERS)
        self.assertIn("the RBAC sync writes it", str(caught.exception))

    def test_an_inventory_path_named_rbac_no_longer_resolves(self):
        with self.assertRaises(forms.SourceError):
            forms.resolve("rbac.roles", APPLICATION, USERS)

    def test_the_converge_leaves_the_rbac_fields_to_the_rbac_sync(self):
        self.assertEqual({}, values("members", FORMS, APPLICATION, USERS))
        self.assertEqual(
            {"title": "Infinito.Nexus"}, values("general", FORMS, APPLICATION, USERS)
        )

    def test_the_source_check_leaves_the_rbac_fields_to_their_own_check(self):
        self.assertEqual(
            [], forms.source_errors("web-app-demo", FORMS, APPLICATION, USERS, {})
        )

    def test_a_form_of_rbac_fields_only_needs_no_converge(self):
        self.assertTrue(source_kinds.only_identity(FORMS["members"]))
        self.assertFalse(source_kinds.only_identity(FORMS["general"]))

    def test_an_rbac_record_source_is_refused(self):
        recorded = copy.deepcopy(FORMS)
        recorded["general"]["record"] = {
            "selector": "#id",
            "source": "rbac.administrator",
        }
        self.assertIn(
            "web-app-demo: general.record.source must name no secret; every page "
            "carries its ids",
            forms.source_errors("web-app-demo", recorded, APPLICATION, USERS, {}),
        )

    def test_the_rbac_fields_of_a_page_lock_as_one_profile_entry_without_unlock(self):
        selector = FORMS["members"]["fields"]["administrator"]["selector"]

        self.assertEqual(
            {
                "page": "/admin/users",
                "selector": f"{selector},{selector}",
                "label": None,
                "path": None,
                "secret": False,
            },
            forms.locks("web-app-demo", FORMS, APPLICATION, USERS, {})[0],
        )

    def test_the_rbac_selectors_are_keyed_by_field(self):
        selector = FORMS["members"]["fields"]["administrator"]["selector"]

        self.assertEqual(
            {"administrator": selector, "collaborator": selector},
            rbac_fields.selectors(FORMS),
        )


if __name__ == "__main__":
    unittest.main()
