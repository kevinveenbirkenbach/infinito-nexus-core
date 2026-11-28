from __future__ import annotations

import io
import subprocess
import unittest
import unittest.mock as mock
from contextlib import redirect_stderr, redirect_stdout
from typing import TYPE_CHECKING, ClassVar

from cli.administration.deploy.ci import gh
from cli.administration.deploy.ci.trigger import __main__ as trigger
from cli.meta.ci import matrix
from tests.utils.ci.job_names import deploy_job_name
from tests.utils.ci.run_name import render
from tests.utils.ci.trigger import run_trigger
from utils.github.variant.pools import ARCHITECTURES, DISTROS, FILESYSTEMS

if TYPE_CHECKING:
    from collections.abc import Callable


def _job(mode: str, app: str, conclusion: str, *, vpn: bool = False) -> dict:
    return {
        "name": deploy_job_name(mode, app, "0,1", vpn=vpn),
        "status": "completed",
        "conclusion": conclusion,
    }


def _green(app: str) -> dict:
    """The deploy job that proves the ranking row ``app#0``."""
    return {
        "name": deploy_job_name("docker", app, "0"),
        "status": "completed",
        "conclusion": "success",
    }


def _row(name: str, priority: str) -> dict:
    return {
        "apps": f"web-app-{name}",
        "variant": "0",
        "priority": priority,
        "clone": "false",
        "covered": "0",
    }


_JOBS = [
    _job("docker", "web-app-x", "success"),
    _job("swarm", "web-app-x", "failure"),
    _job("docker", "web-app-y", "failure"),
    _job("swarm", "web-app-y", "success"),
]

_AXES = f"%{DISTROS[0]}:{ARCHITECTURES[0]}"
"""The distro and architecture glyphs _JOBS carry, spelled back out as ASCII.
The filesystem is deliberately absent: a title states the assigned kind, not
the effective one, while the architecture is the machine the job really ran
on."""

_FAILED_TOKENS = (
    f"web-app-x#0,1@swarm+clearnet{_AXES}&direct web-app-y#0,1@compose+clearnet{_AXES}"
)
"""What _JOBS failed at, exactly: x in swarm, y in compose, both on variant
shard 0,1, both on the clearnet and both on the same distro. Only the swarm
row states its mesh state, because the mesh axis covers no other mode."""

_RUN_URL = "https://github.com/o/r/actions/runs/55"  # nocheck: url
_SOURCE_CONFIG = {
    "distros": "arch centos",
    "mode": "swarm",
    "lifecycles": "stable",
    "filesystem": "btrfs",
    "chunk_gate": "false",
    "workspace": "false",
}
_SOURCE_RUN = {"jobs": _JOBS, "displayTitle": render(_SOURCE_CONFIG)}
_NEVER = {"priority": "web-app-x web-app-never"}

_REAL_PROBLEMS = trigger.validate.problems


class _Stubbed(unittest.TestCase):
    def setUp(self) -> None:
        """Stub the validator: each real call runs a full role discovery.

        ``autospec`` keeps the call checked against the real signature, and
        ``test_priority_is_dispatched_with_the_axis_overrides`` runs the real
        one.
        """
        patcher = mock.patch.object(
            trigger.validate, "problems", autospec=True, return_value=([], [])
        )
        self.problems = patcher.start()
        self.addCleanup(patcher.stop)

    def assert_refused(self, argv: list[str], message: str) -> None:
        """Args:
        argv: the trigger's command line.
        message: what the argument error must say.
        """
        err = io.StringIO()
        with (
            mock.patch.object(gh, "current_branch") as branch,
            self.assertRaises(SystemExit) as ctx,
            redirect_stderr(err),
            redirect_stdout(io.StringIO()),
        ):
            trigger.main(argv)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn(message, err.getvalue())
        branch.assert_not_called()


