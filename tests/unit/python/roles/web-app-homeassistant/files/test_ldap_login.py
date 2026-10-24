import contextlib
import io
import types
import unittest

from utils.cache.files import read_text

from . import PROJECT_ROOT

SCRIPT = (
    PROJECT_ROOT
    / "roles"
    / "web-app-homeassistant"
    / "files"
    / "python"
    / "ldap_login.py"
)
USERS_DN = "ou=users,dc=example,dc=org"
ADMIN_GROUP = "cn=web-app-homeassistant-administrator,ou=roles,dc=example,dc=org"
USER_GROUP = "cn=web-app-homeassistant-user,ou=roles,dc=example,dc=org"
BIBER_DN = "uid=biber,ou=users,dc=example,dc=org"
ARGUMENTS = [
    "--uri",
    "ldap://openldap:389",
    "--users-dn",
    USERS_DN,
    "--login-attribute",
    "uid",
    "--display-attribute",
    "displayName",
    "--name-part-attribute",
    "givenName",
    "--name-part-attribute",
    "sn",
    "--admin-group",
    ADMIN_GROUP,
    "--user-group",
    USER_GROUP,
]


def load_module():
    module = types.ModuleType("homeassistant_ldap_login")
    exec(compile(read_text(str(SCRIPT)), str(SCRIPT), "exec"), module.__dict__)
    return module


class FakeSocket:
    def __init__(self, incoming):
        self.incoming = bytearray(incoming)
        self.sent = bytearray()
        self.closed = False

    def recv(self, count):
        chunk = bytes(self.incoming[: min(count, 3)])
        del self.incoming[: len(chunk)]
        return chunk

    def sendall(self, data):
        self.sent.extend(data)

    def close(self):
        self.closed = True


class StubDirectory:
    def __init__(self, mod, entries, password):
        self.mod = mod
        self.entries = entries
        self.password = password
        self.searches = []
        self.closed = False

    def search(self, base, scope, search_filter, attributes):
        self.searches.append((base, scope, search_filter, attributes))
        if scope == self.mod.SCOPE_ONE_LEVEL:
            return [(dn, {"uid": values["uid"]}) for dn, values in self.entries]
        return [(dn, values) for dn, values in self.entries if dn == base]

    def bind(self, dn, password):
        return self.mod.SUCCESS if password == self.password else 49

    def close(self):
        self.closed = True


def entry(member_of, **attributes):
    values = {"uid": ["biber"], "memberof": member_of}
    values.update({key.lower(): value for key, value in attributes.items()})
    return [(BIBER_DN, values)]


class LdapLoginEncodingTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def connection(self, incoming):
        connection = object.__new__(self.mod.Connection)
        connection.socket = FakeSocket(incoming)
        connection.message_id = 0
        return connection

    def response(self, message_id, operation):
        mod = self.mod
        return mod.tlv(mod.SEQUENCE, mod.number(mod.INTEGER, message_id) + operation)

    def test_bind_request_matches_the_ldapv3_encoding(self):
        mod = self.mod
        result = mod.number(mod.ENUMERATED, 0) + mod.text("") + mod.text("")
        connection = self.connection(
            self.response(1, mod.tlv(mod.BIND_RESPONSE, result))
        )

        self.assertEqual(connection.bind("cn=a", "p"), 0)
        self.assertEqual(
            bytes(connection.socket.sent),
            bytes.fromhex("30 11 02 01 01 60 0c 02 01 03 04 04 63 6e 3d 61 80 01 70"),
        )

    def test_bind_reports_invalid_credentials(self):
        mod = self.mod
        result = mod.number(mod.ENUMERATED, 49) + mod.text("") + mod.text("")
        connection = self.connection(
            self.response(1, mod.tlv(mod.BIND_RESPONSE, result))
        )

        self.assertEqual(connection.bind("cn=a", "wrong"), 49)

    def test_search_collects_entries_until_done(self):
        mod = self.mod
        attribute = mod.tlv(
            mod.SEQUENCE, mod.text("uid") + mod.tlv(0x31, mod.text("biber"))
        )
        found = mod.tlv(
            mod.SEARCH_RESULT_ENTRY,
            mod.text(BIBER_DN) + mod.tlv(mod.SEQUENCE, attribute),
        )
        done = mod.tlv(
            mod.SEARCH_RESULT_DONE,
            mod.number(mod.ENUMERATED, 0) + mod.text("") + mod.text(""),
        )
        connection = self.connection(self.response(1, found) + self.response(1, done))

        entries = connection.search(
            USERS_DN, mod.SCOPE_ONE_LEVEL, mod.equality("uid", "biber"), ["uid"]
        )

        self.assertEqual(entries, [(BIBER_DN, {"uid": ["biber"]})])
        tag, content, _ = mod.decode(bytes(connection.socket.sent), 0)
        self.assertEqual(tag, mod.SEQUENCE)
        self.assertEqual(mod.children(content)[1][0], mod.SEARCH_REQUEST)

    def test_search_raises_on_an_error_result(self):
        mod = self.mod
        done = mod.tlv(
            mod.SEARCH_RESULT_DONE,
            mod.number(mod.ENUMERATED, 32) + mod.text("") + mod.text(""),
        )
        connection = self.connection(self.response(1, done))

        with self.assertRaises(mod.DirectoryError):
            connection.search(
                USERS_DN, mod.SCOPE_ONE_LEVEL, mod.present("objectClass"), []
            )

    def test_long_lengths_round_trip(self):
        mod = self.mod
        value = b"x" * 300
        encoded = mod.tlv(mod.OCTET_STRING, value)

        self.assertEqual(encoded[:4], bytes([mod.OCTET_STRING, 0x82, 0x01, 0x2C]))
        self.assertEqual(
            mod.decode(encoded, 0), (mod.OCTET_STRING, value, len(encoded))
        )

    def test_truncated_element_is_a_directory_error(self):
        mod = self.mod
        with self.assertRaises(mod.DirectoryError):
            mod.decode(bytes([mod.OCTET_STRING, 0x05, 0x61]), 0)


class LdapLoginDecisionTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()
        self.options = self.mod.parse_arguments(ARGUMENTS)

    def test_administrator_group_wins_over_user_group(self):
        self.assertEqual(
            self.mod.group_for([USER_GROUP, ADMIN_GROUP], ADMIN_GROUP, USER_GROUP),
            "system-admin",
        )

    def test_user_group_maps_to_system_users(self):
        self.assertEqual(
            self.mod.group_for([USER_GROUP], ADMIN_GROUP, USER_GROUP), "system-users"
        )

    def test_group_match_ignores_case_and_spacing(self):
        spaced = USER_GROUP.upper().replace(",", ", ")
        self.assertEqual(
            self.mod.group_for([spaced], ADMIN_GROUP, USER_GROUP), "system-users"
        )

    def test_no_role_group_is_refused(self):
        other = "cn=web-app-nextcloud-administrator,ou=roles,dc=example,dc=org"
        self.assertIsNone(self.mod.group_for([other], ADMIN_GROUP, USER_GROUP))

    def test_member_signs_in_with_display_name(self):
        directory = StubDirectory(
            self.mod, entry([ADMIN_GROUP], displayName=["Biber  Beaver"]), "secret"
        )

        self.assertEqual(
            self.mod.authenticate(directory, self.options, "biber", "secret"),
            ("Biber Beaver", "system-admin"),
        )

    def test_name_falls_back_to_name_parts(self):
        directory = StubDirectory(
            self.mod, entry([USER_GROUP], givenName=["Biber"], sn=["Beaver"]), "secret"
        )

        self.assertEqual(
            self.mod.authenticate(directory, self.options, "biber", "secret"),
            ("Biber Beaver", "system-users"),
        )

    def test_wrong_password_is_refused(self):
        directory = StubDirectory(self.mod, entry([ADMIN_GROUP]), "secret")

        self.assertIsNone(
            self.mod.authenticate(directory, self.options, "biber", "wrong")
        )

    def test_member_of_no_role_group_is_refused(self):
        directory = StubDirectory(self.mod, entry([]), "secret")

        self.assertIsNone(
            self.mod.authenticate(directory, self.options, "biber", "secret")
        )

    def test_differently_cased_login_is_refused(self):
        directory = StubDirectory(self.mod, entry([ADMIN_GROUP]), "secret")

        self.assertIsNone(
            self.mod.authenticate(directory, self.options, "Biber", "secret")
        )

    def test_empty_password_never_reaches_the_directory(self):
        directory = StubDirectory(self.mod, entry([ADMIN_GROUP]), "")

        self.assertIsNone(self.mod.authenticate(directory, self.options, "biber", ""))
        self.assertEqual(directory.searches, [])

    def test_ambiguous_login_is_refused(self):
        twice = [
            *entry([ADMIN_GROUP]),
            ("uid=biber,ou=other,dc=example,dc=org", {"uid": ["biber"]}),
        ]
        directory = StubDirectory(self.mod, twice, "secret")

        self.assertIsNone(
            self.mod.authenticate(directory, self.options, "biber", "secret")
        )


class LdapLoginMainTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()

    def run_main(self, environ):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = self.mod.main(ARGUMENTS, environ)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_member_prints_name_and_group(self):
        directory = StubDirectory(
            self.mod, entry([USER_GROUP], displayName=["Biber"]), "secret"
        )
        self.mod.Connection = lambda uri: directory

        code, stdout, _ = self.run_main({"username": "biber", "password": "secret"})

        self.assertEqual(code, 0)
        self.assertEqual(stdout.splitlines(), ["name = Biber", "group = system-users"])
        self.assertTrue(directory.closed)

    def test_refusal_exits_one_without_output(self):
        directory = StubDirectory(self.mod, entry([]), "secret")
        self.mod.Connection = lambda uri: directory

        code, stdout, _ = self.run_main({"username": "biber", "password": "secret"})

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")

    def test_unreachable_directory_exits_one_without_the_password(self):
        def unreachable(uri):
            raise OSError("connection refused")

        self.mod.Connection = unreachable

        code, stdout, stderr = self.run_main(
            {"username": "biber", "password": "very-secret"}
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertNotIn("very-secret", stderr)


if __name__ == "__main__":
    unittest.main()
