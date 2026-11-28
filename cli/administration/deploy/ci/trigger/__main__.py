"""Trigger the manual CI run (entry-manual-steer.yml) for the current branch.

entry-manual-steer.yml reads the "__ALL__" whitelist sentinel as "force a full
deploy across all roles".

A retrigger differs from its source run in the selection and in nothing else:
every other dispatch input is carried over (:func:`runs.carried_inputs`, read
off the workflow itself), and the priority line names the exact selections that
failed -- role, variant, deploy mode, network mode and distro -- rather than the
roles they belong to. The filesystem is left to the rotation
(:mod:`cli.administration.deploy.ci.selections` says why). ``--chunk-gate`` is
the one deliberate exception: it overrides the carried value so a retrigger can
keep deploying past a failed chunk.
"""

from __future__ import annotations

import contextlib
import sys
from typing import TYPE_CHECKING

from cli.administration.deploy.ci import gh, runs, selections
from cli.administration.deploy.ci.trigger import options as cli_args
from cli.administration.deploy.ci.trigger import sources as source_runs
from cli.meta.ci import matrix, query, validate
from utils.github.variant import axes, network, pools, selection, vpn

if TYPE_CHECKING:
    import argparse

    from cli.administration.deploy.ci.trigger.sources import Selection, Source

_WORKFLOW = "entry-manual-steer.yml"
_ALL = source_runs.ALL
REFUSED = 1
NOTHING_FAILED = 3
PLAN_ABORTED = 4
NO_RUN = 5
SOURCE_FAILED = 6


def _axes(config: dict[str, str]) -> dict:
    """Args:
    config: the dispatch inputs the axes are resolved from.

    Returns:
        the axis keywords :func:`matrix.entries_of` and
        :func:`validate.problems` share.
    """
    return {
        "modes": query.resolve_modes(config.get("mode") or query.ALL_MODES),
        "lifecycles": config.get("lifecycles", ""),
        "network_input": network.resolve_network_input(config.get("network")),
        "vpn_mode": vpn.resolve_vpn_mode(config.get("vpn")),
        "distros": pools.resolve_distros(config.get("distros")),
        "filesystems": pools.resolve_filesystems(config.get("filesystem")),
    }


def _ranking(whitelist: str, config: dict[str, str]) -> list[dict[str, str]]:
    """The regular line the retrigger's own discovery would walk.

    The priority line is deliberately left out of that computation: it only
    blacklists rows from the regular query, and a token in it that no longer
    resolves would abort here, in a helper whose job is to save runner time.
    """
    return matrix.entries_of(
        whitelist="" if whitelist == _ALL else whitelist,
        priority="",
        sweep=0,
        architectures=pools.resolve_architectures(config.get("architectures")),
        **_axes(config),
    )


def _planned_priority(
    whitelist: str, priority: str, config: dict[str, str]
) -> tuple[int, int]:
    """Args:
    whitelist: the whitelist input, ``__ALL__`` for every role.
    priority: the priority line as dispatched.
    config: the dispatch inputs, ``offset`` included.

    Returns:
        the priority rows the planner puts into a chunk, and the priority rows
        it discovers in total.
    """
    entries = matrix.entries_of(
        whitelist="" if whitelist == _ALL else whitelist,
        priority=priority,
        sweep=axes.resolve_sweep(),
        architectures=pools.resolve_architectures(config.get("architectures")),
        **_axes(config),
    )
    plan = matrix.chunks_of(entries, config.get("offset", ""))
    planned = sum(row["priority"] == "true" for chunk in plan for row in chunk)
    return planned, sum(row["priority"] == "true" for row in entries)


