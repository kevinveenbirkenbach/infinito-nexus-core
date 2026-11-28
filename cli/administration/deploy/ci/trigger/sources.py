from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING, TypeVar

from cli.administration.deploy.ci import gh, runs, selections
from utils.github import run_name

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable

T = TypeVar("T")

ALL = "__ALL__"
_OVERRIDES = ("chunk_gate", "workspace", "mode", "tor", "distros", "filesystem")


@dataclasses.dataclass(frozen=True)
class Source:
    """Args:
    ref: the run as named on the command line, or how it was found.
    repo: ``owner/repo`` the run lives in, which its job logs are read from.
    run: jobs plus display title, as ``gh.fetch_run`` returns them.
    """

    ref: str
    repo: str
    run: dict


@dataclasses.dataclass
class Selection:
    """Args:
    whitelist: the whitelist input, ``__ALL__`` for every role.
    entries: the priority entries, unsorted.
    untriggered: priority entries a source run never deployed.
    per_run: ``(ref, failed, untriggered)`` counts per source run.
    """

    whitelist: str
    entries: set[str]
    untriggered: list[str] = dataclasses.field(default_factory=list)
    per_run: list[tuple[str, int, int]] = dataclasses.field(default_factory=list)


class SourceError(Exception):
    """Args:
    ref: the run that could not be read.
    cause: the ``SystemExit`` of a failing ``gh`` call, or the ``ValueError``
        of a malformed run URL.
    """

    def __init__(self, ref: str, cause: BaseException) -> None:
        super().__init__(f"{ref}: {cause}")
        self.ref = ref
        self.cause = cause


def _reading(ref: str, read: Callable[[], T]) -> T:
    """Args:
    ref: the run being read, named in the error.
    read: the read itself.

    Returns:
        what *read* returns.

    Raises:
        SourceError: the read exited or the URL did not parse.
    """
    try:
        return read()
    except (SystemExit, ValueError) as exc:
        raise SourceError(ref, exc) from exc


def load(args: argparse.Namespace, branch: str, repo: str) -> list[Source] | None:
    """Args:
    args: the parsed arguments.
    branch: the current branch.
    repo: ``owner/repo`` of the current branch, which a bare id resolves
        against.

    Returns:
        every source run in command-line order, empty when none is read,
        ``None`` when ``--failed`` found no deploy run on the branch.
    """
    if args.runs:
        return [
            _reading(
                ref,
                lambda ref=ref: Source(
                    ref, gh.run_repo(ref, repo), gh.fetch_run_ref(ref, repo)
                ),
            )
            for ref in args.runs
        ]
    if args.failed is None:
        return []
    run = _reading(
        "latest deploy run", lambda: runs.find_last_deploy_run(branch, repo=repo)
    )
    if run is None:
        print(f"No CI run with deploy jobs found on {repo}@{branch}.", file=sys.stderr)
        return None
    return [
        Source(
            "latest deploy run",
            repo,
            {"jobs": run["_jobs"], "displayTitle": run.get("displayTitle", "")},
        )
    ]


def _failed_union(args: argparse.Namespace, sources: list[Source]) -> Selection:
    """Args:
    args: the parsed arguments, which pick the retrigger flavour.
    sources: the runs whose failed selections are united.

    Returns:
        the union of every run's failed selections and never-deployed
        priority entries, with the counts each run contributed.
    """
    picked = Selection("", set())
    untriggered: set[str] = set()
    for source in sources:
        failed, never = _reading(
            source.ref,
            lambda source=source: selections.retrigger_entries(
                source.run,
                source.repo,
                strict=args.strict,
                roles_only=args.roles_only,
                any_axes=args.any_axes,
            ),
        )
        picked.entries |= set(failed) | set(never)
        untriggered |= set(never)
        picked.per_run.append((source.ref, len(failed), len(never)))
    picked.untriggered = sorted(untriggered)
    return picked


def select(args: argparse.Namespace, sources: list[Source]) -> Selection:
    """Args:
    args: the parsed arguments.
    sources: the source runs, read by ``--failed``.

    Returns:
        what the dispatch selects; an empty ``entries`` under ``--failed``
        means nothing failed.
    """
    if args.failed is not None:
        return _failed_union(args, sources)
    picked = Selection(ALL, set(args.priority.split()) if args.priority else set())
    if args.apps is not None:
        picked.whitelist = " ".join(args.apps.split())
    return picked


def carried(
    args: argparse.Namespace, sources: list[Source]
) -> tuple[dict[str, str], str, str]:
    """Args:
    args: the parsed arguments, whose overrides win.
    sources: the source runs; only the first one is carried over.

    Returns:
        the dispatch configuration, the first run's own offset input and its
        whitelist input.
    """
    config: dict[str, str] = {}
    carried_offset = ""
    if sources:
        first = sources[0]
        logged = runs.inputs_from_jobs(first.run["jobs"], first.repo)
        config = runs.config_from_run(
            first.run["displayTitle"], logged, jobs=first.run["jobs"]
        )
        carried_offset = logged.get("offset") or run_name.value_from_title(
            first.run["displayTitle"], "offset"
        )
    carried_whitelist = config.pop("whitelist", "")
    for name in _OVERRIDES:
        value = getattr(args, name)
        if value is not None:
            config[name] = value
    return config, carried_offset, carried_whitelist


def proven(sources: list[Source]) -> tuple[set[str], set[str]]:
    """Args:
    sources: the source runs, the first one anchoring the offset.

    Returns:
        the rows the first run proved, which anchor its window, and those of
        them no other run broke, which the walk past the window may skip.
    """
    anchor = selections.proven_rows(sources[0].run["jobs"])
    every = [job for source in sources for job in source.run["jobs"]]
    return anchor, anchor & selections.proven_rows(every)
