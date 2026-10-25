"""In-memory stand-in for the slice of Frappe the ``infinito_rbac`` app calls."""

from __future__ import annotations

import copy
import json
from types import ModuleType, SimpleNamespace


class FrappeValidationError(Exception):
    pass


class FakeUser:
    def __init__(self, frappe, values):
        object.__setattr__(self, "_frappe", frappe)
        object.__setattr__(self, "flags", SimpleNamespace())
        object.__setattr__(self, "_values", {"roles": [], **values})

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self._values.get(name)

    def __setattr__(self, name, value):
        self._values[name] = value

    def get(self, name):
        return self._values.get(name)

    def add_roles(self, *roles):
        held = {row.role for row in self._values["roles"]}
        self._values["roles"].extend(
            SimpleNamespace(role=role) for role in roles if role not in held
        )
        self.save()

    def remove_roles(self, *roles):
        self._values["roles"] = [
            row for row in self._values["roles"] if row.role not in roles
        ]
        self.save()

    def insert(self):
        self._values["name"] = self._values["email"]
        return self.save()

    def save(self):
        self._frappe.saves.append(
            (self._values["name"], getattr(self.flags, "ignore_permissions", False))
        )
        self._frappe.records[self._values["name"]] = copy.deepcopy(self._values)
        return self


class FakeDb:
    def __init__(self, frappe):
        self._frappe = frappe
        self.committed = False

    def exists(self, doctype, name):
        return doctype == "User" and name in self._frappe.records

    def commit(self):
        self.committed = True


class FakeFrappe:
    def __init__(self):
        self.records = {}
        self.saves = []
        self.conf = {}
        self.userinfo = {}
        self.whitelisted = {}
        self.logged = []
        self.exchanges = []
        self.handovers = []
        self.db = FakeDb(self)

    def seed(self, name, **values):
        self.records[name] = {"roles": [], **values, "name": name}

    def get_doc(self, doctype, name):
        assert doctype == "User"
        return FakeUser(self, copy.deepcopy(self.records[name]))

    def new_doc(self, doctype):
        assert doctype == "User"
        return FakeUser(self, {})

    def generate_hash(self):
        return "generated-hash"

    def whitelist(self, allow_guest=False):
        def register(function):
            self.whitelisted[function.__name__] = allow_guest
            return function

        return register

    def logger(self, name):
        return SimpleNamespace(info=lambda line: self.logged.append((name, line)))

    def throw(self, message):
        raise FrappeValidationError(message)

    def _info_via_oauth(self, provider, code, decoder=None):
        self.exchanges.append((provider, code, decoder))
        return self.userinfo

    def _login_oauth_user(self, data, *, provider=None, state):
        user = self.records.get(data["email"].lower())
        self.handovers.append(
            {
                "provider": provider,
                "state": state,
                "committed": self.db.committed,
                "enabled": user["enabled"] if user else None,
            }
        )

    def modules(self):
        """Return the ``sys.modules`` entries that make this object ``frappe``.

        Returns:
            Module name to module, for ``patch.dict(sys.modules, ...)``.
        """
        oauth2_logins = ModuleType("frappe.integrations.oauth2_logins")
        oauth2_logins.decoder_compat = json.loads
        integrations = ModuleType("frappe.integrations")
        integrations.oauth2_logins = oauth2_logins
        oauth = ModuleType("frappe.utils.oauth")
        oauth.get_email = lambda data: (
            data.get("email") or data.get("upn") or data.get("unique_name")
        )
        oauth.get_info_via_oauth = self._info_via_oauth
        oauth.login_oauth_user = self._login_oauth_user
        utils = ModuleType("frappe.utils")
        utils.oauth = oauth
        return {
            "frappe": self,
            "frappe.integrations": integrations,
            "frappe.integrations.oauth2_logins": oauth2_logins,
            "frappe.utils": utils,
            "frappe.utils.oauth": oauth,
        }
