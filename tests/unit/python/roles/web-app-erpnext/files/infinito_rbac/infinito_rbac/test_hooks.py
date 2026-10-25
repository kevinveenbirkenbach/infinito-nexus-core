from __future__ import annotations

import runpy
import sys
import unittest
from unittest.mock import patch

from utils.cache.files import read_text

from . import APP_PACKAGE
from ._fake_frappe import FakeFrappe

HOOKS = runpy.run_path(str(APP_PACKAGE / "hooks.py"))
UPSTREAM_CALLBACK = "frappe.integrations.oauth2_logins.login_via_keycloak"


class TestHooks(unittest.TestCase):
    def test_the_app_is_named_after_its_package(self) -> None:
        self.assertEqual(HOOKS["app_name"], APP_PACKAGE.name)
        self.assertEqual(APP_PACKAGE.parent.name, APP_PACKAGE.name)

    def test_frappe_finds_the_title_and_description_it_lists_for_every_app(
        self,
    ) -> None:
        for hook in ("app_title", "app_description", "app_publisher", "app_license"):
            self.assertIsInstance(HOOKS[hook], str, hook)
            self.assertTrue(HOOKS[hook].strip(), hook)

    def test_the_keycloak_callback_resolves_to_a_guest_endpoint_of_the_app(
        self,
    ) -> None:
        target = HOOKS["override_whitelisted_methods"][UPSTREAM_CALLBACK]
        module, _, function = target.rpartition(".")
        package, _, name = module.partition(".")

        frappe = FakeFrappe()
        with patch.dict(sys.modules, frappe.modules()):
            loaded = runpy.run_path(str(APP_PACKAGE / f"{name}.py"), run_name=module)

        self.assertEqual(package, HOOKS["app_name"])
        self.assertTrue(callable(loaded[function]))
        self.assertEqual(frappe.whitelisted, {function: True})

    def test_only_the_keycloak_callback_is_replaced(self) -> None:
        self.assertEqual(
            list(HOOKS["override_whitelisted_methods"]), [UPSTREAM_CALLBACK]
        )

    def test_the_module_listed_in_modules_txt_exists_as_a_package(self) -> None:
        modules = read_text(str(APP_PACKAGE / "modules.txt")).split()
        module = "_".join(modules).lower()

        self.assertTrue((APP_PACKAGE / module / "__init__.py").is_file(), module)


if __name__ == "__main__":
    unittest.main()
