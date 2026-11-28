from __future__ import annotations

import unittest

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

from utils.cache.yaml import load_yaml_any
from utils.templating.ansible import _trust_as_template

from . import PROJECT_ROOT

ROLE = PROJECT_ROOT / "roles" / "web-app-stalwart"
TASKS = load_yaml_any(str(ROLE / "tasks" / "submission.yml"), default_if_missing=[])
RESTART = "submission_restart.yml"
PENDING = "stalwart_oidc_restart_pending"


def _conditions(task: dict) -> list[str]:
    when = task.get("when", [])
    return [when] if isinstance(when, str) else list(when)


def _walk(tasks: list[dict], inherited: list[str]):
    for task in tasks:
        conditions = inherited + _conditions(task)
        yield task, conditions
        yield from _walk(task.get("block", []), conditions)


def _holds(conditions: list[str], **variables) -> bool:
    templar = Templar(loader=DataLoader(), variables=variables)
    return all(
        templar.template(_trust_as_template("{{ " + condition + " }}")) is True
        for condition in conditions
    )


def _restarts(**variables) -> bool:
    return any(
        _holds(conditions, **variables)
        for task, conditions in _walk(TASKS, [])
        if task.get("ansible.builtin.include_tasks") == RESTART
    )


class TestSubmissionListenerBindsInItsOwnLoad(unittest.TestCase):
    def test_a_new_listener_restarts_stalwart_with_sso_on_and_off(self):
        for sso in (True, False):
            with self.subTest(sso=sso):
                self.assertTrue(
                    _restarts(
                        stalwart_submission_listener_missing=True,
                        STALWART_SSO_ENABLED=sso,
                    )
                )

    def test_a_bound_listener_never_restarts_stalwart(self):
        for sso in (True, False):
            with self.subTest(sso=sso):
                self.assertFalse(
                    _restarts(
                        stalwart_submission_listener_missing=False,
                        STALWART_SSO_ENABLED=sso,
                    )
                )

    def test_the_bind_is_never_deferred_to_the_post_load_drain(self):
        deferring = [
            task.get("name")
            for task, _ in _walk(TASKS, [])
            if PENDING in (task.get("ansible.builtin.set_fact") or {})
        ]
        self.assertEqual(deferring, [])


if __name__ == "__main__":
    unittest.main()