class TestTriggerMain(_Stubbed):
    def test_default_triggers_all(self) -> None:
        trial = run_trigger([])
        self.assertEqual(trial.rc, 0)
        self.assertEqual(
            trial.dispatched,
            [
                {
                    "workflow": "entry-manual-steer.yml",
                    "ref": "feature/x",
                    "whitelist": "__ALL__",
                    "priority": "",
                    "config": {},
                    "repo": "o/r",
                }
            ],
        )

    def test_priority_is_dispatched_with_the_axis_overrides(self) -> None:
        self.problems.side_effect = _REAL_PROBLEMS
        trial = run_trigger(
            [
                "--priority",
                "web-app-b#1@compose  web-app-a#0@swarm",
                "--workspace",
                "false",
                "--chunk-gate",
                "false",
                "--filesystem",
                "btrfs",
            ]
        )
        self.assertEqual(trial.rc, 0)
        self.assertEqual(
            trial.dispatched[0]["priority"], "web-app-a#0@swarm web-app-b#1@compose"
        )
        self.assertEqual(
            trial.dispatched[0]["config"],
            {"workspace": "false", "chunk_gate": "false", "filesystem": "btrfs"},
        )

    def test_an_unusable_token_is_refused_before_anything_is_dispatched(self) -> None:
        self.problems.return_value = (["bad token"], [])
        trial = run_trigger(["--priority", "web-app-a#9"])
        self.assertEqual(trial.rc, 1)
        self.assertEqual(trial.dispatched, [], "a refused line must not reach CI")

    def test_priority_and_failed_cannot_both_build_the_line(self) -> None:
        self.assert_refused(
            ["--failed", "--priority", "web-app-a#0"],
            "--priority and --failed both build the priority line",
        )

    def test_apps_explicit_list(self) -> None:
        trial = run_trigger(["--apps", "web-app-a  web-app-b"])
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched[0]["whitelist"], "web-app-a web-app-b")
        self.assertEqual(trial.dispatched[0]["priority"], "")

    def test_failed_total_sends_priority_without_whitelist(self) -> None:
        trial = run_trigger(["--failed"], last={"_jobs": _JOBS})
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched[0]["whitelist"], "")
        self.assertEqual(trial.dispatched[0]["priority"], _FAILED_TOKENS)

    def test_a_leftover_scope_argument_no_longer_narrows_the_modes(self) -> None:
        for scope in ("swarm", "compose", "total"):
            with self.subTest(scope=scope):
                trial = run_trigger(["--failed", scope], last={"_jobs": _JOBS})
                self.assertEqual(trial.dispatched[0]["priority"], _FAILED_TOKENS)

    def test_every_failed_mode_of_one_role_comes_back_separately(self) -> None:
        both = [
            _job("docker", "web-app-x", "failure"),
            _job("swarm", "web-app-x", "failure"),
        ]
        trial = run_trigger(["--failed"], last={"_jobs": both})
        self.assertEqual(
            trial.dispatched[0]["priority"],
            f"web-app-x#0,1@compose+clearnet{_AXES}"
            f" web-app-x#0,1@swarm+clearnet{_AXES}&direct",
        )

    def test_a_meshed_swarm_row_comes_back_meshed(self) -> None:
        meshed = [_job("swarm", "web-app-x", "failure", vpn=True)]
        trial = run_trigger(["--failed"], last={"_jobs": meshed})
        self.assertEqual(
            trial.dispatched[0]["priority"], f"web-app-x#0,1@swarm+clearnet{_AXES}&vpn"
        )

    def test_never_deployed_priority_roles_join_the_retrigger(self) -> None:
        trial = run_trigger(
            ["--failed", "--run", _RUN_URL], fetched=_SOURCE_RUN, inputs=_NEVER
        )
        self.assertEqual(trial.rc, 0)
        self.assertEqual(
            trial.dispatched[0]["priority"], f"web-app-never {_FAILED_TOKENS}"
        )

    def test_an_unreadable_job_log_aborts_instead_of_dropping_the_priority(
        self,
    ) -> None:
        source = {
            "jobs": _JOBS,
            "displayTitle": render({**_SOURCE_CONFIG, "priority": "web-app-x"}),
        }
        with self.assertRaises(SystemExit):
            run_trigger(["--failed", "--run", _RUN_URL], fetched=source)

    def test_a_never_deployed_priority_role_alone_still_dispatches(self) -> None:
        green = [
            _job("docker", "web-app-x", "success"),
            _job("swarm", "web-app-x", "success"),
        ]
        trial = run_trigger(
            ["--failed", "--run", _RUN_URL],
            fetched={"jobs": green, "displayTitle": render({})},
            inputs=_NEVER,
        )
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched[0]["priority"], "web-app-never")

    _RANKING: ClassVar[list[dict]] = [
        {
            "apps": f"web-app-{name}",
            "variant": "0",
            "mode": "compose",
            "network": "clearnet",
            "distro": DISTROS[0],
            "filesystem": FILESYSTEMS[0],
            "priority": "false",
        }
        for name in ("a", "b", "c")
    ]

    def test_the_carried_offset_is_the_floor_for_the_new_one(self) -> None:
        """Without it the retrigger restarts at the head every time and
        redeploys the stretch its predecessors already proved."""
        trial = run_trigger(
            ["--failed"],
            last={"_jobs": _JOBS},
            inputs={"offset": "web-app-b#0"},
            entries=self._RANKING,
        )
        self.assertEqual(trial.dispatched[0]["config"]["offset"], "web-app-b#0")

    def test_the_green_stretch_behind_the_carried_offset_moves_it_on(self) -> None:
        trial = run_trigger(
            ["--failed"],
            last={"_jobs": [*_JOBS, _green("web-app-b"), _green("web-app-c")]},
            inputs={"offset": "web-app-b#0"},
            entries=self._RANKING,
        )
        self.assertEqual(trial.dispatched[0]["config"]["offset"], "web-app-c#0")

    def test_failed_nothing_does_not_dispatch(self) -> None:
        green = [
            _job("docker", "web-app-x", "success"),
            _job("swarm", "web-app-x", "success"),
        ]
        trial = run_trigger(["--failed"], last={"_jobs": green})
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched, [])

    def test_failed_with_run_url_uses_that_run(self) -> None:
        trial = run_trigger(["--failed", "--run", _RUN_URL], fetched=_SOURCE_RUN)
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched[0]["priority"], _FAILED_TOKENS)
        self.assertEqual(trial.dispatched[0]["config"], _SOURCE_CONFIG)
        trial.fetch.assert_called_once()
        trial.find_last.assert_not_called()

    def test_failed_with_bare_run_id_resolves_against_branch_repo(self) -> None:
        trial = run_trigger(["--failed", "--run", "55"], fetched=_SOURCE_RUN)
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched[0]["priority"], _FAILED_TOKENS)
        self.assertEqual(trial.dispatched[0]["config"], _SOURCE_CONFIG)
        trial.fetch.assert_called_once_with("55", repo="o/r")
        trial.find_last.assert_not_called()

    def test_print_writes_the_retrigger_line_and_dispatches_nothing(self) -> None:
        trial = run_trigger(
            ["--failed", "--run", _RUN_URL, "--print"],
            fetched=_SOURCE_RUN,
            inputs=_NEVER,
        )
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched, [])
        self.assertEqual(trial.out, f"web-app-never {_FAILED_TOKENS}\n")

    def test_print_without_failed_is_refused(self) -> None:
        self.assert_refused(["--print"], "--print only applies with --failed")

    def test_apps_with_a_run_reproduces_its_configuration(self) -> None:
        trial = run_trigger(
            ["--apps", "web-app-a", "--run", _RUN_URL], fetched=_SOURCE_RUN
        )
        self.assertEqual(trial.rc, 0)
        sent = trial.dispatched[0]
        self.assertEqual(
            (sent["whitelist"], sent["priority"], sent["config"]),
            ("web-app-a", "", _SOURCE_CONFIG),
        )

    def test_chunk_gate_override_replaces_the_carried_value(self) -> None:
        trial = run_trigger(
            ["--failed", "--run", _RUN_URL, "--chunk-gate", "true"],
            fetched=_SOURCE_RUN,
        )
        self.assertEqual(trial.rc, 0)
        self.assertEqual(
            trial.dispatched[0]["config"], {**_SOURCE_CONFIG, "chunk_gate": "true"}
        )

    def test_chunk_gate_override_without_a_source_run(self) -> None:
        trial = run_trigger(["--chunk-gate", "false"])
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched[0]["config"], {"chunk_gate": "false"})

    def test_chunk_gate_rejects_other_values(self) -> None:
        self.assert_refused(["--chunk-gate", "maybe"], "invalid choice: 'maybe'")

    def test_failed_no_run_found(self) -> None:
        trial = run_trigger(["--failed"])
        self.assertEqual(trial.rc, 1)
        self.assertEqual(trial.dispatched, [])

    def test_apps_and_failed_mutually_exclusive(self) -> None:
        self.assert_refused(["--failed", "--apps", "x"], "not allowed with argument")


