from __future__ import annotations

import dataclasses
import io
import unittest.mock as mock
from contextlib import redirect_stderr, redirect_stdout
from typing import TYPE_CHECKING

from cli.administration.deploy.ci import gh, runs
from cli.administration.deploy.ci.trigger import __main__ as trigger
from cli.meta.ci import matrix

if TYPE_CHECKING:
    from collections.abc import Callable

REPO = "o/r"
BRANCH = "feature/x"


@dataclasses.dataclass
class Trial:
    """Args:
    rc: the trigger's exit status.
    dispatched: one ``dispatch_workflow`` call per entry, its inputs by name.
    out: what the trigger wrote to stdout.
    err: what the trigger wrote to stderr.
    fetch: the ``gh.fetch_run`` stub.
    find_last: the ``runs.find_last_deploy_run`` stub.
    read_logs: the ``runs.inputs_from_jobs`` stub.
    """

    rc: int
    dispatched: list[dict]
    out: str
    err: str
    fetch: mock.Mock
    find_last: mock.Mock
    read_logs: mock.Mock


def run_trigger(
    argv: list[str],
    *,
    last: dict | None = None,
    fetched: dict | Callable[..., dict] | None = None,
    inputs: dict[str, str] | None = None,
    entries: list[dict] | mock.Mock | None = None,
) -> Trial:
    """Args:
    argv: the trigger's command line.
    last: what ``runs.find_last_deploy_run`` answers.
    fetched: the run ``gh.fetch_run`` answers, or a function of its arguments.
    inputs: the inputs every job log records.
    entries: the rows ``matrix.entries_of`` answers, or a stub of it.

    Returns:
        the trial, with every stub the trigger reached the network through.
    """
    dispatched: list[dict] = []
    out, err = io.StringIO(), io.StringIO()
    answer = {"side_effect" if callable(fetched) else "return_value": fetched}
    if not isinstance(entries, mock.Mock):
        entries = mock.Mock(return_value=entries or [])
    with (
        mock.patch.object(gh, "current_branch", return_value=BRANCH),
        mock.patch.object(gh, "resolve_repo", return_value=REPO),
        mock.patch.object(gh, "fetch_run", **answer) as fetch,
        mock.patch.object(runs, "find_last_deploy_run", return_value=last) as find,
        mock.patch.object(
            runs, "inputs_from_jobs", return_value=inputs or {}
        ) as read_logs,
        mock.patch.object(matrix, "entries_of", entries),
        mock.patch.object(
            runs,
            "dispatch_workflow",
            side_effect=lambda *args, **kwargs: dispatched.append(
                {"workflow": args[0], "ref": args[1], "whitelist": args[2], **kwargs}
            ),
        ),
        redirect_stdout(out),
        redirect_stderr(err),
    ):
        rc = trigger.main(argv)
    return Trial(rc, dispatched, out.getvalue(), err.getvalue(), fetch, find, read_logs)
