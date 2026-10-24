"""Sign a Home Assistant user in against the directory and name their group.

The command_line auth provider starts this script with an environment that
holds nothing but ``username`` and ``password``, so every setting arrives as
an argument and the interpreter must be called by its absolute path.

Args:
    --uri: ``ldap://`` or ``ldaps://`` URI of the directory.
    --users-dn: DN the login name is searched under, one level deep.
    --login-attribute: attribute that holds the login name.
    --display-attribute: attribute printed as the display name when present.
    --name-part-attribute: attributes joined into the display name otherwise, repeatable.
    --admin-group: DN of the role group whose members become ``system-admin``.
    --user-group: DN of the role group whose members become ``system-users``.

Output:
    ``name = ...`` and ``group = ...`` on standard output and exit code 0 for a
    member of either group; exit code 1 for anyone else and on every directory error.
"""

import argparse
import os
import socket
import ssl
import sys
from urllib.parse import urlsplit

TIMEOUT_SECONDS = 10
MEMBERSHIP_ATTRIBUTE = "memberOf"
PRESENCE_ATTRIBUTE = "objectClass"
ADMIN_GROUP_ID = "system-admin"
USER_GROUP_ID = "system-users"

BOOLEAN = 0x01
INTEGER = 0x02
OCTET_STRING = 0x04
ENUMERATED = 0x0A
SEQUENCE = 0x30
BIND_REQUEST = 0x60
BIND_RESPONSE = 0x61
SEARCH_REQUEST = 0x63
SEARCH_RESULT_ENTRY = 0x64
SEARCH_RESULT_DONE = 0x65
SIMPLE_AUTHENTICATION = 0x80
FILTER_EQUALITY = 0xA3
FILTER_PRESENT = 0x87

LDAP_VERSION = 3
SCOPE_BASE = 0
SCOPE_ONE_LEVEL = 1
DEREF_NEVER = 0
SIZE_UNLIMITED = 0
SUCCESS = 0
DISCONNECTION_NOTICE_ID = 0


class DirectoryError(Exception):
    """The directory refused an operation or answered something unexpected."""


def encode_length(length):
    """Return the BER length octets.

    Args:
        length: number of content octets.
    """
    if length < 0x80:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def tlv(tag, value):
    """Return one BER element.

    Args:
        tag: the identifier octet.
        value: the content octets.
    """
    return bytes([tag]) + encode_length(len(value)) + value


