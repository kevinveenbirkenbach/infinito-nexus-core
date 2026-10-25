"""Refresh the LDAP attributes of every Nextcloud account the directory holds.

Environment:
    RBAC_SYNC_CONTAINER_BIN, RBAC_SYNC_CID: how to reach the Nextcloud container.
    NEXTCLOUD_USER: user ``occ`` runs as inside the container.
    NEXTCLOUD_OCC: path of ``occ`` inside the container.
    RBAC_USERS: JSON list of every directory account.

Output:
    ``REFRESHED <count>`` with the number of refreshed accounts.
"""

import json
import os
import subprocess


def occ(environ, run, *args):
    """Return the standard output of one ``occ`` call inside the container.

    Args:
        environ: the process environment.
        run: ``subprocess.run`` or a stand-in.
        args: the ``occ`` arguments.
    """
    argv = [
        environ["RBAC_SYNC_CONTAINER_BIN"],
        "exec",
        "-i",
        "--user",
        environ["NEXTCLOUD_USER"],
        environ["RBAC_SYNC_CID"],
        "php",
        environ["NEXTCLOUD_OCC"],
        *args,
    ]
    return run(argv, capture_output=True, text=True, check=True).stdout


def main(environ, run=subprocess.run):
    """Refresh the known directory accounts and print how many there were.

    Args:
        environ: the process environment.
        run: ``subprocess.run`` or a stand-in.
    """
    known = set(
        json.loads(occ(environ, run, "user:list", "--output=json", "--limit=0"))
    )
    usernames = sorted(
        {account["username"] for account in json.loads(environ["RBAC_USERS"])} & known
    )
    for username in usernames:
        occ(environ, run, "ldap:check-user", "--update", username)
    print(f"REFRESHED {len(usernames)}")


if __name__ == "__main__":
    main(os.environ)