_FORK_URL = "https://github.com/fork/r/actions/runs/1"  # nocheck: url
_UPSTREAM_URL = "https://github.com/up/r/actions/runs/2"  # nocheck: url
_FORK_CONFIG = {"distros": "arch", "mode": "swarm", "chunk_gate": "false"}
_UPSTREAM_CONFIG = {"distros": "centos", "mode": "compose", "chunk_gate": "true"}


class TestSeveralRuns(_Stubbed):
    _FORK_JOBS: ClassVar[list[dict]] = [
        _job("swarm", "web-app-x", "failure"),
        _job("docker", "web-app-y", "failure"),
    ]
    _UPSTREAM_JOBS: ClassVar[list[dict]] = [
        _job("swarm", "web-app-x", "failure"),
        _job("docker", "web-app-z", "failure"),
        _job("docker", "web-app-aborted", "cancelled"),
    ]

    def _fetched(
        self, jobs: dict[str, list[dict]] | None = None
    ) -> Callable[..., dict]:
        """Args:
        jobs: the jobs per run id that replace the class defaults.

        Returns:
            a ``gh.fetch_run`` stand-in answering both runs.
        """
        jobs = {"1": self._FORK_JOBS, "2": self._UPSTREAM_JOBS, **(jobs or {})}
        titles = {"1": render(_FORK_CONFIG), "2": render(_UPSTREAM_CONFIG)}
        return lambda run_id, **_kwargs: {
            "jobs": jobs[run_id],
            "displayTitle": titles[run_id],
        }

    def test_the_line_is_the_sorted_union_of_every_run(self) -> None:
        trial = run_trigger(
            ["--failed", "--strict", "--run", _FORK_URL, "--run", _UPSTREAM_URL],
            fetched=self._fetched(),
        )
        self.assertEqual(trial.rc, 0)
        self.assertEqual(
            trial.dispatched[0]["priority"],
            f"web-app-x#0,1@swarm+clearnet{_AXES}&direct"
            f" web-app-y#0,1@compose+clearnet{_AXES}"
            f" web-app-z#0,1@compose+clearnet{_AXES}",
        )

    def test_the_configuration_comes_from_the_first_run(self) -> None:
        for first, second, config in (
            (_FORK_URL, _UPSTREAM_URL, _FORK_CONFIG),
            (_UPSTREAM_URL, _FORK_URL, _UPSTREAM_CONFIG),
        ):
            with self.subTest(first=first):
                trial = run_trigger(
                    ["--failed", "--strict", "--run", first, "--run", second],
                    fetched=self._fetched(),
                )
                self.assertEqual(trial.dispatched[0]["config"], config)

    def test_the_dispatch_targets_the_branch_repo_and_logs_their_own(self) -> None:
        trial = run_trigger(
            ["--failed", "--run", _FORK_URL, "--run", _UPSTREAM_URL],
            fetched=self._fetched(),
        )
        self.assertEqual(trial.dispatched[0]["repo"], "o/r")
        self.assertEqual(
            {call.args[1] for call in trial.read_logs.call_args_list},
            {"fork/r", "up/r"},
        )

    def test_a_row_another_run_did_not_finish_stays_unproven(self) -> None:
        ranking = mock.Mock(return_value=[_row("b", "false"), _row("c", "false")])
        fork = [_green("web-app-b"), _green("web-app-c"), *self._FORK_JOBS]
        upstream = [_job("docker", "web-app-c", "cancelled")]
        upstream[0]["name"] = deploy_job_name("docker", "web-app-c", "0")
        alone = run_trigger(
            ["--failed", "--run", _FORK_URL],
            fetched=self._fetched({"1": fork}),
            inputs={"offset": "web-app-b#0"},
            entries=ranking,
        )
        both = run_trigger(
            ["--failed", "--strict", "--run", _FORK_URL, "--run", _UPSTREAM_URL],
            fetched=self._fetched({"1": fork, "2": upstream}),
            inputs={"offset": "web-app-b#0"},
            entries=ranking,
        )
        self.assertEqual(alone.dispatched[0]["config"]["offset"], "web-app-c#0")
        self.assertEqual(both.dispatched[0]["config"]["offset"], "web-app-b#0")

    def test_the_window_is_anchored_on_the_first_runs_own_proof(self) -> None:
        ranking = mock.Mock(
            return_value=[_row("a", "false"), _row("b", "false"), _row("c", "false")]
        )
        fork = [_green("web-app-b"), _green("web-app-c"), *self._FORK_JOBS]
        upstream = [_job("docker", "web-app-b", "cancelled")]
        upstream[0]["name"] = deploy_job_name("docker", "web-app-b", "0")
        trial = run_trigger(
            ["--failed", "--strict", "--run", _FORK_URL, "--run", _UPSTREAM_URL],
            fetched=self._fetched({"1": fork, "2": upstream}),
            inputs={"offset": "web-app-gone#0"},
            entries=ranking,
        )
        self.assertEqual(trial.dispatched[0]["config"]["offset"], "web-app-b#0")

    def test_print_with_nothing_failed_leaves_stdout_empty(self) -> None:
        green = [_green("web-app-b")]
        trial = run_trigger(
            ["--failed", "--strict", "--run", _FORK_URL, "--print"],
            fetched=self._fetched({"1": green}),
        )
        self.assertEqual(trial.rc, trigger.NOTHING_FAILED)
        self.assertEqual(trial.out, "")
        self.assertIn("Nothing failed in that run", trial.err)

    def test_print_reports_a_planner_abort_apart_from_a_refusal(self) -> None:
        with mock.patch.object(
            matrix, "chunks_of", side_effect=SystemExit("too many chunk blocks")
        ):
            trial = run_trigger(
                ["--failed", "--strict", "--run", _FORK_URL, "--print"],
                fetched=self._fetched(),
            )
        self.assertEqual(trial.rc, trigger.PLAN_ABORTED)
        self.assertNotEqual(trigger.PLAN_ABORTED, trigger.REFUSED)
        self.assertEqual(trial.out, "")
        self.assertIn("the planner aborted on this line: too many", trial.err)
        self.assertNotIn("Priority tokens", trial.err)

    def test_print_plans_against_the_carried_whitelist(self) -> None:
        entries = mock.Mock(return_value=[])
        run_trigger(
            ["--failed", "--strict", "--run", _FORK_URL, "--print"],
            fetched=self._fetched(),
            inputs={"whitelist": "web-app-q"},
            entries=entries,
        )
        planned = [
            call.kwargs for call in entries.call_args_list if call.kwargs["priority"]
        ]
        self.assertEqual([kwargs["whitelist"] for kwargs in planned], ["web-app-q"])

    def test_print_reports_an_unreadable_run_with_its_own_status(self) -> None:
        def unreachable(*_args: object, **_kwargs: object) -> dict:
            raise SystemExit(4)

        for argv, fetched in (
            (["--run", _FORK_URL], unreachable),
            (["--run", "https://example.invalid/nope"], self._fetched()),
        ):
            with self.subTest(argv=argv):
                trial = run_trigger(
                    ["--failed", "--strict", *argv, "--print"], fetched=fetched
                )
                self.assertEqual(trial.rc, trigger.SOURCE_FAILED)
                self.assertEqual(trial.out, "")
                self.assertIn(f"error: cannot read run {argv[1]}", trial.err)

    def test_an_unreadable_run_still_fails_as_gh_did_without_print(self) -> None:
        def unreachable(*_args: object, **_kwargs: object) -> dict:
            raise SystemExit(4)

        with self.assertRaises(SystemExit) as ctx:
            run_trigger(["--failed", "--run", _FORK_URL], fetched=unreachable)
        self.assertEqual(ctx.exception.code, 4)

    def test_nothing_failed_names_every_run_read(self) -> None:
        green = [_green("web-app-b")]
        trial = run_trigger(
            ["--failed", "--run", _FORK_URL, "--run", _UPSTREAM_URL, "--print"],
            fetched=self._fetched({"1": green, "2": green}),
        )
        self.assertIn("Nothing failed in those 2 runs", trial.err)

    def test_print_without_a_deploy_run_has_its_own_status(self) -> None:
        trial = run_trigger(["--failed", "--print"])
        self.assertEqual(trial.rc, trigger.NO_RUN)
        self.assertEqual(trial.out, "")

    def test_print_summarises_on_stderr_and_keeps_stdout_the_line(self) -> None:
        planned = [_row("x", "true"), _row("y", "true")]

        def entries(**kwargs: object) -> list[dict]:
            return planned if kwargs["priority"] else []

        argv = ["--failed", "--strict", "--run", _FORK_URL, "--run", _UPSTREAM_URL]
        with mock.patch.object(matrix, "chunks_of", return_value=[planned[:1]]):
            trial = run_trigger(
                [*argv, "--print"],
                fetched=self._fetched(),
                entries=mock.Mock(side_effect=entries),
            )
        self.assertEqual(trial.rc, 0)
        self.assertEqual(trial.dispatched, [])
        self.assertEqual(len(trial.out.splitlines()), 1)
        self.assertEqual(len(trial.out.split()), 3)
        for line in (
            f"Run {_FORK_URL}: 2 failed, 0 never deployed",
            f"Run {_UPSTREAM_URL}: 2 failed, 0 never deployed",
            "Priority tokens: 3 (union, deduplicated)",
            "Priority rows planned: 1 of 2 discovered",
            "Regular line starts at the head",
            "Carried configuration: distros=arch, mode=swarm, chunk_gate=false",
            "Dispatch target: o/r@feature/x",
        ):
            self.assertIn(line, trial.err)

    def test_print_refuses_an_unusable_line_with_an_empty_stdout(self) -> None:
        self.problems.return_value = (["bad token"], [])
        trial = run_trigger(
            ["--failed", "--run", _FORK_URL, "--print"], fetched=self._fetched()
        )
        self.assertEqual(trial.rc, 1)
        self.assertEqual(trial.dispatched, [])
        self.assertEqual(trial.out, "")
        self.assertIn("error: bad token", trial.err)

    def test_argument_errors(self) -> None:
        for argv, message in (
            (
                ["--apps", "web-app-a", "--run", _FORK_URL, "--run", _UPSTREAM_URL],
                "--run is repeatable only with --failed",
            ),
            (["--run", "1", "--run", "2"], "--run is repeatable only with --failed"),
            (["--failed", "--run", " "], "--run was empty"),
            (["--apps", "  "], "--apps was empty"),
            (["--priority", " "], "--priority was empty"),
        ):
            with self.subTest(argv=argv):
                self.assert_refused(argv, message)


