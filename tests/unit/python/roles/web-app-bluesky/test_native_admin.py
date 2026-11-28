from __future__ import annotations

import json
import unittest

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

from utils import PROJECT_ROOT
from utils.templating.ansible import _trust_as_template

TASKS = PROJECT_ROOT / "roles" / "web-app-bluesky" / "tasks" / "04_native_admin.yml"
HELPER = (
    PROJECT_ROOT / "roles" / "sys-svc-compose" / "tasks" / "utils" / "netns_request.yml"
)
HANDLE = "administrator.example.test"
RESERVED = "i8-administrator.example.test"
SKIPPED = {
    "skipped": True,
    "changed": False,
    "skip_reason": "Conditional result was False",
}


def _load(path) -> list:
    return DataLoader().load_from_file(str(path), trusted_as_template=True)


def _task(fragment: str) -> dict:
    return next(task for task in _load(TASKS) if fragment in task["name"])


def _render(expression, **variables):
    templar = Templar(loader=DataLoader(), variables=variables)
    return templar.template(_trust_as_template(expression))


def _kept(answer: dict) -> dict:
    keep = next(task for task in _load(HELPER) if "ansible.builtin.set_fact" in task)
    return _render(
        next(iter(keep["ansible.builtin.set_fact"].values())),
        netns_request_answer=answer,
    )


def _answered(status: int, content: dict) -> dict:
    stdout = json.dumps(
        {
            "status": status,
            "content_type": "application/json",
            "content": json.dumps(content),
        }
    )
    return _kept({"rc": 0, "stdout": stdout, "changed": status == 200})


CREATED = _answered(200, {"did": "did:plc:probe", "handle": HANDLE})
TAKEN = _answered(400, {"error": "InvalidRequest", "message": "Handle already taken"})
RESERVED_NAME = _answered(400, {"error": "InvalidHandle", "message": "Reserved handle"})


def _facts(first: dict, second: dict) -> dict:
    variables = {
        "bluesky_admin_create": first,
        "bluesky_admin_create_reserved": second,
        "BLUESKY_ADMIN_HANDLE": HANDLE,
        "BLUESKY_ADMIN_HANDLE_RESERVED": RESERVED,
    }
    facts = _task("Record the PDS admin handle")["ansible.builtin.set_fact"]
    return {name: _render(value, **variables) for name, value in facts.items()}


class TestTheAdministratorHandle(unittest.TestCase):
    def test_the_reserved_request_is_sent_only_for_a_reserved_handle(self) -> None:
        skip = _task("with the i8- prefix (idempotent)")["vars"]["netns_request_skip"]
        for first, expected in ((CREATED, True), (TAKEN, True), (RESERVED_NAME, False)):
            with self.subTest(first=first["content"]):
                self.assertEqual(
                    str(expected), str(_render(skip, bluesky_admin_create=first))
                )

    def test_the_active_handle_and_creation_follow_the_request_that_ran(self) -> None:
        cases = (
            (CREATED, _kept(dict(SKIPPED)), HANDLE, True),
            (TAKEN, _kept(dict(SKIPPED)), HANDLE, False),
            (RESERVED_NAME, CREATED, RESERVED, True),
            (RESERVED_NAME, TAKEN, RESERVED, False),
        )
        for first, second, handle, created in cases:
            with self.subTest(first=first["content"], second=second.get("content")):
                facts = _facts(first, second)
                self.assertEqual(handle, facts["bluesky_admin_handle_active"])
                self.assertIs(created, facts["bluesky_admin_created"])

    def test_the_password_converges_on_the_active_handle_unless_just_created(
        self,
    ) -> None:
        did = _task("Resolve the DID")["vars"]
        password = _task("Set the native administrator password")["vars"]
        for created in (True, False):
            with self.subTest(created=created):
                for variables in (did, password):
                    self.assertEqual(
                        str(created),
                        str(
                            _render(
                                variables["netns_request_skip"],
                                bluesky_admin_created=created,
                            )
                        ),
                    )
        url = _render(
            did["netns_request_url"],
            BLUESKY_PDS_INTERNAL_URL="http://127.0.0.1:3000",
            bluesky_admin_handle_active=RESERVED,
        )
        self.assertTrue(url.endswith("handle=" + RESERVED))


if __name__ == "__main__":
    unittest.main()
