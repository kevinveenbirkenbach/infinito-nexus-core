import contextlib
import io
import json
import subprocess
import types
import unittest

from utils.cache.files import read_text

from . import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "roles" / "web-app-nextcloud" / "files" / "python" / "ldap_refresh.py"
PREFIX = ["/usr/bin/container", "exec", "-i", "--user", "www-data", "c1", "php", "/var/www/html/occ"]


def load_module():
    module = types.ModuleType("nextcloud_ldap_refresh")
    exec(compile(read_text(str(SCRIPT)), str(SCRIPT), "exec"), module.__dict__)
    return module


class FakeOcc:
    def __init__(self, known):
        self.known = known
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        stdout = json.dumps(self.known) if "user:list" in argv else ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")


class NextcloudLdapRefreshTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def run_main(self, known, directory):
        environ = {
            "RBAC_SYNC_CONTAINER_BIN": "/usr/bin/container",
            "RBAC_SYNC_CID": "c1",
            "NEXTCLOUD_USER": "www-data",
            "NEXTCLOUD_OCC": "/var/www/html/occ",
            "RBAC_USERS": json.dumps([{"username": name, "email": "", "name": ""} for name in directory]),
        }
        fake = FakeOcc(known)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.mod.main(environ, run=fake)
        return fake.calls, stdout.getvalue().strip()

    def test_only_accounts_nextcloud_knows_are_refreshed(self):
        calls, output = self.run_main(
            {"alice": "Alice", "admin": "admin", "bob": "Bob"}, ["bob", "alice", "carol"]
        )

        self.assertEqual(
            calls,
            [
                [*PREFIX, "user:list", "--output=json", "--limit=0"],
                [*PREFIX, "ldap:check-user", "--update", "alice"],
                [*PREFIX, "ldap:check-user", "--update", "bob"],
            ],
        )
        self.assertEqual(output, "REFRESHED 2")

    def test_a_failing_refresh_stops_the_hook(self):
        def failing(argv, **kwargs):
            if "ldap:check-user" in argv:
                raise subprocess.CalledProcessError(1, argv)
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"alice": "A"}), stderr="")

        environ = {
            "RBAC_SYNC_CONTAINER_BIN": "/c",
            "RBAC_SYNC_CID": "c1",
            "NEXTCLOUD_USER": "www-data",
            "NEXTCLOUD_OCC": "occ",
            "RBAC_USERS": json.dumps([{"username": "alice", "email": "", "name": ""}]),
        }
        with self.assertRaises(subprocess.CalledProcessError):
            self.mod.main(environ, run=failing)


if __name__ == "__main__":
    unittest.main()