class TestAnyAxes(_Stubbed):
    _JOBS: ClassVar[list[dict]] = [
        _job("docker", "web-app-green", "success"),
        _job("swarm", "web-app-red", "failure"),
        _job("docker", "web-app-aborted", "cancelled"),
        {
            "name": deploy_job_name("swarm", "web-app-pending", "0,1"),
            "status": "in_progress",
            "conclusion": None,
        },
    ]
    _SOURCE_PRIORITY = "web-app-green web-app-never#1@swarm+tor"
    _BARE = "web-app-aborted web-app-never web-app-pending web-app-red"

    def _priority(self, *flags: str) -> str:
        trial = run_trigger(
            ["--failed", *flags, "--run", _RUN_URL],
            fetched={"jobs": self._JOBS, "displayTitle": render({})},
            inputs={"priority": self._SOURCE_PRIORITY},
        )
        self.assertEqual(trial.rc, 0)
        return trial.dispatched[0]["priority"]

    def test_every_role_that_was_not_green_comes_back_by_bare_name(self) -> None:
        self.assertEqual(self._priority("--any-axes"), self._BARE)

    def test_without_it_some_entry_keeps_its_axes(self) -> None:
        for flags in ((), ("--roles-only",), ("--strict", "--roles-only")):
            with self.subTest(flags=flags):
                self.assertNotEqual(self._priority(*flags), self._BARE)

    def test_it_refuses_strict_and_roles_only(self) -> None:
        for flag in ("--strict", "--roles-only"):
            with self.subTest(flag=flag):
                self.assert_refused(
                    ["--failed", "--any-axes", flag],
                    "--any-axes cannot be combined with --strict or --roles-only",
                )

    def test_it_only_applies_with_failed(self) -> None:
        self.assert_refused(["--any-axes"], "--any-axes only applies with --failed")


class TestBranchRemote(unittest.TestCase):
    def _resolve(self, upstream: str | None, push_default: str | None) -> str:
        remotes = "fork\norigin"

        def fake_run(args: list[str]) -> str:
            if args[1] == "rev-parse":
                if upstream is None:
                    raise subprocess.CalledProcessError(128, args)
                return upstream
            if args[1] == "remote" and len(args) == 2:
                return remotes
            if args[1] == "config":
                if push_default is None:
                    raise subprocess.CalledProcessError(1, args)
                return push_default
            raise AssertionError(f"unexpected git call: {args}")

        with mock.patch.object(gh, "_run", side_effect=fake_run):
            return gh._branch_remote()

    def test_tracking_remote_wins(self) -> None:
        self.assertEqual(self._resolve("origin/main", "fork"), "origin")

    def test_push_default_beats_origin_without_upstream(self) -> None:
        self.assertEqual(self._resolve(None, "fork"), "fork")

    def test_origin_when_no_upstream_and_no_push_default(self) -> None:
        self.assertEqual(self._resolve(None, None), "origin")

    def test_unknown_push_default_is_ignored(self) -> None:
        self.assertEqual(self._resolve(None, "gone"), "origin")


if __name__ == "__main__":
    unittest.main()