def _refused(whitelist: str, priority: str, config: dict[str, str]) -> bool:
    """Whether the selection cannot deploy on this branch, reported in full.

    ``call-orchestrator.yml`` already runs the same check as its first job and
    every other job needs it, so a bad token never reaches a chunk. What it
    does reach is the branch's concurrency group, which
    ``entry-manual-steer.yml`` declares with ``cancel-in-progress``: dispatching
    a run that cannot survive validation first **cancels the run currently in
    flight** on that branch. That is the cost this refusal exists to avoid, not
    the deploy minutes.

    Warnings are printed and do not refuse: a whitelist legitimately names
    roles the lifecycle envelope filters out.

    Args:
        whitelist: the whitelist input, empty for the diff or the all-sentinel.
        priority: the priority line as dispatched.
        config: the dispatch inputs the axes are resolved from.
    """
    resolved = _axes(config)
    errors: list[str] = []
    warnings: list[str] = []
    for label, tokens in (("whitelist", whitelist), ("priority", priority)):
        found, warned = validate.problems(
            tokens, **resolved, label=label, priority=label == "priority"
        )
        errors += found
        warnings += warned
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print(
            f"\n{len(errors)} unusable selection(s); not dispatching. The run "
            "would cancel the one currently in flight on this branch and then "
            "fail its own validation job.",
            file=sys.stderr,
        )
    return bool(errors)


def _resume(
    whitelist: str,
    priority: str,
    config: dict[str, str],
    sources: list[Source],
    carried_offset: str,
) -> None:
    """Args:
    whitelist: the whitelist input, ``__ALL__`` for every role.
    priority: the priority line as dispatched.
    config: the dispatch inputs; ``offset`` is set or dropped in place.
    sources: the source runs.
    carried_offset: the first run's own offset input.
    """
    anchor, proven = source_runs.proven(sources)
    config["offset"] = selections.resume_offset(
        _ranking(whitelist, config),
        proven,
        selection.parse_list(priority),
        carried=carried_offset,
        anchor=anchor,
    )
    if config["offset"]:
        print(f"Regular line resumes at: {config['offset']}")
    else:
        config.pop("offset")


class _PlanAbortedError(Exception):
    pass


def _summary(
    picked: Selection,
    whitelist: str,
    priority: str,
    config: dict[str, str],
    target: str,
) -> None:
    """Args:
    picked: the selection, with its per-run counts.
    whitelist: the whitelist input as dispatched, carried one included.
    priority: the priority line as dispatched.
    config: the dispatch inputs, ``offset`` included.
    target: ``owner/repo@branch`` the dispatch goes to.

    Raises:
        _PlanAbortedError: the planner refused the line before anything was
            printed.
    """
    try:
        planned, discovered = _planned_priority(whitelist, priority, config)
    except SystemExit as exc:
        raise _PlanAbortedError(str(exc)) from exc
    for ref, failed, never in picked.per_run:
        print(f"Run {ref}: {failed} failed, {never} never deployed")
    tokens = len(priority.split())
    print(f"Priority tokens: {tokens} (union, deduplicated)")
    print(f"Priority rows planned: {planned} of {discovered} discovered")
    if not config.get("offset"):
        print("Regular line starts at the head")
    carried = ", ".join(f"{name}={value}" for name, value in config.items())
    print(f"Carried configuration: {carried or '(workflow defaults)'}")
    print(f"Dispatch target: {target}")


def _dispatch(
    whitelist: str,
    priority: str,
    config: dict[str, str],
    repo: str,
    branch: str,
) -> None:
    """Args:
    whitelist: the whitelist input, ``__ALL__`` for every role.
    priority: the priority line as dispatched.
    config: the dispatch inputs.
    repo: ``owner/repo`` the dispatch goes to.
    branch: the branch the run deploys.
    """
    if priority:
        label = f"priority {priority}, then the remaining roles"
    elif whitelist == _ALL:
        label = "all roles"
    else:
        label = whitelist
    carried = ", ".join(f"{name}={value}" for name, value in config.items())
    print(f"Triggering {_WORKFLOW} on {repo}@{branch} for: {label}")
    if carried:
        print(f"Carrying over from the source run: {carried}")
    runs.dispatch_workflow(
        _WORKFLOW, branch, whitelist, priority=priority, config=config, repo=repo
    )
    print("Dispatched. Watch with: infinito administration deploy ci status")


