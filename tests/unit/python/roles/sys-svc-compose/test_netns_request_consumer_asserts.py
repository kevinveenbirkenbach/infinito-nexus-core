from __future__ import annotations

import json
import re
import unittest

from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

from utils import PROJECT_ROOT
from utils.templating.ansible import _trust_as_template

ROLES = PROJECT_ROOT / "roles"
HELPER = ROLES / "sys-svc-compose" / "tasks" / "utils" / "netns_request.yml"
NESTED = ("block", "rescue", "always")
ERROR_BODY = json.dumps({"error": "ProbeError", "message": "probe-message-7f3a"})
SKIPPED = {
    "skipped": True,
    "changed": False,
    "skip_reason": "Conditional result was False",
}


def _load(path) -> list:
    return DataLoader().load_from_file(str(path), trusted_as_template=True) or []


def _walk(tasks: list):
    for task in tasks:
        if not isinstance(task, dict):
            continue
        yield task
        for key in NESTED:
            yield from _walk(task.get(key) or [])


def _role_tasks():
    for path in sorted(ROLES.glob("*/tasks/**/*.yml")):
        for task in _walk(_load(path)):
            yield path, task


def _results() -> dict[str, bool]:
    results: dict[str, bool] = {}
    for _, task in _role_tasks():
        variables = task.get("vars") or {}
        name = variables.get("netns_request_result")
        if isinstance(name, str):
            results[name] = (
                results.get(name, False) or "netns_request_skip" in variables
            )
    return results


def _consumers() -> list[tuple[str, dict, list[str]]]:
    results = _results()
    found = []
    for path, task in _role_tasks():
        args = task.get("ansible.builtin.assert")
        if not isinstance(args, dict) or "fail_msg" not in args:
            continue
        names = [
            name
            for name in results
            if re.search(rf"\b{re.escape(name)}\b", str(args["fail_msg"]))
        ]
        if names:
            found.append((f"{path.relative_to(ROLES)}: {task['name']}", task, names))
    return found


def _render(expression, **variables):
    templar = Templar(loader=DataLoader(), variables=variables)
    return templar.template(_trust_as_template(expression))


def _kept(answer: dict) -> dict:
    keep = next(task for task in _load(HELPER) if "ansible.builtin.set_fact" in task)
    value = next(iter(keep["ansible.builtin.set_fact"].values()))
    return _render(value, netns_request_answer=answer)


def _answered(status: int, content: str) -> dict:
    stdout = json.dumps(
        {"status": status, "content_type": "application/json", "content": content}
    )
    return _kept({"rc": 0, "stdout": stdout, "changed": False})


def _conditions(value) -> list[str]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _holds(conditions: list[str], **variables) -> bool:
    return all(
        _render("{{ (" + str(condition) + ") | bool }}", **variables)
        for condition in conditions
    )


class TestNetnsRequestConsumerAsserts(unittest.TestCase):
    def test_the_scan_finds_the_known_consumers(self) -> None:
        labels = " ".join(label for label, _, _ in _consumers())
        for role in ("web-app-bluesky", "web-app-flowise", "web-app-n8n"):
            with self.subTest(role=role):
                self.assertIn(role, labels)

    def test_a_refused_answer_names_its_status_and_error_body(self) -> None:
        for label, task, names in _consumers():
            with self.subTest(task=label):
                shapes = {name: _answered(400, ERROR_BODY) for name in names}
                that = _conditions(task["ansible.builtin.assert"]["that"])
                self.assertTrue(_holds(_conditions(task.get("when")), **shapes))
                self.assertFalse(_holds(that, **shapes))
                message = _render(task["ansible.builtin.assert"]["fail_msg"], **shapes)
                self.assertIn("400", message)
                self.assertIn("ProbeError", message)
                self.assertIn("probe-message-7f3a", message)

    def test_a_skipped_result_never_reaches_the_message(self) -> None:
        skippable = {name for name, skip in _results().items() if skip}
        guarded = 0
        for label, task, names in _consumers():
            for name in set(names) & skippable:
                with self.subTest(task=label, result=name):
                    shapes = {other: _answered(200, "{}") for other in names}
                    shapes[name] = _kept(dict(SKIPPED))
                    self.assertFalse(_holds(_conditions(task.get("when")), **shapes))
                    with self.assertRaises(AnsibleError):
                        _render(task["ansible.builtin.assert"]["fail_msg"], **shapes)
                    guarded += 1
        self.assertGreaterEqual(guarded, 2)


if __name__ == "__main__":
    unittest.main()