def number(tag, value):
    """Return a BER INTEGER or ENUMERATED element.

    Args:
        tag: ``INTEGER`` or ``ENUMERATED``.
        value: the non-negative number.
    """
    return tlv(tag, value.to_bytes((value.bit_length() + 8) // 8, "big", signed=True))


def text(value):
    """Return an OCTET STRING element holding UTF-8 text.

    Args:
        value: the string.
    """
    return tlv(OCTET_STRING, value.encode("utf-8"))


def decode(data, offset):
    """Return ``(tag, content, next offset)`` of the element at ``offset``.

    Args:
        data: the encoded octets.
        offset: where the element starts.
    """
    if offset + 2 > len(data):
        raise DirectoryError("truncated element")
    tag = data[offset]
    length = data[offset + 1]
    offset += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or offset + count > len(data):
            raise DirectoryError("malformed element length")
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
    end = offset + length
    if end > len(data):
        raise DirectoryError("truncated element")
    return tag, data[offset:end], end


def children(data):
    """Return the ``(tag, content)`` pairs a constructed element holds.

    Args:
        data: the content octets of the constructed element.
    """
    items = []
    offset = 0
    while offset < len(data):
        tag, value, offset = decode(data, offset)
        items.append((tag, value))
    return items


def result_code(content):
    """Return the resultCode of an LDAPResult.

    Args:
        content: the content octets of a response that carries an LDAPResult.
    """
    tag, value = children(content)[0]
    if tag != ENUMERATED:
        raise DirectoryError("response without a result code")
    return int.from_bytes(value, "big")


def parse_entry(content):
    """Return ``(dn, {lowercased attribute: [values]})`` of a SearchResultEntry.

    Args:
        content: the content octets of the SearchResultEntry.
    """
    (_, dn), (_, attributes) = children(content)[:2]
    values = {}
    for _, attribute in children(attributes):
        (_, name), (_, entries) = children(attribute)[:2]
        values[name.decode("utf-8").lower()] = [
            value.decode("utf-8") for _, value in children(entries)
        ]
    return dn.decode("utf-8"), values


def equality(attribute, value):
    """Return an equalityMatch filter; the value is sent as data, so it needs no escaping.

    Args:
        attribute: the attribute description.
        value: the asserted value.
    """
    return tlv(FILTER_EQUALITY, text(attribute) + text(value))


def present(attribute):
    """Return a present filter.

    Args:
        attribute: the attribute description.
    """
    return tlv(FILTER_PRESENT, attribute.encode("utf-8"))


class Connection:
    """One LDAPv3 session over a plain or TLS socket.

    Args:
        uri: ``ldap://`` or ``ldaps://`` URI of the directory.
    """

    def __init__(self, uri):
        parts = urlsplit(uri)
        if parts.scheme not in ("ldap", "ldaps") or not parts.hostname:
            raise DirectoryError(f"unsupported directory URI {uri!r}")
        port = parts.port or (636 if parts.scheme == "ldaps" else 389)
        raw = socket.create_connection((parts.hostname, port), timeout=TIMEOUT_SECONDS)
        if parts.scheme == "ldaps":
            raw = ssl.create_default_context().wrap_socket(
                raw, server_hostname=parts.hostname
            )
        self.socket = raw
        self.message_id = 0

    def close(self):
        self.socket.close()

    def read(self, count):
        """Return exactly ``count`` octets from the socket.

        Args:
            count: number of octets to read.
        """
        chunks = bytearray()
        while len(chunks) < count:
            chunk = self.socket.recv(count - len(chunks))
            if not chunk:
                raise DirectoryError("the directory closed the connection")
            chunks.extend(chunk)
        return bytes(chunks)

    def send(self, operation):
        """Send one request and return its message ID.

        Args:
            operation: the encoded protocolOp.
        """
        self.message_id += 1
        self.socket.sendall(tlv(SEQUENCE, number(INTEGER, self.message_id) + operation))
        return self.message_id

    def message(self):
        """Return ``(message ID, (tag, content))`` of the next LDAPMessage."""
        head = self.read(2)
        if head[0] != SEQUENCE:
            raise DirectoryError("answer is no LDAPMessage")
        length = head[1]
        if length & 0x80:
            length = int.from_bytes(self.read(length & 0x7F), "big")
        items = children(self.read(length))
        return int.from_bytes(items[0][1], "big"), items[1]

    def response(self, message_id):
        """Return ``(tag, content)`` of the next protocolOp answering ``message_id``.

        Args:
            message_id: the ID of the request the answer belongs to.
        """
        answered, operation = self.message()
        while answered != message_id:
            if answered == DISCONNECTION_NOTICE_ID:
                raise DirectoryError("the directory announced a disconnection")
            answered, operation = self.message()
        return operation

    def bind(self, dn, password):
        """Return the result code of a simple bind.

        Args:
            dn: the DN to bind as.
            password: its password.
        """
        credentials = tlv(SIMPLE_AUTHENTICATION, password.encode("utf-8"))
        message_id = self.send(
            tlv(BIND_REQUEST, number(INTEGER, LDAP_VERSION) + text(dn) + credentials)
        )
        tag, content = self.response(message_id)
        if tag != BIND_RESPONSE:
            raise DirectoryError("bind answered with another operation")
        return result_code(content)

    def search(self, base, scope, search_filter, attributes):
        """Return the ``(dn, values)`` entries a search finds.

        Args:
            base: the base DN.
            scope: ``SCOPE_BASE`` or ``SCOPE_ONE_LEVEL``.
            search_filter: the encoded filter.
            attributes: the attribute descriptions to return.
        """
        request = (
            text(base)
            + number(ENUMERATED, scope)
            + number(ENUMERATED, DEREF_NEVER)
            + number(INTEGER, SIZE_UNLIMITED)
            + number(INTEGER, TIMEOUT_SECONDS)
            + tlv(BOOLEAN, b"\x00")
            + search_filter
            + tlv(SEQUENCE, b"".join(text(attribute) for attribute in attributes))
        )
        message_id = self.send(tlv(SEARCH_REQUEST, request))
        entries = []
        tag, content = self.response(message_id)
        while tag != SEARCH_RESULT_DONE:
            if tag == SEARCH_RESULT_ENTRY:
                entries.append(parse_entry(content))
            tag, content = self.response(message_id)
        code = result_code(content)
        if code != SUCCESS:
            raise DirectoryError(f"search answered result code {code}")
        return entries


def normalize_dn(dn):
    """Return a DN comparable regardless of case and spacing after commas.

    Args:
        dn: the DN.
    """
    return ",".join(part.strip() for part in dn.split(",")).lower()


def group_for(member_of, admin_group, user_group):
    """Return the Home Assistant group a directory account belongs in, or None.

    Args:
        member_of: the DNs of the groups the account is a member of.
        admin_group: DN of the administrator role group.
        user_group: DN of the user role group.
    """
    groups = {normalize_dn(dn) for dn in member_of}
    if normalize_dn(admin_group) in groups:
        return ADMIN_GROUP_ID
    if normalize_dn(user_group) in groups:
        return USER_GROUP_ID
    return None


def display_name(values, options, username):
    """Return the single-line display name of an account.

    Args:
        values: the attributes of the account, keyed by lowercased name.
        options: the parsed arguments.
        username: the login name, shown when the directory holds no name.
    """
    shown = values.get(options.display_attribute.lower())
    if not shown:
        parts = [
            values[attribute.lower()][0]
            for attribute in options.name_part_attribute
            if values.get(attribute.lower())
        ]
        shown = [" ".join(parts)] if parts else [username]
    return " ".join(shown[0].split())


def authenticate(connection, options, username, password):
    """Return ``(display name, group)`` for a valid member, or None.

    The typed login name must equal a stored value exactly, so differently
    cased spellings of one account cannot open separate Home Assistant users.

    Args:
        connection: an open ``Connection``.
        options: the parsed arguments.
        username: the login name Home Assistant received.
        password: the password Home Assistant received.
    """
    if not username or not password:
        return None
    login_key = options.login_attribute.lower()
    found = connection.search(
        options.users_dn,
        SCOPE_ONE_LEVEL,
        equality(options.login_attribute, username),
        [options.login_attribute],
    )
    if len(found) != 1 or username not in found[0][1].get(login_key, []):
        return None
    dn = found[0][0]
    if connection.bind(dn, password) != SUCCESS:
        return None
    attributes = [
        MEMBERSHIP_ATTRIBUTE,
        options.display_attribute,
        *options.name_part_attribute,
    ]
    entries = connection.search(dn, SCOPE_BASE, present(PRESENCE_ATTRIBUTE), attributes)
    if len(entries) != 1:
        return None
    values = entries[0][1]
    group = group_for(
        values.get(MEMBERSHIP_ATTRIBUTE.lower(), []),
        options.admin_group,
        options.user_group,
    )
    if group is None:
        return None
    return display_name(values, options, username), group


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--uri", required=True)
    parser.add_argument("--users-dn", required=True)
    parser.add_argument("--login-attribute", required=True)
    parser.add_argument("--display-attribute", required=True)
    parser.add_argument("--name-part-attribute", action="append", required=True)
    parser.add_argument("--admin-group", required=True)
    parser.add_argument("--user-group", required=True)
    return parser.parse_args(argv)


def main(argv, environ):
    """Run one sign-in and return the exit code.

    Args:
        argv: the command line arguments.
        environ: the environment Home Assistant passes.
    """
    options = parse_arguments(argv)
    try:
        username = environ["username"]
        connection = Connection(options.uri)
        try:
            result = authenticate(connection, options, username, environ["password"])
        finally:
            connection.close()
    except (DirectoryError, OSError, KeyError, IndexError, ValueError) as error:
        print(
            f"directory sign-in failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    if result is None:
        print(
            f"directory sign-in refused {username!r}: wrong credentials or no Home Assistant role",
            file=sys.stderr,
        )
        return 1
    name, group = result
    print(f"name = {name}")
    print(f"group = {group}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], os.environ))