def _prepare(
    args: argparse.Namespace,
    sources: list[Source],
    picked: Selection,
    target: str,
) -> tuple[str, str, dict[str, str]] | None:
    """Args:
    args: the parsed arguments.
    sources: the source runs.
    picked: the selection to dispatch.
    target: ``owner/repo@branch`` the dispatch goes to.

    Returns:
        whitelist, priority line and configuration, or ``None`` when the
        validation refuses the selection.
    """
    if picked.untriggered:
        print(f"Priority roles that never deployed: {' '.join(picked.untriggered)}")
    config, carried_offset, carried_whitelist = source_runs.carried(args, sources)
    whitelist = picked.whitelist or carried_whitelist
    priority = " ".join(sorted(picked.entries))
    if args.failed is not None:
        _resume(whitelist, priority, config, sources, carried_offset)
    if _refused(whitelist if whitelist != _ALL else "", priority, config):
        return None
    if args.print_only:
        _summary(picked, whitelist, priority, config, target)
    return whitelist, priority, config


def _nothing_failed(sources: list[Source]) -> str:
    """Args:
    sources: the source runs that were read.

    Returns:
        the report that nothing is left to retrigger.
    """
    runs_read = "that run" if len(sources) == 1 else f"those {len(sources)} runs"
    return f"Nothing failed in {runs_read}; not triggering."


def _read(
    args: argparse.Namespace, branch: str, repo: str
) -> tuple[list[Source], Selection] | int:
    """Args:
    args: the parsed arguments.
    branch: the current branch.
    repo: ``owner/repo`` of the current branch.

    Returns:
        the source runs and the selection, or the exit status when no run
        could be read.

    Raises:
        SystemExit, ValueError: without ``--print``, a run that could not be
            read fails exactly as its ``gh`` call or URL did.
    """
    try:
        sources = source_runs.load(args, branch, repo)
        if sources is None:
            return NO_RUN if args.print_only else 1
        return sources, source_runs.select(args, sources)
    except source_runs.SourceError as exc:
        if not args.print_only:
            raise exc.cause from None
        print(f"error: cannot read run {exc}", file=sys.stderr)
        return SOURCE_FAILED


def _print_line(
    args: argparse.Namespace,
    sources: list[Source],
    picked: Selection,
    target: str,
) -> int:
    """Args:
    args: the parsed arguments.
    sources: the source runs.
    picked: the selection to print.
    target: ``owner/repo@branch`` the dispatch would go to.

    Returns:
        the exit status ``--print`` documents.
    """
    if not picked.entries:
        print(_nothing_failed(sources), file=sys.stderr)
        return NOTHING_FAILED
    try:
        with contextlib.redirect_stdout(sys.stderr):
            prepared = _prepare(args, sources, picked, target)
    except _PlanAbortedError as exc:
        print(f"error: the planner aborted on this line: {exc}", file=sys.stderr)
        return PLAN_ABORTED
    if prepared is None:
        return REFUSED
    print(prepared[1])
    return 0


def main(argv: list[str] | None = None) -> int:
    p = cli_args.parser()
    args = p.parse_args(argv)
    cli_args.check(p, args)

    branch = gh.current_branch()
    repo = gh.resolve_repo()
    read = _read(args, branch, repo)
    if isinstance(read, int):
        return read
    sources, picked = read
    target = f"{repo}@{branch}"
    if args.print_only:
        return _print_line(args, sources, picked, target)
    if args.failed is not None and not picked.entries:
        print(_nothing_failed(sources))
        return 0
    prepared = _prepare(args, sources, picked, target)
    if prepared is None:
        return REFUSED
    _dispatch(*prepared, repo, branch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
