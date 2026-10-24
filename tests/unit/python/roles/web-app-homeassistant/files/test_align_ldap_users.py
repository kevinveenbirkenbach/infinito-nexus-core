import contextlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path

from utils.cache.files import read_text

from . import PROJECT_ROOT

SCRIPT = (
    PROJECT_ROOT
    / "roles"
    / "web-app-homeassistant"
    / "files"
    / "python"
    / "align_ldap_users.py"
)


def load_module():
    module = types.ModuleType("homeassistant_align_ldap_users")
    exec(compile(read_text(str(SCRIPT)), str(SCRIPT), "exec"), module.__dict__)
    return module


def account(user_id, group, active=True, owner=False, system=False):
    return {
        "id": user_id,
        "group_ids": [group],
        "is_active": active,
        "is_owner": owner,
        "system_generated": system,
    }


def credential(user_id, provider, username):
    return {
        "id": f"cred-{user_id}-{provider}",
        "user_id": user_id,
        "auth_provider_type": provider,
        "auth_provider_id": None,
        "data": {"username": username},
    }


def store(users, credentials):
    return {
        "version": 1,
        "key": "auth",
        "data": {"users": users, "credentials": credentials},
    }


class AlignPlanTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_member_of_the_administrator_group_is_promoted(self):
        auth = store(
            [account("u1", "system-users")], [credential("u1", "command_line", "alice")]
        )

        self.assertEqual(
            self.mod.plan(auth, ["alice"], []),
            [{"user_id": "u1", "group_ids": ["system-admin"]}],
        )

    def test_member_of_the_user_group_is_demoted(self):
        auth = store(
            [account("u1", "system-admin")], [credential("u1", "command_line", "alice")]
        )

        self.assertEqual(
            self.mod.plan(auth, [], ["alice"]),
            [{"user_id": "u1", "group_ids": ["system-users"]}],
        )

    def test_administrator_membership_wins(self):
        auth = store(
            [account("u1", "system-users")], [credential("u1", "command_line", "alice")]
        )

        self.assertEqual(
            self.mod.plan(auth, ["alice"], ["alice"]),
            [{"user_id": "u1", "group_ids": ["system-admin"]}],
        )

    def test_account_outside_every_group_is_disabled(self):
        auth = store(
            [account("u1", "system-users")], [credential("u1", "command_line", "alice")]
        )

        self.assertEqual(
            self.mod.plan(auth, [], []), [{"user_id": "u1", "is_active": False}]
        )

    def test_disabled_member_is_enabled_again(self):
        auth = store(
            [account("u1", "system-users", active=False)],
            [credential("u1", "command_line", "alice")],
        )

        self.assertEqual(
            self.mod.plan(auth, [], ["alice"]), [{"user_id": "u1", "is_active": True}]
        )

    def test_aligned_accounts_produce_no_update(self):
        auth = store(
            [account("u1", "system-admin"), account("u2", "system-users")],
            [
                credential("u1", "command_line", "alice"),
                credential("u2", "command_line", "bob"),
            ],
        )

        self.assertEqual(self.mod.plan(auth, ["alice"], ["bob"]), [])

    def test_local_owner_mcp_and_system_accounts_are_never_touched(self):
        auth = store(
            [
                account("owner", "system-admin", owner=True),
                account("mcp", "system-read-only"),
                account("mixed", "system-admin"),
                account("supervisor", "system-admin", system=True),
            ],
            [
                credential("owner", "homeassistant", "platformadmin"),
                credential("owner", "command_line", "platformadmin"),
                credential("mcp", "homeassistant", "mcp-homeassistant"),
                credential("mixed", "homeassistant", "carol"),
                credential("mixed", "command_line", "carol"),
                credential("supervisor", "command_line", "supervisor"),
            ],
        )

        self.assertEqual(self.mod.plan(auth, [], []), [])


class AlignMainTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def test_missing_store_means_no_directory_account(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "auth")

            self.assertEqual(
                self.mod.read_store(missing), {"data": {"users": [], "credentials": []}}
            )

    def test_nothing_to_align_signs_in_nowhere(self):
        def refuse(*arguments):
            raise AssertionError("an aligned hub must not be signed in to")

        self.mod.owner_token = refuse
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth"
            path.write_text(json.dumps(store([], [])), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.mod.main(
                    {
                        "HA_AUTH_STORE": str(path),
                        "HA_ADMIN_MEMBERS": "[]",
                        "HA_USER_MEMBERS": "[]",
                    }
                )

        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
